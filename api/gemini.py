import os
import json
import logging
from datetime import datetime, timedelta
from google import genai
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

    tweets_scrapeados = "\n".join(tweets_lista) if tweets_lista else "No hay tweets relevantes en este periodo."
    
    prompt = f"""
Eres un extractor de datos económicos experto especializado en Argentina.

Tenés dos fuentes de datos:

FUENTE 1 — Tweets recientes de curadores de noticias de inversión en Argentina:
---
{tweets_scrapeados}
---

FUENTE 2 — Buscá en Google noticias publicadas entre el {fecha_hace_7_dias} y el {fecha_hoy} sobre inversiones privadas en Argentina. Excluye cualquier noticia publicada antes del {fecha_hace_7_dias}.

Procesá ambas fuentes y devuelve ÚNICAMENTE un array JSON válido, sin texto adicional, sin markdown, sin emojis.
No agregues bajo ningún punto de vista referencias ni citas como [1], [2], [3] dentro de los campos. Limpiá cualquier vestigio HTML de las cadenas de texto.

Exclusiones de inversión:
- Inversiones directas del Estado nacional, provincial o municipal como principal inversor.
- Empresas operadas exclusivamente por el Estado sin accionistas privados (ej. Correo Argentino, Trenes Argentinas, AYSA). Las empresas con capital mixto o que cotizan en bolsa (ej. YPF, Aerolíneas) sí deben incluirse si la inversión es una decisión corporativa.
- Adquisiciones de empresas u oficinas en el exterior de parte de una matriz argentina.
- Movimientos financieros internos (ej. liquidación de dólares, aumentos de capital societario abstracto).
- Proyecciones sectoriales ("el sector minero va a crecer") sin anuncio concreto de una empresa en particular.
- Convocatorias de empleo inespecíficas que no blanqueen montos de inversión en la noticia original.
- Cuidado: Si la noticia menciona a un gobernador o presidente anunciando una inversión privada de una empresa, registrar al sujeto corporativo (la empresa) y jamás al sujeto político.

Schema del Array JSON de salida:
[
  {{
    "empresa": "nombre comercial de la empresa corto, sin SA ni SRL",
    "descripcion": "máximo 4 oraciones. Solo hechos concretos derivados de la noticia. Sin menciones a fuentes, sin opinión, sin emojis ni hipervínculos.",
    "monto_usd": número entero puro en dólares sin puntos ni comas. Si no se informa, poner null,
    "fecha_anuncio": "YYYY-MM-DD",
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
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=GenerateContentConfig(
                temperature=0.1,
                tools=[Tool(google_search=GoogleSearch())]
            )
        )

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
