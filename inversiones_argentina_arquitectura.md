# inversionesargentina.com.ar — Documento de Arquitectura y Plan de Implementación

---

## 1. Descripción del Proyecto

Agregador web que lista inversiones privadas realizadas o anunciadas en Argentina.  
Ejemplo de card: *"Sinteplast construye una nueva planta en Ezeiza. Inversión: u$s 12 millones."*

**Dominio:** inversionesargentina.com.ar  
**Repositorio:** https://github.com/IvanGomezDellOsa/Inversiones_Argentina  
**Estructura:** Monorepo con carpetas `/frontend` y `/backend`  
**Credenciales:** Exclusivamente en `.env` local, nunca commiteadas al repositorio

---

## 2. Stack Tecnológico

| Capa | Tecnología |
|---|---|
| Frontend | v0 (diseño) + Vercel (deploy) |
| Backend | Python |
| API | FastAPI |
| Base de datos | Neon PostgreSQL + pgvector |
| Ingesta LLM | Gemini API (Gemini 2.5 Flash) |
| Scraping tweets | Apify (apidojo/twitter-scraper-lite) |
| Scheduler | GitHub Actions (cron semanal) |
| Embeddings | text-embedding-004 (Google, 768 dims) |
| Contenedor | Docker |

---

## 3. Arquitectura General

```
GitHub Actions (cron semanal)
    │
    ├── 1. Scraper Python → Apify API (tweets filtrados)
    │
    ├── 2. Prompt ensamblado (tweets + fechas dinámicas)
    │
    ├── 3. Gemini API (Grounding with Google Search)
    │        └── devuelve array JSON estructurado
    │
    ├── 4. Validación y limpieza del JSON en Python
    │
    ├── 5. Generación de embedding (text-embedding-004)
    │
    ├── 6. Desduplicación semántica (pgvector, coseno > 0.85)
    │
    └── 7. Inserción en Neon PostgreSQL

Vercel (serverless, siempre activo)
    └── FastAPI GET /inversiones → lee Neon → sirve al frontend
```

---

## 4. Fuentes de Datos

### Fuente 1 — Apify (apidojo/twitter-scraper-lite)

Se extraerán tweets directamente de X (Twitter) utilizando la API de Apify.

Búsquedas a realizar:
1. `"Más inversión" from:zubel_ok`
2. `"MEGA INVERSIÓN EN ARGENTINA: " from:laderechadiario`

**Configuración Apify:**
- Se utilizará el actor `apidojo/twitter-scraper-lite`.
- Como `searchTerms` se pasará un array con las búsquedas mencionadas.
- Apify devolverá un dataset JSON que contendrá la fecha (`createdAt`) y el texto (`fullText`) de cada tweet.
- El script de Python descartará cualquier tweet mayor a 7 días.

**Formato de salida del scraper hacia Gemini:**
El texto de cada tweet se incluye con su fecha explícita en el prompt:

```text
[2026-03-30] Sinteplast anunció la construcción de una nueva planta en Ezeiza. Inversión: u$s 12 millones.
[2026-03-28] Phoenix Global: el director ejecutivo afirmó que la compañía invertirá en Vaca Muerta.
```

**Resiliencia:** Apify maneja su propia rotación de proxies y cuentas internamente esquivando los bloqueos oficiales de X sin depender de instancias endebles.

### Fuente 2 — Grounding with Google Search (Gemini API)

Gemini busca automáticamente en Google con el rango de fechas explícito que le pasamos en el prompt. No requiere scraping adicional.

---

## 5. Schema de Base de Datos

```sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE inversiones (
    id            SERIAL PRIMARY KEY,
    empresa       TEXT NOT NULL,
    descripcion   TEXT NOT NULL,
    monto_usd     BIGINT,
    fecha_anuncio DATE,
    estado        TEXT CHECK (estado IN ('confirmada', 'anunciada', 'en_evaluacion')),
    embedding     VECTOR(768),
    created_at    TIMESTAMPTZ DEFAULT NOW()
);
```

**Decisión clave:** el número de dimensiones (768) está fijado por el modelo `text-embedding-004`. No cambiar el modelo sin migrar la columna `embedding`.

**Nota sobre índices vectoriales:** no se crea índice en el MVP. Para menos de 10.000 registros, la búsqueda secuencial (fuerza bruta) de pgvector es suficientemente rápida. El índice `ivfflat` para volúmenes pequeños puede ser contraproducente y requiere mantenimiento (`REINDEX`). Cuando el volumen supere los 10.000 registros, agregar un índice `HNSW` que es superior a `ivfflat`:

```sql
-- Agregar solo cuando superes 10.000 registros
CREATE INDEX ON inversiones
USING hnsw (embedding vector_cosine_ops);
```

---

## 6. JSON Schema (output de Gemini)

```json
{
  "empresa": "nombre comercial de la empresa",
  "descripcion": "máximo 4 oraciones. Solo hechos concretos.",
  "monto_usd": 12000000,
  "fecha_anuncio": "2026-03-30",
  "estado": "confirmada"
}
```

**Reglas:**
- `monto_usd`: entero puro en dólares sin puntos ni comas, o `null`
- `fecha_anuncio`: formato `YYYY-MM-DD`, o `null`
- `estado`: exactamente uno de `"confirmada"`, `"anunciada"`, `"en_evaluacion"`
- `descripcion`: sin adjetivos valorativos, sin emojis, sin referencias numéricas como `[1]` o `[2]`

---

## 7. El Prompt

El prompt se ensambla dinámicamente en Python antes de cada ejecución.

### Versión con variables (código Python):

```python
from datetime import datetime, timedelta

fecha_hoy = datetime.today().strftime("%Y-%m-%d")
fecha_hace_7_dias = (datetime.today() - timedelta(days=7)).strftime("%Y-%m-%d")

prompt = f"""
Eres un extractor de datos económicos especializado en Argentina.

Tenés dos fuentes de datos:

FUENTE 1 — Tweets recientes de un curador de noticias de inversión en Argentina:
---
{tweets_scrapeados}
---

FUENTE 2 — Buscá en Google noticias publicadas entre el {fecha_hace_7_dias} y el {fecha_hoy} sobre inversiones privadas en Argentina. Excluye cualquier noticia publicada antes del {fecha_hace_7_dias}.

Procesá ambas fuentes y devuelve ÚNICAMENTE un array JSON válido, sin texto adicional, sin markdown, sin emojis.

Está terminantemente prohibido incluir referencias numéricas como [1], [2], [3] o cualquier número entre corchetes en cualquier parte del output.

Excluye:
- Inversiones directas del Estado nacional, provincial o municipal como principal inversor
- Empresas operadas exclusivamente por el Estado sin accionistas privados (ej. Correo Argentino, Trenes Argentinas, AYSA). Las empresas con capital mixto o que cotizan en bolsa (ej. YPF, Aerolíneas) sí deben incluirse si la inversión es una decisión corporativa
- Adquisiciones de empresas u oficinas en el exterior de parte de una matriz argentina
- Movimientos financieros internos como aumentos de capital
- Proyecciones sectoriales sin empresa ni inversión concreta asociada
- Convocatorias de empleo sin inversión asociada

Si la noticia menciona a un gobierno o ministerio anunciando una inversión de una empresa privada, la empresa privada es el sujeto de la inversión, no el gobierno.

Formato exacto:
[
  {{
    "empresa": "nombre comercial de la empresa",
    "descripcion": "máximo 4 oraciones. Solo hechos concretos de la noticia, sin adjetivos valorativos, sin emojis.",
    "monto_usd": número entero en dólares sin puntos ni comas, o null si no se menciona,
    "fecha_anuncio": "YYYY-MM-DD, o null si no se puede determinar",
    "estado": "confirmada" o "anunciada" o "en_evaluacion"
  }}
]

Ejemplos de descripcion correcta:

Inversión confirmada con monto:
"Construye una nueva planta industrial en Ezeiza con una inversión de u$s 12 millones. Prevé incorporar 400 empleados al plantel actual."

Inversión sin monto:
"Abre sus primeros 5 locales en Argentina luego de 23 años fuera del país. El primero estará ubicado en el barrio de Palermo."

Inversión en evaluación:
"Realizó site inspections en Esquel y evalúa inversiones vía franquicia. La cadena opera más de 7.500 hoteles en 40 países."
"""
```

### Configuración en AI Studio / API:

| Parámetro | Valor |
|---|---|
| Modelo | gemini-2.5-flash |
| Temperature | 1 |
| Thinking level | Minimal |
| Grounding with Google Search | Activado |
| URL Context | Desactivado |

---

## 8. Lógica de Desduplicación Semántica

Para evitar registrar la misma inversión encontrada en distintas semanas:

```python
UMBRAL_SIMILITUD = 0.85

def es_duplicado(nuevo_embedding, conn):
    cursor = conn.cursor()
    cursor.execute("""
        SELECT 1 - (embedding <=> %s::vector) AS similitud
        FROM inversiones
        ORDER BY similitud DESC
        LIMIT 1
    """, (nuevo_embedding,))
    resultado = cursor.fetchone()
    if resultado and resultado[0] >= UMBRAL_SIMILITUD:
        return True
    return False
```

Si `similitud coseno >= 0.85` → registro duplicado, se descarta.  
Si `similitud coseno < 0.85` → registro nuevo, se inserta.

**El texto que se embeddea** es la concatenación de `empresa + descripcion` para maximizar la precisión semántica.

---

## 9. Validación Post-Respuesta de Gemini

Antes de generar el embedding e insertar, Python valida cada registro:

```python
from datetime import datetime, timedelta

ESTADOS_VALIDOS = {"confirmada", "anunciada", "en_evaluacion"}

def validar_registro(registro):
    # Validar estado
    if registro.get("estado") not in ESTADOS_VALIDOS:
        return False

    # Validar monto_usd es entero o null
    monto = registro.get("monto_usd")
    if monto is not None and not isinstance(monto, int):
        return False

    # Validar fecha dentro de rango si existe
    fecha_str = registro.get("fecha_anuncio")
    if fecha_str:
        try:
            fecha = datetime.strptime(fecha_str, "%Y-%m-%d")
            limite = datetime.today() - timedelta(days=10)
            if fecha < limite:
                return False
        except ValueError:
            registro["fecha_anuncio"] = None

    return True
```

---

## 10. Flujo Completo del Script de Ingesta

```python
# ingesta.py

def run_ingesta():
    # 1. Scrapear X vía Apify
    tweets = scrapear_apify()  # devuelve lista de strings con fecha

    # 2. Ensamblar prompt
    prompt = construir_prompt(tweets)

    # 3. Llamar a Gemini API con Grounding
    response = llamar_gemini(prompt)

    # 4. Parsear JSON
    inversiones = json.loads(response)

    # 5. Validar cada registro
    inversiones_validas = [r for r in inversiones if validar_registro(r)]

    # 6. Para cada registro válido
    for inversion in inversiones_validas:

        # 7. Generar embedding
        texto = f"{inversion['empresa']} {inversion['descripcion']}"
        embedding = generar_embedding(texto)

        # 8. Chequear duplicado
        if not es_duplicado(embedding, conn):

            # 9. Insertar en base de datos
            insertar_inversion(inversion, embedding, conn)
```

---

## 11. API FastAPI

```python
# main.py

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
)

@app.get("/inversiones")
def get_inversiones():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT empresa, descripcion, monto_usd, fecha_anuncio, estado, created_at
        FROM inversiones
        ORDER BY created_at DESC
    """)
    rows = cursor.fetchall()
    return [dict(zip([col.name for col in cursor.description], row)) for row in rows]
```

---

## 12. Deploy

### GitHub Actions (scheduler de ingesta)

```yaml
# .github/workflows/ingesta.yml

name: Ingesta semanal

on:
  schedule:
    - cron: '0 10 * * 1'  # Todos los lunes a las 10:00 UTC
  workflow_dispatch:        # También permite ejecución manual

jobs:
  ingesta:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - name: Instalar dependencias
        run: pip install -r backend/requirements.txt
      - name: Ejecutar ingesta
        env:
          GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}
          DATABASE_URL: ${{ secrets.DATABASE_URL }}
        run: python backend/ingesta.py
```

### Vercel (API FastAPI)

Adaptador `mangum` para correr FastAPI en serverless:

```python
# handler.py
from mangum import Mangum
from main import app

handler = Mangum(app)
```

```json
// vercel.json
{
  "builds": [{ "src": "backend/handler.py", "use": "@vercel/python" }],
  "routes": [{ "src": "/(.*)", "dest": "backend/handler.py" }]
}
```

**Nota:** Vercel limita las funciones serverless de Python a 250MB de dependencias. Para este proyecto las dependencias son livianas (`fastapi`, `psycopg2`, `mangum`) y no deberían superar ese límite. Si en el deploy real se excede, el plan B es migrar la API a **Koyeb** o **Google Cloud Run**, ambos con soporte nativo para contenedores Docker Python y capa gratuita.

### Neon PostgreSQL

- Crear proyecto en neon.tech
- Habilitar extensión `pgvector`
- Guardar `DATABASE_URL` en secrets de GitHub y variables de entorno en Vercel

---

## 13. Variables de Entorno

```bash
# .env (nunca commitear)
GEMINI_API_KEY=tu_api_key
APIFY_API_TOKEN=tu_token_apify
DATABASE_URL=postgresql://user:password@host/dbname
```

Secrets a configurar en GitHub Actions:
- `GEMINI_API_KEY`
- `APIFY_API_TOKEN`
- `DATABASE_URL`

Variables de entorno a configurar en Vercel:
- `DATABASE_URL`

---

## 14. Estructura del Repositorio

```
Inversiones_Argentina/
├── frontend/
│   └── (proyecto v0 exportado)
├── backend/
│   ├── main.py          # FastAPI
│   ├── ingesta.py       # Script de ingesta completo
│   ├── scraper.py       # Scraping API de Apify (apidojo/twitter-scraper-lite)
│   ├── gemini.py        # Llamada a Gemini API
│   ├── embeddings.py    # Generación de embeddings
│   ├── database.py      # Conexión y queries a Neon
│   ├── handler.py       # Adaptador Mangum para Vercel
│   ├── requirements.txt
│   └── schema.sql       # Schema de la base de datos
├── .github/
│   └── workflows/
│       └── ingesta.yml
├── .env.example
├── .gitignore
└── README.md
```

---

## 15. Costos Estimados

| Servicio | Uso | Costo |
|---|---|---|
| Gemini 2.5 Flash (tokens) | ~104,000 tokens/año | $0 (free tier) |
| Apify API (Scraping) | 52 requests/año | $0 (free tier de $5/mes cubre sobrante) |
| Gemini Grounding | 52 requests/año | $0 (free tier: 500 RPD) |
| text-embedding-004 | ~52 requests/año | $0 (free tier) |
| Neon PostgreSQL | < 0.5 GB | $0 (free tier) |
| Vercel (API) | Bajo tráfico | $0 (free tier) |
| GitHub Actions | 52 ejecuciones/año | $0 (repo público) |
| **Total** | | **$0** |

---

## 16. Orden de Implementación

1. Crear repo y estructura de carpetas
2. Crear base de datos en Neon y ejecutar `schema.sql`
3. Implementar `scraper.py` (Apify Client)
4. Implementar `gemini.py` (llamada a API con Grounding)
5. Implementar `embeddings.py` (text-embedding-004)
6. Implementar `database.py` (conexión, insert, query dedup)
7. Ensamblar `ingesta.py` con el flujo completo
8. Testear ingesta localmente con `.env`
9. Implementar `main.py` (FastAPI)
10. Configurar `handler.py` + `vercel.json` y deployar API
11. Configurar secrets en GitHub y deployar workflow de ingesta
12. Diseñar frontend en v0 y conectar al endpoint de Vercel
13. Deployar frontend en Vercel
