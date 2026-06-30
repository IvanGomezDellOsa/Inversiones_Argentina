"""
Fuente oficial RIGI (Régimen de Incentivos para Grandes Inversiones).

Lee el listado de proyectos APROBADOS que el Ministerio de Economía publica en
https://www.argentina.gob.ar/economia/rigi . Esa página alimenta su mapa desde
una hoja de Google Sheets pública; consumimos esa misma hoja vía la API de
Sheets (datos ya estructurados: empresa, monto, provincia, sector, descripción).

Por qué sumarla: es la fuente de MENOR margen de error para estos anuncios
(datos oficiales, no interpretación periodística). Cada fila se convierte en una
línea de texto en el MISMO formato que las demás fuentes ("[YYYY-MM-DD] (RIGI)
...") y entra al pipeline existente (Gemini + deduplicación) sin lógica nueva.

Decisiones de diseño:
- Fail-safe: ante cualquier fallo (red, formato, rotación de la API key pública)
  devuelve [] y NO rompe la ingesta.
- La hoja NO trae fecha por proyecto: usamos la fecha de ejecución del cron. Las
  fechas solo dan un orden cronológico aproximado, no son un dato informativo.
- El monto de la hoja está expresado en MILLONES de USD: lo explicitamos como
  "USD N millones" para que el pipeline lo normalice igual que las demás fuentes.
- La hoja tiene DOS filas de encabezado (claves y etiquetas): se saltan ambas.
- La hoja "evaluacion" son solo totales agregados, no proyectos: se ignora.
"""

import logging
import os

import requests
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# ID de la hoja pública del portal RIGI (identificador de documento, no es un secreto).
RIGI_SHEET_ID = "1eytHJrzUjIFOXI-P1Hx_wbmZiSqPxVle059Djdos6u8"
RIGI_SHEET_NAME = "dataset"
# API key de Google Sheets del portal público de gob.ar. Se lee del entorno para no
# versionarla; si falta, la fuente RIGI se omite (fail-safe, no rompe la ingesta).
RIGI_API_KEY = os.getenv("RIGI_API_KEY")

TIMEOUT = 20
FILAS_ENCABEZADO = 2          # fila 0 = claves, fila 1 = etiquetas humanas
MAX_DESCRIPCION = 500         # recorte para no inflar el prompt

# Índice de cada columna en la hoja (orden fijo del dataset oficial).
COL_PROVINCIA = 0
COL_NOMBRE = 1
COL_EMPRESA = 3
COL_INVERSION = 4            # en millones de USD
COL_EMPLEOS = 5
COL_SECTOR = 6
COL_DESCRIPCION = 7


def _celda(fila, indice):
    """Devuelve la celda como texto limpio, o '' si no existe."""
    if indice < len(fila) and fila[indice] is not None:
        return str(fila[indice]).strip()
    return ""


def recopilar_rigi(fecha_hoy: str) -> list:
    """
    Devuelve los proyectos RIGI aprobados como líneas de texto para el pipeline.
    `fecha_hoy` es la fecha de ejecución del cron en formato YYYY-MM-DD.
    """
    if not RIGI_API_KEY:
        logger.warning("RIGI: falta la variable de entorno RIGI_API_KEY. Se omite la fuente RIGI.")
        return []

    url = (
        f"https://sheets.googleapis.com/v4/spreadsheets/{RIGI_SHEET_ID}"
        f"/values/{RIGI_SHEET_NAME}?key={RIGI_API_KEY}&alt=json"
    )
    try:
        resp = requests.get(url, timeout=TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        logger.error(f"RIGI: fallo al obtener/parsear la hoja oficial: {e}")
        return []

    filas = data.get("values") or []
    if len(filas) <= FILAS_ENCABEZADO:
        logger.warning("RIGI: la hoja no trae filas de datos (¿cambió el formato?).")
        return []

    resultados = []
    for fila in filas[FILAS_ENCABEZADO:]:
        empresa = _celda(fila, COL_EMPRESA)
        nombre = _celda(fila, COL_NOMBRE)
        if not empresa or not nombre:
            continue  # fila incompleta: la salteamos sin romper

        provincia = _celda(fila, COL_PROVINCIA)
        sector = _celda(fila, COL_SECTOR)
        empleos = _celda(fila, COL_EMPLEOS)
        descripcion = _celda(fila, COL_DESCRIPCION)[:MAX_DESCRIPCION]
        inversion = _celda(fila, COL_INVERSION)

        partes = [f"{empresa} — proyecto \"{nombre}\""]
        if provincia:
            partes.append(f"en {provincia}")
        detalle = ". ".join([" ".join(partes)])
        extra = []
        if sector:
            extra.append(f"Sector: {sector}")
        if inversion:
            extra.append(f"Inversión comprometida: USD {inversion} millones")
        if empleos:
            extra.append(f"Empleos: {empleos}")
        cuerpo = ". ".join([detalle] + extra)
        if descripcion:
            cuerpo = f"{cuerpo}. {descripcion}"

        # Estado "confirmada": son proyectos ya APROBADOS y adheridos al RIGI.
        texto = f"[{fecha_hoy}] (RIGI) Proyecto aprobado y adherido al RIGI. {cuerpo}"
        resultados.append(texto)

    logger.info(f"RIGI: {len(resultados)} proyectos aprobados recopilados.")
    return resultados


if __name__ == "__main__":
    from datetime import datetime
    logging.basicConfig(level=logging.INFO)
    hoy = datetime.now().strftime("%Y-%m-%d")
    proyectos = recopilar_rigi(hoy)
    print(f"\n=== {len(proyectos)} proyectos RIGI ===\n")
    for p in proyectos:
        print(p)
        print()
