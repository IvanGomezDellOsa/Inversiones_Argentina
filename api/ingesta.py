"""
Flujo de ingesta. Corre por cron cada 3 días desde GitHub Actions.

Recolecta de todas las fuentes -> extrae con Gemini -> valida -> filtra ruido ->
deduplica -> inserta -> publica en Telegram.

Termina imprimiendo el estado de cada fuente y sale distinto de cero si alguna
que debería andar no trajo nada: el scraper de X estuvo roto meses con el
workflow en verde.
"""

import logging
import sys
import unicodedata
from datetime import datetime

import jev
from database import get_db_connection, init_db, insertar_inversion
from dedup import es_duplicado
from embeddings import generar_embedding
from fuentes_rigi import recopilar_rigi
from fuentes_web import recopilar_fuentes_web
from gemini import procesar_con_gemini
from scraper import scrapear_twitter_detallado
from telegram import enviar_inversion_a_telegram

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

ESTADOS_VALIDOS = {"confirmada", "anunciada", "en_evaluacion"}

# Nombres genéricos o no identificables que no deben publicarse en el campo "empresa".
# El sujeto de una inversión tiene que ser una empresa concreta, no un sector ni un placeholder.
_EMPRESAS_GENERICAS = {
    "empresa", "empresas", "empresa privada", "empresas privadas",
    "inversor privado", "inversores privados", "sector privado",
    "privado", "privados", "varios", "varias", "varias empresas",
    "no especificada", "no especificado", "sin especificar",
    "desconocida", "desconocido", "n/a", "na", "anonimo",
    "estado", "estado nacional", "gobierno", "gobierno nacional",
}

# Lo que NO es una inversión productiva nueva. Red determinista que complementa
# al prompt de Gemini y al filtro de Jev.
_PATRONES_NO_INVERSION = (
    # operaciones financieras
    "obligaciones negociables", "emision de deuda", "coloco us", "colocacion de deuda",
    "bono a ", "nuevo bono", "prestamo sindicado", "credito sindicado",
    "salida a bolsa", "oferta publica de acciones",
    # constitución de sociedades (Boletín Oficial)
    "nueva sociedad de responsabilidad limitada", "nueva srl", "nueva sa con un capital",
    "con un capital de $", "capital social de $",
    # compraventa de acciones
    "adquirio acciones", "compro acciones", "compro el 50%", "adquirio el 50%",
    "paquete accionario", "adquirio la participacion",
    # lanzamientos y alianzas
    "lanzo una nueva aplicacion", "nueva aplicacion para", "alianza estrategica donde",
    "marca recomendada",
)


def _normalizar(texto: str) -> str:
    """Minúsculas sin tildes ni espacios sobrantes, para comparar nombres."""
    sin_tildes = unicodedata.normalize("NFKD", str(texto)).encode("ascii", "ignore").decode("ascii")
    return sin_tildes.strip().lower()


def _empresa_invalida(empresa) -> bool:
    """Vacío, genérico, o tan largo que es una lista o descripción, no una marca."""
    if not empresa or not str(empresa).strip():
        return True
    texto = str(empresa)
    if _normalizar(texto) in _EMPRESAS_GENERICAS:
        return True
    if len(texto) > 90:   # un nombre tan largo es una lista o una descripción, no una marca
        return True
    return False


def _parece_operacion_financiera(registro) -> bool:
    """Red determinista contra lo que no es una inversión productiva."""
    texto = _normalizar(registro.get("descripcion", ""))
    return any(p in texto for p in _PATRONES_NO_INVERSION)


def validar_registro(registro):
    if not isinstance(registro, dict):
        return False

    if registro.get("estado") not in ESTADOS_VALIDOS:
        logger.warning(f"Registro descartado por estado inválido: {registro.get('estado')}")
        return False

    monto = registro.get("monto_usd")
    if isinstance(monto, bool):
        registro["monto_usd"] = None  # bool es subclase de int en Python
    elif monto is not None and not isinstance(monto, int):
        if isinstance(monto, float) and monto.is_integer():
            registro["monto_usd"] = int(monto)
        elif isinstance(monto, str) and monto.strip().isdigit():
            registro["monto_usd"] = int(monto.strip())
        else:
            logger.warning(f"monto_usd no normalizable, seteando None: {monto!r}")
            registro["monto_usd"] = None  # se conserva el registro, se anula solo el monto

    # Un monto muy bajo casi siempre es una cifra en pesos leída como dólares.
    # Se anula el monto, no el registro.
    monto = registro.get("monto_usd")
    if monto is not None and monto < 500_000:
        logger.warning(f"monto_usd sospechosamente bajo ({monto}), probablemente pesos. Se anula.")
        registro["monto_usd"] = None

    # Sin fecha válida usamos la de ejecución: solo dan un orden cronológico
    # aproximado, así que es preferible a un nulo.
    fecha_str = registro.get("fecha_anuncio")
    fecha_valida = False
    if fecha_str:
        try:
            datetime.strptime(str(fecha_str), "%Y-%m-%d")
            fecha_valida = True
        except (ValueError, TypeError):
            logger.warning(f"Fecha inválida: {fecha_str!r}. Se usará la fecha de ejecución.")
    if not fecha_valida:
        registro["fecha_anuncio"] = datetime.now().strftime("%Y-%m-%d")

    if not registro.get("descripcion"):
        logger.warning("Registro descartado por falta de descripción.")
        return False

    if _empresa_invalida(registro.get("empresa")):
        logger.warning(f"Registro descartado por empresa inválida o genérica: {registro.get('empresa')!r}")
        return False

    if _parece_operacion_financiera(registro):
        logger.warning(
            f"Registro descartado: no es una inversión productiva "
            f"({registro.get('empresa')}): {str(registro.get('descripcion'))[:90]}"
        )
        return False

    return True


def _filtrar_con_jev(inversiones):
    """Segunda pasada con Jev. Sin Jev devuelve la lista tal cual."""
    if not jev.disponible():
        logger.info("Jev no está configurado; se usa solo el filtrado determinista.")
        return inversiones

    logger.info(f"Filtrando {len(inversiones)} registros con Jev...")
    aprobadas = []
    for inv in inversiones:
        veredicto, p = jev.es_inversion_real(inv)
        if veredicto is False:
            detalle = " ".join(f"{k}={v:.2f}" for k, v in p.items()) if p else ""
            logger.info(f"    Jev descartó '{inv.get('empresa')}': {detalle}")
            continue
        if veredicto is None:
            logger.debug(f"    Jev no respondió por '{inv.get('empresa')}'; se conserva.")
        aprobadas.append(inv)

    logger.info(f"Jev: {len(aprobadas)}/{len(inversiones)} registros aprobados.")
    return aprobadas


def _recolectar(conn):
    """Junta el material de todas las fuentes y devuelve (publicaciones, estado)."""
    estado = {}

    logger.info("Recolectando de X (Apify)...")
    resultado_x = scrapear_twitter_detallado()
    estado["X"] = {
        "items": len(resultado_x.lineas),
        "ok": bool(resultado_x.cuentas_ok),
        "detalle": f"cuentas OK: {resultado_x.cuentas_ok or 'ninguna'}; errores: {resultado_x.errores or 'ninguno'}",
    }

    logger.info("Recolectando fuentes web (RSS)...")
    publicaciones_web = recopilar_fuentes_web()
    estado["Web"] = {
        "items": len(publicaciones_web),
        "ok": bool(publicaciones_web),
        "detalle": "notas relevantes tras el filtro",
    }

    logger.info("Recolectando fuente oficial RIGI...")
    publicaciones_rigi = recopilar_rigi(datetime.now().strftime("%Y-%m-%d"), conn=conn)
    # RIGI es incremental: cero novedades es lo NORMAL, no una falla.
    estado["RIGI"] = {
        "items": len(publicaciones_rigi),
        "ok": True,
        "detalle": "solo proyectos nuevos o modificados",
    }

    # Deduplicamos el batch: varias fuentes suelen traer la misma línea.
    publicaciones = list(dict.fromkeys(
        resultado_x.lineas + publicaciones_web + publicaciones_rigi
    ))
    return publicaciones, estado


def _imprimir_parte(estado, metricas):
    logger.info("=" * 58)
    logger.info("PARTE DE LA INGESTA")
    logger.info("=" * 58)
    for fuente, d in estado.items():
        marca = "OK  " if d["ok"] else "FALLA"
        logger.info(f"  [{marca}] {fuente:<5} {d['items']:>4} items — {d['detalle']}")
    logger.info("-" * 58)
    for k, v in metricas.items():
        logger.info(f"  {k:<28} {v}")
    logger.info("=" * 58)


def run_ingesta():
    logger.info("Iniciando flujo de ingesta...")

    logger.info("Conectando a la Base de Datos Neon...")
    conn = get_db_connection()
    if not conn:
        logger.error("No se pudo conectar a la base de datos. Abortando.")
        return 1

    metricas = {}
    try:
        # Una vez por corrida, fuera del camino de los lectores de la API.
        init_db(conn)

        publicaciones, estado = _recolectar(conn)
        logger.info(
            f"Publicaciones combinadas: {len(publicaciones)} "
            f"({estado['X']['items']} de X, {estado['Web']['items']} de web, "
            f"{estado['RIGI']['items']} de RIGI)."
        )

        if not publicaciones:
            logger.warning("No se obtuvo material de ninguna fuente. Gemini buscará solo en Google.")

        logger.info("Procesando contenido con Gemini (interpreta y busca en Google)...")
        inversiones_crudo = procesar_con_gemini(publicaciones)
        metricas["Extraídas por Gemini"] = len(inversiones_crudo or [])

        if not inversiones_crudo:
            logger.warning("Gemini no devolvió resultados o hubo un error al parsear.")
            _imprimir_parte(estado, metricas)
            return 0 if all(d["ok"] for d in estado.values()) else 1

        logger.info("Validando formato y consistencia de datos...")
        inversiones_validas = [r for r in inversiones_crudo if validar_registro(r)]
        metricas["Válidas tras validación"] = len(inversiones_validas)

        inversiones_validas = _filtrar_con_jev(inversiones_validas)
        metricas["Tras el filtro de Jev"] = len(inversiones_validas)

        nuevas_inserciones = 0
        duplicados = 0
        sin_embedding = 0

        logger.info("Generando embeddings, deduplicando e insertando...")
        for inversion in inversiones_validas:
            texto = f"{inversion['empresa']} {inversion['descripcion']}"
            logger.info(f" -> Procesando: {inversion['empresa']}")

            embedding = generar_embedding(texto)
            if not embedding:
                logger.error(f"    Fallo al generar embedding para {inversion['empresa']}. Saltando.")
                sin_embedding += 1
                continue

            duplicado, motivo = es_duplicado(inversion, embedding, conn)
            if duplicado:
                logger.info(f"    Duplicado, se omite — {motivo}")
                duplicados += 1
                continue

            logger.info(f"    Nuevo — {motivo}")
            if insertar_inversion(inversion, embedding, conn) is not None:
                enviar_inversion_a_telegram(inversion)
                nuevas_inserciones += 1

        metricas["Nuevas inserciones"] = nuevas_inserciones
        metricas["Duplicados omitidos"] = duplicados
        if sin_embedding:
            metricas["Sin embedding (saltadas)"] = sin_embedding

        _imprimir_parte(estado, metricas)

        # En rojo si una fuente cayó: es la única forma de enterarse sin leer logs.
        fuentes_caidas = [f for f, d in estado.items() if not d["ok"]]
        if fuentes_caidas:
            logger.error(f"FUENTES CAÍDAS: {', '.join(fuentes_caidas)}. Revisar antes del próximo ciclo.")
            return 1
        return 0

    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(run_ingesta())
