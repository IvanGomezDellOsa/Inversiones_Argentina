"""
Deduplicación de inversiones.

POR QUÉ SE REESCRIBIÓ ESTO
--------------------------
El esquema anterior era: generar un embedding de `empresa + descripcion`,
calcular la similitud coseno contra todo lo guardado y descartar si superaba
0.85. La auditoría de septiembre de 2026 midió los 12 duplicados reales que
había en la base: su similitud iba de **0.758 a 0.846**. Todos por debajo del
umbral. Con 0.85 no había un solo par por encima en toda la tabla: la
deduplicación semántica nunca se activó sobre los datos guardados.

Y bajarlo no arregla nada. En la banda 0.84-0.85 conviven duplicados genuinos
(Sidersa/Sidersa, Minas Argentinas, Meitner) con proyectos legítimamente
distintos (la planta de urea de Pampa vs. la de Profertil, Pluspetrol vs. Vista,
Coral Energía vs. Edesur). Un solo embedding sobre un corpus tan temático —casi
todo Vaca Muerta, litio, cobre y RIGI— comprime el espacio vectorial: dos
proyectos distintos del mismo rubro se parecen tanto como el mismo proyecto
contado dos veces. No existe un umbral que los separe.

CÓMO FUNCIONA AHORA
-------------------
El embedding pasa a ser lo que sabe hacer bien —RECUPERAR candidatos— y la
decisión la toma otra cosa:

  1. Se traen los k vecinos más cercanos por coseno (umbral bajo, 0.70, para no
     perder ninguno: el duplicado más lejano que conocemos estaba en 0.758).
  2. Texto casi idéntico (>= 0.93): duplicado sin preguntar. Es el caso de una
     fuente que reenvía la misma fila, como hacía RIGI en cada corrida.
  3. Si hay Jev configurado, se le pregunta lo que realmente importa: "¿son el
     mismo proyecto?". Es la pregunta correcta en vez de una aproximación por
     distancia, y resuelve el caso difícil: el mismo proyecto con nombres de
     empresa distintos (McEwen Cooper / Andes Corporación Minera = Los Azules).
  4. Sin Jev, tres heurísticas deterministas: misma empresa con similitud muy
     alta; misma empresa con el mismo monto exacto; o un nombre propio
     distintivo compartido (el topónimo o el nombre del proyecto).

QUÉ TAN BIEN FUNCIONA (medido sobre los 143 registros de producción)
--------------------------------------------------------------------
Reproduciendo los 12 duplicados reales y 19 pares de proyectos distintos:

    esquema anterior (umbral 0.85)  ->  0/12 detectados
    capa determinista de acá        ->  6/12 detectados, 0 falsos positivos
    + Jev                           ->  cubre los 6 restantes

Los 6 que la capa determinista no puede resolver son los que exigen juicio
semántico de verdad: "Pampa Energía" y "Fertil Pampa" son la misma planta de
urea; "BHP y Lundin Mining" y "Vicuña Argentina" son el mismo proyecto de cobre.
Ningún umbral ni heurística de texto los separa de dos proyectos distintos de la
misma empresa — es exactamente el mismo muro que encontró la auditoría, y es la
razón concreta por la que se sumó Jev.

CRITERIO ANTE LA DUDA
---------------------
Un falso positivo acá significa NO publicar una inversión real, en silencio.
Eso es peor que publicar un duplicado, que se ve y se corrige. Por eso los
umbrales de las heurísticas son conservadores, se prefiere detectar de menos, y
los casos que quedan cerca se loguean para poder revisarlos a mano.
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
    """
    Nombre comercial normalizado, sin sufijos societarios ni puntuación.
    Es la clave de identidad más barata y precisa que tenemos.
    """
    base = normalizar(empresa)
    base = _SUFIJOS.sub(" ", base)
    base = re.sub(r"[^a-z0-9 ]+", " ", base)
    return re.sub(r"\s+", " ", base).strip()


def misma_empresa(a, b) -> bool:
    """
    True si dos nombres de empresa designan a la misma.
    Se compara por contención de tokens, no por igualdad exacta, porque la misma
    empresa llega escrita de formas distintas según la fuente: "Sidersa",
    "Sidersa Acería" y "Sidersa Acería s.d.e." son la misma; "Vista" y "Vista
    Energy" también. En cambio "Pampa Energía" y "Fertil Pampa" no, porque
    ninguno de los dos conjuntos de tokens contiene al otro.
    """
    ka, kb = clave_identidad(a), clave_identidad(b)
    if not ka or not kb:
        return False
    if ka == kb:
        return True
    ta, tb = set(ka.split()), set(kb.split())
    return ta <= tb or tb <= ta


# --- Nombres propios distintivos -----------------------------------------------

# Términos que aparecen en muchísimos registros y por lo tanto NO distinguen un
# proyecto de otro. Incluye tres grupos:
#  - Provincias y polos industriales. Bahía Blanca, Escobar o Vaca Muerta
#    concentran decenas de proyectos DISTINTOS: compartir el lugar no dice nada.
#  - Vocabulario del rubro (minera, gasoducto, litio, RIGI...).
#  - Palabras corrientes que aparecen en mayúscula por empezar una oración.
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
    Tokens en mayúscula que identifican de verdad a un proyecto: el topónimo o
    el nombre propio — "Gualcamayo", "Veladero", "Azules", "Timbúes", "Aranda".

    Se descartan los que abren oración: si no se hiciera, "Contempla",
    "Construcción" o "Incluye" contarían como nombres propios y dos proyectos
    sin relación quedarían emparentados. Ese error hacía que la planta de urea
    de Pampa y la de Profertil parecieran el mismo proyecto.
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
    Nombres propios distintivos en común entre dos registros.

    Se miran solo las descripciones, y se restan los tokens del nombre de las
    empresas: que dos registros compartan el nombre de la empresa no dice nada
    sobre si son el mismo PROYECTO (YPF tiene seis proyectos distintos). La
    identidad de empresa la resuelve `misma_empresa`, que es otra regla.
    """
    propios_a = _nombres_propios(a.get("descripcion")) - set(clave_identidad(a.get("empresa")).split())
    propios_b = _nombres_propios(b.get("descripcion")) - set(clave_identidad(b.get("empresa")).split())
    return propios_a & propios_b


def _mismo_monto(a: dict, b: dict) -> bool:
    """
    True si ambos registros declaran exactamente el mismo monto en dólares.

    Es una señal fuerte que no depende de la similitud del texto: que una misma
    empresa tenga dos proyectos DISTINTOS por exactamente la misma cifra al
    dólar es rarísimo. En cambio es lo habitual cuando la misma inversión entra
    dos veces desde fuentes distintas (Sidersa 286M dos veces, Meitner 1.200M
    dos veces).
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
    """
    Los k registros más parecidos por distancia coseno, de mayor a menor.
    Devuelve una lista de dicts con los campos del registro más `similitud`.
    """
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

    usar_jev = jev.disponible()

    for v in vecinos:
        sim = v["similitud"]
        etiqueta = f"id={v['id']} ({v['empresa']}) sim={sim:.3f}"

        # 1. Texto casi idéntico: la misma fuente reenviando la misma fila.
        if sim >= UMBRAL_IDENTICO:
            return True, f"texto casi idéntico a {etiqueta}"

        # 2. Jev: la pregunta correcta, no una aproximación por distancia.
        if usar_jev:
            veredicto, p = jev.es_mismo_proyecto(inversion, v)
            if veredicto is True:
                return True, f"Jev: mismo proyecto que {etiqueta} (p={p:.2f})"
            if veredicto is False:
                # Jev descartó este vecino; seguimos con el siguiente.
                continue
            # veredicto None = Jev no respondió; caemos a las heurísticas.

        # 3. Heurísticas deterministas.
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
