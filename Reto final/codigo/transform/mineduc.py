"""
transform/mineduc.py
====================
ETL para el archivo AMIE 2023-2024 del MINEDUC (Bloque 3).

Tabla Silver que carga:
  · fact_bachilleres  (por institución, nivel, provincia, cantón)
"""

import warnings
warnings.filterwarnings("ignore")

import sys
import logging
from pathlib import Path

import pandas as pd
from unidecode import unidecode
from sqlalchemy import create_engine, text
from tqdm import tqdm

sys.path.append(str(Path(__file__).resolve().parent.parent))
from config.settings import FUENTES, DB_URL

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [MINEDUC] %(levelname)s — %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


def get_engine():
    return create_engine(DB_URL, echo=False)


def norm(s):
    if pd.isna(s):
        return ""
    return unidecode(str(s)).strip().upper()


def _get_or_create_geo(engine, provincia, canton):
    prov = norm(provincia)
    cant = norm(canton)
    if not prov:
        return None
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO silver.dim_geografia (provincia, canton)
            VALUES (:p, :c)
            ON CONFLICT (provincia, canton) DO NOTHING
        """), {"p": prov, "c": cant})
        r = conn.execute(text("""
            SELECT id_geo FROM silver.dim_geografia
            WHERE provincia=:p AND canton=:c LIMIT 1
        """), {"p": prov, "c": cant}).fetchone()
    return r[0] if r else None


# Columnas de bachilleres por año en el AMIE
COL_BACH_1 = ["EstudiantesMasculinoPrimerAñoBACH",  "EstudiantesFemeninoPrimerAñoBACH"]
COL_BACH_2 = ["EstudiantesMasculinoSegundoAñoBACH", "EstudiantesFemeninoSegundoAñoBACH"]
COL_BACH_3 = ["EstudiantesMasculinoTercerAñoBACH",  "EstudiantesFemeninoTercerAñoBACH"]


def _find_col(columns, *keywords):
    """Busca columna que contenga todas las keywords (case-insensitive, sin tildes)."""
    for col in columns:
        col_n = norm(col)
        if all(norm(kw) in col_n for kw in keywords):
            return col
    return None


def load_bachilleres(engine):
    log.info("Cargando AMIE MINEDUC 2023-2024 (sep=';', latin-1)…")
    path = FUENTES["mineduc"]

    # Leer completo (6 MB es manejable)
    df = pd.read_csv(path, sep=";", encoding="latin-1", on_bad_lines="skip",
                     low_memory=False)
    log.info("  Filas totales AMIE: %d | Columnas: %d", len(df), len(df.columns))

    # ── Normalizar nombres de columna ────────────────────────────────────────
    cols_original = df.columns.tolist()

    # Mapeo de columnas clave
    col_map = {
        "anio_lectivo":      _find_col(cols_original, "lectivo") or "Año lectivo",
        "amie":              _find_col(cols_original, "amie"),
        "nombre_inst":       _find_col(cols_original, "nombre", "instit"),
        "provincia":         _find_col(cols_original, "provincia") or "Provincia",
        "canton":            _find_col(cols_original, "canton")    or "Cantón",
        "nivel_educacion":   _find_col(cols_original, "nivel", "educacion"),
        "sostenimiento":     _find_col(cols_original, "sostenimiento"),
        "modalidad":         _find_col(cols_original, "modalidad"),
        "area":              _find_col(cols_original, "area") or _find_col(cols_original, "Área"),
        "total_estudiantes": _find_col(cols_original, "total", "estudiante"),
        # Bachilleres por año
        "bach_1m": _find_col(cols_original, "masculino", "primer", "bach"),
        "bach_1f": _find_col(cols_original, "femenino",  "primer", "bach"),
        "bach_2m": _find_col(cols_original, "masculino", "segundo", "bach"),
        "bach_2f": _find_col(cols_original, "femenino",  "segundo", "bach"),
        "bach_3m": _find_col(cols_original, "masculino", "tercer", "bach"),
        "bach_3f": _find_col(cols_original, "femenino",  "tercer", "bach"),
    }

    log.info("  Columnas mapeadas: %s", {k: v for k, v in col_map.items() if v})

    # ── Filtrar Bachillerato ─────────────────────────────────────────────────
    col_nivel = col_map["nivel_educacion"]
    if col_nivel and col_nivel in df.columns:
        mask = df[col_nivel].astype(str).str.lower().str.contains(
            "bachillerato|bach", na=False
        )
        df_bach = df[mask].copy()
        log.info("  Filas con bachillerato: %d", len(df_bach))
    else:
        df_bach = df.copy()
        log.warning("  No se encontró columna de nivel educación — procesando todo")

    # ── Calcular totales de bachilleres por año ──────────────────────────────
    def safe_sum_cols(row, c1, c2):
        v1 = pd.to_numeric(row.get(c1, 0), errors="coerce") if c1 else 0
        v2 = pd.to_numeric(row.get(c2, 0), errors="coerce") if c2 else 0
        return int((v1 or 0) + (v2 or 0))

    df_bach["bach_1_total"] = df_bach.apply(
        lambda r: safe_sum_cols(r, col_map["bach_1m"], col_map["bach_1f"]), axis=1)
    df_bach["bach_2_total"] = df_bach.apply(
        lambda r: safe_sum_cols(r, col_map["bach_2m"], col_map["bach_2f"]), axis=1)
    df_bach["bach_3_total"] = df_bach.apply(
        lambda r: safe_sum_cols(r, col_map["bach_3m"], col_map["bach_3f"]), axis=1)

    col_est = col_map["total_estudiantes"]
    if col_est and col_est in df_bach.columns:
        df_bach["total_est"] = pd.to_numeric(df_bach[col_est], errors="coerce").fillna(0).astype(int)
    else:
        df_bach["total_est"] = 0

    # ── Insertar en bulk ─────────────────────────────────────────────────────
    inserted = 0
    geo_cache = {}
    params = []

    for _, row in tqdm(df_bach.iterrows(), total=len(df_bach), desc="MINEDUC", unit="rows"):
        prov = norm(row.get(col_map["provincia"], ""))
        cant = norm(row.get(col_map["canton"],    ""))

        if not prov:
            continue

        cache_key = (prov, cant)
        if cache_key not in geo_cache:
            geo_cache[cache_key] = _get_or_create_geo(engine, prov, cant)
        id_geo = geo_cache[cache_key]

        anio_l = str(row.get(col_map["anio_lectivo"], ""))[:20]
        amie   = str(row.get(col_map["amie"],   ""))[:20]   if col_map["amie"]   else ""
        nombre = str(row.get(col_map["nombre_inst"], ""))[:250] if col_map["nombre_inst"] else ""
        nivel  = str(row.get(col_map["nivel_educacion"], ""))[:100] if col_map["nivel_educacion"] else ""
        sost   = str(row.get(col_map["sostenimiento"], ""))[:30]    if col_map["sostenimiento"]   else ""
        modal  = str(row.get(col_map["modalidad"], ""))[:30]        if col_map["modalidad"]       else ""
        area   = str(row.get(col_map["area"], ""))[:10]             if col_map["area"]            else ""

        try:
            params.append({
                "al": anio_l, "am": amie, "ni": nombre, "g": id_geo,
                "nv": nivel,  "so": sost,  "mo": modal,  "ar": area,
                "te": int(row["total_est"]),
                "b1": int(row["bach_1_total"]),
                "b2": int(row["bach_2_total"]),
                "b3": int(row["bach_3_total"]),
            })
        except Exception as ex:
            log.debug("Skip MINEDUC fila: %s", ex)
            
    if params:
        with engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO silver.fact_bachilleres
                  (anio_lectivo, amie, nombre_institucion, id_geo,
                   nivel_educacion, sostenimiento, modalidad, area,
                   total_estudiantes,
                   bachilleres_1er_anio, bachilleres_2do_anio, bachilleres_3er_anio)
                VALUES
                  (:al, :am, :ni, :g,
                   :nv, :so, :mo, :ar,
                   :te, :b1, :b2, :b3)
                ON CONFLICT (amie, anio_lectivo) DO UPDATE
                  SET nombre_institucion=EXCLUDED.nombre_institucion,
                      id_geo=EXCLUDED.id_geo, nivel_educacion=EXCLUDED.nivel_educacion,
                      sostenimiento=EXCLUDED.sostenimiento, modalidad=EXCLUDED.modalidad,
                      area=EXCLUDED.area, total_estudiantes=EXCLUDED.total_estudiantes,
                      bachilleres_1er_anio=EXCLUDED.bachilleres_1er_anio,
                      bachilleres_2do_anio=EXCLUDED.bachilleres_2do_anio,
                      bachilleres_3er_anio=EXCLUDED.bachilleres_3er_anio
            """), params)
        inserted = len(params)

    log.info("fact_bachilleres: %d filas insertadas", inserted)


# =============================================================================
# Entry point
# =============================================================================

def run():
    engine = get_engine()
    log.info("=== MINEDUC ETL START ===")
    load_bachilleres(engine)
    log.info("=== MINEDUC ETL COMPLETADO ===")


if __name__ == "__main__":
    run()
