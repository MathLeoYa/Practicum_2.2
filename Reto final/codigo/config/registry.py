"""
config/registry.py
==================
REGISTRO CENTRAL DE FUENTES — único archivo que se edita al agregar una fuente nueva.

Para añadir un nuevo Excel/CSV al pipeline:
  1. Agregar la ruta en config/settings.py → FUENTES
  2. Escribir la función ETL en el módulo transform/ correspondiente
  3. Registrar la fuente en SOURCE_REGISTRY aquí abajo (UN solo bloque)

Nada más. pipeline.py, watchdog y --status se actualizan solos.
"""

# Importaciones diferidas para evitar dependencias circulares al importar registry
# Las funciones se resuelven en tiempo de ejecución (lazy imports)
_REGISTRY: list[dict] = []


def register(
    key: str,
    *,
    label: str,
    module: str,
    fn: str,
    keywords: list[str],
    table: str,
    description: str = "",
):
    """
    Registra una fuente de datos en el pipeline.

    Parámetros
    ----------
    key         : Identificador único de la fuente (igual al key en FUENTES)
    label       : Nombre legible para logs y --status
    module      : Módulo transform donde vive la función, ej: "transform.bce"
    fn          : Nombre de la función ETL, ej: "load_pib_percapita"
    keywords    : Lista de palabras clave para el watchdog RPA
    table       : Tabla Silver principal que carga (para --status)
    description : Descripción breve (opcional)
    """
    _REGISTRY.append({
        "key":         key,
        "label":       label,
        "module":      module,
        "fn":          fn,
        "keywords":    [k.lower() for k in keywords],
        "table":       table,
        "description": description,
    })


# =============================================================================
# BLOQUE 1 — Banco Central del Ecuador
# =============================================================================

register(
    "pib_percapita",
    label="PIB per cápita nominal",
    module="transform.bce",
    fn="load_pib_percapita",
    keywords=["pib", "percapita", "nominal"],
    table="fact_macro_anual",
    description="PIB per cápita nominal anual (2000-2025) — BCE",
)

register(
    "vab_nacional",
    label="PIB real + VAB nacional",
    module="transform.bce",
    fn="load_pib_real",
    keywords=["pib_real", "retropolacion", "retropolación"],
    table="fact_macro_anual",
    description="PIB real y VAB sectorial nacional (retropolación 1965-2024) — BCE",
)

register(
    "vab_nacional_sectores",
    label="VAB nacional por sectores",
    module="transform.bce",
    fn="load_vab_nacional",
    keywords=["retropolacion", "retropolación", "vab", "vab_nacional"],
    table="fact_vab_nacional",
    description="VAB sectorial nacional (real y nominal) — BCE",
)

register(
    "wti",
    label="Petróleo WTI + Riesgo País",
    module="transform.bce",
    fn="load_indicadores_diarios",
    keywords=["wti", "petroleo", "petróleo", "riesgo", "pais"],
    table="fact_indicadores_diarios",
    description="Precio WTI diario y Riesgo País en puntos básicos — BCE",
)

register(
    "iee",
    label="IEE Nueva Metodología",
    module="transform.bce",
    fn="load_iee",
    keywords=["iee", "expectativa", "empresarial"],
    table="fact_iee_mensual",
    description="Índice de Expectativas Empresariales mensual por sector (2010-) — BCE",
)

register(
    "vab_provincial",
    label="VAB Provincial (CNR 2007-2018)",
    module="transform.bce",
    fn="load_vab_provincial",
    keywords=["vab", "provincial", "cnr", "retro_cnr"],
    table="fact_vab_provincial",
    description="Valor Agregado Bruto por provincia y sector CIIU (2007-2018) — BCE",
)

# =============================================================================
# BLOQUE 2 — INEC
# =============================================================================

register(
    "enemdu",
    label="ENEMDU — Mercado Laboral",
    module="transform.inec",
    fn="load_enemdu",
    keywords=["enemdu", "mercado_laboral", "tabulados", "trimestre"],
    table="fact_empleo",
    description="Tasas de empleo, desempleo y subempleo trimestral (ENEMDU) — INEC",
)

register(
    "censo_trabajo",
    label="Censo 2022 — Actividad Laboral",
    module="transform.inec",
    fn="load_censo",
    keywords=["cpv", "censo", "trabajo"],
    table="fact_censo_actividad",
    description="Condición de actividad/ocupación por provincia del Censo 2022 — INEC",
)

# =============================================================================
# BLOQUE 3 — Supercias y MINEDUC
# =============================================================================

register(
    "bi_compania",
    label="Supercias — Catálogo Empresas",
    module="transform.supercias",
    fn="load_dim_empresa",
    keywords=["bi_compania", "compan"],
    table="dim_empresa",
    description="Catálogo maestro de 337K empresas registradas — Supercias",
)

register(
    "bi_ranking",
    label="Supercias — Ranking Financiero",
    module="transform.supercias",
    fn="load_ranking",
    keywords=["bi_ranking", "ranking"],
    table="fact_empresa_ranking",
    description="Indicadores financieros anuales por empresa (2008-2025) — Supercias",
)

register(
    "directorio",
    label="Supercias — Directorio de Empresas",
    module="transform.supercias",
    fn="load_directorio",
    keywords=["directorio", "directo"],
    table="fact_directorio_empresas",
    description="Directorio de empresas activas con geolocalización (222K filas) — Supercias",
)

register(
    "mineduc",
    label="MINEDUC — AMIE 2023-2024",
    module="transform.mineduc",
    fn="load_bachilleres",
    keywords=["amie", "mineduc", "registro", "administrativo"],
    table="fact_bachilleres",
    description="Registros administrativos AMIE: instituciones y estudiantes por nivel — MINEDUC",
)

# =============================================================================
# ── Para agregar una nueva fuente, agrega un bloque register() aquí arriba ──
#
# Ejemplo de nueva fuente (comentado):
#
# register(
#     "sri_catastro",
#     label="SRI — Catastro de Contribuyentes 2025",
#     module="transform.sri",         # crea transform/sri.py con load_catastro()
#     fn="load_catastro",
#     keywords=["sri", "catastro", "contribuyente"],
#     table="fact_sri_catastro",      # define la tabla en db/create_tables.sql
#     description="Catastro de contribuyentes activos por provincia — SRI",
# )
#
# =============================================================================


# =============================================================================
# API pública del registry (usada por pipeline.py)
# =============================================================================

def get_all() -> list[dict]:
    """Retorna todas las fuentes registradas."""
    return list(_REGISTRY)


def get_by_key(key: str) -> dict | None:
    """Busca un entry por key exacto."""
    return next((e for e in _REGISTRY if e["key"] == key), None)


def find_by_filename(filename: str) -> dict | None:
    """
    Busca el handler que corresponde a un nombre de archivo del RPA.
    Retorna el primer registro cuyas keywords aparezcan en el nombre.
    """
    fname_lower = filename.lower()
    for entry in _REGISTRY:
        if any(kw in fname_lower for kw in entry["keywords"]):
            return entry
    return None


def resolve_fn(entry: dict):
    """
    Importa dinámicamente el módulo y retorna la función ETL.
    Lazy import: los módulos transform solo se cargan cuando se necesitan.
    """
    import importlib
    module = importlib.import_module(entry["module"])
    return getattr(module, entry["fn"])


def get_all_tables() -> list[str]:
    """Lista de tablas Silver únicas registradas (para --status)."""
    seen = set()
    tables = []
    # Dimensiones siempre primero
    for dim in ["dim_geografia", "dim_tiempo", "dim_empresa"]:
        if dim not in seen:
            tables.append(dim)
            seen.add(dim)
    for entry in _REGISTRY:
        t = entry["table"]
        if t not in seen:
            tables.append(t)
            seen.add(t)
    return tables
