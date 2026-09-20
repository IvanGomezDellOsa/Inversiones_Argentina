"""
Scraping de X (Twitter) vía la API REST de Apify.

Se usa la API REST y no el SDK `apify-client`: una versión menor del SDK renombró
un argumento de `call()` y dejó el scraper roto durante meses. La REST v2 es
estable y ya dependemos de `requests`.

Los actores desaparecen del store (ya pasó una vez), así que hay una cadena: si
el primero falla se prueba el siguiente. Nunca revienta la ingesta, pero deja
registro del estado de cada cuenta para poder avisar.
"""

import os
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import requests
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

APIFY_API_TOKEN = os.getenv("APIFY_API_TOKEN")
APIFY_BASE = "https://api.apify.com/v2"

# Ventana de recolección. Coincide con la del resto de las fuentes.
DIAS_VENTANA = 7
# Tope de posts por consulta. El plan FREE de Apify lo limita a 20 por corrida;
# pedir más no rompe, la plataforma recorta.
MAX_POSTS = int(os.getenv("APIFY_MAX_POSTS", "20"))
# Segundos que esperamos a que el actor termine (del lado del servidor y del cliente).
ESPERA_ACTOR = 180
TIMEOUT_HTTP = ESPERA_ACTOR + 60


# Cuentas de X que seguimos. `query` usa la sintaxis de búsqueda avanzada de X.
# `-filter:replies` saca las respuestas: son conversación suelta, y en el plan
# FREE cada uno de los 20 slots gastado ahí es un anuncio que no traemos.

@dataclass
class CuentaX:
    handle: str
    query: str
    max_posts: int = MAX_POSTS


# Términos que aparecen en un anuncio de inversión. Se usan para que una segunda
# consulta rescate anuncios que quedaron fuera de los últimos MAX_POSTS posts.
_TERMINOS_INVERSION = (
    "inversión OR inversion OR inversiones OR invertirá OR invertira OR millones "
    "OR u$s OR USD OR planta OR fábrica OR fabrica OR desembarca OR RIGI"
)

CUENTAS = [
    # @zubel_ok mezcla anuncios con política y posts personales: van dos consultas,
    # la cronológica cruda y una filtrada que rescata lo que quedó fuera de los 20.
    CuentaX(handle="zubel_ok", query="from:zubel_ok -filter:replies"),
    CuentaX(handle="zubel_ok", query=f"from:zubel_ok ({_TERMINOS_INVERSION}) -filter:replies"),
    # @LuisCaputoAR publica sobre todo macro, así que el filtro es la consulta
    # principal, no un rescate.
    CuentaX(handle="LuisCaputoAR", query=f"from:LuisCaputoAR ({_TERMINOS_INVERSION} OR anuncio) -filter:replies"),
]


# Cada actor del store tiene su propio esquema de entrada.

def _input_danek(cuenta: CuentaX) -> dict:
    return {"query": cuenta.query, "search_type": "Latest", "max_posts": cuenta.max_posts}


def _input_apidojo(cuenta: CuentaX) -> dict:
    return {"searchTerms": [cuenta.query], "sort": "Latest", "maxItems": cuenta.max_posts}


@dataclass
class Actor:
    id: str                       # formato usuario~nombre, como lo espera la URL
    construir_input: object
    nombre: str = ""


ACTORES = [
    Actor(id="danek~twitter-scraper", construir_input=_input_danek, nombre="danek/twitter-scraper"),
    Actor(id="apidojo~twitter-scraper-lite", construir_input=_input_apidojo, nombre="apidojo/twitter-scraper-lite"),
]

# Permite cambiar de actor por variable de entorno, sin deploy.
_ACTOR_OVERRIDE = os.getenv("APIFY_ACTOR_ID")
if _ACTOR_OVERRIDE:
    _override = _ACTOR_OVERRIDE.replace("/", "~")
    _conocido = next((a for a in ACTORES if a.id == _override), None)
    if _conocido:
        ACTORES.insert(0, ACTORES.pop(ACTORES.index(_conocido)))
    else:
        # Actor desconocido: asumimos el esquema de danek, que es el más común.
        ACTORES.insert(0, Actor(id=_override, construir_input=_input_danek, nombre=_ACTOR_OVERRIDE))


# --- Normalización de items ----------------------------------------------------

def _primer_valor(item: dict, *claves):
    """Primer valor no vacío entre varias claves posibles."""
    for c in claves:
        v = item.get(c)
        if v:
            return v
    return None


def _parsear_fecha_twitter(fecha_str):
    """X entrega 'Fri Apr 03 15:26:15 +0000 2026'. Devuelve datetime naive en UTC."""
    if not fecha_str:
        return None
    try:
        dt = datetime.strptime(str(fecha_str), "%a %b %d %H:%M:%S %z %Y")
        return dt.replace(tzinfo=None)
    except (ValueError, TypeError):
        pass
    # Algunos actores devuelven ISO 8601 en vez del formato de X.
    try:
        return datetime.fromisoformat(str(fecha_str).replace("Z", "+00:00")).replace(tzinfo=None)
    except (ValueError, TypeError):
        return None


def _es_respuesta(item: dict) -> bool:
    """True si el post es una respuesta a otro. Son ruido conversacional."""
    if item.get("in_reply_to_screen_name") or item.get("in_reply_to_status_id_str"):
        return True
    return bool(item.get("isReply"))


def _extraer_texto(item: dict) -> str:
    texto = _primer_valor(item, "text", "full_text", "content") or ""
    # Si el post cita a otro, el contenido citado suele traer el anuncio.
    citado = item.get("quoted")
    if isinstance(citado, dict):
        texto_citado = _primer_valor(citado, "text", "full_text") or ""
        if texto_citado:
            texto = f"{texto} | Cita: {texto_citado}"
    return str(texto).strip()


def _id_item(item: dict):
    return _primer_valor(item, "tweet_id", "id", "id_str", "rest_id")


# --- Llamada a Apify -----------------------------------------------------------

class ApifyActorAusente(Exception):
    """El actor no existe (fue eliminado o renombrado en el store)."""


def _correr_actor(actor: Actor, cuenta: CuentaX) -> list:
    """
    Corre un actor y devuelve los items del dataset.
    Lanza ApifyActorAusente si el actor no existe, para que se pruebe el siguiente.
    """
    url = f"{APIFY_BASE}/acts/{actor.id}/run-sync-get-dataset-items"
    resp = requests.post(
        url,
        params={"token": APIFY_API_TOKEN, "timeout": ESPERA_ACTOR},
        json=actor.construir_input(cuenta),
        timeout=TIMEOUT_HTTP,
    )
    if resp.status_code == 404:
        raise ApifyActorAusente(f"Apify no encuentra el actor '{actor.nombre}' (404).")
    resp.raise_for_status()
    datos = resp.json()
    return datos if isinstance(datos, list) else []


def _recolectar_cuenta(cuenta: CuentaX, limite_fecha: datetime, ids_vistos: set) -> tuple:
    """
    Devuelve (lineas, error). `error` es None si la cuenta se pudo leer,
    aunque haya devuelto cero posts dentro de la ventana.
    """
    ultimo_error = None

    for actor in ACTORES:
        try:
            items = _correr_actor(actor, cuenta)
        except ApifyActorAusente as e:
            logger.warning(f"X/@{cuenta.handle}: {e} Probando el siguiente actor.")
            ultimo_error = str(e)
            continue
        except Exception as e:
            logger.error(f"X/@{cuenta.handle}: fallo con '{actor.nombre}': {e}")
            ultimo_error = f"{actor.nombre}: {e}"
            continue

        logger.info(f"X/@{cuenta.handle}: '{actor.nombre}' devolvió {len(items)} posts.")

        lineas = []
        descartados_fecha = 0
        for item in items:
            item_id = _id_item(item)
            if item_id:
                if item_id in ids_vistos:
                    continue
                ids_vistos.add(item_id)

            if _es_respuesta(item):
                continue

            fecha = _parsear_fecha_twitter(_primer_valor(item, "created_at", "createdAt"))
            if not fecha:
                continue
            if fecha < limite_fecha:
                descartados_fecha += 1
                continue

            texto = _extraer_texto(item)
            if not texto:
                continue

            lineas.append(f"[{fecha.strftime('%Y-%m-%d')}] (@{cuenta.handle}) {texto}")

        logger.info(
            f"X/@{cuenta.handle}: {len(lineas)} posts útiles "
            f"({descartados_fecha} fuera de la ventana de {DIAS_VENTANA} días)."
        )
        return lineas, None

    return [], ultimo_error or "ningún actor disponible"


# --- API pública ---------------------------------------------------------------

@dataclass
class ResultadoX:
    """Lo recolectado más el estado de cada cuenta."""
    lineas: list = field(default_factory=list)
    errores: dict = field(default_factory=dict)   # handle -> mensaje de error
    cuentas_ok: list = field(default_factory=list)

    @property
    def todo_falló(self) -> bool:
        return bool(self.errores) and not self.cuentas_ok


def scrapear_twitter_detallado() -> ResultadoX:
    """Versión con diagnóstico. `scrapear_twitter()` envuelve a esta."""
    resultado = ResultadoX()

    if not APIFY_API_TOKEN:
        logger.error("Falta la variable de entorno APIFY_API_TOKEN. Se omite la fuente X.")
        resultado.errores["*"] = "falta APIFY_API_TOKEN"
        return resultado

    limite_fecha = datetime.utcnow() - timedelta(days=DIAS_VENTANA)
    ids_vistos = set()

    for cuenta in CUENTAS:
        logger.info(f"X: recolectando @{cuenta.handle} — query: {cuenta.query}")
        lineas, error = _recolectar_cuenta(cuenta, limite_fecha, ids_vistos)
        if error:
            resultado.errores.setdefault(cuenta.handle, error)
        elif cuenta.handle not in resultado.cuentas_ok:
            resultado.cuentas_ok.append(cuenta.handle)
        resultado.lineas.extend(lineas)

    # Una cuenta cuenta como sana si al menos una de sus consultas funcionó.
    for handle in resultado.cuentas_ok:
        resultado.errores.pop(handle, None)

    handles = {c.handle for c in CUENTAS}
    if resultado.errores:
        logger.error(f"X: cuentas con error: {resultado.errores}")
    logger.info(
        f"X: {len(resultado.lineas)} posts recolectados de "
        f"{len(resultado.cuentas_ok)}/{len(handles)} cuentas."
    )
    return resultado


def scrapear_twitter() -> list:
    """Lista de líneas '[YYYY-MM-DD] (@handle) texto', igual que el resto de fuentes."""
    return scrapear_twitter_detallado().lineas


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    r = scrapear_twitter_detallado()
    print(f"\n=== {len(r.lineas)} posts | cuentas OK: {r.cuentas_ok} | errores: {r.errores} ===\n")
    for linea in r.lineas:
        print(linea)
        print()
