import os
import logging
from datetime import datetime, timedelta
from apify_client import ApifyClient
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

APIFY_API_TOKEN = os.getenv("APIFY_API_TOKEN")

# Queries de búsqueda directa en Twitter (redundante y específica: "huella digital")
SEARCH_QUERIES = [
    "Más inversión 🤝 Más empleo from:zubel_ok",
    "Más inversión Más empleo from:zubel_ok",
    "Más inversiones 🤝 Más empleo from:zubel_ok",
    "inversión from:zubel_ok",
    "inversion from:zubel_ok",
    "inversiones from:zubel_ok",
]


def _parsear_fecha_twitter(fecha_str):
    """Parsea el formato de fecha de Twitter: 'Fri Apr 03 15:26:15 +0000 2026'"""
    try:
        return datetime.strptime(fecha_str, "%a %b %d %H:%M:%S %z %Y")
    except (ValueError, TypeError):
        return None


def _extraer_texto_completo(item):
    """Extrae el texto completo del tweet, incluyendo citas (quoted tweets)."""
    texto = item.get("text", "")
    quoted = item.get("quoted")
    if quoted and isinstance(quoted, dict):
        texto_cita = quoted.get("text", "")
        if texto_cita:
            texto += f" | Cita: {texto_cita}"
    return texto.strip()


def scrapear_twitter():
    """
    Busca tweets usando searchTerms en Apify (danek/twitter-scraper-ppr).
    El filtrado de keywords se hace SERVER-SIDE: Apify devuelve sólo los tweets
    que contienen la query, en lugar de traer el perfil completo y filtrar localmente.
    Esto resuelve el problema del límite de 20 posts en el free tier.
    """
    if not APIFY_API_TOKEN:
        logger.error("Falta la variable de entorno APIFY_API_TOKEN")
        return []

    client = ApifyClient(APIFY_API_TOKEN)
    limite_fecha = datetime.now(tz=None) - timedelta(days=7)
    todos_los_tweets = []
    ids_vistos = set()  # evitar duplicados entre queries

    for query in SEARCH_QUERIES:
        logger.info(f"Buscando en Twitter: '{query}'")

        run_input = {
            "query": query,
            "search_type": "Latest",
            "max_posts": 20,
        }

        try:
            run = client.actor("danek/twitter-scraper-ppr").call(
                run_input=run_input,
                timeout_secs=120
            )

            status = run.get("status")
            if status != "SUCCEEDED":
                logger.warning(f"Actor Apify terminó con estado: {status} para query '{query}'")
                continue

            dataset_id = run.get("defaultDatasetId")
            items = list(client.dataset(dataset_id).iterate_items())
            logger.info(f"Apify devolvió {len(items)} tweets para '{query}'")

            tweets_nuevos = 0
            for item in items:
                # Deduplicar por ID
                tweet_id = item.get("id") or item.get("tweet_id")
                if tweet_id and tweet_id in ids_vistos:
                    continue
                if tweet_id:
                    ids_vistos.add(tweet_id)

                fecha_obj = _parsear_fecha_twitter(item.get("created_at", ""))
                if not fecha_obj:
                    continue

                fecha_naive = fecha_obj.replace(tzinfo=None)
                if fecha_naive < limite_fecha:
                    logger.debug(f"Tweet descartado por fecha: {fecha_naive}")
                    continue

                texto = _extraer_texto_completo(item)
                if not texto:
                    continue

                fecha_formateada = fecha_naive.strftime("%Y-%m-%d")
                todos_los_tweets.append(f"[{fecha_formateada}] {texto}")
                tweets_nuevos += 1

            logger.info(f"Tweets válidos (dentro de 7 días): {tweets_nuevos}")

        except Exception as e:
            logger.error(f"Error al ejecutar query '{query}': {e}")
            continue

    logger.info(f"Total tweets recopilados: {len(todos_los_tweets)}")
    return todos_los_tweets


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    resultado = scrapear_twitter()
    print(f"\n=== {len(resultado)} tweets encontrados ===\n")
    for t in resultado:
        print(t)
        print()
