from fastapi import FastAPI, HTTPException
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

@app.get("/")
def home():
    return {"status": "ok", "message": "API de Inversiones Argentina activa"}

@app.get("/inversiones")
def get_inversiones():
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=503, detail="Fallo de conexión a la base de datos")

    try:
        with conn.cursor() as cursor:
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
