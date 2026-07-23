"""
transform/bce.py
================
ETL para las 5 fuentes del Banco Central del Ecuador (Bloque 1).

Tablas Silver que carga:
  · dim_tiempo           (población incremental)
  · fact_macro_anual     (PIB real + PIB per cápita + variación)
  · fact_indicadores_diarios (WTI + Riesgo País)
  · fact_iee_mensual     (IEE global + 4 sectores)
  · fact_vab_nacional    (VAB real y nominal por sector CIIU)
  · fact_vab_provincial  (VAB por provincia × sector × año)
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

# ── Setup de importaciones relativas ────────────────────────────────────────
sys.path.append(str(Path(__file__).resolve().parent.parent))
from config.settings import FUENTES, DB_URL

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [BCE] %(levelname)s — %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# =============================================================================
# Utilidades
# =============================================================================

def get_engine():
    return create_engine(DB_URL, echo=False)


def normalizar_provincia(nombre: str) -> str:
    """Normaliza nombre de provincia: sin tildes, sin espacios extras, mayúsculas."""
    if pd.isna(nombre):
        return ""
    return unidecode(str(nombre)).strip().upper()


def _upsert_dim_tiempo(engine, fechas: pd.Series):
    """
    Inserta fechas únicas en dim_tiempo ignorando duplicados.
    fechas: Series de objetos datetime.date o Timestamp.
    """
    df = pd.DataFrame({"fecha": pd.to_datetime(fechas).dt.normalize().drop_duplicates()})
    df = df.dropna()
    df["anio"]      = df["fecha"].dt.year.astype("Int16")
    df["mes"]       = df["fecha"].dt.month.astype("Int16")
    df["trimestre"] = df["fecha"].dt.quarter.astype("Int16")

    with engine.begin() as conn:
        for _, row in df.iterrows():
            conn.execute(text("""
                INSERT INTO silver.dim_tiempo (fecha, anio, mes, trimestre)
                VALUES (:f, :a, :m, :t)
                ON CONFLICT (fecha) DO NOTHING
            """), {"f": row["fecha"].date(), "a": int(row["anio"]),
                   "m": int(row["mes"]),    "t": int(row["trimestre"])})
    log.info("dim_tiempo: %d fechas procesadas", len(df))


def _get_id_tiempo(engine, anio: int) -> int | None:
    """Retorna id_tiempo del 1 de enero del año dado."""
    with engine.connect() as conn:
        result = conn.execute(
            text("SELECT id_tiempo FROM silver.dim_tiempo WHERE anio=:a AND mes=1 LIMIT 1"),
            {"a": anio}
        ).fetchone()
    return result[0] if result else None


# =============================================================================
# 1. PIB per cápita nominal  →  fact_macro_anual
# =============================================================================

def load_pib_percapita(engine):
    log.info("Cargando PIB per cápita nominal…")
    path = FUENTES["pib_percapita"]

    df = pd.read_excel(path, header=None)
    # Fila 0 = nombre indicador, fila 1 en adelante = datos
    df = df.iloc[1:].copy()
    df.columns = ["periodo", "pib_percapita_nominal"]
    df = df[df["periodo"].notna() & (df["periodo"] != "Período")].copy()

    df["periodo"] = pd.to_datetime(df["periodo"], errors="coerce")
    df = df.dropna(subset=["periodo"])
    df["anio"] = df["periodo"].dt.year.astype(int)
    df["pib_percapita_nominal"] = pd.to_numeric(df["pib_percapita_nominal"], errors="coerce")

    # Poblar dim_tiempo (1 fecha por año, primer día del año)
    fechas_anio = pd.to_datetime(df["anio"].astype(str) + "-01-01")
    _upsert_dim_tiempo(engine, fechas_anio)

    params = []
    for _, row in df.iterrows():
        id_t = _get_id_tiempo(engine, int(row["anio"]))
        if id_t is None:
            continue
        params.append({"t": id_t, "p": float(row["pib_percapita_nominal"])})

    if params:
        with engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO silver.fact_macro_anual (id_tiempo, pib_percapita_nominal)
                VALUES (:t, :p)
                ON CONFLICT (id_tiempo) DO UPDATE
                  SET pib_percapita_nominal = EXCLUDED.pib_percapita_nominal
            """), params)

    log.info("fact_macro_anual (PIB per cápita): %d filas", len(df))


# =============================================================================
# 2. PIB real (retropolación 1965-2024)  →  fact_macro_anual
# =============================================================================

def load_pib_real(engine):
    log.info("Cargando PIB real (retropolación)…")
    path = FUENTES["vab_nacional"]
    xf   = pd.ExcelFile(path)

    # Hoja con series de PIB real: buscar por nombre
    hoja_pib = next((s for s in xf.sheet_names if "retro pib" in s.lower()), None)
    if hoja_pib is None:
        log.warning("No se encontró hoja de PIB real en retropolación.")
        return

    df = pd.read_excel(xf, sheet_name=hoja_pib, header=None)
    # Encontrar fila donde está "Años" o similar
    start_row = None
    for i, row in df.iterrows():
        if any("año" in str(v).lower() or "anio" in str(v).lower() for v in row.values):
            start_row = i
            break
    if start_row is None:
        log.warning("No se encontró fila de encabezado en PIB real.")
        return

    headers = df.iloc[start_row].tolist()
    data    = df.iloc[start_row + 1:].copy()
    data.columns = [str(h).strip() for h in headers]
    data = data.dropna(subset=[data.columns[0]])

    # Col 0 = año; limpiar sufijos provisionales del BCE antes de convertir
    # Ejemplos reales: "2024 (p)", "2024(p)", "2023 (p*)", "2024 (e)"
    col_anio = data.columns[0]
    import re as _re
    data[col_anio] = (
        data[col_anio]
        .astype(str)
        .str.strip()
        .apply(lambda x: _re.sub(r"\s*\(.*?\)\*?", "", x).strip())  # quita (p), (e), (p*)
    )
    data[col_anio] = pd.to_numeric(data[col_anio], errors="coerce")
    data = data[data[col_anio].notna() & (data[col_anio] >= 1960)].copy()
    data[col_anio] = data[col_anio].astype(int)
    log.info("  Anos cargados: %d  (rango %d–%d)", len(data),
             int(data[col_anio].min()), int(data[col_anio].max()))

    # Columna PIB total = última o la que contiene "total" o "pib"
    col_pib = next(
        (c for c in data.columns[1:]
         if "total" in str(c).lower() or "pib" in str(c).lower()),
        data.columns[-1]
    )
    data[col_pib] = pd.to_numeric(data[col_pib], errors="coerce")

    # Calcular variación YoY
    data = data.sort_values(col_anio).reset_index(drop=True)
    data["variacion_pct"] = data[col_pib].pct_change() * 100

    fechas = pd.to_datetime(data[col_anio].astype(str) + "-01-01")
    _upsert_dim_tiempo(engine, fechas)

    params = []
    for _, row in data.iterrows():
        id_t = _get_id_tiempo(engine, int(row[col_anio]))
        if id_t is None:
            continue
        params.append({
            "t": id_t,
            "r": float(row[col_pib]) if pd.notna(row[col_pib]) else None,
            "v": round(float(row["variacion_pct"]), 4) if pd.notna(row["variacion_pct"]) else None,
        })
        
    if params:
        with engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO silver.fact_macro_anual (id_tiempo, pib_real_musd, variacion_pib_pct)
                VALUES (:t, :r, :v)
                ON CONFLICT (id_tiempo) DO UPDATE
                  SET pib_real_musd     = EXCLUDED.pib_real_musd,
                      variacion_pib_pct = EXCLUDED.variacion_pib_pct
            """), params)

    log.info("fact_macro_anual (PIB real): %d filas", len(data))


# =============================================================================
# 3. Precio Petróleo WTI + Riesgo País  →  fact_indicadores_diarios
# =============================================================================

def load_indicadores_diarios(engine):
    log.info("Cargando WTI y Riesgo País…")

    # ── WTI ──────────────────────────────────────────────────────────────────
    df_wti = pd.read_excel(FUENTES["wti"], header=None)
    df_wti = df_wti.iloc[1:].copy()
    df_wti.columns = ["fecha", "precio_petroleo_wti"]
    df_wti = df_wti[df_wti["fecha"].notna() & (df_wti["fecha"] != "Período")].copy()
    df_wti["fecha"] = pd.to_datetime(df_wti["fecha"], errors="coerce")
    df_wti["precio_petroleo_wti"] = pd.to_numeric(df_wti["precio_petroleo_wti"], errors="coerce")
    df_wti = df_wti.dropna(subset=["fecha", "precio_petroleo_wti"])
    df_wti["fecha"] = df_wti["fecha"].dt.normalize()
    df_wti = df_wti.drop_duplicates(subset=["fecha"])  # quitar fines de semana duplicados

    # ── Riesgo País ──────────────────────────────────────────────────────────
    df_rp = pd.read_excel(FUENTES["riesgo_pais"], header=None)
    df_rp = df_rp.iloc[1:].copy()
    df_rp.columns = ["fecha", "riesgo_pais_pb"]
    df_rp = df_rp[df_rp["fecha"].notna() & (df_rp["fecha"] != "Período")].copy()
    df_rp["fecha"] = pd.to_datetime(df_rp["fecha"], errors="coerce")
    df_rp["riesgo_pais_pb"] = pd.to_numeric(df_rp["riesgo_pais_pb"], errors="coerce").astype("Int64")
    df_rp = df_rp.dropna(subset=["fecha"])
    df_rp["fecha"] = df_rp["fecha"].dt.normalize()

    # ── Merge por fecha (outer join) ─────────────────────────────────────────
    df = pd.merge(df_wti, df_rp, on="fecha", how="outer").sort_values("fecha")

    _upsert_dim_tiempo(engine, df["fecha"])

    params = []
    for _, row in df.iterrows():
        wti = float(row["precio_petroleo_wti"]) if pd.notna(row.get("precio_petroleo_wti")) else None
        rp  = int(row["riesgo_pais_pb"])        if pd.notna(row.get("riesgo_pais_pb"))    else None
        params.append({"f": row["fecha"].date(), "w": wti, "r": rp})
        
    if params:
        with engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO silver.fact_indicadores_diarios (fecha, precio_petroleo_wti, riesgo_pais_pb)
                VALUES (:f, :w, :r)
                ON CONFLICT (fecha) DO UPDATE
                  SET precio_petroleo_wti = COALESCE(EXCLUDED.precio_petroleo_wti, fact_indicadores_diarios.precio_petroleo_wti),
                      riesgo_pais_pb      = COALESCE(EXCLUDED.riesgo_pais_pb,      fact_indicadores_diarios.riesgo_pais_pb)
            """), params)

    log.info("fact_indicadores_diarios: %d filas", len(df))


# =============================================================================
# 4. IEE Nueva Metodología  →  fact_iee_mensual
# =============================================================================

def load_iee(engine):
    log.info("Cargando IEE mensual…")
    df = pd.read_excel(FUENTES["iee"], header=None)

    # Encontrar fila del header real (contiene "Fecha")
    start_row = None
    for i, row in df.iterrows():
        if any(str(v).strip().lower() == "fecha" for v in row.values):
            start_row = i
            break
    if start_row is None:
        log.warning("No se encontró encabezado en IEE.")
        return

    data = df.iloc[start_row + 1:].copy()
    data.columns = ["fecha", "iee_global", "comercio", "construccion", "manufactura", "servicios"]
    data = data[data["fecha"].notna()].copy()

    # Filtrar filas que no son datos (notas al pie)
    data = data[data["fecha"].apply(lambda x: str(x).strip()[:4].isdigit() or
                                              (hasattr(x, 'year')))]
    data["fecha"] = pd.to_datetime(data["fecha"], errors="coerce")
    data = data.dropna(subset=["fecha"])

    for col in ["iee_global", "comercio", "construccion", "manufactura", "servicios"]:
        data[col] = pd.to_numeric(data[col], errors="coerce")

    _upsert_dim_tiempo(engine, data["fecha"])

    params = []
    for _, row in data.iterrows():
        params.append({
            "f":  row["fecha"].date(),
            "g":  float(row["iee_global"])   if pd.notna(row["iee_global"])   else None,
            "c":  float(row["comercio"])      if pd.notna(row["comercio"])     else None,
            "co": float(row["construccion"])  if pd.notna(row["construccion"]) else None,
            "m":  float(row["manufactura"])   if pd.notna(row["manufactura"])  else None,
            "s":  float(row["servicios"])     if pd.notna(row["servicios"])    else None,
        })
        
    if params:
        with engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO silver.fact_iee_mensual
                  (fecha, iee_global, comercio, construccion, manufactura, servicios)
                VALUES (:f, :g, :c, :co, :m, :s)
                ON CONFLICT (fecha) DO UPDATE
                  SET iee_global   = EXCLUDED.iee_global,
                      comercio     = EXCLUDED.comercio,
                      construccion = EXCLUDED.construccion,
                      manufactura  = EXCLUDED.manufactura,
                      servicios    = EXCLUDED.servicios
            """), params)

    log.info("fact_iee_mensual: %d filas", len(data))


# =============================================================================
# 5. VAB nacional por sector CIIU  →  fact_vab_nacional
# =============================================================================

def load_vab_nacional(engine):
    log.info("Cargando VAB nacional…")
    path = FUENTES["vab_nacional"]
    xf   = pd.ExcelFile(path)

    for tipo, hoja_key in [("real", "Serie VAB real"), ("nominal", "Serie VAB nominal")]:
        hoja = next((s for s in xf.sheet_names if hoja_key.lower() in s.lower()), None)
        if hoja is None:
            log.warning("Hoja '%s' no encontrada.", hoja_key)
            continue

        df = pd.read_excel(xf, sheet_name=hoja, header=None)

        # Encontrar fila con "Año" o "Anio"
        start_row = None
        for i, row in df.iterrows():
            vals = [str(v).strip().lower() for v in row.values if pd.notna(v)]
            if any("a" in v and ("o" in v or "\xf1o" in v or "ño" in v) and len(v) <= 5 for v in vals):
                start_row = i
                break
        if start_row is None:
            # fallback: buscar fila con años numéricos en siguiente fila
            for i in range(len(df) - 1):
                next_vals = pd.to_numeric(df.iloc[i + 1, 1:5], errors="coerce")
                if next_vals.notna().sum() >= 3:
                    start_row = i
                    break

        if start_row is None:
            log.warning("No se encontró encabezado en hoja '%s'.", hoja)
            continue

        # Verificar si siguiente fila tiene códigos CIIU (row start_row+1)
        # Headers reales pueden estar en dos filas
        headers_row = df.iloc[start_row].tolist()
        # Si siguiente fila tiene códigos numéricos, son sub-headers → saltar
        sub_row = df.iloc[start_row + 1].tolist()
        if all(pd.to_numeric(v, errors="coerce") is not None or pd.isna(v) for v in sub_row[1:5]):
            data_start = start_row + 2
        else:
            data_start = start_row + 1

        data = df.iloc[data_start:].copy()
        data.columns = [str(h).strip() for h in headers_row]
        col_anio = data.columns[0]
        data[col_anio] = pd.to_numeric(data[col_anio], errors="coerce")
        data = data[data[col_anio].notna() & (data[col_anio] >= 1960)].copy()
        data[col_anio] = data[col_anio].astype(int)

        # Columnas de sectores = todas excepto la primera
        sector_cols = [c for c in data.columns[1:] if str(c).strip() not in ("", "nan")]

        # En el archivo VAB Nacional NO hay fila de códigos CIIU explícitos, solo nombres de sectores.
        # Por tanto, asignamos "S1", "S2", etc.
        ciiu_codes = [f"S{i+1}" for i in range(len(sector_cols))]

        params = []
        for _, row in data.iterrows():
            anio_val = int(row[col_anio])
            for j, col in enumerate(sector_cols):
                val = pd.to_numeric(row[col], errors="coerce")
                if pd.isna(val):
                    continue
                ciiu = ciiu_codes[j]
                nombre = str(col)[:200]
                params.append({"a": anio_val, "c": ciiu, "n": nombre, "v": float(val)})

        if params:
            field = "vab_real_musd" if tipo == "real" else "vab_nominal_musd"
            with engine.begin() as conn:
                conn.execute(text(f"""
                    INSERT INTO silver.fact_vab_nacional
                      (anio, sector_ciiu, sector_nombre, {field})
                    VALUES (:a, :c, :n, :v)
                    ON CONFLICT (anio, sector_ciiu) DO UPDATE
                      SET {field} = EXCLUDED.{field},
                          sector_nombre = EXCLUDED.sector_nombre
                """), params)

        log.info("fact_vab_nacional (%s): procesado", tipo)


# =============================================================================
# 6. VAB provincial (CNR 2007-2018)  →  fact_vab_provincial + dim_geografia
# =============================================================================

def load_vab_provincial(engine):
    log.info("Cargando VAB provincial (CNR 2007-2018)...")
    path = FUENTES["vab_provincial"]
    xf   = pd.ExcelFile(path)

    # La hoja de valores tiene 'retropolacion' o 'prov' en el nombre
    # Excluir portada, indice y tasas de variacion
    hoja = next(
        (s for s in xf.sheet_names
         if any(k in s.lower() for k in ("retropol", "prov"))
         and not any(k in s.lower() for k in ("variaci", "tasa", "portada", "indic"))),
        None
    )
    if hoja is None:
        log.warning("Hoja provincial no encontrada. Hojas disponibles: %s", xf.sheet_names)
        return

    df = pd.read_excel(xf, sheet_name=hoja, header=None)

    # El header real esta en la fila donde aparece 'Codigo provincia' o 'PROVINCIA'
    # La estructura tiene ~10 filas NaN antes del header (fila 11, indice 10 en 0-based)
    start_row = None
    for i, row in df.iterrows():
        vals = [str(v).strip().lower() for v in row.values if pd.notna(v)]
        if any("a" in v for v in vals) and any(v.isdigit() and int(v) > 2000 for v in vals):
            start_row = i
            break
        # También buscar por presencia de valores 2007-2018 en la fila
        nums = [pd.to_numeric(v, errors="coerce") for v in row.values]
        years = [n for n in nums if pd.notna(n) and 2005 <= n <= 2020]
        if len(years) >= 5:
            start_row = i
            break

    if start_row is None:
        log.warning("No se encontró encabezado en VAB provincial.")
        return

    headers = df.iloc[start_row].tolist()
    data    = df.iloc[start_row + 1:].copy()

    # Normalizar nombres de columna: convertir floats de año (2007.0) a strings enteros ('2007')
    norm_headers = []
    for h in headers:
        try:
            val = float(str(h).strip())
            norm_headers.append(str(int(val)) if 2000 <= val <= 2030 else str(h).strip())
        except (ValueError, TypeError):
            norm_headers.append(str(h).strip())
    data.columns = norm_headers

    log.info("  Columnas detectadas: %s", norm_headers[:8])

    # Columnas de año y columnas de identificacion
    year_cols = [c for c in data.columns if c.isdigit() and 2005 <= int(c) <= 2025]
    log.info("  Anos disponibles: %s", year_cols)

    # Detectar columnas de descripcion por nombre exacto
    # En el archivo: 'Codigo provincia', 'PROVINCIA', 'Codigo Industria', 'Industria'
    col_prov = next((c for c in data.columns if str(c).strip().upper() == 'PROVINCIA'), None)
    col_ciiu = next((c for c in data.columns
                     if 'industria' in str(c).lower()
                     and any(p in str(c).lower() for p in ('cod', 'c\xf3d', 'c\xf3digo'))), None)
    col_ind  = next((c for c in data.columns
                     if str(c).strip().upper() == 'INDUSTRIA'), None)

    # Fallback por posición si los nombres no coinciden exactamente
    id_cols = [c for c in data.columns if c not in year_cols]
    if col_prov is None and len(id_cols) > 1:
        col_prov = id_cols[1]
    if col_ind is None and len(id_cols) > 3:
        col_ind = id_cols[3]

    log.info("  col_prov='%s'  col_ciiu='%s'  col_ind='%s'", col_prov, col_ciiu, col_ind)

    # Filtrar filas con provincia válida
    data = data[data[col_prov].notna()].copy()
    data[col_prov] = data[col_prov].astype(str).str.strip().str.upper()

    # Registrar provincias en dim_geografia
    provincias = data[col_prov].unique()
    with engine.begin() as conn:
        for prov in provincias:
            if not prov or prov.lower() in ("nan", "none"):
                continue
            conn.execute(text("""
                INSERT INTO silver.dim_geografia (provincia)
                VALUES (:p)
                ON CONFLICT (provincia, canton) DO NOTHING
            """), {"p": prov})

    # Melt años → long format
    data_long = data.melt(
        id_vars=[col_prov] + ([col_ciiu] if col_ciiu else []) + ([col_ind] if col_ind else []),
        value_vars=year_cols,
        var_name="anio",
        value_name="vab_miles_usd",
    )
    data_long["anio"] = pd.to_numeric(data_long["anio"], errors="coerce").astype("Int16")
    data_long["vab_miles_usd"] = pd.to_numeric(data_long["vab_miles_usd"], errors="coerce")
    data_long = data_long.dropna(subset=["vab_miles_usd"])

    # Obtener id_geo de dim_geografia (nivel provincia, canton NULL o vacio)
    with engine.connect() as conn:
        geo_map = {
            row[0]: row[1]
            for row in conn.execute(
                text("SELECT provincia, id_geo FROM silver.dim_geografia WHERE canton IS NULL OR canton = ''")
            ).fetchall()
        }
    log.info("  geo_map: %d provincias encontradas en dim_geografia", len(geo_map))

    inserted = 0
    params = []
    for _, row in data_long.iterrows():
        prov = str(row[col_prov]).strip().upper()
        id_geo = geo_map.get(prov)
        if id_geo is None:
            continue
        ciiu  = str(row[col_ciiu]).strip() if col_ciiu and pd.notna(row.get(col_ciiu)) else None
        nom   = str(row[col_ind])[:200]    if col_ind   and pd.notna(row.get(col_ind))  else None
        params.append({
            "g": id_geo, "a": int(row["anio"]),
            "c": ciiu,   "n": nom,
            "v": float(row["vab_miles_usd"]),
        })

    if params:
        with engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO silver.fact_vab_provincial
                  (id_geo, anio, sector_ciiu, sector_nombre, vab_miles_usd)
                VALUES (:g, :a, :c, :n, :v)
                ON CONFLICT (id_geo, anio, sector_ciiu) DO UPDATE
                  SET vab_miles_usd = EXCLUDED.vab_miles_usd
            """), params)
        inserted = len(params)

    log.info("fact_vab_provincial: %d filas insertadas", inserted)


# =============================================================================
# Entry point
# =============================================================================

def run():
    engine = get_engine()
    log.info("=== BCE ETL START ===")
    load_pib_percapita(engine)
    load_pib_real(engine)
    load_indicadores_diarios(engine)
    load_iee(engine)
    load_vab_nacional(engine)
    load_vab_provincial(engine)
    log.info("=== BCE ETL COMPLETADO ===")


if __name__ == "__main__":
    run()
