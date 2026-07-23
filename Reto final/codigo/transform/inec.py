"""
transform/inec.py
=================
ETL para las 2 fuentes del INEC (Bloque 2).

Tablas Silver que carga:
  · fact_empleo          (ENEMDU trimestral — requiere melt())
  · dim_geografia        (provincias del Censo, complementario)
  · fact_censo_actividad (Censo 2022 – condición de actividad por provincia)
"""

import warnings
warnings.filterwarnings("ignore")

import sys
import logging
from pathlib import Path

import pandas as pd
import numpy as np
from unidecode import unidecode
from sqlalchemy import create_engine, text

sys.path.append(str(Path(__file__).resolve().parent.parent))
from config.settings import FUENTES, DB_URL

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [INEC] %(levelname)s — %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


def get_engine():
    return create_engine(DB_URL, echo=False)


def normalizar(s):
    if pd.isna(s):
        return ""
    return unidecode(str(s)).strip().upper()


def _upsert_geo(engine, provincia, canton=None):
    prov = normalizar(provincia)
    cant = normalizar(canton) if canton else None
    if not prov:
        return None
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO silver.dim_geografia (provincia, canton)
            VALUES (:p, :c)
            ON CONFLICT (provincia, canton) DO NOTHING
        """), {"p": prov, "c": cant or ""})
        result = conn.execute(text("""
            SELECT id_geo FROM silver.dim_geografia
            WHERE provincia = :p AND canton = COALESCE(:c, '')
            LIMIT 1
        """), {"p": prov, "c": cant or ""}).fetchone()
    return result[0] if result else None


# =============================================================================
# 1. ENEMDU — Mercado Laboral Trimestral  →  fact_empleo
# =============================================================================

def load_enemdu(engine):
    log.info("Cargando ENEMDU (tasas de empleo)…")
    path = FUENTES["enemdu"]
    xf   = pd.ExcelFile(path)

    # Hoja con indicadores
    hoja = next((s for s in xf.sheet_names if "tasa" in s.lower()), None)
    if hoja is None:
        log.warning("Hoja 'Tasas' no encontrada en ENEMDU.")
        return

    df = pd.read_excel(xf, sheet_name=hoja, header=None)

    # Buscar fila del encabezado: contiene "Trimestre" e "Indicadores"
    start_row = None
    for i, row in df.iterrows():
        vals = [str(v).strip().lower() for v in row.values if pd.notna(v)]
        if any("trimestre" in v for v in vals) and any("indicador" in v for v in vals):
            start_row = i
            break

    if start_row is None:
        log.warning("No se encontró encabezado en ENEMDU.")
        return

    # Fila start_row = primera fila de headers (puede haber sub-headers)
    # Fila start_row+1 = sub-headers de área (Urbana, Rural, etc.)
    # Fila start_row+2 = sub-sub-headers de dominio
    # Datos desde start_row + 3
    header_row_1 = df.iloc[start_row].tolist()
    header_row_2 = df.iloc[start_row + 1].tolist()

    # Construir nombres de columna combinando ambas filas
    col_names = []
    for h1, h2 in zip(header_row_1, header_row_2):
        h1s = str(h1).strip() if pd.notna(h1) else ""
        h2s = str(h2).strip() if pd.notna(h2) else ""
        name = f"{h1s}_{h2s}".strip("_") if h2s and h2s.lower() not in ("nan", "") else h1s
        col_names.append(name)

    # Datos desde 3 filas después del header principal
    data = df.iloc[start_row + 3:].copy()
    data.columns = col_names[: len(data.columns)]

    # Columna 0 = Trimestre, Columna 1 = Indicadores
    col_trim = col_names[0]
    col_ind  = col_names[1]

    data = data[data[col_trim].notna() | data[col_ind].notna()].copy()

    # Forward-fill trimestre (puede venir vacío en filas de mismo trimestre)
    data[col_trim] = data[col_trim].ffill()
    data = data[data[col_ind].notna()].copy()

    # Columnas de área = todas excepto las dos primeras
    area_cols = col_names[2:]

    # Melt: una fila por (trimestre, indicador, área)
    data_long = data.melt(
        id_vars=[col_trim, col_ind],
        value_vars=[c for c in area_cols if c in data.columns],
        var_name="area_raw",
        value_name="valor_pct",
    )
    data_long["valor_pct"] = pd.to_numeric(data_long["valor_pct"], errors="coerce")
    data_long = data_long.dropna(subset=["valor_pct"])

    # Parsear trimestre "I - 2021" → (anio=2021, trimestre=1)
    def parse_trimestre(s):
        s = str(s).strip()
        try:
            partes = s.replace("–", "-").replace("—", "-").split("-")
            num_map = {"I": 1, "II": 2, "III": 3, "IV": 4}
            trim_str = partes[0].strip()
            anio_str = partes[-1].strip()
            return num_map.get(trim_str, 1), int(anio_str)
        except Exception:
            return None, None

    data_long[["trimestre", "anio"]] = data_long[col_trim].apply(
        lambda x: pd.Series(parse_trimestre(x))
    )
    data_long = data_long.dropna(subset=["trimestre", "anio"])
    data_long["trimestre"] = data_long["trimestre"].astype(int)
    data_long["anio"]      = data_long["anio"].astype(int)

    # Limpiar nombre de área
    data_long["area"] = data_long["area_raw"].apply(
        lambda x: x.split("_")[-1].strip()[:20] if "_" in x else str(x).strip()[:20]
    )

    inserted = 0
    params = []
    for _, row in data_long.iterrows():
        indicador = str(row[col_ind])[:150]
        periodo   = str(row[col_trim])[:15]
        try:
            params.append({
                "a": row["anio"], "t": row["trimestre"],
                "p": periodo,     "i": indicador,
                "ar": row["area"][:20], "v": float(row["valor_pct"]),
            })
        except Exception as e:
            log.debug("Skip fila ENEMDU: %s", e)

    if params:
        with engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO silver.fact_empleo
                  (anio, trimestre, periodo_texto, indicador, area, valor_pct)
                VALUES (:a, :t, :p, :i, :ar, :v)
                ON CONFLICT (anio, trimestre, indicador, area) DO UPDATE
                  SET valor_pct = EXCLUDED.valor_pct
            """), params)
        inserted = len(params)

    log.info("fact_empleo (ENEMDU): %d filas insertadas", inserted)


# =============================================================================
# 2. Censo 2022 — Actividad laboral por provincia  →  fact_censo_actividad
# =============================================================================

def load_censo(engine):
    log.info("Cargando Censo 2022 (actividad laboral)…")
    path = FUENTES["censo_trabajo"]
    xf   = pd.ExcelFile(path)

    # Usar hoja "3" — condición de actividad por provincia, área, sexo
    hoja = "3"
    if hoja not in xf.sheet_names:
        log.warning("Hoja '3' no encontrada en Censo 2022.")
        return

    df = pd.read_excel(xf, sheet_name=hoja, header=None)

    # Buscar fila de datos reales (contiene "Total Nacional" o valores numéricos grandes)
    start_row = None
    for i, row in df.iterrows():
        vals = [str(v).strip().lower() for v in row.values if pd.notna(v)]
        if any("total nacional" in v for v in vals):
            start_row = i
            break

    if start_row is None:
        log.warning("No se encontró inicio de datos en Censo 2022.")
        return

    data = df.iloc[start_row:].copy()
    # Columnas conocidas por posición (inspección previa):
    # 0=índice, 1=provincia/área, 2=área_residencia, 3=sexo, 4=total_15mas,
    # 5=ocupada, 6=desocupada, 7=fuera_fuerza
    data.columns = [
        "indice", "entidad", "area_residencia", "sexo",
        "total_personas_15mas", "ocupada", "desocupada", "fuera_fuerza_trabajo"
    ]

    for col in ["total_personas_15mas", "ocupada", "desocupada", "fuera_fuerza_trabajo"]:
        data[col] = pd.to_numeric(data[col], errors="coerce").astype("Int64")

    # La estructura tiene: entidad="Total Nacional"/provincia, area_residencia="Urbana"/"Rural"
    # sexo = "Total Nacional"/"Hombres"/"Mujeres"
    data = data[data["total_personas_15mas"].notna()].copy()

    # Extraer filas de provincias (excluir "Total Nacional")
    data["provincia"] = data["entidad"].ffill()
    data = data[~data["provincia"].str.lower().str.contains("total nacional", na=False)]

    inserted = 0
    params = []
    for _, row in data.iterrows():
        prov = normalizar(row["provincia"])
        area = str(row.get("area_residencia", "")).strip()[:10]
        sexo = str(row.get("sexo", "")).strip()[:10]

        if not prov or not area or not sexo:
            continue

        id_geo = _upsert_geo(engine, prov)
        if id_geo is None:
            continue

        try:
            params.append({
                "g": id_geo, "a": area, "s": sexo,
                "t": int(row["total_personas_15mas"]) if pd.notna(row["total_personas_15mas"]) else None,
                "o": int(row["ocupada"])               if pd.notna(row["ocupada"])               else None,
                "d": int(row["desocupada"])            if pd.notna(row["desocupada"])            else None,
                "f": int(row["fuera_fuerza_trabajo"])  if pd.notna(row["fuera_fuerza_trabajo"])  else None,
            })
        except Exception as e:
            log.debug("Skip fila Censo: %s", e)
            
    if params:
        with engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO silver.fact_censo_actividad
                  (id_geo, area, sexo, total_personas_15mas,
                   ocupada, desocupada, fuera_fuerza_trabajo)
                VALUES (:g, :a, :s, :t, :o, :d, :f)
                ON CONFLICT (id_geo, area, sexo) DO UPDATE
                  SET total_personas_15mas = EXCLUDED.total_personas_15mas,
                      ocupada              = EXCLUDED.ocupada,
                      desocupada           = EXCLUDED.desocupada,
                      fuera_fuerza_trabajo = EXCLUDED.fuera_fuerza_trabajo
            """), params)
        inserted = len(params)

    log.info("fact_censo_actividad: %d filas insertadas", inserted)


# =============================================================================
# Entry point
# =============================================================================

def run():
    engine = get_engine()
    log.info("=== INEC ETL START ===")
    load_enemdu(engine)
    load_censo(engine)
    log.info("=== INEC ETL COMPLETADO ===")


if __name__ == "__main__":
    run()
