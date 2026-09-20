import os
import json
import time
import logging
from datetime import datetime, timedelta
from google import genai
from google.genai import errors as genai_errors
from google.genai.types import GenerateContentConfig, Tool, GoogleSearch, HttpOptions
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

_client = None

def get_client():
    global _client
    if _client is None and GEMINI_API_KEY:
        _client = genai.Client(
            api_key=GEMINI_API_KEY,
            http_options=HttpOptions(timeout=300000)  # 5 minutos (300,000ms)
        )
    return _client

def construir_prompt(tweets_lista):
    fecha_hoy = datetime.now().strftime("%Y-%m-%d")
    fecha_hace_7_dias = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")

    fuentes_scrapeadas = "\n".join(tweets_lista) if tweets_lista else "No hay publicaciones relevantes en este periodo."

    prompt = f"""
Eres un extractor de datos económicos experto especializado en Argentina.

Tenés dos fuentes de datos:

FUENTE 1 — Publicaciones recientes sobre inversión en Argentina. Cada línea indica su origen entre paréntesis: "(RIGI)" es el registro oficial de grandes inversiones del Ministerio de Economía (dato confiable, ya estructurado); "(EconoJournal)", "(Infobae Economía)", "(Bichos de Campo)" y otros son portales periodísticos; "(@zubel_ok)" y "(@LuisCaputoAR)" son cuentas de X. Un mismo proyecto puede aparecer varias veces o con distinto encuadre (anuncio, aprobación, adhesión al RIGI): consolidá todo en un único registro, sin duplicar.
---
{fuentes_scrapeadas}
---

FUENTE 2 — Buscá en Google noticias publicadas entre el {fecha_hace_7_dias} y el {fecha_hoy} sobre inversiones privadas en Argentina. Excluye cualquier noticia publicada antes del {fecha_hace_7_dias}.
Prestá atención especial a rubros que las fuentes de arriba cubren poco: agroindustria (plantas de molienda, aceiteras, puertos graneleros), retail y consumo masivo (cadenas que abren locales o desembarcan en el país), automotriz, farmacéutica, logística y tecnología (data centers).

Procesá ambas fuentes y devuelve ÚNICAMENTE un array JSON válido, sin texto adicional, sin markdown, sin emojis.
No agregues bajo ningún punto de vista referencias ni citas como [1], [2], [3] dentro de los campos. Limpiá cualquier vestigio HTML de las cadenas de texto.

REGLA CENTRAL: el registro existe solo si una empresa privada concreta compromete capital en un activo productivo en Argentina — una obra, una planta, una mina, un pozo, un gasoducto, un data center, una red de locales, equipamiento productivo. Si no hay activo productivo, no hay registro.

Exclusiones (si el caso cae en alguna, NO generes el registro):
- Estado como inversor: inversiones directas del Estado (nacional, provincial o municipal), empresas 100% estatales sin accionistas privados (Correo Argentino, Trenes Argentinas, AYSA), o licitaciones del Estado convocando a privados a invertir cuando todavía no hay una empresa concreta comprometida. Las empresas mixtas o que cotizan en bolsa (YPF, Aerolíneas) sí van si la inversión es una decisión corporativa.
- Adquisiciones de empresas u oficinas en el exterior por parte de una matriz argentina.
- OPERACIONES FINANCIERAS, aunque mencionen cifras grandes en dólares: emisión de bonos u obligaciones negociables, colocación de deuda, préstamos bancarios o sindicados, aumentos de capital societario, liquidación de divisas, salidas a bolsa. Un préstamo o un bono es cómo se consigue la plata, no una inversión. Solo va si la noticia describe además la obra concreta que se financia, y en ese caso el registro es la obra.
- CONSTITUCIÓN DE SOCIEDADES: la inscripción de una nueva SA o SRL y su capital social, tomadas del Boletín Oficial. Nunca son inversiones, y además ese capital está en PESOS, no en dólares.
- COMPRAVENTA DE ACCIONES Y M&A: que alguien compre acciones de una empresa en el mercado o adquiera un paquete accionario de otra no es una inversión productiva nueva. El dinero cambia de manos entre accionistas, no se crea un activo.
- CONTRATOS ADJUDICADOS A PROVEEDORES: si una empresa gana la licitación para construir o proveer algo, el que invierte es quien la contrató, no el proveedor. Registrá al inversor, no al contratista.
- LANZAMIENTOS DE PRODUCTOS, APLICACIONES, SERVICIOS O ALIANZAS COMERCIALES: una app nueva, un acuerdo de provisión entre dos marcas o un convenio de distribución no son inversiones.
- CIFRAS AGREGADAS DE CARTERA: el total de todos los proyectos de una empresa, su guidance de capex anual, o su plan plurianual global. Ejemplo de lo que NO va: "los proyectos RIGI de la empresa superarán los US$154.000 millones". Solo se registran proyectos individuales e identificables.
- Proyecciones o anuncios colectivos sin empresa concreta: "el sector minero va a crecer", "varias empresas invertirán". No agrupes una lista de empresas en un registro.
- Estadísticas macroeconómicas: exportaciones, superávit fiscal, PBI, cotizaciones, precios de commodities.
- Hitos operativos sin nueva inversión: inauguraciones o "comenzó a operar/abastecer/producir", cuando NO se anuncia un monto nuevo ni un proyecto concreto de obra/planta/expansión.
- Intenciones vagas: "expresó interés", "evalúa", "podría invertir", cuando falta a la vez el monto y un plan específico (obra, planta, pozos, sucursales).
- Convocatorias de empleo inespecíficas que no blanqueen montos de inversión.
- Si un gobernador o presidente anuncia la inversión de una empresa privada, registrá a la empresa, jamás al político.

Schema del Array JSON de salida:
[
  {{
    "empresa": "nombre comercial corto de UNA empresa real e identificable, sin SA ni SRL. Si no hay una empresa concreta (solo un sector, un genérico como 'empresas privadas', una categoría/descripción en lugar de la marca, o el nombre de una persona física sin empresa), omití el registro entero.",
    "descripcion": "máximo 4 oraciones. Solo hechos concretos derivados de la noticia. Incluí SIEMPRE, si aparecen, el nombre propio del proyecto y la localidad exacta (ej: 'Los Azules', 'Gualcamayo', 'Rincón de Aranda', 'Timbúes'): son lo que permite reconocer después que dos noticias hablan del mismo proyecto. Sin menciones a fuentes, sin opinión, sin emojis ni hipervínculos.",
    "monto_usd": número entero puro EN DÓLARES sin puntos ni comas (ej: 40 millones -> 40000000). Si la cifra está en pesos argentinos, poné null: no la conviertas. Si no se informa, poner null,
    "fecha_anuncio": "fecha real del anuncio en formato YYYY-MM-DD; si no surge de la noticia, poné null",
    "estado": "confirmada" o "anunciada" o "en_evaluacion",
    "ubicacion": "nombre de la provincia argentina donde ocurre la inversión, o null si no se menciona. Solo la provincia, sin ciudad ni país. Ejemplos: 'Neuquén', 'Buenos Aires', 'Salta'.",
    "empleos": número entero de puestos de trabajo directos generados o previstos, o null si no se menciona. No incluir empleos indirectos.
  }}
]
"""
    return prompt


def procesar_con_gemini(tweets_lista):
    if not GEMINI_API_KEY:
        logger.error("Falta la variable de entorno GEMINI_API_KEY")
        return []

    client = get_client()
    if not client:
        return []
    prompt = construir_prompt(tweets_lista)

    logger.info("Enviando prompt a Gemini 2.5 Flash con Grounding activado...")
    try:
        # Los 503 por alta demanda son transitorios: reintentar antes de perder el ciclo de 72hs
        intentos_maximos = 4
        espera_segundos = 30
        for intento in range(1, intentos_maximos + 1):
            try:
                response = client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=prompt,
                    config=GenerateContentConfig(
                        temperature=0.1,
                        tools=[Tool(google_search=GoogleSearch())]
                    )
                )
                break
            except genai_errors.ServerError as se:
                if intento == intentos_maximos:
                    raise
                logger.warning(
                    f"Gemini devolvió un error de servidor (intento {intento}/{intentos_maximos}): {se}. "
                    f"Reintentando en {espera_segundos}s..."
                )
                time.sleep(espera_segundos)
                espera_segundos *= 2

        texto_crudo = response.text
        logger.info(f"Texto crudo de Gemini (primeros 500 chars): {texto_crudo[:500]}")

        # Limpieza de bloques markdown (Grounding no admite JSON nativo)
        texto_limpio = texto_crudo.replace("```json", "").replace("```", "").strip()

        try:
            array_json = json.loads(texto_limpio)
            if not isinstance(array_json, list):
                logger.error("Gemini no devolvió una lista JSON.")
                return []
            if len(array_json) == 0:
                logger.warning("Gemini devolvió un array JSON vacío.")
                return []
            return array_json

        except json.JSONDecodeError as de:
            logger.error(f"JSONDecodeError: {de}")
            logger.error(f"Texto crudo completo:\n{texto_crudo}")
            return []

    except Exception as e:
        import traceback
        logger.error(f"Fallo en la comunicación con el servicio de API Google Gemini: {e}")
        logger.error(traceback.format_exc())
        return []

if __name__ == "__main__":
    tweets_prueba = [
        "[2026-03-31] Bridgestone invierte u$s 40.000.000 para ampliar planta de Llavallol.",
        "[2026-04-01] Coca-Cola no invertirá en el país, canceló el lanzamiento de su planta.",
    ]

    resultados = procesar_con_gemini(tweets_prueba)
    print(json.dumps(resultados, indent=2, ensure_ascii=False))
