from fastapi import FastAPI, HTTPException, Query
from typing import Optional
from fastapi.middleware.cors import CORSMiddleware
from fastapi.encoders import jsonable_encoder
from mangum import Mangum
from .database import get_db_connection, init_db

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

_db_initialized = False

@app.get("/api/")
@app.get("/")
def home():
    return {"status": "ok", "message": "API de Inversiones Argentina activa"}

@app.get("/api/inversiones")
@app.get("/inversiones")
def get_inversiones(
    q: Optional[str] = Query(None, description="Búsqueda por empresa o descripción"),
    limit: int = Query(10, ge=1, le=100, description="Cantidad de resultados por página"),
    offset: int = Query(0, ge=0, description="Desplazamiento para paginación"),
):
    global _db_initialized
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=503, detail="Fallo de conexión a la base de datos")

    # Inicialización de BD en primer acceso
    if not _db_initialized:
        init_db(conn)
        _db_initialized = True

    try:
        with conn.cursor() as cursor:
            if q:
                pattern = f"%{q}%"
                where_clause = "WHERE empresa ILIKE %s OR descripcion ILIKE %s"
                
                # Contar total de resultados
                cursor.execute(f"SELECT COUNT(*) FROM inversiones {where_clause}", (pattern, pattern))
                total = cursor.fetchone()[0]
                
                # Obtener página
                query = f"""
                    SELECT empresa, descripcion, monto_usd, fecha_anuncio, estado, ubicacion, empleos, created_at
                    FROM inversiones
                    {where_clause}
                    ORDER BY fecha_anuncio DESC NULLS LAST, created_at DESC
                    LIMIT %s OFFSET %s
                """
                cursor.execute(query, (pattern, pattern, limit, offset))
            else:
                # Contar total
                cursor.execute("SELECT COUNT(*) FROM inversiones")
                total = cursor.fetchone()[0]
                
                cursor.execute("""
                    SELECT empresa, descripcion, monto_usd, fecha_anuncio, estado, ubicacion, empleos, created_at
                    FROM inversiones
                    ORDER BY fecha_anuncio DESC NULLS LAST, created_at DESC
                    LIMIT %s OFFSET %s
                """, (limit, offset))
            
            rows = cursor.fetchall()
            columnas = [col.name for col in cursor.description]
            resultado = [dict(zip(columnas, row)) for row in rows]
            
            return jsonable_encoder({
                "data": resultado,
                "total": total,
                "hasMore": (offset + limit) < total,
            })
    except Exception as e:
        error_msg = f"DB Error: {str(e)}"
        print(error_msg)
        raise HTTPException(status_code=500, detail=error_msg)
    finally:
        conn.close()

@app.api_route("/{path_name:path}", methods=["GET"])
def catch_all(path_name: str):
    return {"error": "Ruta no encontrada", "path_received": path_name}

handler = Mangum(app, lifespan="off")
