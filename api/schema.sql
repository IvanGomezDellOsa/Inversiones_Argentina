-- Schema de base de datos para inversionesargentina.com.ar
-- Habilitar pgvector en Neon PostgreSQL antes de ejecutar.
-- init_db() en database.py aplica esto mismo de forma idempotente en cada ingesta.

CREATE EXTENSION IF NOT EXISTS vector;
-- unaccent permite que buscar "Neuquen" encuentre "Neuquén".
CREATE EXTENSION IF NOT EXISTS unaccent;

-- Tabla de inversiones con soporte para búsqueda vectorial
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

-- Proyectos RIGI ya procesados. La hoja oficial trae las mismas ~23 filas
-- siempre; sin este registro se reenviaban enteras a Gemini en cada corrida,
-- consumiendo ~75% del prompt para producir ~23 descartes por duplicado.
CREATE TABLE IF NOT EXISTS rigi_vistos (
    clave     TEXT PRIMARY KEY,   -- "empresa|nombre del proyecto"
    huella    TEXT NOT NULL,      -- hash del contenido; si cambia, se reprocesa
    visto_en  TIMESTAMPTZ DEFAULT NOW()
);

-- El listado ordena por fecha_anuncio; created_at es el desempate.
CREATE INDEX IF NOT EXISTS idx_inversiones_created_at
    ON inversiones (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_inversiones_fecha_anuncio
    ON inversiones (fecha_anuncio DESC NULLS LAST, created_at DESC);

-- La deduplicación trae los k vecinos más cercanos (ORDER BY embedding <=> ...).
-- Con pocos miles de filas el escaneo secuencial alcanza; pasado ese volumen,
-- descomentar el índice HNSW.
-- CREATE INDEX idx_inversiones_embedding ON inversiones
-- USING hnsw (embedding vector_cosine_ops);
