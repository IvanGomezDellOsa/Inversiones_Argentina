# inversionesargentina.com.ar 🚧 (proyecto en curso)

Agregador web de inversiones privadas anunciadas o realizadas en Argentina.

**Estado:** en desarrollo activo. La arquitectura está definida, el backend en construcción.

---

## ¿Qué es esto?

Un sitio que centraliza anuncios de inversión privada en Argentina en un formato limpio y estandarizado. Ejemplo de lo que vas a encontrar:

> *Sinteplast construye una nueva planta industrial en Ezeiza. Inversión: u$s 12 millones. Prevé incorporar 400 empleados al plantel actual.*

Los datos se actualizan semanalmente de forma automática combinando dos fuentes: búsqueda en Google vía Gemini API y tweets de cuentas curadoras especializadas.

---

## Stack

| Capa | Tecnología |
|---|---|
| Frontend | v0 + Vercel |
| Backend | Python + FastAPI |
| Base de datos | Neon PostgreSQL + pgvector |
| Ingesta | Gemini API (Grounding with Google Search) |
| Scheduler | GitHub Actions (cron semanal) |
| Embeddings | text-embedding-004 (Google) |

---

## Estructura del repositorio

```
Inversiones_Argentina/
├── frontend/        # Proyecto v0 exportado
├── backend/         # Python: ingesta, API, embeddings
└── .github/
    └── workflows/   # GitHub Actions cron semanal
```

---

## Cómo funciona

1. Cada lunes, GitHub Actions dispara el script de ingesta.
2. El script scrapea tweets filtrados de Nitter y los combina con búsquedas en Google vía Gemini API.
3. Gemini devuelve un array JSON estructurado con los anuncios de inversión de la semana.
4. Cada registro se embeddea y se compara semánticamente contra la base de datos para evitar duplicados.
5. Los registros nuevos se insertan en Neon PostgreSQL.
6. El frontend consume la API REST y muestra las cards actualizadas.

---

## Costo operativo

$0. Todo corre en capas gratuitas de Gemini API, Neon, Vercel y GitHub Actions.

---

## Autor

**Iván Gómez Dell'Osa**

- Email: [ivangomezdellosa@gmail.com](mailto:ivangomezdellosa@gmail.com)
- LinkedIn: [linkedin.com/in/ivangomezdellosa](https://linkedin.com/in/ivangomezdellosa)
- GitHub: [IvanGomezDellOsa](https://github.com/IvanGomezDellOsa)
