[Español](README.md) | [English](README.en.md)

# Inversiones en Argentina — Agregador de Inversiones Privadas en Argentina

🌐 **Deploy en producción:** [inversionesargentina.com.ar](https://inversionesargentina.com.ar)
📢 **Canal de Telegram:** [t.me/inversiones_en_argentina](https://t.me/inversiones_en_argentina)

Agregador web automatizado que recopila, estructura y lista inversiones privadas realizadas o anunciadas en Argentina. El sistema combina el registro oficial RIGI, cuentas especializadas de X, feeds RSS de medios de distintos rubros y búsqueda en Google vía IA generativa, y expone los datos a través de una API REST hacia un frontend en forma de cronología interactiva. Cada 72 horas, las nuevas inversiones detectadas se publican automáticamente tanto en la web como en el canal de Telegram.

---

## 🏗️ Arquitectura del Sistema

```text
GitHub Actions (cron cada 72hs)
↓
┌─────────────────┬──────────────────────┬─────────────────────┐
│ Cuentas de X    │ Medios por RSS       │ Registro oficial    │
│ (Apify REST)    │ energía, agro,       │ RIGI — incremental  │
│                 │ negocios, general    │ (Min. de Economía)  │
└─────────────────┴──────────────────────┴─────────────────────┘
↓
Filtro de relevancia (determinista, sin costo)
↓
Gemini 2.5 Flash + Google Search Grounding  →  extracción a JSON
↓
Validación, normalización y filtro de operaciones no productivas
↓
Jev (TypeSafe AI) — opcional: juicio semántico con probabilidad calibrada
↓
Deduplicación: pgvector recupera candidatos + identidad/Jev deciden
↓
Neon PostgreSQL
↓
Telegram Bot API (publicación automática en canal)
↓
FastAPI (Mangum) → Vercel Serverless
↓
Next.js con render en servidor (inversionesargentina.com.ar)
```

---

## 🛠️ Stack Tecnológico

### Backend / Flujo

| Capa | Tecnología |
|------|------------|
| **Automatización** | GitHub Actions (cron cada 72hs) |
| **Scraping de X** | API REST v2 de Apify (actor configurable por entorno) |
| **Fuentes web** | Feeds RSS de medios de economía, energía y agroindustria |
| **Fuente oficial** | Portal público del RIGI (argentina.gob.ar) |
| **IA Generativa** | Google Gemini 2.5 Flash con Google Search Grounding |
| **Juicio semántico** | Jev (TypeSafe AI) — opcional, se activa por variable de entorno |
| **Embeddings** | `gemini-embedding-2-preview` (768 dimensiones) |
| **Base de datos** | Neon PostgreSQL con extensiones `pgvector` y `unaccent` |
| **Notificaciones** | Telegram Bot API |
| **API** | Python, FastAPI (async), Mangum (adaptador serverless) |
| **Deploy API** | Vercel Serverless Functions |

### Frontend

| Capa | Tecnología |
|------|------------|
| **Framework** | Next.js 16 (App Router, render en servidor con ISR) |
| **Lenguaje** | TypeScript |
| **Estilos** | Tailwind CSS v4 |
| **Animaciones** | Framer Motion |
| **Componentes UI** | shadcn/ui + Radix UI |
| **Analytics** | Vercel Analytics |
| **Deploy** | Vercel |

---

## ⚙️ Flujo de ingesta cada 72hs

**1. Recolección multi-fuente**

- **Cuentas especializadas de X**, vía la API REST de Apify, con sintaxis de búsqueda avanzada y ventana temporal acotada.
- **Medios por RSS** de rubros distintos, paginados hasta cubrir la ventana completa.
- **Registro oficial RIGI**, de forma **incremental**: se guarda una huella de cada proyecto y solo se reenvían los nuevos o los que cambiaron de monto, empleos o descripción.

**2. Filtro de relevancia**
Antes de gastar un token de Gemini, un filtro determinista descarta el ruido estructural de los feeds. Prioriza recall: ante la duda deja pasar, porque descartar de más significa perder una inversión real.

**3. Extracción con Gemini + Grounding**
El material recolectado entra como primera fuente y Gemini busca en Google noticias adicionales del período como segunda, con foco explícito en los rubros que las fuentes propias cubren poco. Devuelve un array JSON con `empresa`, `descripcion`, `monto_usd`, `fecha_anuncio`, `estado`, `ubicacion` y `empleos`.

**4. Validación y filtrado de lo que no es inversión**
Se validan tipos, estados y fechas, y se normalizan los montos. Una red determinista descarta lo que no es una inversión productiva nueva: emisiones de deuda y obligaciones negociables, préstamos, constituciones de sociedades, compraventa de acciones y M&A, contratos ganados por proveedores, lanzamientos de productos o servicios, y cifras agregadas de cartera.

**5. Juicio semántico con Jev (opcional)**
Si hay `TYPESAFE_API_KEY`, cada registro pasa por [Jev](https://typesafe.ai), un modelo que devuelve decisiones tipadas con probabilidad calibrada en lugar de texto, y que responde si se trata de una inversión privada concreta. Sin la variable, el pipeline funciona igual sobre sus capas deterministas.

**6. Deduplicación**
El embedding se usa para **recuperar** los candidatos más parecidos, no para decidir. La decisión la toman reglas de identidad y Jev respondiendo si dos registros describen el mismo proyecto.

> **Por qué la similitud recupera pero no decide.** Sobre un corpus temáticamente estrecho, el espacio vectorial se comprime: dos proyectos distintos del mismo rubro y la misma región pueden parecerse tanto como el mismo proyecto contado dos veces por dos medios. No hay un umbral que separe esos dos casos, así que la similitud selecciona a quién mirar y la identidad del proyecto se resuelve aparte.

**7. Publicación y parte de estado**
Los registros únicos se persisten con su embedding y se publican en simultáneo en el canal de Telegram. La corrida termina imprimiendo el estado de cada fuente y sale con código distinto de cero si alguna que debería responder no trajo nada.

---

## 🎯 Funcionalidades

**Cronología interactiva**
- Cards ordenadas por `fecha_anuncio` descendente con animaciones escalonadas (Framer Motion)
- Indicadores de estado con colores diferenciados: confirmada (verde), anunciada (azul), en evaluación (amarillo)
- Formato inteligente de montos: `USD 40M`, `USD 1.2B`, o monto exacto para cifras menores
- Badges de provincia y empleos cuando están disponibles
- La primera página se renderiza en el servidor con ISR, así que el contenido es indexable
- Datos estructurados JSON-LD (un `ItemList` de proyectos de inversión), `sitemap.xml` y `robots.txt`

**Búsqueda en tiempo real**
- Input con debounce (300ms) que consulta la API con parámetro `?q=`
- Busca sobre `empresa`, `descripcion` **y** `ubicacion`, ignorando tildes: escribir "Neuquen" encuentra las inversiones de Neuquén
- Contador de resultados y estado de carga con skeletons animados

**API REST**
- `GET /api/inversiones` — Lista paginada, ordenada por fecha
- `GET /api/inversiones?q={query}` — Búsqueda por empresa, descripción o provincia
- Documentación automática en `/api/docs`

---

## 👤 Autor

**Iván Gómez Dell'Osa**

- Email: [ivangomezdellosa@gmail.com](mailto:ivangomezdellosa@gmail.com)
- LinkedIn: [linkedin.com/in/ivangomezdellosa](https://www.linkedin.com/in/ivangomezdellosa/)
- GitHub: [IvanGomezDellOsa](https://github.com/IvanGomezDellOsa)
