import os
import json
import logging
from datetime import datetime, timedelta
from google import genai
from google.genai.types import GenerateContentConfig, Tool, GoogleSearch
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

_client = None

def get_client():
    global _client
    if _client is None and GEMINI_API_KEY:
        _client = genai.Client(api_key=GEMINI_API_KEY)
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
    "monto_usd": número entero puro en dólares sin puntos ni comas. (ej. si son 12 millones poner 12000000). Si no se informa, o está en otra moneda sin poder convertirse limpiamente, poner null,
    "fecha_anuncio": "YYYY-MM-DD",
    "estado": "confirmada" o "anunciada" o "en_evaluacion"
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
                temperature=1.0,
                tools=[Tool(google_search=GoogleSearch())]
            )
        )

        texto_crudo = response.text
        logger.info("Respuesta recibida de Gemini")

        # Grounding no admite response_mime_type JSON; se limpia el bloque markdown si lo agrega el modelo
        texto_limpio = texto_crudo.replace("```json", "").replace("```", "").strip()
        
        try:
            array_json = json.loads(texto_limpio)
            if not isinstance(array_json, list):
                logger.error("Gemini no devolvió una lista JSON.")
                return []
            return array_json
            
        except json.JSONDecodeError as de:
            logger.error(f"Falla crítica: el output de Gemini no es JSON válido. \nOutput crudo: {texto_crudo}")
            return []
            
    except Exception as e:
        logger.error(f"Fallo en la comunicación con el servicio de API Google Gemini: {e}")
        return []

if __name__ == "__main__":
    tweets_prueba = [
        "[2026-03-31] Bridgestone invierte u$s 40.000.000 para ampliar planta de Llavallol.",
        "[2026-04-01] Coca-Cola no invertirá en el país, canceló el lanzamiento de su planta.",
    ]

    resultados = procesar_con_gemini(tweets_prueba)
    print(json.dumps(resultados, indent=2, ensure_ascii=False))
