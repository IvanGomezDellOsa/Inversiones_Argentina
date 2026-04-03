import os
import logging
import psycopg2
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")
UMBRAL_SIMILITUD = 0.85

def get_db_connection():
    if not DATABASE_URL:
        logger.error("Falta la variable de entorno DATABASE_URL")
        return None
    try:
        conn = psycopg2.connect(DATABASE_URL)
        return conn
    except Exception as e:
        logger.error(f"Error conectando a la base de datos: {e}")
        return None

def es_duplicado(nuevo_embedding, conn):
    if not conn:
        return False
    try:
        # pgvector requiere formato string [val1, val2, ...]
        vector_str = f"[{','.join(map(str, nuevo_embedding))}]"
        
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT 1 - (embedding <=> %s::vector) AS similitud
                FROM inversiones
                ORDER BY similitud DESC
                LIMIT 1
            """, (vector_str,))
            
            resultado = cursor.fetchone()
        
        if resultado is None:
            return False
        return resultado[0] >= UMBRAL_SIMILITUD
    except Exception as e:
        logger.error(f"Error comprobando duplicados: {e}")
        return False

def insertar_inversion(inversion, embedding, conn):
    if not conn:
        return
    try:
        vector_str = f"[{','.join(map(str, embedding))}]"
        
        with conn.cursor() as cursor:
            cursor.execute("""
                INSERT INTO inversiones (empresa, descripcion, monto_usd, fecha_anuncio, estado, embedding)
                VALUES (%s, %s, %s, %s, %s, %s::vector)
            """, (
                inversion.get('empresa'),
                inversion.get('descripcion'),
                inversion.get('monto_usd'),
                inversion.get('fecha_anuncio'),
                inversion.get('estado'),
                vector_str
            ))
        conn.commit()
        logger.info(f"Insertada nueva inversión: {inversion.get('empresa')}")
    except Exception as e:
        logger.error(f"Error insertando inversión: {e}")
        conn.rollback()
