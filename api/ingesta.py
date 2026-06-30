import logging
import unicodedata
from datetime import datetime
from scraper import scrapear_twitter
from fuentes_web import recopilar_fuentes_web
from fuentes_rigi import recopilar_rigi
from gemini import procesar_con_gemini
from embeddings import generar_embedding
from database import get_db_connection, es_duplicado, insertar_inversion
from telegram import enviar_inversion_a_telegram

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

ESTADOS_VALIDOS = {"confirmada", "anunciada", "en_evaluacion"}

# Nombres genéricos o no identificables que no deben publicarse en el campo "empresa".
# El sujeto de una inversión tiene que ser una empresa concreta, no un sector ni un placeholder.
_EMPRESAS_GENERICAS = {
    "empresa", "empresas", "empresa privada", "empresas privadas",
    "inversor privado", "inversores privados", "sector privado",
    "privado", "privados", "varios", "varias", "varias empresas",
    "no especificada", "no especificado", "sin especificar",
    "desconocida", "desconocido", "n/a", "na", "anonimo",
}


def _normalizar(texto: str) -> str:
    """Minúsculas sin tildes ni espacios sobrantes, para comparar nombres."""
    sin_tildes = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    return sin_tildes.strip().lower()


def _empresa_invalida(empresa) -> bool:
    """
    Red de seguridad determinística (complementa, no reemplaza, al prompt de Gemini).
    True si el nombre de empresa no sirve para publicar: vacío, genérico, o
    anómalamente largo (una lista de empresas o una descripción, no una marca).
    """
    if not empresa or not str(empresa).strip():
        return True
    texto = str(empresa)
    if _normalizar(texto) in _EMPRESAS_GENERICAS:
        return True
    if len(texto) > 90:   # un nombre tan largo es una lista o una descripción, no una marca
        return True
    return False


def validar_registro(registro):
    if not isinstance(registro, dict):
        return False

    if registro.get("estado") not in ESTADOS_VALIDOS:
        logger.warning(f"Registro descartado por estado inválido: {registro.get('estado')}")
        return False

    monto = registro.get("monto_usd")
    if isinstance(monto, bool):
        registro["monto_usd"] = None  # bool es subclase de int en Python
    elif monto is not None and not isinstance(monto, int):
        if isinstance(monto, float) and monto.is_integer():
            registro["monto_usd"] = int(monto)
        elif isinstance(monto, str) and monto.strip().isdigit():
            registro["monto_usd"] = int(monto.strip())
        else:
            logger.warning(f"monto_usd no normalizable, seteando None: {monto!r}")
            registro["monto_usd"] = None  # se conserva el registro, se anula solo el monto

    # Fecha: si no viene una fecha válida del anuncio, usamos la fecha de ejecución
    # del cron. Las fechas solo dan un orden cronológico aproximado (el cron corre
    # seguido), no son un dato informativo, así que evitamos fechas nulas en la base.
    fecha_str = registro.get("fecha_anuncio")
    fecha_valida = False
    if fecha_str:
        try:
            datetime.strptime(str(fecha_str), "%Y-%m-%d")
            fecha_valida = True
        except (ValueError, TypeError):
            logger.warning(f"Fecha inválida: {fecha_str!r}. Se usará la fecha de ejecución.")
    if not fecha_valida:
        registro["fecha_anuncio"] = datetime.now().strftime("%Y-%m-%d")

    if not registro.get("descripcion"):
        logger.warning("Registro descartado por falta de descripción.")
        return False

    if _empresa_invalida(registro.get("empresa")):
        logger.warning(f"Registro descartado por empresa inválida o genérica: {registro.get('empresa')!r}")
        return False

    return True

def run_ingesta():
    logger.info("Iniciando flujo de ingesta semanal...")

    logger.info("Scraping tweets via Apify (danek/twitter-scraper-ppr)...")
    tweets = scrapear_twitter()

    if not tweets:
        logger.warning("No se obtuvieron tweets de Apify. Se continúa con las fuentes web y la búsqueda de Gemini.")

    logger.info("Recopilando fuentes web (EconoJournal RSS)...")
    publicaciones_web = recopilar_fuentes_web()

    logger.info("Recopilando fuente oficial RIGI (proyectos aprobados)...")
    publicaciones_rigi = recopilar_rigi(datetime.now().strftime("%Y-%m-%d"))

    # Combinamos todas las fuentes y deduplicamos el batch antes de procesar,
    # para no enviar la misma línea repetida cuando varias fuentes coinciden.
    publicaciones = list(dict.fromkeys(
        (tweets or []) + (publicaciones_web or []) + (publicaciones_rigi or [])
    ))
    logger.info(
        f"Publicaciones combinadas: {len(publicaciones)} "
        f"({len(tweets or [])} de X, {len(publicaciones_web or [])} de web, "
        f"{len(publicaciones_rigi or [])} de RIGI)."
    )

    if not publicaciones:
        logger.warning("No se obtuvo material de ninguna fuente. Gemini buscará exclusivamente en Google.")

    logger.info("Procesando contenido con Gemini (interpreta y busca en Google)...")
    inversiones_crudo = procesar_con_gemini(publicaciones)

    if not inversiones_crudo:
        logger.warning("Gemini no devolvió resultados o hubo un error al parsear. Finalizando.")
        return

    logger.info(f"Gemini extrajo {len(inversiones_crudo)} posibles inversiones en formato JSON.")

    logger.info("Validando formato y consistencia de datos...")
    inversiones_validas = [r for r in inversiones_crudo if validar_registro(r)]
    logger.info(f"Quedan {len(inversiones_validas)} inversiones viables luego de validación.")

    if not inversiones_validas:
        return

    logger.info("Conectando a la Base de Datos Neon...")
    conn = get_db_connection()
    if not conn:
        logger.error("No se pudo conectar a la base de datos. Abortando inserción.")
        return

    nuevas_inserciones = 0
    duplicados = 0

    try:
        logger.info("Generando embeddings, desduplicando e insertando...")
        for inversion in inversiones_validas:
            texto = f"{inversion['empresa']} {inversion['descripcion']}"
            logger.info(f" -> Procesando: {inversion['empresa']}")

            embedding = generar_embedding(texto)

            if not embedding:
                logger.error(f"    Fallo al generar embedding para {inversion['empresa']}. Saltando.")
                continue

            es_dup = es_duplicado(embedding, conn)
            if not es_dup:
                logger.info("    No es duplicado. Insertando...")
                insertar_inversion(inversion, embedding, conn)
                enviar_inversion_a_telegram(inversion)
                nuevas_inserciones += 1
            else:
                logger.info("    Registro detectado como ya existente (duplicado por similitud). Omitiendo.")
                duplicados += 1
    finally:
        conn.close()

    logger.info("====================================")
    logger.info("Flujo de Ingesta semanal FINALIZADO.")
    logger.info(f"Nuevas inserciones: {nuevas_inserciones}")
    logger.info(f"Duplicados omitidos: {duplicados}")
    logger.info("====================================")

if __name__ == "__main__":
    run_ingesta()
