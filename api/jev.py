"""
Cliente de Jev (TypeSafe AI) — capa opcional de juicio semántico.

Qué es Jev: un "System One model" presentado el 2026-09-15. No genera texto:
recibe un `state` y un mapa de preguntas tipadas, y devuelve decisiones con
probabilidades calibradas. Para este proyecto sirve en dos puntos donde hoy
fallamos, y en los dos la pregunta es un juicio binario, no una redacción:

1. FILTRO DE RUIDO. La auditoría encontró 16 registros publicados que no son
   inversiones privadas nuevas: constituciones de SRL con capital en pesos,
   emisiones de deuda, compras de acciones, lanzamientos de apps. El prompt de
   Gemini ya las excluye por texto y aun así se filtran. Un Noul por registro
   resuelve eso con una probabilidad calibrada.

2. DEDUPLICACIÓN. Los 12 duplicados reales tenían similitud coseno entre 0.758
   y 0.846, mezclados en la misma banda que proyectos legítimamente distintos.
   No hay umbral que los separe. Jev responde la pregunta correcta —"¿son el
   mismo proyecto?"— en vez de aproximarla con distancia vectorial.

Por qué HTTP directo y no el SDK `typesafe-sdk`: misma razón que con Apify. Un
SDK más es otra dependencia que puede renombrar argumentos entre versiones
menores y dejar la ingesta muda durante meses. La API REST es estable y ya
tenemos `requests`.

IMPORTANTE — es OPCIONAL. Jev está en acceso por waitlist. Si no hay
`TYPESAFE_API_KEY` en el entorno, `disponible()` devuelve False y todo el
pipeline sigue funcionando con las heurísticas deterministas. El día que llegue
el acceso, se agrega la variable y se activa sin tocar código.

Límites tenidos en cuenta (doc "Jev 1.13 jaggedness"):
- No sirve para números ni fechas: nada de "¿el monto es mayor a X?". Los montos
  y las fechas se siguen procesando en código.
- Lee de forma literal: las instrucciones dicen la condición exacta, y los casos
  borde van en `criteria`.
- El inglés es su idioma principal. Las instrucciones van en inglés; el `state`
  va en español, que es el contenido real.
"""

import logging
import os

import requests
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

TYPESAFE_API_KEY = os.getenv("TYPESAFE_API_KEY")
TYPESAFE_BASE_URL = os.getenv("TYPESAFE_BASE_URL", "https://api.typesafe.ai")
MODELO = os.getenv("TYPESAFE_MODEL", "jev-latest")
TIMEOUT = 30

# Umbrales de decisión sobre la probabilidad que devuelve un Noul.
# Se eligen conservadores a propósito: ante la duda, el registro se publica.
# Preferimos un registro de más que perder una inversión real.
UMBRAL_ES_INVERSION = 0.35     # por debajo de esto, se descarta como ruido
UMBRAL_ES_DUPLICADO = 0.70     # por encima de esto, se considera el mismo proyecto


def disponible() -> bool:
    """True si hay credencial configurada. Todo el módulo es opt-in."""
    return bool(TYPESAFE_API_KEY)


def _preguntar(state, questions: dict):
    """
    Una llamada a la API. Devuelve el mapa `answers` o None si algo falló.
    Jev evalúa todas las preguntas en paralelo contra el mismo state, así que
    conviene mandarlas juntas en vez de una por llamada.
    """
    if not disponible():
        return None
    try:
        resp = requests.post(
            f"{TYPESAFE_BASE_URL}/v1/systemone",
            headers={
                "Authorization": f"Bearer {TYPESAFE_API_KEY}",
                "Content-Type": "application/json",
            },
            json={"state": state, "model": MODELO, "questions": questions},
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        return resp.json().get("answers") or {}
    except Exception as e:
        # Nunca rompemos la ingesta por Jev: se degrada a las heurísticas.
        logger.warning(f"Jev: fallo en la consulta ({e}). Se sigue sin Jev.")
        return None


def _noul(answers: dict, clave: str):
    """Extrae la probabilidad de un Noul. None si no vino."""
    if not answers:
        return None
    a = answers.get(clave) or {}
    valor = a.get("noul")
    return float(valor) if isinstance(valor, (int, float)) else None


# --- 1) Filtro de ruido --------------------------------------------------------

_CRITERIOS_INVERSION = {
    "true": (
        "A specific, identifiable private company is committing capital to a productive "
        "asset or operation in Argentina: building or expanding a plant, factory, mine, "
        "pipeline, data center, power park, port or store network; drilling wells; "
        "buying productive equipment; or launching a named project with a stated "
        "investment plan."
    ),
    "false": (
        "Any of the following: the incorporation or registration of a new company and "
        "its share capital; issuing bonds, notes or debt; taking out a loan; buying or "
        "selling shares of an existing company on the market or in an M&A deal; winning "
        "a supply or construction contract awarded by someone else; launching an app, a "
        "product, a service or a commercial partnership; a government or state-owned "
        "entity investing its own money; an aggregate forecast of a company's whole "
        "portfolio or annual capital expenditure guidance rather than one concrete "
        "project; macroeconomic statistics."
    ),
}


def es_inversion_real(inversion: dict):
    """
    ¿El registro es una inversión privada concreta y nueva?
    Devuelve (veredicto, probabilidad). `veredicto` es None si Jev no está
    disponible o falló, para que el llamador decida con sus propias reglas.
    """
    if not disponible():
        return None, None

    state = {
        "empresa": inversion.get("empresa"),
        "descripcion": inversion.get("descripcion"),
        "estado": inversion.get("estado"),
        "ubicacion": inversion.get("ubicacion"),
    }
    answers = _preguntar(
        state,
        {
            "es_inversion": {
                "type": "noul",
                "instructions": (
                    "This record comes from an aggregator of private investments in "
                    "Argentina. Does it describe a concrete private investment in a "
                    "productive asset or operation located in Argentina?"
                ),
                "criteria": _CRITERIOS_INVERSION,
            }
        },
    )
    p = _noul(answers, "es_inversion")
    if p is None:
        return None, None
    return p >= UMBRAL_ES_INVERSION, p


# --- 2) Deduplicación ----------------------------------------------------------

def es_mismo_proyecto(candidato: dict, existente: dict):
    """
    ¿El candidato y el registro existente describen el MISMO proyecto de inversión?

    El caso difícil no es el texto parecido sino el mismo proyecto contado por
    fuentes distintas y con nombres de empresa distintos: "McEwen Cooper" y
    "Andes Corporación Minera" son ambos el proyecto Los Azules; "Pampa Energía"
    y "Fertil Pampa" son ambos la planta de urea de Bahía Blanca.

    Devuelve (veredicto, probabilidad); (None, None) si Jev no está disponible.
    """
    if not disponible():
        return None, None

    state = {
        "registro_a": {
            "empresa": candidato.get("empresa"),
            "descripcion": candidato.get("descripcion"),
            "ubicacion": candidato.get("ubicacion"),
        },
        "registro_b": {
            "empresa": existente.get("empresa"),
            "descripcion": existente.get("descripcion"),
            "ubicacion": existente.get("ubicacion"),
        },
    }
    answers = _preguntar(
        state,
        {
            "mismo_proyecto": {
                "type": "noul",
                "instructions": (
                    "Do `registro_a` and `registro_b` describe the same single "
                    "investment project?"
                ),
                "criteria": {
                    "true": (
                        "Both records refer to the same physical project or the same "
                        "corporate commitment: the same plant, mine, pipeline, field, "
                        "park or facility, at the same site. Treat them as the same "
                        "project even when the company name differs (a subsidiary, a "
                        "joint venture partner, a project vehicle or the parent "
                        "company), when the stated amount differs, or when one frames "
                        "it as an announcement and the other as a regulatory approval."
                    ),
                    "false": (
                        "They are different projects, even if they belong to the same "
                        "company, the same industry or the same city. Two separate "
                        "plants, two separate fields, or a plant and a pipeline are "
                        "different projects."
                    ),
                },
            }
        },
    )
    p = _noul(answers, "mismo_proyecto")
    if p is None:
        return None, None
    return p >= UMBRAL_ES_DUPLICADO, p


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    if not disponible():
        print("TYPESAFE_API_KEY no configurada: Jev está desactivado (el pipeline funciona igual).")
        raise SystemExit(0)

    print("=== Filtro de ruido ===")
    for caso in [
        {"empresa": "Sinteplast", "descripcion": "Construye una nueva planta en Ezeiza para duplicar su producción de productos cementicios.", "estado": "confirmada"},
        {"empresa": "YPF", "descripcion": "YPF colocó US$ 1.200 millones en el mercado internacional a través de un nuevo bono a nueve años.", "estado": "confirmada"},
        {"empresa": "Carnescatano", "descripcion": "Nueva SRL con un capital de $1.000.000, enfocada en el negocio de la carne.", "estado": "confirmada"},
        {"empresa": "Puma Energy", "descripcion": "Puma Energy lanzó Puma Flota, una nueva aplicación para empresas de transporte.", "estado": "anunciada"},
    ]:
        v, p = es_inversion_real(caso)
        print(f"  {str(v):<5} p={p}  {caso['empresa']}: {caso['descripcion'][:70]}")

    print("\n=== Deduplicación ===")
    pares = [
        ({"empresa": "McEwen Cooper", "descripcion": "Inversión para explotación de cobre en el proyecto Los Azules, aprobado en el RIGI.", "ubicacion": "San Juan"},
         {"empresa": "Andes Corporación Minera", "descripcion": "Proyecto Los Azules en San Juan para la exploración y explotación de cobre.", "ubicacion": "San Juan"}, True),
        ({"empresa": "Pampa Energía", "descripcion": "Busca ingresar al RIGI para construir una planta de urea en Bahía Blanca.", "ubicacion": "Buenos Aires"},
         {"empresa": "Profertil", "descripcion": "Presentará el proyecto de ampliación de su planta de fertilizantes en Bahía Blanca en el RIGI.", "ubicacion": "Buenos Aires"}, False),
    ]
    for a, b, esperado in pares:
        v, p = es_mismo_proyecto(a, b)
        print(f"  esperado={esperado!s:<5} obtuvo={v!s:<5} p={p}  {a['empresa']} vs {b['empresa']}")
