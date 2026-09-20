"""
Deduplicación de inversiones.

El embedding se usa para RECUPERAR candidatos, no para decidir. Un umbral de
similitud no sirve acá: sobre los datos de producción, los duplicados reales
caían entre 0.758 y 0.846, la misma banda donde hay proyectos distintos.

La decisión la toman, en orden: texto casi idéntico, Jev, y tres heurísticas
deterministas. Ante la duda se publica: un falso positivo es una inversión real
que se pierde en silencio, peor que un duplicado visible.
"""

import logging
import re
import unicodedata

import jev

logger = logging.getLogger(__name__)

# Cuántos vecinos se traen y desde qué similitud se los considera candidatos.
# 0.70 está bien por debajo del duplicado más lejano observado (0.758).
VECINOS_K = 5
UMBRAL_RECUPERACION = 0.70

# Texto prácticamente igual: es la misma fuente reenviando la misma fila.
UMBRAL_IDENTICO = 0.93

# Heurísticas para cuando Jev no está disponible.
UMBRAL_MISMA_EMPRESA = 0.88   # misma empresa + descripción muy parecida
UMBRAL_MISMO_PROYECTO = 0.75  # nombre propio distintivo compartido
UMBRAL_MISMO_MONTO = 0.78    # misma empresa y monto idéntico al dólar


# --- Normalización de nombres de empresa ---------------------------------------

# Sufijos societarios y de vehículo de proyecto. Sacarlos hace que "Sidersa",
# "Sidersa Acería" y "Sidersa Acería s.d.e." colapsen en la misma clave.
_SUFIJOS = re.compile(
    r"\b(s\.?a\.?u?\.?|s\.?r\.?l\.?|s\.?d\.?e\.?|sau|srl|sa|sociedad anonima|"
    r"sucursal dedicada|sucursal argentina|sucursal|dedicada|"
    r"inc|ltd|ltda|llc|plc|pty|corp|corporation|holdings?|group|grupo|"
    r"company|co|argentina|argentino|argentinos)\b",
    re.IGNORECASE,
)


def normalizar(texto) -> str:
    """Minúsculas, sin tildes, espacios normalizados."""
    if not texto:
        return ""
    sin_tildes = unicodedata.normalize("NFKD", str(texto)).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", sin_tildes).strip().lower()


def clave_identidad(empresa) -> str:
    """Nombre comercial normalizado, sin sufijos societarios ni puntuación."""
    base = normalizar(empresa)
    base = _SUFIJOS.sub(" ", base)
    base = re.sub(r"[^a-z0-9 ]+", " ", base)
    return re.sub(r"\s+", " ", base).strip()


# Vehículos societarios y socios de JV que ejecutan un proyecto a nombre de otra
# empresa. No se deducen del texto: "Fertil Pampa" es la subsidiaria 100% de
# Pampa Energía para la planta de urea, y ninguna descripción lo dice. Va en
# código porque es conocimiento estable del dominio, no un juicio.
_ALIAS_EMPRESAS = {
    "fertil pampa": "pampa energia",
    "vicuna": "vicuna",
    "bhp y lundin mining": "vicuna",
    "lundin mining": "vicuna",
    "bhp": "vicuna",
    "mcewen cooper": "andes corporacion minera",
    "mcewen mining": "andes corporacion minera",
    "minas argentinas": "minas argentinas",
    "tgs": "transportadora de gas del sur",
    "tgs sd1": "transportadora de gas del sur",
}


def _canonica(empresa) -> str:
    """Clave de identidad, resolviendo alias societarios conocidos."""
    clave = clave_identidad(empresa)
    return _ALIAS_EMPRESAS.get(clave, clave)


def misma_empresa(a, b) -> bool:
    """
    True si dos nombres designan a la misma empresa. Compara por contención de
    tokens y resuelve alias: "Sidersa" y "Sidersa Acería s.d.e." sí, igual que
    "Fertil Pampa" y "Pampa Energía"; "Profertil" y "Pampa Energía" no.
    """
    ka, kb = _canonica(a), _canonica(b)
    if not ka or not kb:
        return False
    if ka == kb:
        return True
    ta, tb = set(ka.split()), set(kb.split())
    return ta <= tb or tb <= ta


# --- Nombres propios distintivos -----------------------------------------------

# Términos que no distinguen un proyecto de otro: provincias y polos
# industriales (Bahía Blanca concentra decenas de proyectos distintos),
# vocabulario del rubro, y palabras corrientes que caen en mayúscula.
_NO_DISTINTIVOS = {
    # geografía y polos industriales
    "vaca", "muerta", "argentina", "argentino", "argentinas", "buenos", "aires",
    "neuquen", "rio", "negro", "san", "juan", "santa", "cruz", "salta", "bahia",
    "blanca", "catamarca", "mendoza", "cordoba", "jujuy", "chubut", "formosa",
    "entre", "rios", "corrientes", "pampa", "luis", "tierra", "fuego", "plata",
    "escobar", "rosario", "campana", "zarate", "pilar", "ezeiza",
    "patagonia", "cuyo", "puna", "golfo", "matias", "neuquina",
    # vocabulario del rubro
    "rigi", "regimen", "regimenes", "incentivo", "incentivos", "grandes",
    "inversion", "inversiones", "proyecto", "proyectos", "planta", "plantas",
    "empresa", "empresas", "compania", "sociedad", "nacional", "provincial",
    "gobierno", "ministerio", "legislatura", "millones", "dolares", "usd",
    "energia", "energy", "mining", "minera", "mineria", "petrolera", "petroleo",
    "gas", "litio", "cobre", "oro", "plata", "solar", "eolico", "eolica",
    "parque", "gasoducto", "oleoducto", "yacimiento", "refineria", "terminal",
    "capacidad", "produccion", "exportacion", "exportaciones", "toneladas",
    "barriles", "hidrocarburos", "combustibles", "fertilizantes", "acero",
    # palabras corrientes que caen en mayúscula por posición
    "contempla", "construccion", "construira", "consiste", "incluye", "permite",
    "permitira", "realizara", "desarrollo", "desarrollara", "ampliacion",
    "nueva", "nuevo", "nuevos", "nuevas", "primera", "primer", "segunda",
    "tambien", "ademas", "esta", "este", "esto", "estos", "para", "como",
    "norte", "sur", "oeste", "estima", "preve", "busca", "objetivo", "obras",
    "obra", "sector", "actualmente", "durante", "entre", "sobre", "segun",
}

# Separadores de oración: el primer token después de uno de estos va en
# mayúscula por ortografía, no por ser un nombre propio.
_FIN_ORACION = re.compile(r"(?:^|[.!?¡¿:;]\s*|\n)\s*")


def _nombres_propios(texto) -> set:
    """
    Tokens en mayúscula que identifican a un proyecto ("Gualcamayo", "Azules").
    Se descartan los que abren oración, que van en mayúscula por ortografía.
    """
    if not texto:
        return set()

    crudo = str(texto)
    # Posiciones donde empieza una oración: el token que arranca ahí no cuenta.
    inicios = {m.end() for m in _FIN_ORACION.finditer(crudo)}

    encontrados = set()
    for m in re.finditer(r"\b[A-ZÁÉÍÓÚÑ][\wÁÉÍÓÚÑáéíóúñ]{3,}\b", crudo):
        if m.start() in inicios:
            continue
        token = normalizar(m.group())
        if token and token not in _NO_DISTINTIVOS:
            encontrados.add(token)
    return encontrados


def _comparten_nombre_propio(a: dict, b: dict) -> set:
    """
    Nombres propios en común, sin contar los de la empresa: compartir empresa no
    dice nada sobre el proyecto (YPF tiene seis distintos).
    """
    propios_a = _nombres_propios(a.get("descripcion")) - set(clave_identidad(a.get("empresa")).split())
    propios_b = _nombres_propios(b.get("descripcion")) - set(clave_identidad(b.get("empresa")).split())
    return propios_a & propios_b


def _mismo_monto(a: dict, b: dict) -> bool:
    """
    Mismo monto exacto en dólares. Señal fuerte e independiente del texto: dos
    proyectos distintos de una misma empresa rara vez coinciden al dólar.
    """
    ma, mb = a.get("monto_usd"), b.get("monto_usd")
    if ma is None or mb is None:
        return False
    try:
        return int(ma) == int(mb)
    except (TypeError, ValueError):
        return False


# --- Recuperación de vecinos ---------------------------------------------------

def vecinos_similares(embedding, conn, k: int = VECINOS_K, umbral: float = UMBRAL_RECUPERACION):
    """Los k registros más parecidos por coseno, de mayor a menor similitud."""
    if not conn or not embedding:
        return []
    vector = f"[{','.join(map(str, embedding))}]"
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, empresa, descripcion, ubicacion, monto_usd,
                       1 - (embedding <=> %s::vector) AS similitud
                FROM inversiones
                WHERE embedding IS NOT NULL
                ORDER BY embedding <=> %s::vector
                LIMIT %s
                """,
                (vector, vector, k),
            )
            filas = cur.fetchall()
    except Exception as e:
        logger.error(f"Dedup: error consultando vecinos: {e}")
        conn.rollback()
        return []

    vecinos = []
    for id_, empresa, descripcion, ubicacion, monto, similitud in filas:
        sim = float(similitud) if similitud is not None else 0.0
        if sim < umbral:
            continue
        vecinos.append({
            "id": id_, "empresa": empresa, "descripcion": descripcion,
            "ubicacion": ubicacion, "monto_usd": monto, "similitud": sim,
        })
    return vecinos


# --- Decisión ------------------------------------------------------------------

def es_duplicado(inversion: dict, embedding, conn):
    """
    ¿Esta inversión ya está en la base?
    Devuelve (bool, motivo). `motivo` explica la decisión para el log.
    """
    vecinos = vecinos_similares(embedding, conn)
    if not vecinos:
        return False, "sin vecinos por encima del umbral de recuperación"

    def etiquetar(v):
        return f"id={v['id']} ({v['empresa']}) sim={v['similitud']:.3f}"

    # 1. Texto casi idéntico: la misma fuente reenviando la misma fila.
    for v in vecinos:
        if v["similitud"] >= UMBRAL_IDENTICO:
            return True, f"texto casi idéntico a {etiquetar(v)}"

    # 2. Jev, una sola llamada para todos los vecinos.
    if jev.disponible():
        match, p = jev.cual_es_el_mismo_proyecto(inversion, vecinos, mismo_grupo=misma_empresa)
        if match is not None:
            return True, f"Jev: mismo proyecto que {etiquetar(match)} (p={p:.2f})"
        if p is not None:
            return False, f"Jev descartó los {len(vecinos)} vecinos (máx p={p:.2f})"
        # p None = Jev no respondió; caemos a las heurísticas.

    # 3. Heurísticas deterministas.
    for v in vecinos:
        sim = v["similitud"]
        etiqueta = etiquetar(v)
        es_misma_empresa = misma_empresa(inversion.get("empresa"), v["empresa"])

        if es_misma_empresa and sim >= UMBRAL_MISMA_EMPRESA:
            return True, f"misma empresa y descripción muy similar a {etiqueta}"

        if es_misma_empresa and _mismo_monto(inversion, v) and sim >= UMBRAL_MISMO_MONTO:
            return True, f"misma empresa y mismo monto exacto que {etiqueta}"

        compartidos = _comparten_nombre_propio(inversion, v)
        if compartidos and sim >= UMBRAL_MISMO_PROYECTO:
            return True, f"comparte {sorted(compartidos)} con {etiqueta}"

        # Nada concluyente, pero lo bastante cerca como para querer mirarlo.
        if sim >= 0.80:
            logger.info(
                f"    Dedup: '{inversion.get('empresa')}' quedó cerca de {etiqueta} "
                f"pero se publica como nuevo (empresa distinta y sin nombre propio en común)."
            )

    return False, f"revisados {len(vecinos)} vecinos, ninguno es el mismo proyecto"
