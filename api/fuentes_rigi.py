"""
Fuente oficial RIGI (Régimen de Incentivos para Grandes Inversiones).

Lee el listado de proyectos APROBADOS que el Ministerio de Economía publica en
https://www.argentina.gob.ar/economia/rigi . Esa página alimenta su mapa desde
una hoja de Google Sheets pública; consumimos esa misma hoja vía la API de
Sheets (datos ya estructurados: empresa, monto, provincia, sector, descripción).

Es la fuente de menor margen de error: datos oficiales, no interpretación
periodística.

La hoja trae filas repetidas (un proyecto por provincia: 29 filas para 23
proyectos) y antes se reenviaba entera en cada corrida, consumiendo ~75% del
prompt para generar puros descartes. Ahora se guarda una huella por proyecto en
`rigi_vistos` y solo se mandan los nuevos o los que cambiaron.

Fail-safe: ante cualquier fallo devuelve [] y no rompe la ingesta. Sin conexión
a la base manda todo, que es preferible a perder un proyecto nuevo.
"""

import hashlib
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


def _descargar_filas():
    """Devuelve las filas de datos de la hoja, o None si falló."""
    if not RIGI_API_KEY:
        logger.warning("RIGI: falta la variable de entorno RIGI_API_KEY. Se omite la fuente RIGI.")
        return None

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
        return None

    filas = data.get("values") or []
    if len(filas) <= FILAS_ENCABEZADO:
        logger.warning("RIGI: la hoja no trae filas de datos (¿cambió el formato?).")
        return None
    return filas[FILAS_ENCABEZADO:]


def _proyectos_unicos(filas):
    """Colapsa las filas repetidas por provincia en proyectos únicos."""
    unicos = {}
    for fila in filas:
        empresa = _celda(fila, COL_EMPRESA)
        nombre = _celda(fila, COL_NOMBRE)
        if not empresa or not nombre:
            continue  # fila incompleta: la salteamos sin romper

        clave = (empresa.lower(), nombre.lower())
        provincia = _celda(fila, COL_PROVINCIA)

        if clave in unicos:
            if provincia and provincia not in unicos[clave]["provincias"]:
                unicos[clave]["provincias"].append(provincia)
            continue

        unicos[clave] = {
            "clave": f"{empresa}|{nombre}",
            "empresa": empresa,
            "nombre": nombre,
            "provincias": [provincia] if provincia else [],
            "sector": _celda(fila, COL_SECTOR),
            "empleos": _celda(fila, COL_EMPLEOS),
            "inversion": _celda(fila, COL_INVERSION),
            "descripcion": _celda(fila, COL_DESCRIPCION)[:MAX_DESCRIPCION],
        }
    return list(unicos.values())


def _huella(proyecto) -> str:
    """Hash del contenido: si cambia, el proyecto se vuelve a mandar."""
    crudo = "|".join([
        proyecto["empresa"], proyecto["nombre"], proyecto["inversion"],
        proyecto["empleos"], proyecto["descripcion"],
    ])
    return hashlib.sha256(crudo.encode("utf-8")).hexdigest()


def _linea(proyecto, fecha_hoy: str) -> str:
    """Arma la línea de texto para el pipeline, en el formato de las demás fuentes."""
    partes = [f"{proyecto['empresa']} — proyecto \"{proyecto['nombre']}\""]
    if proyecto["provincias"]:
        partes.append(f"en {', '.join(proyecto['provincias'])}")
    cuerpo = " ".join(partes)

    extra = []
    if proyecto["sector"]:
        extra.append(f"Sector: {proyecto['sector']}")
    if proyecto["inversion"]:
        extra.append(f"Inversión comprometida: USD {proyecto['inversion']} millones")
    if proyecto["empleos"]:
        extra.append(f"Empleos: {proyecto['empleos']}")
    cuerpo = ". ".join([cuerpo] + extra)

    if proyecto["descripcion"]:
        cuerpo = f"{cuerpo}. {proyecto['descripcion']}"

    # Estado "confirmada": son proyectos ya APROBADOS y adheridos al RIGI.
    return f"[{fecha_hoy}] (RIGI) Proyecto aprobado y adherido al RIGI. {cuerpo}"


# --- Registro de lo ya procesado ----------------------------------------------

def _leer_vistos(conn) -> dict:
    """clave -> huella de los proyectos RIGI ya procesados."""
    with conn.cursor() as cur:
        cur.execute("SELECT clave, huella FROM rigi_vistos")
        return dict(cur.fetchall())


def _marcar_vistos(conn, proyectos):
    """Guarda (o actualiza) la huella de los proyectos que se acaban de mandar."""
    if not proyectos:
        return
    with conn.cursor() as cur:
        for p in proyectos:
            cur.execute(
                """
                INSERT INTO rigi_vistos (clave, huella, visto_en)
                VALUES (%s, %s, NOW())
                ON CONFLICT (clave) DO UPDATE
                  SET huella = EXCLUDED.huella, visto_en = NOW()
                """,
                (p["clave"], _huella(p)),
            )
    conn.commit()


def recopilar_rigi(fecha_hoy: str, conn=None) -> list:
    """
    Proyectos RIGI nuevos o modificados desde la última corrida.
    Con `conn=None` devuelve todos, sin filtro incremental.
    """
    filas = _descargar_filas()
    if filas is None:
        return []

    proyectos = _proyectos_unicos(filas)
    logger.info(f"RIGI: {len(filas)} filas en la hoja -> {len(proyectos)} proyectos únicos.")

    if conn is None:
        logger.info("RIGI: sin conexión a la base, se mandan todos los proyectos.")
        return [_linea(p, fecha_hoy) for p in proyectos]

    try:
        vistos = _leer_vistos(conn)
    except Exception as e:
        # Tabla inexistente o error de lectura: degradamos a mandar todo.
        logger.warning(f"RIGI: no se pudo leer el registro de vistos ({e}). Se mandan todos.")
        conn.rollback()
        return [_linea(p, fecha_hoy) for p in proyectos]

    nuevos = [p for p in proyectos if vistos.get(p["clave"]) != _huella(p)]

    try:
        _marcar_vistos(conn, nuevos)
    except Exception as e:
        logger.warning(f"RIGI: no se pudo actualizar el registro de vistos ({e}).")
        conn.rollback()

    if not nuevos:
        logger.info(f"RIGI: sin novedades ({len(proyectos)} proyectos ya procesados).")
    else:
        logger.info(
            f"RIGI: {len(nuevos)} proyectos nuevos o modificados "
            f"(de {len(proyectos)}): {[p['empresa'] for p in nuevos]}"
        )
    return [_linea(p, fecha_hoy) for p in nuevos]


if __name__ == "__main__":
    from datetime import datetime
    logging.basicConfig(level=logging.INFO)
    hoy = datetime.now().strftime("%Y-%m-%d")
    proyectos = recopilar_rigi(hoy)  # sin conn: devuelve todos
    print(f"\n=== {len(proyectos)} proyectos RIGI ===\n")
    for p in proyectos:
        print(p[:220])
        print()
