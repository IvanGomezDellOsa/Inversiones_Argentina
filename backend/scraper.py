import os
import logging
from datetime import datetime, timedelta
from apify_client import ApifyClient
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

APIFY_API_TOKEN = os.getenv("APIFY_API_TOKEN")

# Lista vacía de keywords = sin filtro; el actor devuelve todos los posts del perfil
TWITTER_CONFIG = {
    "zubel_ok": ["Más inversión", "Mas inversion", "más inversión", "mas inversion"],
}


def _parsear_fecha_twitter(fecha_str):
    """Parsea el formato de fecha de Twitter: 'Fri Apr 03 15:26:15 +0000 2026'"""
    try:
        return datetime.strptime(fecha_str, "%a %b %d %H:%M:%S %z %Y")
    except (ValueError, TypeError):
        return None


def _extraer_texto_completo(item):
    """Extrae el texto completo del tweet, incluyendo citas (quoted tweets)."""
    texto = item.get("text", "")

    # Si tiene un tweet citado, concatenar su texto
    quoted = item.get("quoted")
    if quoted and isinstance(quoted, dict):
        texto_cita = quoted.get("text", "")
        if texto_cita:
            texto += f" | Cita: {texto_cita}"

    return texto.strip()


def _cumple_filtro(texto_completo, keywords):
    """Retorna True si el texto contiene al menos una keyword, o si no hay filtro definido."""
    if not keywords:
        return True
    texto_lower = texto_completo.lower()
    return any(kw.lower() in texto_lower for kw in keywords)


def scrapear_twitter():
    """
    Scrapea los últimos tweets de las cuentas configuradas usando Apify (danek/twitter-scraper-ppr).
    Filtra por fecha (últimos 7 días) y por keywords definidas en TWITTER_CONFIG.
    Devuelve una lista de strings con formato: [YYYY-MM-DD] texto del tweet
    """
    if not APIFY_API_TOKEN:
        logger.error("Falta la variable de entorno APIFY_API_TOKEN")
        return []

    client = ApifyClient(APIFY_API_TOKEN)
    limite_fecha = datetime.now(tz=None) - timedelta(days=7)
    todos_los_tweets = []

    for username, keywords in TWITTER_CONFIG.items():
        logger.info(f"Scrapeando tweets de @{username} via Apify...")
        if keywords:
            logger.info(f"  Filtro de keywords activo: {keywords}")

        run_input = {
            "username": username,
            "max_posts": 50,  # Los últimos 50 posts, luego filtramos por fecha y keyword
        }

        try:
            run = client.actor("danek/twitter-scraper-ppr").call(
                run_input=run_input,
                timeout_secs=120
            )

            status = run.get("status")
            if status != "SUCCEEDED":
                logger.warning(f"Actor Apify terminó con estado: {status}")
                continue

            dataset_id = run.get("defaultDatasetId")
            items = list(client.dataset(dataset_id).iterate_items())
            logger.info(f"Apify devolvió {len(items)} tweets brutos de @{username}")

            tweets_cuenta = 0
            for item in items:
                fecha_obj = _parsear_fecha_twitter(item.get("created_at", ""))
                if not fecha_obj:
                    continue

                # Convertir a naive datetime para comparar con limite_fecha
                fecha_naive = fecha_obj.replace(tzinfo=None)
                if fecha_naive < limite_fecha:
                    continue

                texto = _extraer_texto_completo(item)
                if not texto:
                    continue

                # Se omiten tweets que no contienen la keyword de inversión
                if not _cumple_filtro(texto, keywords):
                    continue

                fecha_formateada = fecha_naive.strftime("%Y-%m-%d")
                todos_los_tweets.append(f"[{fecha_formateada}] {texto}")
                tweets_cuenta += 1

            logger.info(f"Tweets de @{username} que pasan filtro (fecha + keyword): {tweets_cuenta}")

        except Exception as e:
            logger.error(f"Error al scrapear @{username} con Apify: {e}")
            continue

    return todos_los_tweets


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    resultado = scrapear_twitter()
    print(f"\n=== {len(resultado)} tweets encontrados con filtro 'Más inversión' ===\n")
    for t in resultado:
        print(t)
        print()
