-- Schema de base de datos para inversionesargentina.com.ar
-- Habilitar pgvector en Neon PostgreSQL antes de ejecutar

CREATE EXTENSION IF NOT EXISTS vector;

-- Tabla de inversiones con soporte para búsqueda vectorial
CREATE TABLE inversiones (
    id            SERIAL PRIMARY KEY,
    empresa       TEXT NOT NULL,
    descripcion   TEXT NOT NULL,
    monto_usd     BIGINT,
    fecha_anuncio DATE,
    estado        TEXT NOT NULL
                  CONSTRAINT chk_inversiones_estado
                  CHECK (estado IN ('confirmada', 'anunciada', 'en_evaluacion')),
    embedding     VECTOR(768),
    created_at    TIMESTAMPTZ DEFAULT NOW()
);

-- Índice para optimizar consultas de listado por fecha desc
CREATE INDEX idx_inversiones_created_at ON inversiones (created_at DESC);

-- Búsqueda secuencial de pgvector suficiente para <10.000 registros
-- Agregar índice HNSW si el volumen supera ese umbral
-- CREATE INDEX idx_inversiones_embedding ON inversiones
-- USING hnsw (embedding vector_cosine_ops);
