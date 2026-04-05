import os
import logging
import psycopg2
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL").strip() if os.getenv("DATABASE_URL") else None
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
        # Serialización para pgvector
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
                INSERT INTO inversiones (empresa, descripcion, monto_usd, fecha_anuncio, estado, ubicacion, empleos, embedding)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s::vector)
            """, (
                inversion.get('empresa'),
                inversion.get('descripcion'),
                inversion.get('monto_usd'),
                inversion.get('fecha_anuncio'),
                inversion.get('estado'),
                inversion.get('ubicacion'),
                inversion.get('empleos'),
                vector_str
            ))
        conn.commit()
        logger.info(f"Insertada nueva inversión: {inversion.get('empresa')}")
    except Exception as e:
        logger.error(f"Error insertando inversión: {e}")
        conn.rollback()

def init_db(conn):
    # Inicialización de tablas y extensiones
    if not conn:
        return
    try:
        with conn.cursor() as cursor:
            cursor.execute("CREATE EXTENSION IF NOT EXISTS vector;")
            
            # Crear tabla base si no existe
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS inversiones (
                    id            SERIAL PRIMARY KEY,
                    empresa       TEXT NOT NULL,
                    descripcion   TEXT NOT NULL,
                    monto_usd     BIGINT,
                    fecha_anuncio DATE,
                    estado        TEXT NOT NULL
                                  CONSTRAINT chk_inversiones_estado
                                  CHECK (estado IN ('confirmada', 'anunciada', 'en_evaluacion')),
                    ubicacion     TEXT,
                    empleos       INTEGER,
                    embedding     VECTOR(768),
                    created_at    TIMESTAMPTZ DEFAULT NOW()
                );
            """)

            # Asegurar columnas (migración automática para tablas ya creadas)
            cursor.execute("ALTER TABLE inversiones ADD COLUMN IF NOT EXISTS ubicacion TEXT;")
            cursor.execute("ALTER TABLE inversiones ADD COLUMN IF NOT EXISTS empleos INTEGER;")
            
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_inversiones_created_at ON inversiones (created_at DESC);")
            
        conn.commit()
        logger.info("Base de datos inicializada correctamente")
    except Exception as e:
        logger.error(f"Error inicializando base de datos: {e}")
        conn.rollback()
