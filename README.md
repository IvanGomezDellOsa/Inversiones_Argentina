# Inversiones Argentina 🇦🇷

Agregador web automatizado que recopila y lista inversiones privadas realizadas o anunciadas en Argentina.

Este sistema está compuesto de tres partes principales:
1. **Scraping automatizado** (vía GitHub Actions y la API de Apify) para traer información de fuentes de Twitter.
2. **Post-procesamiento y almacenamiento** con IA (Google Gemini 2.5 Flash API + Grounding) para estructurar datos, generar embeddings, detectar inversiones únicas y guardarlas en **Neon PostgreSQL con pgvector**.
3. **Frontend Vercel + Backend FastAPI**, para exponer el JSON unificado de forma simple hacia un frontend construido en web moderna.

## Requisitos previos

* Python 3.11+
* Cuenta en **Neon** para PostgreSQL.
* Cuenta en **Apify** y token para usar el scraper lite de Twitter (`APIFY_API_TOKEN`).
* Cuenta en **Google AI Studio** para usar la API de **Gemini** (`GEMINI_API_KEY`).

## Estructura Local (Setup Inicial)

1. Renombrar el archivo `.env.example` a `.env` y rellenar las credenciales.
2. Instalar el entorno backend:
   ```bash
   cd backend
   pip install -r requirements.txt
   ```
3. Ejecutar inicialización de la tabla SQL (`schema.sql`) dentro de tu proyecto en Neon.

---

🏗️ *Proyecto en fase de construcción.*
