"""
Limpieza puntual de los datos que encontró la auditoría de septiembre de 2026.

Es un script de UNA SOLA VEZ, no parte del pipeline. Corrige lo que ya está
publicado; que no vuelva a entrar es trabajo de `ingesta.py`, `dedup.py` y del
prompt de Gemini.

Qué hace:
  1. Guarda un backup JSON de la tabla completa antes de tocar nada.
  2. Borra 13 duplicados (el mismo proyecto cargado dos o tres veces).
  3. Borra 16 registros que no son inversiones productivas: constituciones de
     SRL con capital en pesos, emisiones de deuda, compras de acciones,
     lanzamientos de apps, contratos ganados por proveedores.
  4. Borra 2 cifras agregadas de cartera que distorsionaban el total. Una sola
     —la proyección de USD 154.000 millones de YPF— era el 42% del monto que
     mostraba el sitio.
  5. Completa montos oficiales del RIGI que faltaban o estaban mal.
  6. Siembra `rigi_vistos` con el estado actual de la hoja oficial, para que la
     primera corrida con la ingesta nueva no reprocese los 23 proyectos.

Uso:
    python api/limpieza_auditoria.py           # simulacro, no escribe nada
    python api/limpieza_auditoria.py --aplicar # ejecuta
"""

import json
import os
import sys
from datetime import datetime

import psycopg2
from dotenv import load_dotenv

load_dotenv()

# --- Duplicados: se borra el id, se conserva el que queda anotado al lado ------
DUPLICADOS = {
    78:  (121, "Sidersa — acería San Nicolás"),
    114: (121, "Sidersa — acería San Nicolás"),
    81:  (92,  "Los Azules (McEwen Cooper = Andes Corporación Minera)"),
    82:  (115, "Gualcamayo (Minas Argentinas)"),
    5:   (99,  "Veladero — ampliación fases 8 y 9"),
    70:  (96,  "Ampliación Tramo I del Gasoducto Perito Moreno (TGS)"),
    4:   (116, "Vicuña — cobre en San Juan"),
    80:  (116, "Vicuña (BHP y Lundin = Vicuña Argentina)"),
    42:  (146, "Planta de urea en Bahía Blanca (Pampa = Fertil Pampa)"),
    108: (146, "Planta de urea en Bahía Blanca"),
    137: (100, "Reactor SMR de Meitner en Atucha"),
    32:  (118, "Ampliación Compañía Mega"),
    49:  (14,  "GNL del Golfo San Matías (ratificación legislativa del mismo proyecto)"),
}

# --- No son inversiones productivas nuevas -------------------------------------
RUIDO = {
    9:   "constitución de SRL, capital en pesos",
    10:  "constitución de SRL, capital en pesos",
    11:  "constitución de SRL, capital en pesos",
    12:  "constitución de SA, capital en pesos",
    13:  "constitución de SRL, capital en pesos",
    69:  "gimnasio en una terminal de ómnibus, USD 140.000",
    71:  "compra de acciones de Transener (M&A secundario)",
    112: "alianza comercial BAIC–Puma, no hay inversión",
    119: "emisión de Obligaciones Negociables (AES)",
    127: "Huawei provee a la Provincia: es una venta, no su inversión",
    128: "Peter Thiel compra acciones de Vista en el mercado",
    131: "lanzamiento de una aplicación (Puma Flota)",
    132: "Continental compra el 50% de Phoenix (M&A)",
    144: "YPF coloca un bono de deuda",
    147: "Edesur toma un préstamo sindicado en pesos",
    149: "Contreras gana un contrato de obra; la inversión es de Vicuña",
}

# --- Cifras agregadas de cartera, no proyectos --------------------------------
AGREGADOS = {
    145: "proyección agregada de toda la cartera RIGI de YPF (USD 154.000 M)",
    125: "guidance de capex anual de YPF, no es un proyecto",
}

# --- Correcciones sobre registros que se conservan ----------------------------
# Los montos salen del registro oficial del RIGI (la misma hoja que consume la
# ingesta), que es la fuente de menor margen de error para estos proyectos.
CORRECCIONES = [
    (14,  {"monto_usd": 15_156_000_000, "ubicacion": "Río Negro"},
     "Southern Energy: el proyecto de licuefacción estaba sin monto; oficial USD 15.156 M"),
    (72,  {"monto_usd": 1_241_000_000},
     "Minera Exar (Cauchari Olaroz): estaba sin monto; oficial USD 1.241 M"),
    (118, {"monto_usd": 365_000_000},
     "Compañía Mega: figuraba USD 650 M; oficial USD 365 M"),
    (100, {"ubicacion": "Buenos Aires"},
     "Meitner: el reactor va en el predio de Atucha, provincia de Buenos Aires"),
]


def backup(cur, carpeta):
    cur.execute(
        "SELECT id, empresa, descripcion, monto_usd, fecha_anuncio, estado, "
        "ubicacion, empleos, created_at FROM inversiones ORDER BY id"
    )
    cols = [c.name for c in cur.description]
    filas = []
    for row in cur.fetchall():
        d = dict(zip(cols, row))
        d["fecha_anuncio"] = str(d["fecha_anuncio"]) if d["fecha_anuncio"] else None
        d["created_at"] = d["created_at"].isoformat() if d["created_at"] else None
        filas.append(d)

    os.makedirs(carpeta, exist_ok=True)
    ruta = os.path.join(carpeta, f"backup_inversiones_{datetime.now():%Y%m%d_%H%M%S}.json")
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(filas, f, ensure_ascii=False, indent=1)
    return ruta, filas


def main():
    aplicar = "--aplicar" in sys.argv
    url = os.getenv("DATABASE_URL")
    if not url:
        print("Falta DATABASE_URL")
        return 1

    conn = psycopg2.connect(url.strip())
    cur = conn.cursor()

    carpeta = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backups")
    ruta, filas = backup(cur, carpeta)
    por_id = {f["id"]: f for f in filas}
    print(f"Backup guardado en: {os.path.normpath(ruta)}")
    print(f"Filas actuales: {len(filas)}\n")

    def describir(ids, titulo, motivos):
        print("=" * 78)
        print(f"{titulo} ({len(ids)})")
        print("=" * 78)
        for i in sorted(ids):
            f = por_id.get(i)
            if not f:
                print(f"  id={i:<4} (ya no existe, se omite)")
                continue
            monto = f"USD {f['monto_usd']:,}" if f["monto_usd"] else "sin monto"
            extra = motivos[i][1] if isinstance(motivos[i], tuple) else motivos[i]
            conserva = f" -> se conserva id={motivos[i][0]}" if isinstance(motivos[i], tuple) else ""
            print(f"  id={i:<4} {f['empresa'][:30]:<32} {monto:>20}")
            print(f"        {extra}{conserva}")
        print()

    existentes = set(por_id)
    dup_ids = [i for i in DUPLICADOS if i in existentes]
    ruido_ids = [i for i in RUIDO if i in existentes]
    agreg_ids = [i for i in AGREGADOS if i in existentes]

    describir(dup_ids, "DUPLICADOS A BORRAR", DUPLICADOS)
    describir(ruido_ids, "NO SON INVERSIONES PRODUCTIVAS", RUIDO)
    describir(agreg_ids, "CIFRAS AGREGADAS DE CARTERA", AGREGADOS)

    print("=" * 78)
    print(f"CORRECCIONES DE MONTOS Y DATOS ({len(CORRECCIONES)})")
    print("=" * 78)
    for id_, campos, motivo in CORRECCIONES:
        f = por_id.get(id_)
        if not f:
            print(f"  id={id_} ya no existe, se omite")
            continue
        antes = {k: f.get(k) for k in campos}
        print(f"  id={id_:<4} {f['empresa'][:28]:<30} {antes}  ->  {campos}")
        print(f"        {motivo}")
    print()

    a_borrar = dup_ids + ruido_ids + agreg_ids
    total_antes = sum(f["monto_usd"] or 0 for f in filas)
    borrado = sum(por_id[i]["monto_usd"] or 0 for i in a_borrar)
    ajuste = sum(
        c.get("monto_usd", por_id[i]["monto_usd"] or 0) - (por_id[i]["monto_usd"] or 0)
        for i, c, _ in CORRECCIONES if i in por_id and "monto_usd" in c
    )
    print("=" * 78)
    print("RESUMEN")
    print("=" * 78)
    print(f"  Registros                 {len(filas)} -> {len(filas) - len(a_borrar)}   (-{len(a_borrar)})")
    print(f"  Monto publicado           USD {total_antes:,}")
    print(f"  Monto tras la limpieza    USD {total_antes - borrado + ajuste:,}")
    print()

    if not aplicar:
        print("SIMULACRO: no se escribió nada. Para ejecutar: python api/limpieza_auditoria.py --aplicar")
        conn.close()
        return 0

    for id_, campos, _ in CORRECCIONES:
        if id_ not in por_id:
            continue
        sets = ", ".join(f"{k} = %s" for k in campos)
        cur.execute(f"UPDATE inversiones SET {sets} WHERE id = %s", (*campos.values(), id_))

    if a_borrar:
        cur.execute("DELETE FROM inversiones WHERE id = ANY(%s)", (a_borrar,))

    conn.commit()
    cur.execute("SELECT COUNT(*), COALESCE(SUM(monto_usd), 0) FROM inversiones")
    n, suma = cur.fetchone()
    print(f"APLICADO. Quedan {n} registros por USD {suma:,}.")

    # Sembrar rigi_vistos para que la próxima ingesta no reprocese los 23 proyectos.
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    try:
        from database import init_db
        from fuentes_rigi import _descargar_filas, _huella, _marcar_vistos, _proyectos_unicos

        init_db(conn)
        filas_rigi = _descargar_filas()
        if filas_rigi:
            proyectos = _proyectos_unicos(filas_rigi)
            _marcar_vistos(conn, proyectos)
            print(f"rigi_vistos sembrada con {len(proyectos)} proyectos.")
        else:
            print("No se pudo leer la hoja RIGI; rigi_vistos queda vacía (la próxima ingesta la llena).")
    except Exception as e:
        print(f"No se pudo sembrar rigi_vistos: {e}")

    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
