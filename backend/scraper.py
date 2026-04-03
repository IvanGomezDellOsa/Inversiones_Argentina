import os
import logging
from datetime import datetime, timedelta, timezone
from apify_client import ApifyClient
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

APIFY_TOKEN = os.getenv("APIFY_API_TOKEN")

def scrapear_apify():
    if not APIFY_TOKEN:
        logger.error("Falta la variable de entorno APIFY_API_TOKEN")
        return []

    client = ApifyClient(APIFY_TOKEN)

    # from: y since: delegan el filtrado a Twitter
    fecha_limite = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d")
    query = f'("Más inversión" from:zubel_ok) OR ("MEGA INVERSIÓN EN ARGENTINA: " from:laderechadiario) since:{fecha_limite}'

    run_input = {
        "searchTerms": [query],
        "sort": "Latest",
        "max_posts": 50,
    }

    logger.info(f"Lanzando actor Apify con query: {query}")
    
    try:
        run = client.actor("danek/twitter-scraper-ppr").call(run_input=run_input)
        dataset_id = run.get("defaultDatasetId")
        if not dataset_id:
            logger.error("No se obtuvo dataset ID")
            return []
            
        logger.info("Recuperando resultados del dataset")
        
        todos_los_tweets = []
        for item in client.dataset(dataset_id).iterate_items():
            texto = item.get("fullText") or item.get("full_text") or item.get("text")
            fecha_iso = item.get("createdAt") or item.get("created_at") 
            
            if texto and fecha_iso:
                try:
                    fecha_obj = datetime.fromisoformat(fecha_iso.replace("Z", "+00:00")).replace(tzinfo=None)
                    fecha_str = fecha_obj.strftime("%Y-%m-%d")
                    todos_los_tweets.append(f"[{fecha_str}] {texto}")
                except Exception as e:
                    logger.warning(f"Error procesando fecha {fecha_iso}: {e}")
                    
        return todos_los_tweets

    except Exception as e:
        logger.error(f"Falla durante la ejecución en Apify: {e}")
        return []

if __name__ == "__main__":
    resultado = scrapear_apify()
    for t in resultado:
        print(t)
