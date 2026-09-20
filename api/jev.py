"""
Capa de juicio semántico con Jev (TypeSafe AI).

Se usa en dos puntos: filtrar registros que no son inversiones productivas y
decidir si dos registros son el mismo proyecto. Es opcional: sin API key el
pipeline corre igual con las heurísticas deterministas.

Las preguntas y los umbrales viven todos acá arriba, juntos, para poder
revisarlos de un vistazo.
"""

import logging
import os

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# El SDK lee TYPESAFE_API_KEY del entorno; aceptamos JEV_API_KEY como alias.
API_KEY = os.getenv("TYPESAFE_API_KEY") or os.getenv("JEV_API_KEY")
MODELO = os.getenv("TYPESAFE_MODEL", "jev-latest")

try:
    from typesafe_sdk import Noul, NoulCriteria, TypeSafeClient
    _SDK_OK = True
except ImportError:  # el paquete es opcional
    _SDK_OK = False


# --- Umbrales -----------------------------------------------------------------
# Conservadores a propósito: publicar un registro de más es preferible a
# descartar una inversión real en silencio.

UMBRAL_INVERSION = 0.40      # por debajo, el registro se descarta como ruido
UMBRAL_DESCARTE_DURO = 0.75  # probabilidad de ser deuda/M&A/agregado que basta para descartar
UMBRAL_DUPLICADO = 0.75      # por encima, dos registros son el mismo proyecto.
                             # Medido: los duplicados reales dan >=0.80 y el par más
                             # confuso (una obra y la mina que la encarga) da 0.70.


# --- Preguntas ----------------------------------------------------------------
# En inglés porque es el idioma primario de Jev; el contenido evaluado va en
# español. Se piden varias preguntas atómicas por llamada y se combinan en
# código, que es más preciso que una sola pregunta amplia.

_PREGUNTAS_INVERSION = {
    "activo_productivo": Noul(
        instructions="A private company is committing capital to a productive asset or operation in Argentina.",
        criteria=NoulCriteria(
            true={
                "what": "Building or expanding a plant, factory, mine, pipeline, data center, "
                        "power park, port or store network; drilling wells; buying productive "
                        "equipment; or a named project with a stated investment plan.",
                "examples": ["Builds a new plant in Ezeiza", "Drills 259 wells in Vaca Muerta"],
            },
            false={
                "what": "No productive asset is created or expanded.",
                "examples": ["Launches a mobile app", "Signs a fuel supply partnership"],
            },
        ),
    ),
    "operacion_financiera": Noul(
        instructions="The record describes a financial operation rather than a productive investment.",
        criteria=NoulCriteria(
            true={
                "what": "Issuing bonds or notes, placing debt, taking a loan, a capital increase, "
                        "an IPO, or buying and selling shares of a company.",
                "examples": ["Placed US$1.2bn in a nine-year bond", "Acquired 50% of the shares"],
            },
            false={"what": "Money is committed to building or operating something."},
        ),
    ),
    "cifra_agregada": Noul(
        instructions="The figure is a company-wide aggregate rather than one identifiable project.",
        criteria=NoulCriteria(
            true={
                "what": "The total of a whole portfolio, annual capital expenditure guidance, or a "
                        "multi-year global plan.",
                "examples": ["Its projects will exceed US$154bn", "Raised its 2026 capex forecast"],
            },
            false={"what": "One concrete, identifiable project."},
        ),
    ),
    "inversor_estatal": Noul(
        instructions="The investor is the State or a wholly state-owned company with no private shareholders.",
        criteria=NoulCriteria(
            true={"what": "National, provincial or municipal government, or a fully state-owned entity."},
            false={
                "what": "A private company, or a listed or mixed-ownership company making a corporate decision.",
                "not_for": "A politician announcing a private company's investment: the investor is the company.",
            },
        ),
    ),
}

_CRITERIOS_MISMO_PROYECTO = NoulCriteria(
    true={
        "what": "Both records report the same underlying investment: the same facility, site, works, "
                "purchase or tender. This includes any kind of commitment, not only plants and mines.",
        "still_true_when": [
            "The company name differs: a subsidiary, a joint venture partner, a project vehicle, "
            "the operator or the parent company. The field "
            "`mismo_grupo_societario_que_el_candidato`, when present and true, means the code has "
            "already confirmed both names belong to the same corporate group.",
            "The stated amount differs, or one of them states no amount.",
            "One frames it as an announcement and the other as an approval, an award or progress.",
            "The wording differs because two outlets reported the same event.",
        ],
        "examples": [
            "McEwen Cooper and Andes Corporación Minera both mean the Los Azules project",
            "Vicuña Argentina and Lundin Mining both tendering 200 buses for the same mine",
        ],
    },
    false={
        "what": "Two genuinely separate investments, even for the same company, industry or city.",
        "examples": ["Two separate plants in Bahía Blanca", "A plant and a pipeline"],
    },
)


def disponible() -> bool:
    """True si hay SDK y credencial. Todo el módulo es opt-in."""
    return _SDK_OK and bool(API_KEY)


def _preguntar(state, questions):
    """Una llamada a la API. Devuelve la respuesta o None si falló."""
    if not disponible():
        return None
    try:
        with TypeSafeClient(api_key=API_KEY, model=MODELO) as client:
            return client.system_one(state=state, questions=questions)
    except Exception as e:
        # Jev nunca rompe la ingesta: se degrada a las heurísticas.
        logger.warning(f"Jev: fallo en la consulta ({e}). Se sigue sin Jev.")
        return None


def es_inversion_real(inversion: dict):
    """
    ¿El registro es una inversión privada productiva?
    Devuelve (veredicto, detalle). veredicto None = Jev no respondió.
    """
    respuesta = _preguntar(
        {
            "empresa": inversion.get("empresa"),
            "descripcion": inversion.get("descripcion"),
            "ubicacion": inversion.get("ubicacion"),
        },
        _PREGUNTAS_INVERSION,
    )
    if respuesta is None:
        return None, None

    p = {k: respuesta.nouls[k].noul for k in _PREGUNTAS_INVERSION}

    # Un descarte fuerte en cualquiera de los tres vetos alcanza; si no, decide
    # la probabilidad de que haya un activo productivo.
    vetado = (
        p["operacion_financiera"] >= UMBRAL_DESCARTE_DURO
        or p["cifra_agregada"] >= UMBRAL_DESCARTE_DURO
        or p["inversor_estatal"] >= UMBRAL_DESCARTE_DURO
    )
    veredicto = (not vetado) and p["activo_productivo"] >= UMBRAL_INVERSION
    return veredicto, p


def cual_es_el_mismo_proyecto(candidato: dict, vecinos: list, mismo_grupo=None):
    """
    Compara el candidato contra varios vecinos en UNA sola llamada.
    Devuelve (vecino, probabilidad) del primero que supere el umbral, o (None, None).

    `mismo_grupo` es una función (a, b) -> bool con la que el código le informa a
    Jev si dos nombres son del mismo grupo societario. Es un dato que no está en
    el texto —"Fertil Pampa" es la subsidiaria de Pampa Energía— y que Jev no
    puede inferir.
    """
    if not vecinos:
        return None, None

    def existente(v):
        d = {
            "id": str(v.get("id")),
            "empresa": v.get("empresa"),
            "descripcion": v.get("descripcion"),
            "ubicacion": v.get("ubicacion"),
        }
        if mismo_grupo is not None:
            d["mismo_grupo_societario_que_el_candidato"] = bool(
                mismo_grupo(candidato.get("empresa"), v.get("empresa"))
            )
        return d

    state = {
        "candidato": {
            "empresa": candidato.get("empresa"),
            "descripcion": candidato.get("descripcion"),
            "ubicacion": candidato.get("ubicacion"),
        },
        "existentes": [existente(v) for v in vecinos],
    }
    # Las preguntas corren en paralelo contra el mismo state, así que preguntar
    # por los k vecinos de una no cuesta más tiempo que preguntar por uno.
    questions = {
        f"v{i}": Noul(
            instructions={
                "question": f"Do `candidato` and `existentes[{i}]` describe the same investment project?",
                "compare": ["`candidato`", f"`existentes[{i}]`"],
            },
            criteria=_CRITERIOS_MISMO_PROYECTO,
        )
        for i in range(len(vecinos))
    }

    respuesta = _preguntar(state, questions)
    if respuesta is None:
        return None, None

    mejor, mejor_p = None, 0.0
    for i, vecino in enumerate(vecinos):
        p = respuesta.nouls[f"v{i}"].noul
        if p > mejor_p:
            mejor, mejor_p = vecino, p
    if mejor_p >= UMBRAL_DUPLICADO:
        return mejor, mejor_p
    return None, mejor_p


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    if not disponible():
        print("Jev desactivado: falta TYPESAFE_API_KEY (o JEV_API_KEY) o el paquete typesafe-sdk.")
        raise SystemExit(0)

    print("=== Filtro de ruido ===")
    casos = [
        ("Sinteplast", "Construye una nueva planta en Ezeiza para duplicar su producción de productos cementicios.", True),
        ("YPF", "YPF colocó US$ 1.200 millones en el mercado internacional a través de un nuevo bono a nueve años.", False),
        ("Carnescatano", "Nueva SRL con un capital de $1.000.000, enfocada en el negocio de la carne.", False),
        ("Puma Energy", "Puma Energy lanzó Puma Flota, una nueva aplicación para empresas de transporte.", False),
        ("Vista", "Peter Thiel adquirió acciones de Vista por US$ 76 millones.", False),
        ("YPF", "YPF anticipa que sus proyectos bajo el RIGI superarán los US$154.000 millones.", False),
        ("Huawei", "La provincia de Buenos Aires le adjudicó la provisión de baterías de almacenamiento.", False),
        ("Toyota", "Abrirá su tercera planta en Zárate para fabricar una Hilux híbrida.", True),
    ]
    ok = 0
    for empresa, desc, esperado in casos:
        v, p = es_inversion_real({"empresa": empresa, "descripcion": desc})
        ok += v == esperado
        print(f"  {'OK ' if v == esperado else 'MAL'} esperado={esperado!s:<5} obtuvo={v!s:<5} {empresa}")
        if p:
            print(f"        productivo={p['activo_productivo']:.2f} financiera={p['operacion_financiera']:.2f} "
                  f"agregado={p['cifra_agregada']:.2f} estatal={p['inversor_estatal']:.2f}")
    print(f"\n  {ok}/{len(casos)} correctos")
