[Español](README.md) | [English](README.en.md)

# Inversiones en Argentina — Private Investment Aggregator for Argentina

🌐 **Production deploy:** [inversionesargentina.com.ar](https://inversionesargentina.com.ar)
📢 **Telegram channel:** [t.me/inversiones_en_argentina](https://t.me/inversiones_en_argentina)

Automated web aggregator that collects, structures and lists private investments made or announced in Argentina. It combines the official RIGI registry, scraping of specialised X accounts, RSS feeds from outlets across different sectors, and semantic search on Google via generative AI, exposing the data through a REST API to a frontend that renders an interactive timeline. Every 72 hours, newly detected investments are published automatically to both the website and the Telegram channel.

---

## 🏗️ System Architecture

```text
GitHub Actions (cron every 72h)
↓
┌─────────────────┬──────────────────────┬─────────────────────┐
│ Apify REST API  │ RSS from 6 outlets   │ Official RIGI sheet │
│ X: @zubel_ok    │ energy, agriculture, │ (Ministry of        │
│    @LuisCaputoAR│ business, general    │  Economy) incremental│
└─────────────────┴──────────────────────┴─────────────────────┘
↓
Relevance filter (deterministic, zero cost)
↓
Gemini 2.5 Flash + Google Search Grounding  →  JSON extraction
↓
Validation, normalisation and non-productive-operation filter
↓
Jev (TypeSafe AI) — optional: semantic noise filter
↓
Deduplication: pgvector retrieves candidates + identity/Jev decide
↓
Neon PostgreSQL
↓
Telegram Bot API (automatic channel publishing)
↓
FastAPI (Mangum) → Vercel Serverless
↓
Server-rendered Next.js (inversionesargentina.com.ar)
```

---

## 🛠️ Tech Stack

### Backend / Pipeline

| Layer | Technology |
|-------|------------|
| **Automation** | GitHub Actions (cron every 72h, 01:00 AM ARG) |
| **X scraping** | Apify REST API v2 (`danek/twitter-scraper`, configurable) |
| **Web sources** | RSS from EconoJournal, Bichos de Campo, Infocampo, Infobae Economía, El Cronista and Ámbito |
| **Official source** | Public Google Sheet from the RIGI portal (argentina.gob.ar) |
| **Generative AI** | Google Gemini 2.5 Flash with Google Search Grounding |
| **Semantic judgement** | Jev (TypeSafe AI) — optional, enabled by environment variable |
| **Embeddings** | `gemini-embedding-2-preview` (768 dimensions) |
| **Database** | Neon PostgreSQL with `pgvector` and `unaccent` extensions |
| **Notifications** | Telegram Bot API |
| **API** | Python, FastAPI (async), Mangum (serverless adapter) |
| **API deploy** | Vercel Serverless Functions |

### Frontend

| Layer | Technology |
|-------|------------|
| **Framework** | Next.js 16 (App Router, server rendering with ISR) |
| **Language** | TypeScript |
| **Styling** | Tailwind CSS v4 |
| **Animation** | Framer Motion |
| **UI components** | shadcn/ui + Radix UI |
| **Analytics** | Vercel Analytics |
| **Deploy** | Vercel |

---

## ⚙️ The 72-hour ingestion pipeline

**1. Multi-source collection**

- **X via Apify.** Pulls `@zubel_ok` (an investment-announcement curator) and `@LuisCaputoAR` (Ministry of Economy) using X's advanced search syntax, excluding replies and filtering to a 7-day window. It calls the **REST API directly rather than the SDK**: the SDK renamed an argument in a minor release and left the scraper broken for months without anything failing.
- **RSS from six outlets** across different sectors, paginated until the 7-day window is actually covered. A WordPress feed returns only 10 items — about 3 days — so without pagination the declared window was unreachable.
- **Official RIGI registry**, **incrementally**: a fingerprint of each project is stored and only new ones, or ones whose amount, jobs or description changed, are re-sent.

**2. Relevance filter**
Before spending a single Gemini token, a deterministic filter drops the structural noise in the feeds (daily price quotes, weather, sports). It favours recall: when in doubt it lets content through, because over-filtering means losing a real investment.

**3. Processing with Gemini + Grounding**
The prompt sends the collected material as SOURCE 1 and instructs Gemini to search Google for additional news from the period as SOURCE 2, explicitly targeting the sectors the owned sources cover poorly. It returns a JSON array with `empresa`, `descripcion`, `monto_usd`, `fecha_anuncio`, `estado`, `ubicacion` and `empleos`.

**4. Validation and non-investment filtering**
Beyond validating types, states and dates, a deterministic net rejects what is not a new productive investment: bond and note issuances, loans, company incorporations lifted from the Official Gazette (with capital denominated in pesos), share purchases and M&A, contracts won by suppliers, product or app launches, and aggregate portfolio figures. Suspiciously small amounts are nulled out: they are almost always pesos read as dollars.

**5. Semantic judgement with Jev (optional)**
When `TYPESAFE_API_KEY` is set, each record goes through a [Jev](https://typesafe.ai) Noul that returns a calibrated probability of it being a concrete private investment. Without the variable the pipeline runs exactly the same on its deterministic layers.

**6. Deduplication**
The embedding is used to **retrieve** the k nearest neighbours, not to decide. The decision is made, in order, by: near-identical text, Jev answering "are these the same project?", and three deterministic heuristics (same normalised company with very high similarity, same company with an identical amount, or a shared distinctive proper noun).

> **Why a similarity threshold isn't enough.** Measuring the real duplicates found in production, their cosine similarity ranged from 0.758 to 0.846 — and legitimately distinct projects live in that same band: Pampa's urea plant and Profertil's, Pluspetrol and Vista, Coral Energía and Edesur. A single embedding over such a thematically narrow corpus (Vaca Muerta, lithium, copper, RIGI) compresses the vector space until two different projects in the same sector look as alike as the same project reported twice. No threshold separates them; the actual question has to be asked.

**7. Insertion and publishing**
Unique records are persisted with their embedding and published to the Telegram channel at the same time.

**8. Status report**
Each run ends by printing the status of every source and exits non-zero if one that should be working returned nothing. A cron job that fails green is worse than one that fails red.

---

## 🎯 Features

**Interactive timeline**
- Cards sorted by `fecha_anuncio` descending with staggered animations (Framer Motion)
- Colour-coded status indicators: confirmed (green), announced (blue), under evaluation (yellow)
- Smart amount formatting: `USD 40M`, `USD 1.2B`, or the exact figure for smaller amounts
- Province and jobs badges when available
- The first page is server-rendered with ISR, so the content is indexable
- JSON-LD structured data (an `ItemList` of investment projects), `sitemap.xml` and `robots.txt`. Before, the crawler got an empty page and `/sitemap.xml` returned a 404

**Real-time search**
- Debounced input (300ms) querying the API with a `?q=` parameter
- Searches across `empresa`, `descripcion` **and** `ubicacion`, accent-insensitively: typing "Neuquen" finds investments in Neuquén
- Result counter and loading state with animated skeletons

**REST API**
- `GET /api/inversiones` — Paginated list ordered by date
- `GET /api/inversiones?q={query}` — Search by company, description or province
- Auto-generated documentation at `/api/docs`

---

## 🔧 Getting started

```bash
cp .env.example .env    # fill in credentials
pip install -r api/requirements.txt
npm install

python api/ingesta.py   # run the full pipeline once
npm run dev             # frontend on localhost:3000
```

Each module under `api/` runs standalone to diagnose a single source:

```bash
python api/scraper.py        # what X returns
python api/fuentes_web.py    # what the RSS feeds return
python api/fuentes_rigi.py   # what the official registry returns
python api/relevancia.py     # relevance-filter test
python api/jev.py            # Jev test (if configured)
```

---

## 📝 Development Notes

LLM-assisted development for component scaffolding, animation code and boilerplate. The decisions that actually define the product — the AI pipeline design, the deduplication strategy, the ingestion architecture, the prompt design with its exclusions, the choice of sources and thresholds, and the integration of Google Search Grounding as a second data source — were made and orchestrated by me.

---

## 👤 Author

**Iván Gómez Dell'Osa**

- Email: [ivangomezdellosa@gmail.com](mailto:ivangomezdellosa@gmail.com)
- LinkedIn: [linkedin.com/in/ivangomezdellosa](https://www.linkedin.com/in/ivangomezdellosa/)
- GitHub: [IvanGomezDellOsa](https://github.com/IvanGomezDellOsa)
