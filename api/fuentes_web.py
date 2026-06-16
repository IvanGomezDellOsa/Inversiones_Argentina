"""
Fuentes web complementarias a la cuenta de X (@zubel_ok).

Objetivo: diversificar la recolección sin depender de un único curador y sin
gastar scrapeos de Apify. Cada fuente devuelve una lista de strings en el MISMO
formato que el scraper de Twitter ("[YYYY-MM-DD] texto"), de modo que se integran
al pipeline existente sin tocar la lógica de Gemini.

Principios de diseño:
- Fail-safe: si una fuente falla (red, parseo) devuelve [] y NO rompe la ingesta.
  El sistema degrada con elegancia.
- Bajo riesgo: EconoJournal vía RSS (XML estándar, solo librería estándar).
- Timeouts en todas las peticiones.
"""

import re
import html
import logging
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree as ET

import requests

logger = logging.getLogger(__name__)

# User-Agent de navegador real para evitar bloqueos anti-bot básicos.
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
}

DIAS_VENTANA = 7
TIMEOUT = 20

# --- EconoJournal (RSS de WordPress) ---
ECONOJOURNAL_FEEDS = [
    "https://econojournal.com.ar/feed/",
]


def _limpiar_texto(texto: str) -> str:
    """Quita etiquetas HTML, des-escapa entidades y normaliza espacios."""
    if not texto:
        return ""
    sin_tags = re.sub(r"<[^>]+>", " ", texto)
    return re.sub(r"\s+", " ", html.unescape(sin_tags)).strip()


def _dentro_de_ventana(fecha_dt, dias: int = DIAS_VENTANA) -> bool:
    """True si la fecha está dentro de la ventana. Si no hay fecha, no descarta."""
    if fecha_dt is None:
        return True
    ahora = datetime.now(timezone.utc)
    if fecha_dt.tzinfo is None:
        fecha_dt = fecha_dt.replace(tzinfo=timezone.utc)
    return fecha_dt >= (ahora - timedelta(days=dias))


def scrapear_econojournal(dias: int = DIAS_VENTANA) -> list:
    """Lee el/los RSS de EconoJournal y devuelve notas recientes como texto."""
    resultados = []
    for url in ECONOJOURNAL_FEEDS:
        try:
            resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
            resp.raise_for_status()
            root = ET.fromstring(resp.content)
        except Exception as e:
            logger.error(f"EconoJournal: fallo al obtener/parsear {url}: {e}")
            continue

        items = list(root.iter("item"))
        if not items:
            logger.warning(
                f"EconoJournal: respuesta sin <item> en {url} "
                f"(¿cambió el formato del feed, p. ej. a Atom?)."
            )

        for item in items:
            try:
                titulo = _limpiar_texto(item.findtext("title", ""))
                descripcion = _limpiar_texto(item.findtext("description", ""))
                pub = item.findtext("pubDate", "")

                fecha_dt = None
                if pub:
                    try:
                        fecha_dt = parsedate_to_datetime(pub)
                    except Exception:
                        fecha_dt = None

                if not _dentro_de_ventana(fecha_dt, dias):
                    continue
                if not titulo:
                    continue

                fecha_str = fecha_dt.strftime("%Y-%m-%d") if fecha_dt else "fecha-desconocida"
                # Recortamos la descripción para no inflar el prompt.
                descripcion = descripcion[:400]
                texto = f"[{fecha_str}] (EconoJournal) {titulo}. {descripcion}".strip()
                resultados.append(texto)
            except Exception as e:
                logger.debug(f"EconoJournal: item descartado: {e}")
                continue

    logger.info(f"EconoJournal: {len(resultados)} notas recientes recopiladas.")
    return resultados


def recopilar_fuentes_web(dias: int = DIAS_VENTANA) -> list:
    """Combina todas las fuentes web. Cada una es fail-safe por separado."""
    publicaciones = []
    publicaciones.extend(scrapear_econojournal(dias))
    logger.info(f"Fuentes web: {len(publicaciones)} publicaciones en total.")
    return publicaciones


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    web = recopilar_fuentes_web()
    print(f"\n=== {len(web)} publicaciones web ===\n")
    for p in web:
        print(p)
        print()
