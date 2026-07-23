"""
config/settings.py
==================
Configuración centralizada del pipeline.
Edita las variables de entorno o modifica los valores por defecto aquí.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ── Rutas base ──────────────────────────────────────────────────────────────
BASE_DIR   = Path(__file__).resolve().parent.parent
DATA_DIR   = BASE_DIR / "datos_macroentorno"

BLOQUE_BCE      = DATA_DIR / "Bloque 1  Banco Central del Ecuador"
BLOQUE_INEC     = DATA_DIR / "Bloque 2 INEC"
BLOQUE_SUPERCIAS = DATA_DIR / "Bloque 3 Supercias y MINEDUC"

# ── Archivos fuente ──────────────────────────────────────────────────────────
FUENTES = {
    # Bloque 1 – BCE
    "pib_percapita":   BLOQUE_BCE / "pib-per-cpita-nominal.xlsx",
    "wti":             BLOQUE_BCE / "precio-petrleo-wti.xls.xlsx",
    "riesgo_pais":     BLOQUE_BCE / "riesgo-pas.xlsx",
    "iee":             BLOQUE_BCE / "IEE_Nueva_Metodologia.xlsx",
    "vab_nacional":    BLOQUE_BCE / "retropolacion_1965_2024p.xlsx",
    "vab_provincial":  BLOQUE_BCE / "Retro_CNR provinciales 2007_2018_PUB_valores.xlsx",
    # Bloque 2 – INEC
    "enemdu":          BLOQUE_INEC / "2026_I_trimestre_Tabulados_Mercado_Laboral.xlsx",
    "censo_trabajo":   BLOQUE_INEC / "2022_CPV_Trabajo.xlsx",
    # Bloque 3 – Supercias & MINEDUC
    "bi_compania":     BLOQUE_SUPERCIAS / "bi_compania.csv",
    "bi_ranking":      BLOQUE_SUPERCIAS / "bi_ranking.csv",
    "directorio":      BLOQUE_SUPERCIAS / "directorio_companias.xlsx",
    "mineduc":         BLOQUE_SUPERCIAS / "2_MINEDUC_RegistrosAdministrativos_2023-2024Inicio.csv",
}

# ── PostgreSQL ───────────────────────────────────────────────────────────────
DB_CONFIG = {
    "host":     os.getenv("PG_HOST",     "localhost"),
    "port":     int(os.getenv("PG_PORT", "5432")),
    "dbname":   os.getenv("PG_DB",       "macroentorno_utpl"),
    "user":     os.getenv("PG_USER",     "postgres"),
    "password": os.getenv("PG_PASSWORD", "password"),
}

DB_URL = (
    f"postgresql+psycopg://{DB_CONFIG['user']}:{DB_CONFIG['password']}"
    f"@{DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['dbname']}"
)

# ── Opciones de carga ────────────────────────────────────────────────────────
CHUNK_SIZE      = 50_000    # filas por lote para archivos grandes
IF_EXISTS       = "append"  # "replace" | "append" — comportamiento al insertar
BI_RANKING_YEARS = list(range(2015, 2026))  # años a cargar de bi_ranking (filtro tamaño)
