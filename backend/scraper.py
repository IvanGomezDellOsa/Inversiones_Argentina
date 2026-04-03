import logging
import locale
import requests
import urllib.parse
from datetime import datetime, timedelta
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

NITTER_INSTANCES = [
    "https://nitter.net",
    "https://nitter.poast.org",
    "https://nitter.cz",
    "https://xcancel.com"
]

def parsear_tweets(html_content):
    tweets_filtrados = []
    limite_fecha = datetime.now() - timedelta(days=7)
    
    soup = BeautifulSoup(html_content, 'html.parser')
    items = soup.select('.timeline-item')
    
    for item in items:
        # Extraer texto (puede tener quote/cita)
        content_div = item.select_one('.tweet-content')
        quote_div = item.select_one('.quote .tweet-content')
        
        texto_principal = content_div.text.strip() if content_div else ""
        texto_cita = quote_div.text.strip() if quote_div else ""
        
        texto_final = texto_principal
        if texto_cita:
            texto_final += f" | Cita: {texto_cita}"
            
        if not texto_final:
            continue
            
        # Extraer fecha
        date_a = item.select_one('.tweet-date a')
        if not date_a or not date_a.get('title'):
            continue
            
        # Nitter format: title="Apr 2, 2026 · 12:45 PM UTC"
        fecha_str_raw = date_a['title'].split('·')[0].strip() # "Apr 2, 2026"
        try:
            locale.setlocale(locale.LC_TIME, 'C')
            fecha_obj = datetime.strptime(fecha_str_raw, "%b %d, %Y")
            if fecha_obj >= limite_fecha:
                fecha_formateada = fecha_obj.strftime("%Y-%m-%d")
                tweets_filtrados.append(f"[{fecha_formateada}] {texto_final}")
        except ValueError:
            logger.warning(f"Error parseando fecha nitter: {fecha_str_raw}")
            continue
            
    return tweets_filtrados

def scrapear_nitter():
    query_zubel = '"Más inversión"'
    encoded_q = urllib.parse.quote(query_zubel)
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9"
    }

    todos_los_tweets = []

    for instancia in NITTER_INSTANCES:
        url = f"{instancia}/zubel_ok/search?f=tweets&q={encoded_q}"
        logger.info(f"Lanzando scraper Nitter contra: {url}")
        
        try:
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code == 200:
                logger.info(f"¡Éxito! Nitter respondió en {instancia}")
                tweets_extraidos = parsear_tweets(response.text)
                todos_los_tweets.extend(tweets_extraidos)
                break # Si una instancia funcionó, no seguimos golpeando a las demás
            else:
                logger.warning(f"Instancia {instancia} devolvió HTTP {response.status_code}")
        except Exception as e:
            logger.warning(f"Instancia {instancia} no disponible (Error DNS/Timeout)")
            continue

    return todos_los_tweets

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    resultado = scrapear_nitter()
    for t in resultado:
        print(t)
