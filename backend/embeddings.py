import os
import logging
from google import genai
from google.genai.types import EmbedContentConfig
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

def generar_embedding(texto: str) -> list[float]:
    if not GEMINI_API_KEY:
        logger.error("Falta la variable de entorno GEMINI_API_KEY")
        return []

    client = get_client()
    if not client:
        return []
    
    try:
        response = client.models.embed_content(
            model='gemini-embedding-2-preview',
            contents=texto,
            config=EmbedContentConfig(output_dimensionality=768)
        )
        return response.embeddings[0].values
    except Exception as e:
        logger.error(f"Error al generar embedding: {e}")
        return []

if __name__ == "__main__":
    texto_prueba = "Sinteplast Construye una nueva planta en Ezeiza con una inversión de u$s 12 millones."
    vector = generar_embedding(texto_prueba)
    
    if vector:
        print(f"Embedding generado con éxito. Dimensión: {len(vector)}")
        print(f"Muestra de valores: {vector[:5]}...")
    else:
        print("Falló la generación del vector.")
