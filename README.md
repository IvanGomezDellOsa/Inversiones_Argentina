```markdown
# InversionesArgentina — Agregador de Inversiones Privadas en Argentina

🌐 **Deploy en producción:** [inversionesargentina.com.ar](https://inversionesargentina.com.ar)

Agregador web automatizado que recopila, estructura y lista inversiones privadas realizadas o anunciadas en Argentina. El sistema combina scraping de fuentes especializadas en Twitter/X, búsqueda semántica en Google vía IA generativa y una API REST para exponer los datos a un frontend moderno en forma de cronología interactiva.

---

## 🏗️ Arquitectura del Sistema

```text
GitHub Actions (cron semanal)
↓
Apify API (scraper Twitter/X)
↓
Gemini 2.5 Flash + Google Search Grounding
↓
Validación y normalización de datos
↓
gemini-embedding-2-preview → pgvector (deduplicación semántica)
↓
Neon PostgreSQL
↓
FastAPI (Mangum) → Vercel Serverless
↓
Next.js Frontend (inversionesargentina.com.ar)
```

---

## 🛠️ Stack Tecnológico

### Backend / Pipeline

| Capa | Tecnología |
|------|------------|
| **Automatización** | GitHub Actions (cron semanal, lunes 07:00 AM ARG) |
| **Scraping** | Apify — `danek/twitter-scraper-ppr` |
| **IA Generativa** | Google Gemini 2.5 Flash con Google Search Grounding |
| **Embeddings** | `gemini-embedding-2-preview` (768 dimensiones) |
| **Base de datos** | Neon PostgreSQL con extensión `pgvector` |
| **API** | Python, FastAPI (async), Mangum (adaptador serverless) |
| **Deploy API** | Vercel Serverless Functions |

### Frontend

| Capa | Tecnología |
|------|------------|
| **Framework** | Next.js 16 (App Router) |
| **Lenguaje** | TypeScript |
| **Estilos** | Tailwind CSS v4 |
| **Animaciones** | Framer Motion |
| **Componentes UI** | shadcn/ui + Radix UI |
| **Analytics** | Vercel Analytics |
| **Deploy** | Vercel |

---

## ⚙️ Pipeline de Ingesta

El corazón del proyecto es un pipeline completamente automatizado que se ejecuta cada lunes:

**1. Scraping de Twitter/X via Apify**
Consulta múltiples queries sobre inversiones desde cuentas seleccionadas, filtra tweets de los últimos 7 días y deduplica por ID.

**2. Procesamiento con Gemini + Grounding**
El prompt envía los tweets scrapeados como FUENTE 1 e instruye a Gemini a buscar en Google noticias adicionales del período como FUENTE 2. El modelo devuelve un array JSON estructurado con campos `empresa`, `descripcion`, `monto_usd`, `fecha_anuncio`, `estado`, `ubicacion` y `empleos`.

Exclusiones explícitas: inversiones estatales puras, adquisiciones en el exterior, proyecciones sectoriales sin empresa concreta y movimientos financieros internos abstractos.

**3. Validación y normalización**
Cada registro pasa por validación de tipos, estados válidos (`confirmada` / `anunciada` / `en_evaluacion`), formato de fecha ISO y presencia de campos obligatorios.

**4. Deduplicación semántica con pgvector**
Se genera un embedding de 768 dimensiones combinando `empresa + descripcion`. Se calcula la distancia coseno contra todos los embeddings existentes. Si la similitud supera `0.85`, el registro se descarta como duplicado.

**5. Inserción en Neon PostgreSQL**
Los registros únicos se persisten con su embedding vectorial para futuras deduplicaciones.

---

## 🎯 Funcionalidades

**Cronología interactiva**
- Cards ordenadas por `fecha_anuncio` descendente con animaciones escalonadas (Framer Motion)
- Indicadores de estado con colores diferenciados: confirmada (verde), anunciada (azul), en evaluación (amarillo)
- Formato inteligente de montos: `USD 40M`, `USD 1.2B`, o monto exacto para cifras menores
- Badges de provincia y empleos cuando están disponibles

**Búsqueda en tiempo real**
- Input con debounce (300ms) que consulta la API con parámetro `?q=`
- Búsqueda ILIKE simultánea sobre `empresa` y `descripcion`
- Contador de resultados y estado de carga con skeletons animados

**API REST**
- `GET /api/inversiones` — Lista todas las inversiones ordenadas por fecha
- `GET /api/inversiones?q={query}` — Búsqueda por empresa o descripción
- Documentación automática en `/api/docs`

---

## 🔮 Próximas Implementaciones

**Chatbot de Telegram automatizado**
Integración con la API de Telegram Bot para envío automático de resúmenes semanales de nuevas inversiones detectadas. Cada vez que el pipeline de ingesta finalice con nuevas inserciones, el bot notificaría a un canal o grupo con un resumen estructurado de los anuncios de la semana.

---

## 📝 Notas de Desarrollo

- **Metodología:** Desarrollo asistido por LLMs para maquetación de componentes, escritura de animaciones y generación de código boilerplate. Las decisiones que definen realmente el producto —diseño del pipeline de IA, estrategia de deduplicación semántica con pgvector, arquitectura de la ingesta, diseño del prompt de Gemini con las exclusiones de inversiones estatales, elección de umbrales de similitud y la integración de Google Search Grounding como segunda fuente de datos— fueron tomadas y orquestadas por mí.
- **Resultado:** Sistema productivo en inversionesargentina.com.ar con pipeline de ingesta completamente automatizado y costo operativo mínimo.

---

## 👤 Autor

**Iván Gómez Dell'Osa**

- **GitHub:** IvanGomezDellOsa
- **Email:** ivangomezdellosa@gmail.com
- **LinkedIn:** ivangomezdellosa
```