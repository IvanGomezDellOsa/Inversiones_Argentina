[Español](README.md) | [English](README.en.md)

# Inversiones en Argentina — Private Investment Aggregator for Argentina

🌐 **Production deploy:** [inversionesargentina.com.ar](https://inversionesargentina.com.ar)
📢 **Telegram channel:** [t.me/inversiones_en_argentina](https://t.me/inversiones_en_argentina)

Automated web aggregator that collects, structures and lists private investments made or announced in Argentina. It combines the official RIGI registry, specialised X accounts, RSS feeds from outlets across different sectors, and Google search via generative AI, exposing the data through a REST API to a frontend that renders an interactive timeline. Every 72 hours, newly detected investments are published automatically to both the website and the Telegram channel.

---

## 🏗️ System Architecture

```text
GitHub Actions (cron every 72h)
↓
┌─────────────────┬──────────────────────┬─────────────────────┐
│ X accounts      │ RSS outlets          │ Official RIGI       │
│ (Apify REST)    │ energy, agriculture, │ registry —          │
│                 │ business, general    │ incremental         │
└─────────────────┴──────────────────────┴─────────────────────┘
↓
Relevance filter (deterministic, zero cost)
↓
Gemini 2.5 Flash + Google Search Grounding  →  JSON extraction
↓
Validation, normalisation and non-productive-operation filter
↓
Jev (TypeSafe AI) — optional: typed judgements with calibrated probability
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
| **Automation** | GitHub Actions (cron every 72h) |
| **X scraping** | Apify REST API v2 (actor configurable via environment) |
| **Web sources** | RSS feeds from economics, energy and agribusiness outlets |
| **Official source** | Public RIGI portal (argentina.gob.ar) |
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

## ⚙️ Ingestion pipeline, every 72h

**1. Multi-source collection**

- **Specialised X accounts**, through Apify's REST API, using advanced search syntax over a bounded time window.
- **RSS outlets** across different sectors, paginated until the full window is covered.
- **Official RIGI registry**, **incrementally**: a fingerprint of each project is stored and only new ones, or ones whose amount, jobs or description changed, are re-sent.

**2. Relevance filter**
Before spending a Gemini token, a deterministic filter discards the structural noise in the feeds. It favours recall: when in doubt it lets an item through, because over-filtering means losing a real investment.

**3. Extraction with Gemini + Grounding**
The collected material goes in as the first source and Gemini searches Google for additional news from the period as the second, explicitly focused on the sectors the owned sources cover least. It returns a JSON array with `empresa`, `descripcion`, `monto_usd`, `fecha_anuncio`, `estado`, `ubicacion` and `empleos`.

**4. Validation and filtering of what is not an investment**
Types, statuses and dates are validated and amounts normalised. A deterministic net discards whatever is not a new productive investment: bond and note issuance, loans, company incorporations, share purchases and M&A, contracts won by suppliers, product or service launches, and portfolio-wide figures.

**5. Semantic judgement with Jev (optional)**
When `TYPESAFE_API_KEY` is set, each record goes through [Jev](https://typesafe.ai), a model that returns typed decisions with calibrated probability instead of text, answering whether the record is a concrete private investment. Without the variable the pipeline runs exactly the same on its deterministic layers.

**6. Deduplication**
The embedding is used to **retrieve** the closest candidates, not to decide. The decision is made by identity rules and by Jev answering whether two records describe the same project.

> **Why similarity retrieves but does not decide.** Over a thematically narrow corpus the vector space compresses: two distinct projects in the same sector and region can look as alike as the same project reported twice by two outlets. No threshold separates those two cases, so similarity picks what to look at and project identity is resolved separately.

**7. Insertion, publishing and status report**
Unique records are persisted with their embedding and published to the Telegram channel at the same time. Each run ends by printing the status of every source and exits non-zero if one that should be responding returned nothing.

---

## 🎯 Features

**Interactive timeline**
- Cards sorted by `fecha_anuncio` descending with staggered animations (Framer Motion)
- Colour-coded status indicators: confirmed (green), announced (blue), under evaluation (yellow)
- Smart amount formatting: `USD 40M`, `USD 1.2B`, or the exact figure for smaller amounts
- Province and jobs badges when available
- The first page is server-rendered with ISR, so the content is indexable
- JSON-LD structured data (an `ItemList` of investment projects), `sitemap.xml` and `robots.txt`

**Real-time search**
- Debounced input (300ms) querying the API with a `?q=` parameter
- Searches across `empresa`, `descripcion` **and** `ubicacion`, accent-insensitively: typing "Neuquen" finds investments in Neuquén
- Result counter and loading state with animated skeletons

**REST API**
- `GET /api/inversiones` — Paginated list ordered by date
- `GET /api/inversiones?q={query}` — Search by company, description or province
- Auto-generated documentation at `/api/docs`

---

## 👤 Author

**Iván Gómez Dell'Osa**

- Email: [ivangomezdellosa@gmail.com](mailto:ivangomezdellosa@gmail.com)
- LinkedIn: [linkedin.com/in/ivangomezdellosa](https://www.linkedin.com/in/ivangomezdellosa/)
- GitHub: [IvanGomezDellOsa](https://github.com/IvanGomezDellOsa)
