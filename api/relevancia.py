"""
Pre-filtro de relevancia para el material crudo de las fuentes.

Para qué existe: paginar los RSS y sumar medios llevó el volumen de ~10 notas
por corrida a 200+. La mayoría es ruido estructural (cotizaciones diarias,
clima, deportes, política) que infla el prompt de Gemini, lo hace más caro y
diluye la señal.

Criterio de diseño: este filtro prioriza RECALL sobre precisión. Dejar pasar una
nota irrelevante cuesta unos tokens; descartar un anuncio real significa perder
una inversión, que es exactamente el problema que la auditoría encontró. Ante la
duda, pasa. La precisión se resuelve después, sobre los registros ya extraídos
(ver `jev.py` y `validar_registro` en `ingesta.py`).

Es deterministico y gratis: sin llamadas a API.
"""

import re
import unicodedata


def _normalizar(texto: str) -> str:
    """Minúsculas sin tildes, para que 'inversión' e 'inversion' sean lo mismo."""
    sin_tildes = unicodedata.normalize("NFKD", str(texto)).encode("ascii", "ignore").decode("ascii")
    return sin_tildes.lower()


# Señales de que una nota puede estar hablando de una inversión concreta.
# Se buscan como subcadenas sobre el texto normalizado.
_SENALES = (
    # dinero y compromiso
    "invertir", "inversion", "invertira", "invierte", "invirtio", "desembolso",
    "millones de dolares", "millones de usd", "u$s", "us$", "usd", "millonaria",
    # obra física
    "nueva planta", "planta de", "fabrica", "refineria", "acería", "aceria",
    "construira", "construccion de", "ampliacion", "amplia su", "expansion",
    "obra", "gasoducto", "oleoducto", "parque solar", "parque eolico",
    "terminal", "mina", "yacimiento", "pozo", "data center", "centro de datos",
    # anuncio corporativo
    "rigi", "desembarca", "desembarco", "abrira", "inaugura", "inauguro",
    "radicacion", "puesta en marcha", "joint venture", "anuncio una inversion",
    "plan de inversion", "capex",
    # empleo asociado a inversión
    "puestos de trabajo", "empleos directos", "generara empleo",
)

# Ruido estructural: notas que se publican todos los días y nunca son inversiones.
# Si el título cae acá, se descarta aunque contenga alguna señal.
_RUIDO = (
    re.compile(r"\bprecio (del|de la|de los)\b"),
    re.compile(r"\bcotiza(cion|n|)\b.*\bhoy\b"),
    re.compile(r"\bdolar (blue|hoy|oficial)\b"),
    re.compile(r"\beuro blue\b"),
    re.compile(r"\bpizarra\b"),
    re.compile(r"\bpronostico\b|\bclima\b|\bheladas\b|\blluvias\b"),
    re.compile(r"\bhoroscopo\b|\bagenda deportiva\b|\bfutbol\b|\bmundial\b"),
    re.compile(r"\bque significa\b|\bpor que se celebra\b"),
)


def es_candidato_inversion(texto: str) -> bool:
    """
    True si el texto merece llegar al prompt de Gemini.

    Se usa sobre las líneas ya formateadas de las fuentes RSS. Las líneas de X y
    de RIGI NO pasan por acá: las cuentas de X ya vienen curadas o filtradas por
    query, y RIGI es un registro oficial donde todo es una inversión.
    """
    if not texto:
        return False

    norma = _normalizar(texto)

    for patron in _RUIDO:
        if patron.search(norma):
            return False

    return any(senal in norma for senal in _SENALES)


def filtrar_publicaciones(lineas, etiqueta_log=""):
    """
    Aplica el filtro a una lista de líneas. Devuelve (filtradas, descartadas).
    Se devuelve el conteo de descartes para poder loguearlo.
    """
    filtradas = [l for l in lineas if es_candidato_inversion(l)]
    return filtradas, len(lineas) - len(filtradas)


if __name__ == "__main__":
    pruebas = [
        ("[2026-09-20] (Infocampo) Precio del maíz en Rosario hoy 20 septiembre 2026.", False),
        ("[2026-09-20] (Infocampo) Dólar BLUE: a cuánto cotizan hoy.", False),
        ("[2026-09-18] (Bichos de Campo) Aseguran que con la nueva ley de biocombustibles se vienen inversiones por más de 1000 millones de dólares", True),
        ("[2026-09-18] (EconoJournal) Contreras hermanos se adjudicó el contrato de US$ 135 millones para construir accesos viales", True),
        ("[2026-09-19] (Bichos de Campo) Martín Romeo fue a Vietnam para ayudar a desarrollar la ganadería de cría", False),
        ("[2026-09-20] (@zubel_ok) Dolce & Gabbana construirá su primera torre de ultra lujo. Inversión: u$s 160 millones.", True),
        ("[2026-09-18] (Bichos de Campo) Una cosecha amenazada: las heladas siguen castigando a viñedos", False),
    ]
    ok = 0
    for texto, esperado in pruebas:
        r = es_candidato_inversion(texto)
        marca = "OK " if r == esperado else "MAL"
        ok += r == esperado
        print(f"  {marca} esperado={esperado!s:<5} obtuvo={r!s:<5} {texto[:88]}")
    print(f"\n{ok}/{len(pruebas)} correctos")
