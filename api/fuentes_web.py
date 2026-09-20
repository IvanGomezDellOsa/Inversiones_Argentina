"""
Fuentes web (RSS), en el mismo formato que el resto del pipeline.

Los feeds de WordPress devuelven 10 items (~3 días) con una ventana declarada de
7, así que se pagina con `?paged=N` hasta cubrirla de verdad. Hay medios de
rubros distintos porque con X caída quedaba solo energía.

Cada fuente es fail-safe por separado: si una se cae devuelve [] y no rompe la
ingesta.
"""

import re
import html
import logging
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree as ET

import requests

from relevancia import filtrar_publicaciones

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
}

DIAS_VENTANA = 7
TIMEOUT = 20
MAX_PAGINAS = 4          # tope de seguridad: 4 páginas x 10 items = ~40 notas por medio
MAX_DESCRIPCION = 400    # recorte para no inflar el prompt


# (etiqueta, url, admite ?paged=N). Los de Infobae, Cronista y Ámbito no son
# WordPress: no paginan, pero traen muchos más items por página.
FUENTES = [
    ("EconoJournal", "https://econojournal.com.ar/feed/", True),
    ("Bichos de Campo", "https://bichosdecampo.com/feed/", True),
    ("Infocampo", "https://www.infocampo.com.ar/feed/", True),
    ("Infobae Economía", "https://www.infobae.com/arc/outboundfeeds/rss/category/economia/?outputType=xml", False),
    ("El Cronista", "https://www.cronista.com/files/rss/negocios.xml", False),
    ("Ámbito", "https://www.ambito.com/rss/pages/economia.xml", False),
]


def _limpiar_texto(texto: str) -> str:
    """Quita etiquetas HTML, des-escapa entidades y normaliza espacios."""
    if not texto:
        return ""
    sin_tags = re.sub(r"<[^>]+>", " ", texto)
    return re.sub(r"\s+", " ", html.unescape(sin_tags)).strip()


def _parsear_fecha(pub: str):
    """pubDate de RSS a datetime con zona. None si no se puede."""
    if not pub:
        return None
    try:
        dt = parsedate_to_datetime(pub)
    except (TypeError, ValueError):
        return None
    if dt is not None and dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _leer_pagina(url: str) -> list:
    """Descarga y parsea un feed. Devuelve los <item> (o <entry> si es Atom)."""
    resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    resp.raise_for_status()
    root = ET.fromstring(resp.content)
    items = list(root.iter("item"))
    if not items:
        # Algunos feeds son Atom en vez de RSS.
        items = [e for e in root.iter() if e.tag.endswith("}entry") or e.tag == "entry"]
    return items


def _texto_item(item, etiqueta: str, corte):
    """
    Convierte un <item> en (fecha, linea) o (None, None) si no sirve.
    `corte` es el datetime mínimo aceptado.
    """
    titulo = _limpiar_texto(item.findtext("title", "") or "")
    if not titulo:
        return None, None

    descripcion = _limpiar_texto(
        item.findtext("description", "")
        or item.findtext("{http://purl.org/rss/1.0/modules/content/}encoded", "")
        or item.findtext("summary", "")
        or ""
    )[:MAX_DESCRIPCION]

    fecha = _parsear_fecha(item.findtext("pubDate", "") or item.findtext("published", "") or "")
    if fecha is not None and fecha < corte:
        return fecha, None

    fecha_str = fecha.strftime("%Y-%m-%d") if fecha else datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return fecha, f"[{fecha_str}] ({etiqueta}) {titulo}. {descripcion}".strip()


def scrapear_feed(etiqueta: str, url: str, pagina: bool, dias: int = DIAS_VENTANA) -> list:
    """
    Lee un feed RSS, paginando mientras siga trayendo notas dentro de la ventana.
    Cualquier fallo devuelve lo juntado hasta ese momento.
    """
    corte = datetime.now(timezone.utc) - timedelta(days=dias)
    resultados = []
    paginas = MAX_PAGINAS if pagina else 1

    for n in range(1, paginas + 1):
        url_pagina = url if n == 1 else f"{url}{'&' if '?' in url else '?'}paged={n}"
        try:
            items = _leer_pagina(url_pagina)
        except Exception as e:
            # Fallar en la primera página es un problema; en las siguientes suele
            # ser simplemente el final del feed.
            nivel = logger.error if n == 1 else logger.debug
            nivel(f"{etiqueta}: fallo al leer {url_pagina}: {e}")
            break

        if not items:
            if n == 1:
                logger.warning(f"{etiqueta}: el feed no trajo items (¿cambió el formato?).")
            break

        agotado = False
        for item in items:
            try:
                fecha, linea = _texto_item(item, etiqueta, corte)
            except Exception as e:
                logger.debug(f"{etiqueta}: item descartado: {e}")
                continue
            if linea:
                resultados.append(linea)
            elif fecha is not None:
                # Ya pasamos la ventana: no tiene sentido seguir paginando.
                agotado = True

        if agotado:
            break

    logger.info(f"{etiqueta}: {len(resultados)} notas dentro de los últimos {dias} días.")
    return resultados


def recopilar_fuentes_web(dias: int = DIAS_VENTANA) -> list:
    """
    Combina todas las fuentes y deja solo las notas que parecen hablar de una
    inversión. Cada fuente es fail-safe por separado.
    """
    crudas = []
    caidas = []
    for etiqueta, url, pagina in FUENTES:
        try:
            notas = scrapear_feed(etiqueta, url, pagina, dias)
        except Exception as e:
            logger.error(f"{etiqueta}: error inesperado: {e}")
            notas = []
        if not notas:
            caidas.append(etiqueta)
        crudas.extend(notas)

    publicaciones, descartadas = filtrar_publicaciones(crudas)

    if caidas:
        logger.warning(f"Fuentes web sin resultados: {', '.join(caidas)}")
    logger.info(
        f"Fuentes web: {len(crudas)} notas leídas de "
        f"{len(FUENTES) - len(caidas)}/{len(FUENTES)} medios; "
        f"{len(publicaciones)} pasan el filtro de relevancia ({descartadas} descartadas)."
    )
    return publicaciones


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    web = recopilar_fuentes_web()
    print(f"\n=== {len(web)} publicaciones web ===\n")
    for p in web:
        print(p[:200])
        print()
