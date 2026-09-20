from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from mangum import Mangum

from .database import get_db_connection

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

COLUMNAS = "empresa, descripcion, monto_usd, fecha_anuncio, estado, ubicacion, empleos, created_at"
ORDEN = "ORDER BY fecha_anuncio DESC NULLS LAST, created_at DESC"

# Si la extensión unaccent está disponible, la búsqueda ignora tildes: escribir
# "Neuquen" encuentra "Neuquén". Se detecta una vez por contenedor y se cachea.
_unaccent_disponible = None


def _tiene_unaccent(conn) -> bool:
    global _unaccent_disponible
    if _unaccent_disponible is None:
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM pg_extension WHERE extname = 'unaccent'")
                _unaccent_disponible = cur.fetchone() is not None
        except Exception:
            conn.rollback()
            _unaccent_disponible = False
    return _unaccent_disponible


def _clausula_busqueda(conn):
    """
    WHERE de la búsqueda. Cubre empresa, descripción Y ubicación.

    La versión anterior solo miraba empresa y descripción: buscar "Neuquén"
    devolvía 6 resultados cuando había 19 inversiones en esa provincia, porque
    la provincia vive en su propia columna. Y sin unaccent, "Neuquen" sin tilde
    devolvía cero.
    """
    if _tiene_unaccent(conn):
        campo = "unaccent(empresa || ' ' || descripcion || ' ' || COALESCE(ubicacion, ''))"
        patron = "unaccent(%s)"
    else:
        campo = "(empresa || ' ' || descripcion || ' ' || COALESCE(ubicacion, ''))"
        patron = "%s"
    return f"WHERE {campo} ILIKE {patron}"


def _escapar_patron(q: str) -> str:
    """
    Escapa los comodines de ILIKE. Sin esto, buscar "%" devolvía las 143 filas
    y "_" hacía de comodín de un carácter.
    """
    limpio = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{limpio}%"


@app.get("/api/")
@app.get("/")
def home():
    return {"status": "ok", "message": "API de Inversiones Argentina activa"}


@app.get("/api/inversiones")
@app.get("/inversiones")
def get_inversiones(
    q: Optional[str] = Query(None, description="Búsqueda por empresa, descripción o provincia"),
    limit: int = Query(10, ge=1, le=100, description="Cantidad de resultados por página"),
    offset: int = Query(0, ge=0, description="Desplazamiento para paginación"),
):
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=503, detail="Fallo de conexión a la base de datos")

    try:
        with conn.cursor() as cursor:
            if q and q.strip():
                where = _clausula_busqueda(conn)
                patron = _escapar_patron(q.strip())

                cursor.execute(f"SELECT COUNT(*) FROM inversiones {where}", (patron,))
                total = cursor.fetchone()[0]

                cursor.execute(
                    f"SELECT {COLUMNAS} FROM inversiones {where} {ORDEN} LIMIT %s OFFSET %s",
                    (patron, limit, offset),
                )
            else:
                cursor.execute("SELECT COUNT(*) FROM inversiones")
                total = cursor.fetchone()[0]

                cursor.execute(
                    f"SELECT {COLUMNAS} FROM inversiones {ORDEN} LIMIT %s OFFSET %s",
                    (limit, offset),
                )

            columnas = [col.name for col in cursor.description]
            resultado = [dict(zip(columnas, row)) for row in cursor.fetchall()]

            return jsonable_encoder({
                "data": resultado,
                "total": total,
                "hasMore": (offset + limit) < total,
            })
    except Exception as e:
        # No se filtra el detalle del error al cliente: puede exponer el esquema.
        print(f"DB Error: {e}")
        raise HTTPException(status_code=500, detail="Error al consultar las inversiones")
    finally:
        conn.close()


@app.api_route("/{path_name:path}", methods=["GET"])
def catch_all(path_name: str):
    return {"error": "Ruta no encontrada", "path_received": path_name}


handler = Mangum(app, lifespan="off")
