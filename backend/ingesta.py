import logging
from datetime import datetime
from scraper import scrapear_nitter
from gemini import procesar_con_gemini
from embeddings import generar_embedding
from database import get_db_connection, es_duplicado, insertar_inversion

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

ESTADOS_VALIDOS = {"confirmada", "anunciada", "en_evaluacion"}

def validar_registro(registro):
    if not isinstance(registro, dict):
        return False
        
    if registro.get("estado") not in ESTADOS_VALIDOS:
        logger.warning(f"Registro descartado por estado inválido: {registro.get('estado')}")
        return False

    monto = registro.get("monto_usd")
    if monto is not None and not isinstance(monto, int):
        logger.warning(f"Registro descartado por monto_usd inválido: {monto}")
        return False

    fecha_str = registro.get("fecha_anuncio")
    if fecha_str:
        try:
            datetime.strptime(fecha_str, "%Y-%m-%d")
        except ValueError:
            logger.warning(f"Fecha inválida, seteando a None: {fecha_str}")
            registro["fecha_anuncio"] = None
    
    if not registro.get("empresa") or not registro.get("descripcion"):
        logger.warning("Registro descartado por falta de empresa o descripción.")
        return False

    return True

def run_ingesta():
    logger.info("Iniciando pipeline de ingesta...")
    
    logger.info("Scraping a través de Nitter...")
    tweets = scrapear_nitter()
    
    if not tweets:
        logger.warning("No se obtuvieron tweets de Nitter. Continuando para que Gemini busque exclusivamente en Google.")
        
    logger.info("Procesando contenido con Gemini (interpreta y busca en Google)...")
    inversiones_crudo = procesar_con_gemini(tweets)
    
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
                nuevas_inserciones += 1
            else:
                logger.info("    Registro detectado como ya existente (duplicado por similitud). Omitiendo.")
                duplicados += 1
    finally:
        conn.close()
    
    logger.info("====================================")
    logger.info("Pipeline de Ingesta FINALIZADO.")
    logger.info(f"Nuevas inserciones: {nuevas_inserciones}")
    logger.info(f"Duplicados omitidos: {duplicados}")
    logger.info("====================================")

if __name__ == "__main__":
    run_ingesta()
