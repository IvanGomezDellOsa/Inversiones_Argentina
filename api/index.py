from fastapi import FastAPI, HTTPException, Query
from typing import Optional
from fastapi.middleware.cors import CORSMiddleware
from fastapi.encoders import jsonable_encoder
from database import get_db_connection

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

@app.get("/api/")
@app.get("/")
def home():
    return {"status": "ok", "message": "API de Inversiones Argentina activa"}

@app.get("/api/inversiones")
@app.get("/inversiones")
def get_inversiones(q: Optional[str] = Query(None, description="Búsqueda por empresa o descripción")):
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=503, detail="Fallo de conexión a la base de datos")

    try:
        with conn.cursor() as cursor:
            if q:
                # Búsqueda case-insensitive en empresa y descripción
                query = """
                    SELECT empresa, descripcion, monto_usd, fecha_anuncio, estado, created_at
                    FROM inversiones
                    WHERE empresa ILIKE %s OR descripcion ILIKE %s
                    ORDER BY created_at DESC
                """
                pattern = f"%{q}%"
                cursor.execute(query, (pattern, pattern))
            else:
                cursor.execute("""
                    SELECT empresa, descripcion, monto_usd, fecha_anuncio, estado, created_at
                    FROM inversiones
                    ORDER BY created_at DESC
                """)
            rows = cursor.fetchall()
            columnas = [col.name for col in cursor.description]
            resultado = [dict(zip(columnas, row)) for row in rows]
            return jsonable_encoder(resultado)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

@app.api_route("/{path_name:path}", methods=["GET"])
def catch_all(path_name: str):
    return {"error": "Ruta no encontrada by FastAPI", "path_received": path_name}
