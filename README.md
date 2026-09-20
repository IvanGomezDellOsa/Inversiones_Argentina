[Español](README.md) | [English](README.en.md)

# Inversiones en Argentina — Agregador de Inversiones Privadas en Argentina

🌐 **Deploy en producción:** [inversionesargentina.com.ar](https://inversionesargentina.com.ar)
📢 **Canal de Telegram:** [t.me/inversiones_en_argentina](https://t.me/inversiones_en_argentina)

Agregador web automatizado que recopila, estructura y lista inversiones privadas realizadas o anunciadas en Argentina. El sistema combina el registro oficial RIGI, scraping de cuentas especializadas en X, feeds RSS de medios de distintos rubros y búsqueda semántica en Google vía IA generativa, y expone los datos a través de una API REST hacia un frontend en forma de cronología interactiva. Cada 72 horas, las nuevas inversiones detectadas se publican automáticamente tanto en la web como en el canal de Telegram.

---

## 🏗️ Arquitectura del Sistema

```text
GitHub Actions (cron cada 72hs)
↓
┌─────────────────┬──────────────────────┬─────────────────────┐
│ Apify REST API  │ RSS de 6 medios      │ Hoja oficial RIGI   │
│ X: @zubel_ok    │ energía, agro,       │ (Min. de Economía)  │
│    @LuisCaputoAR│ negocios, general    │ incremental         │
└─────────────────┴──────────────────────┴─────────────────────┘
↓
Filtro de relevancia (determinista, sin costo)
↓
Gemini 2.5 Flash + Google Search Grounding  →  extracción a JSON
↓
Validación, normalización y filtro de operaciones no productivas
↓
Jev (TypeSafe AI) — opcional: filtro semántico de ruido
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
| **Automatización** | GitHub Actions (cron cada 72hs, 01:00 AM ARG) |
| **Scraping de X** | API REST v2 de Apify (`danek/twitter-scraper`, configurable) |
| **Fuentes web** | RSS de EconoJournal, Bichos de Campo, Infocampo, Infobae Economía, El Cronista y Ámbito |
| **Fuente oficial** | Google Sheets pública del portal RIGI (argentina.gob.ar) |
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

- **X vía Apify.** Se consumen `@zubel_ok` (curador de anuncios de inversión) y `@LuisCaputoAR` (Ministerio de Economía) con la sintaxis de búsqueda avanzada de X. Se excluyen respuestas y se filtra por ventana de 7 días. Se usa la **API REST directamente, no el SDK**: el SDK renombró un argumento en una versión menor y dejó el scraper roto durante meses sin que nada fallara.
- **RSS de seis medios** de rubros distintos, paginados hasta cubrir la ventana de 7 días. Un feed de WordPress devuelve solo 10 items —unos 3 días—, así que sin paginar la ventana declarada era inalcanzable.
- **Registro oficial RIGI**, de forma **incremental**: se guarda una huella de cada proyecto y solo se reenvían los nuevos o los que cambiaron de monto, empleos o descripción.

**2. Filtro de relevancia**
Antes de gastar un token de Gemini, un filtro determinista descarta el ruido estructural de los feeds (cotizaciones diarias, clima, deportes). Prioriza recall: ante la duda deja pasar, porque descartar de más significa perder una inversión.

**3. Procesamiento con Gemini + Grounding**
El prompt manda el material recolectado como FUENTE 1 e instruye a Gemini a buscar en Google noticias adicionales del período como FUENTE 2, con foco explícito en los rubros que las fuentes propias cubren poco. Devuelve un array JSON con `empresa`, `descripcion`, `monto_usd`, `fecha_anuncio`, `estado`, `ubicacion` y `empleos`.

**4. Validación y filtrado de lo que no es inversión**
Además de validar tipos, estados y fechas, hay una red determinista contra lo que no es una inversión productiva nueva: emisiones de deuda y obligaciones negociables, préstamos, constituciones de sociedades tomadas del Boletín Oficial (con capital en pesos), compraventa de acciones y M&A, contratos ganados por proveedores, lanzamientos de productos o apps, y cifras agregadas de cartera. Los montos sospechosamente bajos se anulan: casi siempre son pesos leídos como dólares.

**5. Juicio semántico con Jev (opcional)**
Si hay `TYPESAFE_API_KEY`, cada registro pasa por un Noul de [Jev](https://typesafe.ai) que responde con probabilidad calibrada si se trata de una inversión privada concreta. Sin la variable, el pipeline funciona igual con las capas deterministas.

**6. Deduplicación**
El embedding se usa para **recuperar** los k vecinos más cercanos, no para decidir. La decisión la toman, en orden: texto casi idéntico, Jev respondiendo "¿son el mismo proyecto?", y tres heurísticas deterministas (misma empresa normalizada con similitud muy alta, misma empresa con monto idéntico, o un nombre propio distintivo compartido).

> **Por qué no alcanza un umbral de similitud.** Midiendo los duplicados reales que había en producción, su similitud coseno iba de 0.758 a 0.846 — y en esa misma banda conviven proyectos legítimamente distintos: la planta de urea de Pampa y la de Profertil, Pluspetrol y Vista, Coral Energía y Edesur. Un solo embedding sobre un corpus tan temático (Vaca Muerta, litio, cobre, RIGI) comprime el espacio vectorial hasta que dos proyectos distintos del mismo rubro se parecen tanto como el mismo proyecto contado dos veces. No existe un umbral que los separe; hace falta responder la pregunta correcta.

**7. Inserción y publicación**
Los registros únicos se persisten con su embedding y se publican en simultáneo en el canal de Telegram.

**8. Parte de estado**
La corrida termina imprimiendo el estado de cada fuente y sale con código distinto de cero si alguna que debería andar no trajo nada. Un cron que falla en verde es peor que uno que falla en rojo.

---

## 🎯 Funcionalidades

**Cronología interactiva**
- Cards ordenadas por `fecha_anuncio` descendente con animaciones escalonadas (Framer Motion)
- Indicadores de estado con colores diferenciados: confirmada (verde), anunciada (azul), en evaluación (amarillo)
- Formato inteligente de montos: `USD 40M`, `USD 1.2B`, o monto exacto para cifras menores
- Badges de provincia y empleos cuando están disponibles
- La primera página se renderiza en el servidor con ISR, así que el contenido es indexable
- Datos estructurados JSON-LD (un `ItemList` de proyectos de inversión), `sitemap.xml` y `robots.txt`. Antes el crawler recibía una página vacía y `/sitemap.xml` devolvía 404

**Búsqueda en tiempo real**
- Input con debounce (300ms) que consulta la API con parámetro `?q=`
- Busca sobre `empresa`, `descripcion` **y** `ubicacion`, ignorando tildes: escribir "Neuquen" encuentra las inversiones de Neuquén
- Contador de resultados y estado de carga con skeletons animados

**API REST**
- `GET /api/inversiones` — Lista paginada, ordenada por fecha
- `GET /api/inversiones?q={query}` — Búsqueda por empresa, descripción o provincia
- Documentación automática en `/api/docs`

---

## 🔧 Puesta en marcha

```bash
cp .env.example .env    # completar credenciales
pip install -r api/requirements.txt
npm install

python api/ingesta.py   # corre el flujo completo una vez
npm run dev             # frontend en localhost:3000
```

Cada módulo de `api/` se puede correr solo para diagnosticar una fuente:

```bash
python api/scraper.py        # qué trae X
python api/fuentes_web.py    # qué traen los RSS
python api/fuentes_rigi.py   # qué trae el registro oficial
python api/relevancia.py     # test del filtro de relevancia
python api/jev.py            # test de Jev (si está configurado)
```

---

## 📝 Notas de Desarrollo

Desarrollo asistido por LLMs para maquetación de componentes, escritura de animaciones y generación de código boilerplate. Las decisiones que definen el producto —diseño del flujo de IA, estrategia de deduplicación, arquitectura de la ingesta, diseño del prompt con las exclusiones, elección de fuentes y de umbrales, y la integración de Google Search Grounding como segunda fuente— fueron tomadas y orquestadas por mí.

---

## 👤 Autor

**Iván Gómez Dell'Osa**

- Email: [ivangomezdellosa@gmail.com](mailto:ivangomezdellosa@gmail.com)
- LinkedIn: [linkedin.com/in/ivangomezdellosa](https://www.linkedin.com/in/ivangomezdellosa/)
- GitHub: [IvanGomezDellOsa](https://github.com/IvanGomezDellOsa)
