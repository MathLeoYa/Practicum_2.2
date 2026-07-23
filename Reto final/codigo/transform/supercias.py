"""
transform/supercias.py
======================
ETL para las 3 fuentes de Supercias (Bloque 3).

Tablas Silver que carga:
  · dim_empresa           (catálogo bi_compania.csv — 337K empresas)
  · fact_empresa_ranking  (bi_ranking.csv — 1.6M filas, cargado en chunks)
  · fact_directorio_empresas (directorio_companias.xlsx — 222K filas activas)
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
from config.settings import FUENTES, DB_URL, CHUNK_SIZE, BI_RANKING_YEARS

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [SUPERCIAS] %(levelname)s — %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


def get_engine():
    return create_engine(DB_URL, echo=False)


def norm(s):
    if pd.isna(s):
        return ""
    return unidecode(str(s)).strip().upper()


def _get_or_create_geo(engine, provincia, canton=None):
    prov = norm(provincia)
    cant = norm(canton) if canton else ""
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


# =============================================================================
# 1. bi_compania.csv  →  dim_empresa
# =============================================================================

def load_dim_empresa(engine):
    log.info("Cargando dim_empresa (bi_compania.csv)…")
    path = FUENTES["bi_compania"]

    df = pd.read_csv(path, encoding="latin-1", on_bad_lines="skip")
    df.columns = [c.strip().lower() for c in df.columns]

    # Normalizar
    df["nombre"]   = df["nombre"].astype(str).str.strip()
    df["tipo"]     = df["tipo"].astype(str).str.strip()
    df["provincia"] = df["provincia"].astype(str).str.strip().str.upper()
    df["ruc"]      = pd.to_numeric(df["ruc"], errors="coerce").astype("Int64")

    df = df.dropna(subset=["expediente"])
    df["expediente"] = df["expediente"].astype(int)

    log.info("  Insertando %d empresas…", len(df))
    inserted = 0
    params = []
    for _, row in tqdm(df.iterrows(), total=len(df), desc="dim_empresa", unit="rows"):
        try:
            params.append({
                "e":  int(row["expediente"]),
                "r":  int(row["ruc"])        if pd.notna(row["ruc"])        else None,
                "n":  str(row["nombre"])[:250],
                "t":  str(row["tipo"])[:50],
                "p":  int(row["pro_codigo"]) if pd.notna(row.get("pro_codigo")) else None,
                "pv": str(row["provincia"])[:80],
            })
        except Exception as ex:
            log.debug("Skip empresa %s: %s", row.get("expediente"), ex)

    if params:
        with engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO silver.dim_empresa
                  (expediente, ruc, nombre, tipo, pro_codigo, provincia)
                VALUES (:e, :r, :n, :t, :p, :pv)
                ON CONFLICT (expediente) DO UPDATE
                  SET ruc=EXCLUDED.ruc, nombre=EXCLUDED.nombre,
                      tipo=EXCLUDED.tipo, pro_codigo=EXCLUDED.pro_codigo,
                      provincia=EXCLUDED.provincia
            """), params)
        inserted = len(params)

    log.info("dim_empresa: %d filas insertadas", inserted)


# =============================================================================
# 2. bi_ranking.csv  →  fact_empresa_ranking  (chunks de 50K)
# =============================================================================

def load_ranking(engine):
    log.info("Cargando bi_ranking.csv (años: %s)…", BI_RANKING_YEARS)
    path  = FUENTES["bi_ranking"]
    total = 0

    COLS_NEEDED = [
        "anio", "expediente", "posicion_general",
        "ingresos_ventas", "activos", "patrimonio",
        "utilidad_ejercicio", "n_empleados",
        "ciiu_n1", "ciiu_n6", "roe", "roa",
    ]

    reader = pd.read_csv(
        path, encoding="latin-1", on_bad_lines="skip",
        chunksize=CHUNK_SIZE, usecols=COLS_NEEDED,
    )

    for chunk in tqdm(reader, desc="bi_ranking chunks", unit="chunk"):
        # Filtrar solo años de interés
        chunk = chunk[chunk["anio"].isin(BI_RANKING_YEARS)].copy()
        if chunk.empty:
            continue

        chunk["anio"]       = chunk["anio"].astype(int)
        chunk["expediente"] = pd.to_numeric(chunk["expediente"], errors="coerce").astype("Int64")
        chunk = chunk.dropna(subset=["expediente"])

        numeric_cols = [
            "ingresos_ventas", "activos", "patrimonio",
            "utilidad_ejercicio", "roe", "roa",
        ]
        for col in numeric_cols:
            chunk[col] = pd.to_numeric(chunk[col], errors="coerce")

        int_cols = ["posicion_general", "n_empleados", "ciiu_n1", "ciiu_n6"]
        for col in int_cols:
            chunk[col] = pd.to_numeric(chunk[col], errors="coerce").astype("Int64")

        params = []
        for _, row in chunk.iterrows():
            try:
                params.append({
                    "a":  int(row["anio"]),
                    "e":  int(row["expediente"]),
                    "pg": int(row["posicion_general"]) if pd.notna(row["posicion_general"]) else None,
                    "iv": float(row["ingresos_ventas"]) if pd.notna(row["ingresos_ventas"]) else None,
                    "ac": float(row["activos"])         if pd.notna(row["activos"])         else None,
                    "pa": float(row["patrimonio"])      if pd.notna(row["patrimonio"])      else None,
                    "ue": float(row["utilidad_ejercicio"]) if pd.notna(row["utilidad_ejercicio"]) else None,
                    "ne": int(row["n_empleados"])  if pd.notna(row["n_empleados"])  else None,
                    "c1": int(row["ciiu_n1"])      if pd.notna(row["ciiu_n1"])      else None,
                    "c6": int(row["ciiu_n6"])      if pd.notna(row["ciiu_n6"])      else None,
                    "roe": float(row["roe"])        if pd.notna(row["roe"])         else None,
                    "roa": float(row["roa"])        if pd.notna(row["roa"])         else None,
                })
            except Exception as ex:
                log.debug("Skip ranking row: %s", ex)

        if params:
            with engine.begin() as conn:
                conn.execute(text("""
                    INSERT INTO silver.fact_empresa_ranking
                      (anio, expediente, posicion_general,
                       ingresos_ventas, activos, patrimonio,
                       utilidad_ejercicio, n_empleados,
                       ciiu_n1, ciiu_n6, roe, roa)
                    VALUES
                      (:a, :e, :pg,
                       :iv, :ac, :pa,
                       :ue, :ne,
                       :c1, :c6, :roe, :roa)
                    ON CONFLICT (anio, expediente) DO UPDATE
                      SET ingresos_ventas    = EXCLUDED.ingresos_ventas,
                          activos            = EXCLUDED.activos,
                          patrimonio         = EXCLUDED.patrimonio,
                          utilidad_ejercicio = EXCLUDED.utilidad_ejercicio,
                          roe                = EXCLUDED.roe,
                          roa                = EXCLUDED.roa
                """), params)
            total += len(params)

    log.info("fact_empresa_ranking: %d filas insertadas", total)


# =============================================================================
# 3. directorio_companias.xlsx  →  fact_directorio_empresas
# =============================================================================

def load_directorio(engine):
    log.info("Cargando directorio_companias.xlsx…")
    path = FUENTES["directorio"]
    xf   = pd.ExcelFile(path)
    hoja = xf.sheet_names[0]

    df = pd.read_excel(xf, sheet_name=hoja, header=None)

    # Header real en fila 4 (índice 4)
    header_row = None
    for i, row in df.iterrows():
        vals = [str(v).strip().upper() for v in row.values if pd.notna(v)]
        if any(v in ("RUC", "EXPEDIENTE", "NOMBRE") for v in vals):
            header_row = i
            break

    if header_row is None:
        log.warning("No se encontró header en directorio_companias.")
        return

    data = df.iloc[header_row + 1:].copy()
    data.columns = [
        str(h).strip().upper().replace(" ", "_")
        for h in df.iloc[header_row].tolist()
    ]

    # Renombrar columnas estándar
    rename_map = {
        "NO._FILA":          "no_fila",
        "EXPEDIENTE":        "expediente",
        "RUC":               "ruc",
        "NOMBRE":            "nombre",
        "SITUACIÓN_LEGAL":   "situacion_legal",
        "SITUACION_LEGAL":   "situacion_legal",
        "FECHA_CONSTITUCION":"fecha_constitucion",
        "TIPO":              "tipo",
        "PAÍS":              "pais",
        "PAIS":              "pais",
        "REGIÓN":            "region",
        "REGION":            "region",
        "PROVINCIA":         "provincia",
        "CANTÓN":            "canton",
        "CANTON":            "canton",
        "CIUDAD":            "ciudad",
    }
    data.rename(columns={k: v for k, v in rename_map.items() if k in data.columns}, inplace=True)

    # Filtrar solo empresas ACTIVAS
    if "situacion_legal" in data.columns:
        data = data[data["situacion_legal"].astype(str).str.upper().str.contains("ACTIVA")].copy()

    data["provincia"] = data.get("provincia", pd.Series(dtype=str)).astype(str).str.strip().str.upper()
    data["canton"]    = data.get("canton", pd.Series(dtype=str)).astype(str).str.strip().str.upper()

    # Fecha
    if "fecha_constitucion" in data.columns:
        data["fecha_constitucion"] = pd.to_datetime(
            data["fecha_constitucion"], errors="coerce", dayfirst=True
        )

    log.info("  Empresas activas encontradas: %d", len(data))

    # Insertar en chunks de 5K
    inserted = 0
    chunk_size = 5_000
    for start in tqdm(range(0, len(data), chunk_size), desc="directorio", unit="chunk"):
        chunk = data.iloc[start: start + chunk_size]
        params = []
        with engine.begin() as conn:
            for _, row in chunk.iterrows():
                prov = str(row.get("provincia", "")).strip()
                cant = str(row.get("canton", "")).strip()
                id_geo = None
                if prov and prov.lower() not in ("nan", "none", ""):
                    conn.execute(text("""
                        INSERT INTO silver.dim_geografia (provincia, canton)
                        VALUES (:p, :c)
                        ON CONFLICT (provincia, canton) DO NOTHING
                    """), {"p": prov, "c": cant or ""})
                    r = conn.execute(text("""
                        SELECT id_geo FROM silver.dim_geografia
                        WHERE provincia=:p AND canton=:c LIMIT 1
                    """), {"p": prov, "c": cant or ""}).fetchone()
                    id_geo = r[0] if r else None

                fc = row.get("fecha_constitucion")
                try:
                    params.append({
                        "e":  int(row["expediente"])     if pd.notna(row.get("expediente"))      else None,
                        "r":  str(row.get("ruc",""))[:15],
                        "n":  str(row.get("nombre",""))[:300],
                        "sl": str(row.get("situacion_legal",""))[:20],
                        "fc": fc.date()                  if pd.notna(fc)                         else None,
                        "t":  str(row.get("tipo",""))[:50],
                        "p":  str(row.get("pais",""))[:50],
                        "rg": str(row.get("region",""))[:20],
                        "pv": prov[:80],
                        "ca": cant[:80],
                        "ci": str(row.get("ciudad",""))[:80],
                        "g":  id_geo,
                    })
                except Exception as ex:
                    log.debug("Skip directorio row: %s", ex)
            
            if params:
                conn.execute(text("""
                    INSERT INTO silver.fact_directorio_empresas
                      (expediente, ruc, nombre, situacion_legal, fecha_constitucion,
                       tipo, pais, region, provincia, canton, ciudad, id_geo)
                    VALUES
                      (:e, :r, :n, :sl, :fc,
                       :t, :p, :rg, :pv, :ca, :ci, :g)
                    ON CONFLICT (expediente) DO UPDATE
                      SET ruc=EXCLUDED.ruc, nombre=EXCLUDED.nombre,
                          situacion_legal=EXCLUDED.situacion_legal, 
                          fecha_constitucion=EXCLUDED.fecha_constitucion,
                          tipo=EXCLUDED.tipo, pais=EXCLUDED.pais,
                          region=EXCLUDED.region, provincia=EXCLUDED.provincia,
                          canton=EXCLUDED.canton, ciudad=EXCLUDED.ciudad,
                          id_geo=EXCLUDED.id_geo
                """), params)
                inserted += len(params)

    log.info("fact_directorio_empresas: %d filas insertadas", inserted)


# =============================================================================
# Entry point
# =============================================================================

def run():
    engine = get_engine()
    log.info("=== SUPERCIAS ETL START ===")
    load_dim_empresa(engine)
    load_ranking(engine)
    load_directorio(engine)
    log.info("=== SUPERCIAS ETL COMPLETADO ===")


if __name__ == "__main__":
    run()
