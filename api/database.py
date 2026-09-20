import logging
import os

import psycopg2
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL").strip() if os.getenv("DATABASE_URL") else None


def get_db_connection():
    if not DATABASE_URL:
        logger.error("Falta la variable de entorno DATABASE_URL")
        return None
    try:
        return psycopg2.connect(DATABASE_URL)
    except Exception as e:
        logger.error(f"Error conectando a la base de datos: {e}")
        return None


def insertar_inversion(inversion, embedding, conn):
    """Inserta una inversión y devuelve su id, o None si falló."""
    if not conn:
        return None
    try:
        vector_str = f"[{','.join(map(str, embedding))}]"
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO inversiones
                    (empresa, descripcion, monto_usd, fecha_anuncio, estado, ubicacion, empleos, embedding)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s::vector)
                RETURNING id
                """,
                (
                    inversion.get("empresa"),
                    inversion.get("descripcion"),
                    inversion.get("monto_usd"),
                    inversion.get("fecha_anuncio"),
                    inversion.get("estado"),
                    inversion.get("ubicacion"),
                    inversion.get("empleos"),
                    vector_str,
                ),
            )
            nuevo_id = cursor.fetchone()[0]
        conn.commit()
        logger.info(f"Insertada nueva inversión (id={nuevo_id}): {inversion.get('empresa')}")
        return nuevo_id
    except Exception as e:
        logger.error(f"Error insertando inversión: {e}")
        conn.rollback()
        return None


def init_db(conn):
    """
    Crea/actualiza el esquema. Idempotente. Corre desde la ingesta, no desde la
    API: el DDL en el primer request penalizaba la primera visita.
    """
    if not conn:
        return
    try:
        with conn.cursor() as cursor:
            cursor.execute("CREATE EXTENSION IF NOT EXISTS vector;")
            # unaccent permite buscar "Neuquen" y encontrar "Neuquén".
            try:
                cursor.execute("CREATE EXTENSION IF NOT EXISTS unaccent;")
            except Exception as e:
                # En algunos planes no se puede crear; la API cae a ILIKE común.
                logger.warning(f"No se pudo habilitar unaccent: {e}")
                conn.rollback()

            cursor.execute(
                """
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
                """
            )

            cursor.execute("ALTER TABLE inversiones ADD COLUMN IF NOT EXISTS ubicacion TEXT;")
            cursor.execute("ALTER TABLE inversiones ADD COLUMN IF NOT EXISTS empleos INTEGER;")

            # Proyectos RIGI ya procesados, para no reenviar la hoja entera.
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS rigi_vistos (
                    clave     TEXT PRIMARY KEY,
                    huella    TEXT NOT NULL,
                    visto_en  TIMESTAMPTZ DEFAULT NOW()
                );
                """
            )

            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_inversiones_created_at ON inversiones (created_at DESC);"
            )
            # El listado ordena por fecha_anuncio, no por created_at.
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_inversiones_fecha_anuncio "
                "ON inversiones (fecha_anuncio DESC NULLS LAST, created_at DESC);"
            )

        conn.commit()
        logger.info("Base de datos inicializada correctamente")
    except Exception as e:
        logger.error(f"Error inicializando base de datos: {e}")
        conn.rollback()
