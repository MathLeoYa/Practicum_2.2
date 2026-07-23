"""
auditoria_datos.py
==================
Auditoría completa de TODOS los archivos fuente del pipeline.
Analiza estructura, calidad de datos y estima filas que pasarán a Silver.
"""
import sys, os
sys.path.insert(0, '.')
import warnings
warnings.filterwarnings("ignore")

import pandas as pd
import numpy as np
from pathlib import Path
from config.settings import FUENTES, BI_RANKING_YEARS

SEP = "=" * 70

def hdr(titulo):
    print(f"\n{SEP}")
    print(f"  {titulo}")
    print(SEP)

def sub(titulo):
    print(f"\n  {'─'*60}")
    print(f"  {titulo}")
    print(f"  {'─'*60}")

def fmt(n):
    return f"{n:,}"

# ─────────────────────────────────────────────────────────────────────────────
# BLOQUE 1 – BANCO CENTRAL DEL ECUADOR
# ─────────────────────────────────────────────────────────────────────────────

hdr("BLOQUE 1 — BANCO CENTRAL DEL ECUADOR")

# ── 1A. PIB per cápita nominal ────────────────────────────────────────────────
sub("1A · pib-per-cpita-nominal.xlsx  →  fact_macro_anual")
try:
    path = FUENTES["pib_percapita"]
    print(f"  Archivo : {path.name}  ({path.stat().st_size/1024:.1f} KB)")
    df = pd.read_excel(path, header=None)
    print(f"  Filas raw : {len(df)}")
    df = df.iloc[1:].copy()
    df.columns = ["periodo", "pib_percapita_nominal"]
    df = df[df["periodo"].notna() & (df["periodo"] != "Período")].copy()
    df["periodo"] = pd.to_datetime(df["periodo"], errors="coerce")
    antes = len(df)
    df = df.dropna(subset=["periodo"])
    df["pib_percapita_nominal"] = pd.to_numeric(df["pib_percapita_nominal"], errors="coerce")
    nulos = df["pib_percapita_nominal"].isna().sum()
    rango = f"{int(df['periodo'].dt.year.min())} – {int(df['periodo'].dt.year.max())}"
    print(f"  Filas con fecha válida : {fmt(len(df))}  (descartadas: {antes-len(df)})")
    print(f"  Nulos en pib_percapita_nominal : {nulos}")
    print(f"  Rango de años : {rango}")
    print(f"  ✅ Filas → fact_macro_anual (PIB per cápita) : {fmt(len(df) - nulos)}")
    print(f"  Muestra:\n{df[['periodo','pib_percapita_nominal']].head(3).to_string(index=False)}")
except Exception as e:
    print(f"  ❌ ERROR: {e}")

# ── 1B. PIB real (retropolación) ──────────────────────────────────────────────
sub("1B · retropolacion_1965_2024p.xlsx  →  fact_macro_anual + fact_vab_nacional")
try:
    path = FUENTES["vab_nacional"]
    print(f"  Archivo : {path.name}  ({path.stat().st_size/1024/1024:.1f} MB)")
    xf = pd.ExcelFile(path)
    print(f"  Hojas disponibles: {xf.sheet_names}")

    # Hoja PIB real
    hoja_pib = next((s for s in xf.sheet_names if "retro pib" in s.lower()), None)
    print(f"\n  ── Sub-hoja PIB Real: '{hoja_pib}' ──")
    if hoja_pib:
        df_p = pd.read_excel(xf, sheet_name=hoja_pib, header=None)
        print(f"  Dimensiones: {df_p.shape}")
        start_row = None
        for i, row in df_p.iterrows():
            if any("año" in str(v).lower() or "anio" in str(v).lower() for v in row.values):
                start_row = i
                break
        if start_row is not None:
            headers = df_p.iloc[start_row].tolist()
            data = df_p.iloc[start_row+1:].copy()
            data.columns = [str(h).strip() for h in headers]
            import re
            col_anio = data.columns[0]
            data[col_anio] = data[col_anio].astype(str).str.strip().apply(
                lambda x: re.sub(r"\s*\(.*?\)\*?", "", x).strip())
            data[col_anio] = pd.to_numeric(data[col_anio], errors="coerce")
            data = data[data[col_anio].notna() & (data[col_anio] >= 1960)].copy()
            data[col_anio] = data[col_anio].astype(int)
            col_pib = next((c for c in data.columns[1:] if "total" in str(c).lower() or "pib" in str(c).lower()), data.columns[-1])
            data[col_pib] = pd.to_numeric(data[col_pib], errors="coerce")
            nulos = data[col_pib].isna().sum()
            print(f"  Años cargados: {fmt(len(data))}  ({int(data[col_anio].min())}–{int(data[col_anio].max())})")
            print(f"  Nulos en PIB total: {nulos}")
            print(f"  ✅ Filas → fact_macro_anual (PIB real): {fmt(len(data)-nulos)}")

    # Hojas VAB
    for tipo, clave in [("real","serie vab real"), ("nominal","serie vab nominal")]:
        hoja_v = next((s for s in xf.sheet_names if clave in s.lower()), None)
        print(f"\n  ── Sub-hoja VAB {tipo.upper()}: '{hoja_v}' ──")
        if hoja_v:
            df_v = pd.read_excel(xf, sheet_name=hoja_v, header=None)
            print(f"  Dimensiones: {df_v.shape}")
            start_row = None
            for i, row in df_v.iterrows():
                vals = [str(v).strip().lower() for v in row.values if pd.notna(v)]
                if any(len(v)<=5 and ("o" in v or "ño" in v) and "a" in v for v in vals):
                    start_row = i; break
            if start_row is not None:
                headers = df_v.iloc[start_row].tolist()
                data_v = df_v.iloc[start_row+1:].copy()
                data_v.columns = [str(h).strip() for h in headers]
                col_a = data_v.columns[0]
                data_v[col_a] = pd.to_numeric(data_v[col_a], errors="coerce")
                data_v = data_v[data_v[col_a].notna() & (data_v[col_a] >= 1960)].copy()
                sectores = [c for c in data_v.columns[1:] if str(c).strip() not in ("","nan")]
                print(f"  Años: {fmt(len(data_v))}  |  Sectores CIIU: {len(sectores)}")
                total_celdas = len(data_v) * len(sectores)
                no_nulos = sum(pd.to_numeric(data_v[c], errors="coerce").notna().sum() for c in sectores)
                print(f"  Celdas totales: {fmt(total_celdas)}  |  Con valor: {fmt(no_nulos)}")
                print(f"  ✅ Filas → fact_vab_nacional ({tipo}): {fmt(no_nulos)}")
except Exception as e:
    print(f"  ❌ ERROR: {e}")

# ── 1C. WTI + Riesgo País ─────────────────────────────────────────────────────
sub("1C · precio-petrleo-wti.xls.xlsx + riesgo-pas.xlsx  →  fact_indicadores_diarios")
try:
    # WTI
    path_wti = FUENTES["wti"]
    print(f"  WTI: {path_wti.name}  ({path_wti.stat().st_size/1024:.1f} KB)")
    df_wti = pd.read_excel(path_wti, header=None).iloc[1:].copy()
    df_wti.columns = ["fecha", "precio_petroleo_wti"]
    df_wti = df_wti[df_wti["fecha"].notna() & (df_wti["fecha"] != "Período")]
    df_wti["fecha"] = pd.to_datetime(df_wti["fecha"], errors="coerce")
    df_wti["precio_petroleo_wti"] = pd.to_numeric(df_wti["precio_petroleo_wti"], errors="coerce")
    df_wti = df_wti.dropna(subset=["fecha","precio_petroleo_wti"])
    df_wti = df_wti.drop_duplicates(subset=["fecha"])
    print(f"  WTI — filas válidas: {fmt(len(df_wti))} | rango: {df_wti['fecha'].min().date()} → {df_wti['fecha'].max().date()}")
    print(f"  WTI — precio min: ${df_wti['precio_petroleo_wti'].min():.2f} | max: ${df_wti['precio_petroleo_wti'].max():.2f} | media: ${df_wti['precio_petroleo_wti'].mean():.2f}")

    # Riesgo País
    path_rp = FUENTES["riesgo_pais"]
    print(f"\n  Riesgo País: {path_rp.name}  ({path_rp.stat().st_size/1024:.1f} KB)")
    df_rp = pd.read_excel(path_rp, header=None).iloc[1:].copy()
    df_rp.columns = ["fecha", "riesgo_pais_pb"]
    df_rp = df_rp[df_rp["fecha"].notna() & (df_rp["fecha"] != "Período")]
    df_rp["fecha"] = pd.to_datetime(df_rp["fecha"], errors="coerce")
    df_rp["riesgo_pais_pb"] = pd.to_numeric(df_rp["riesgo_pais_pb"], errors="coerce")
    df_rp = df_rp.dropna(subset=["fecha"])
    print(f"  Riesgo País — filas: {fmt(len(df_rp))} | rango: {df_rp['fecha'].min().date()} → {df_rp['fecha'].max().date()}")
    print(f"  Riesgo País — nulos en pb: {df_rp['riesgo_pais_pb'].isna().sum()}")
    print(f"  Riesgo País — min: {df_rp['riesgo_pais_pb'].min():.0f} pb | max: {df_rp['riesgo_pais_pb'].max():.0f} pb")

    # Merge
    df_merge = pd.merge(df_wti, df_rp, on="fecha", how="outer")
    solo_wti  = df_merge["riesgo_pais_pb"].isna().sum()
    solo_rp   = df_merge["precio_petroleo_wti"].isna().sum()
    ambos     = df_merge.dropna(subset=["precio_petroleo_wti","riesgo_pais_pb"])
    print(f"\n  Merge outer — total filas: {fmt(len(df_merge))}")
    print(f"  Solo WTI (sin riesgo):  {solo_wti}  |  Solo Riesgo (sin WTI):  {solo_rp}")
    print(f"  Con ambos valores:      {fmt(len(ambos))}")
    print(f"  ✅ Filas → fact_indicadores_diarios: {fmt(len(df_merge))}")
except Exception as e:
    print(f"  ❌ ERROR: {e}")

# ── 1D. IEE ───────────────────────────────────────────────────────────────────
sub("1D · IEE_Nueva_Metodologia.xlsx  →  fact_iee_mensual")
try:
    path = FUENTES["iee"]
    print(f"  Archivo: {path.name}  ({path.stat().st_size/1024:.1f} KB)")
    df = pd.read_excel(path, header=None)
    print(f"  Dimensiones raw: {df.shape}")
    start_row = None
    for i, row in df.iterrows():
        if any(str(v).strip().lower() == "fecha" for v in row.values):
            start_row = i; break
    print(f"  Header encontrado en fila: {start_row}")
    if start_row is not None:
        data = df.iloc[start_row+1:].copy()
        data.columns = ["fecha","iee_global","comercio","construccion","manufactura","servicios"]
        data = data[data["fecha"].notna()].copy()
        data = data[data["fecha"].apply(lambda x: str(x).strip()[:4].isdigit() or hasattr(x,'year'))]
        data["fecha"] = pd.to_datetime(data["fecha"], errors="coerce")
        data = data.dropna(subset=["fecha"])
        for col in ["iee_global","comercio","construccion","manufactura","servicios"]:
            data[col] = pd.to_numeric(data[col], errors="coerce")
        nulos = data[["iee_global","comercio","construccion","manufactura","servicios"]].isna().sum()
        print(f"  Filas válidas: {fmt(len(data))}")
        print(f"  Rango: {data['fecha'].min().date()} → {data['fecha'].max().date()}")
        print(f"  Nulos por columna:\n{nulos.to_string()}")
        print(f"  IEE global — min: {data['iee_global'].min():.2f} | max: {data['iee_global'].max():.2f} | media: {data['iee_global'].mean():.2f}")
        print(f"  ✅ Filas → fact_iee_mensual: {fmt(len(data))}")
except Exception as e:
    print(f"  ❌ ERROR: {e}")

# ── 1E. VAB Provincial ────────────────────────────────────────────────────────
sub("1E · Retro_CNR provinciales 2007_2018_PUB_valores.xlsx  →  fact_vab_provincial")
try:
    path = FUENTES["vab_provincial"]
    print(f"  Archivo: {path.name}  ({path.stat().st_size/1024/1024:.1f} MB)")
    xf = pd.ExcelFile(path)
    print(f"  Hojas: {xf.sheet_names}")
    hoja = next((s for s in xf.sheet_names if any(k in s.lower() for k in ("retropol","prov")) and
                 not any(k in s.lower() for k in ("variaci","tasa","portada","indic"))), None)
    print(f"  Hoja seleccionada: '{hoja}'")
    if hoja:
        df = pd.read_excel(xf, sheet_name=hoja, header=None)
        print(f"  Dimensiones raw: {df.shape}")
        start_row = None
        for i, row in df.iterrows():
            nums = [pd.to_numeric(v, errors="coerce") for v in row.values]
            years = [n for n in nums if pd.notna(n) and 2005 <= n <= 2020]
            if len(years) >= 5:
                start_row = i; break
        print(f"  Header de años encontrado en fila: {start_row}")
        if start_row is not None:
            headers = df.iloc[start_row].tolist()
            data = df.iloc[start_row+1:].copy()
            norm_h = []
            for h in headers:
                try:
                    v = float(str(h).strip())
                    norm_h.append(str(int(v)) if 2000<=v<=2030 else str(h).strip())
                except: norm_h.append(str(h).strip())
            data.columns = norm_h
            year_cols = [c for c in data.columns if c.isdigit() and 2005<=int(c)<=2025]
            col_prov = next((c for c in data.columns if str(c).strip().upper()=="PROVINCIA"), None)
            if col_prov is None:
                id_cols = [c for c in data.columns if c not in year_cols]
                col_prov = id_cols[1] if len(id_cols)>1 else data.columns[1]
            data = data[data[col_prov].notna()].copy()
            # Conteo de filas raw y provincias únicas
            provincias = data[col_prov].astype(str).str.strip().str.upper().unique()
            print(f"  Columnas de año: {year_cols}")
            print(f"  Filas (combinaciones prov×sector): {fmt(len(data))}")
            print(f"  Provincias únicas: {len(provincias)}")
            print(f"  Provincias: {list(provincias)[:10]}...")
            # Melt
            id_cols = [c for c in data.columns if c not in year_cols]
            data_long = data.melt(id_vars=id_cols[:3], value_vars=year_cols,
                                   var_name="anio", value_name="vab_miles_usd")
            data_long["vab_miles_usd"] = pd.to_numeric(data_long["vab_miles_usd"], errors="coerce")
            antes = len(data_long)
            data_long = data_long.dropna(subset=["vab_miles_usd"])
            print(f"  Filas long format (tras melt): {fmt(antes)}  |  Con valor: {fmt(len(data_long))}")
            print(f"  Descartadas (NaN): {fmt(antes - len(data_long))}")
            print(f"  ✅ Filas → fact_vab_provincial (estimado): {fmt(len(data_long))}")
except Exception as e:
    print(f"  ❌ ERROR: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# BLOQUE 2 – INEC
# ─────────────────────────────────────────────────────────────────────────────

hdr("BLOQUE 2 — INEC")

# ── 2A. ENEMDU ────────────────────────────────────────────────────────────────
sub("2A · 2026_I_trimestre_Tabulados_Mercado_Laboral.xlsx  →  fact_empleo")
try:
    path = FUENTES["enemdu"]
    print(f"  Archivo: {path.name}  ({path.stat().st_size/1024/1024:.1f} MB)")
    xf = pd.ExcelFile(path)
    print(f"  Hojas: {xf.sheet_names}")
    hoja = next((s for s in xf.sheet_names if "tasa" in s.lower()), None)
    print(f"  Hoja seleccionada: '{hoja}'")
    if hoja:
        df = pd.read_excel(xf, sheet_name=hoja, header=None)
        print(f"  Dimensiones raw: {df.shape}")
        start_row = None
        for i, row in df.iterrows():
            vals = [str(v).strip().lower() for v in row.values if pd.notna(v)]
            if any("trimestre" in v for v in vals) and any("indicador" in v for v in vals):
                start_row = i; break
        print(f"  Header principal en fila: {start_row}")
        if start_row is not None:
            hr1 = df.iloc[start_row].tolist()
            hr2 = df.iloc[start_row+1].tolist()
            col_names = []
            for h1,h2 in zip(hr1,hr2):
                h1s = str(h1).strip() if pd.notna(h1) else ""
                h2s = str(h2).strip() if pd.notna(h2) else ""
                n = f"{h1s}_{h2s}".strip("_") if h2s and h2s.lower() not in ("nan","") else h1s
                col_names.append(n)
            data = df.iloc[start_row+3:].copy()
            data.columns = col_names[:len(data.columns)]
            col_trim = col_names[0]
            col_ind  = col_names[1]
            data = data[data[col_trim].notna() | data[col_ind].notna()].copy()
            data[col_trim] = data[col_trim].ffill()
            data = data[data[col_ind].notna()].copy()
            area_cols = [c for c in col_names[2:] if c in data.columns]
            print(f"  Columnas de área/dominio: {len(area_cols)} → {area_cols[:5]}...")
            print(f"  Indicadores únicos: {data[col_ind].nunique()}")
            print(f"  Trimestres únicos: {data[col_trim].nunique()} → {list(data[col_trim].unique())[:4]}...")
            data_long = data.melt(id_vars=[col_trim, col_ind], value_vars=area_cols,
                                   var_name="area_raw", value_name="valor_pct")
            data_long["valor_pct"] = pd.to_numeric(data_long["valor_pct"], errors="coerce")
            antes = len(data_long)
            data_long = data_long.dropna(subset=["valor_pct"])
            print(f"  Filas long (tras melt): {fmt(antes)}  |  Con valor: {fmt(len(data_long))}")
            print(f"  Descartadas (NaN/vacías): {fmt(antes-len(data_long))}")
            print(f"  ✅ Filas → fact_empleo: {fmt(len(data_long))}")
except Exception as e:
    print(f"  ❌ ERROR: {e}")

# ── 2B. Censo 2022 ────────────────────────────────────────────────────────────
sub("2B · 2022_CPV_Trabajo.xlsx  →  fact_censo_actividad")
try:
    path = FUENTES["censo_trabajo"]
    print(f"  Archivo: {path.name}  ({path.stat().st_size/1024/1024:.1f} MB)")
    xf = pd.ExcelFile(path)
    print(f"  Hojas disponibles: {xf.sheet_names}")
    hoja = "3"
    if hoja in xf.sheet_names:
        df = pd.read_excel(xf, sheet_name=hoja, header=None)
        print(f"  Hoja '3' — Dimensiones raw: {df.shape}")
        start_row = None
        for i, row in df.iterrows():
            vals = [str(v).strip().lower() for v in row.values if pd.notna(v)]
            if any("total nacional" in v for v in vals):
                start_row = i; break
        print(f"  Inicio de datos en fila: {start_row}")
        if start_row is not None:
            data = df.iloc[start_row:].copy()
            data.columns = ["indice","entidad","area_residencia","sexo",
                            "total_personas_15mas","ocupada","desocupada","fuera_fuerza_trabajo"]
            for col in ["total_personas_15mas","ocupada","desocupada","fuera_fuerza_trabajo"]:
                data[col] = pd.to_numeric(data[col], errors="coerce").astype("Int64")
            data = data[data["total_personas_15mas"].notna()].copy()
            data["provincia"] = data["entidad"].ffill()
            data_prov = data[~data["provincia"].str.lower().str.contains("total nacional", na=False)]
            print(f"  Filas totales con datos: {fmt(len(data))}")
            print(f"  Filas de provincias (sin Total Nacional): {fmt(len(data_prov))}")
            print(f"  Provincias únicas: {data_prov['provincia'].nunique()}")
            print(f"  Áreas únicas: {list(data_prov['area_residencia'].unique())}")
            print(f"  Sexos únicos: {list(data_prov['sexo'].unique())}")
            validos = data_prov[(data_prov["area_residencia"].notna()) & (data_prov["sexo"].notna())]
            print(f"  ✅ Filas → fact_censo_actividad: {fmt(len(validos))}")
            print(f"\n  Resumen nacional (Total Nacional):")
            total_nac = data[data["provincia"].str.lower().str.contains("total nacional",na=False)]
            if len(total_nac) > 0:
                row_tn = total_nac.iloc[0]
                print(f"    Total personas 15+: {fmt(int(row_tn['total_personas_15mas']))}")
                print(f"    Ocupadas:           {fmt(int(row_tn['ocupada']))}")
                print(f"    Desocupadas:        {fmt(int(row_tn['desocupada']))}")
                print(f"    Fuera fuerza trab:  {fmt(int(row_tn['fuera_fuerza_trabajo']))}")
except Exception as e:
    print(f"  ❌ ERROR: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# BLOQUE 3 – SUPERCIAS y MINEDUC
# ─────────────────────────────────────────────────────────────────────────────

hdr("BLOQUE 3 — SUPERCIAS y MINEDUC")

# ── 3A. bi_compania.csv ───────────────────────────────────────────────────────
sub("3A · bi_compania.csv  →  dim_empresa")
try:
    path = FUENTES["bi_compania"]
    print(f"  Archivo: {path.name}  ({path.stat().st_size/1024/1024:.1f} MB)")
    df = pd.read_csv(path, encoding="latin-1", on_bad_lines="skip")
    print(f"  Columnas: {list(df.columns)}")
    print(f"  Filas raw: {fmt(len(df))}")
    df.columns = [c.strip().lower() for c in df.columns]
    df["ruc"] = pd.to_numeric(df["ruc"], errors="coerce").astype("Int64")
    df_ok = df.dropna(subset=["expediente"]).copy()
    df_ok["expediente"] = df_ok["expediente"].astype(int)
    print(f"  Filas con expediente válido: {fmt(len(df_ok))}")
    print(f"  RUC nulos: {fmt(df['ruc'].isna().sum())}")
    print(f"  Tipos únicos de empresa: {df_ok['tipo'].nunique()} → {list(df_ok['tipo'].value_counts().head(5).index)}")
    print(f"  Provincias únicas: {df_ok['provincia'].nunique()}")
    if 'provincia' in df_ok.columns:
        top5 = df_ok['provincia'].value_counts().head(5)
        print(f"  Top 5 provincias:\n{top5.to_string()}")
    print(f"  ✅ Filas → dim_empresa: {fmt(len(df_ok))}")
except Exception as e:
    print(f"  ❌ ERROR: {e}")

# ── 3B. bi_ranking.csv (solo muestra por tamaño) ──────────────────────────────
sub("3B · bi_ranking.csv  →  fact_empresa_ranking  (357 MB — análisis por chunks)")
try:
    path = FUENTES["bi_ranking"]
    print(f"  Archivo: {path.name}  ({path.stat().st_size/1024/1024:.1f} MB)")
    COLS_NEEDED = ["anio","expediente","posicion_general","ingresos_ventas",
                   "activos","patrimonio","utilidad_ejercicio","n_empleados",
                   "ciiu_n1","ciiu_n6","roe","roa"]
    # Primeras filas para ver columnas
    df_head = pd.read_csv(path, encoding="latin-1", on_bad_lines="skip", nrows=5)
    print(f"  Columnas totales: {len(df_head.columns)}")
    print(f"  Columnas: {list(df_head.columns)[:12]}...")

    total_filas = 0
    filas_por_anio = {}
    nulos_total = 0
    n_chunks = 0

    reader = pd.read_csv(path, encoding="latin-1", on_bad_lines="skip",
                         chunksize=100_000, usecols=COLS_NEEDED)
    for chunk in reader:
        total_filas += len(chunk)
        nulos_total += chunk["expediente"].isna().sum()
        for anio, cnt in chunk["anio"].value_counts().items():
            filas_por_anio[anio] = filas_por_anio.get(anio, 0) + cnt
        n_chunks += 1

    filas_filtradas = sum(v for k,v in filas_por_anio.items() if k in BI_RANKING_YEARS)
    print(f"\n  Total filas raw: {fmt(total_filas)}")
    print(f"  Chunks procesados (100K): {n_chunks}")
    print(f"  Expediente nulos: {fmt(nulos_total)}")
    print(f"\n  Distribución por año:")
    for anio in sorted(filas_por_anio.keys()):
        marca = " ✅ (incluido)" if anio in BI_RANKING_YEARS else " ⛔ (excluido)"
        print(f"    {anio}: {fmt(filas_por_anio[anio])}{marca}")
    print(f"\n  Años incluidos (BI_RANKING_YEARS={BI_RANKING_YEARS[0]}–{BI_RANKING_YEARS[-1]}): {fmt(filas_filtradas)} filas")
    print(f"  Filas excluidas por año: {fmt(total_filas - filas_filtradas)}")
    print(f"  ✅ Filas → fact_empresa_ranking (estimado): {fmt(filas_filtradas)}")
except Exception as e:
    print(f"  ❌ ERROR: {e}")

# ── 3C. directorio_companias.xlsx ─────────────────────────────────────────────
sub("3C · directorio_companias.xlsx  →  fact_directorio_empresas")
try:
    path = FUENTES["directorio"]
    print(f"  Archivo: {path.name}  ({path.stat().st_size/1024/1024:.1f} MB)")
    xf = pd.ExcelFile(path)
    print(f"  Hojas: {xf.sheet_names}")
    df = pd.read_excel(xf, sheet_name=xf.sheet_names[0], header=None)
    print(f"  Dimensiones raw: {df.shape}")
    header_row = None
    for i, row in df.iterrows():
        vals = [str(v).strip().upper() for v in row.values if pd.notna(v)]
        if any(v in ("RUC","EXPEDIENTE","NOMBRE") for v in vals):
            header_row = i; break
    print(f"  Header real encontrado en fila: {header_row}")
    if header_row is not None:
        data = df.iloc[header_row+1:].copy()
        data.columns = [str(h).strip().upper().replace(" ","_") for h in df.iloc[header_row].tolist()]
        print(f"  Columnas: {list(data.columns)}")
        rename = {"SITUACIÓN_LEGAL":"situacion_legal","SITUACION_LEGAL":"situacion_legal",
                  "PROVINCIA":"provincia","CANTÓN":"canton","CANTON":"canton",
                  "REGIÓN":"region","REGION":"region"}
        data.rename(columns={k:v for k,v in rename.items() if k in data.columns}, inplace=True)
        total_raw = len(data)
        print(f"  Filas totales (todas situaciones): {fmt(total_raw)}")
        if "situacion_legal" in data.columns:
            print(f"\n  Situaciones legales:")
            for sit, cnt in data["situacion_legal"].value_counts().items():
                print(f"    {sit}: {fmt(cnt)}")
            data_act = data[data["situacion_legal"].astype(str).str.upper().str.contains("ACTIVA")].copy()
            print(f"\n  Solo ACTIVAS: {fmt(len(data_act))}")
        if "provincia" in data.columns:
            data_act["provincia"] = data_act["provincia"].astype(str).str.strip().str.upper()
            top5 = data_act["provincia"].value_counts().head(5)
            print(f"  Top 5 provincias (activas):\n{top5.to_string()}")
        print(f"  ✅ Filas → fact_directorio_empresas: {fmt(len(data_act))}")
except Exception as e:
    print(f"  ❌ ERROR: {e}")

# ── 3D. MINEDUC AMIE ──────────────────────────────────────────────────────────
sub("3D · 2_MINEDUC_RegistrosAdministrativos_2023-2024Inicio.csv  →  fact_bachilleres")
try:
    path = FUENTES["mineduc"]
    print(f"  Archivo: {path.name}  ({path.stat().st_size/1024/1024:.1f} MB)")
    df = pd.read_csv(path, sep=";", encoding="latin-1", on_bad_lines="skip", low_memory=False)
    print(f"  Dimensiones: {df.shape}")
    print(f"  Columnas ({len(df.columns)}): {list(df.columns)[:8]}...")

    # Nivel educación
    col_nivel = next((c for c in df.columns if "nivel" in c.lower() and "educaci" in c.lower()), None)
    col_prov  = next((c for c in df.columns if "provincia" in c.lower()), None)
    col_cant  = next((c for c in df.columns if "cant" in c.lower()), None)
    col_sost  = next((c for c in df.columns if "sostenimiento" in c.lower()), None)

    print(f"\n  Columna nivel educación: '{col_nivel}'")
    print(f"  Columna provincia: '{col_prov}'")
    print(f"  Columna cantón: '{col_cant}'")

    if col_nivel:
        print(f"\n  Niveles educativos únicos:")
        for nv, cnt in df[col_nivel].value_counts().items():
            print(f"    {nv}: {fmt(cnt)}")

    if col_nivel:
        df_bach = df[df[col_nivel].astype(str).str.lower().str.contains("bachillerato|bach", na=False)].copy()
        print(f"\n  Filas de Bachillerato: {fmt(len(df_bach))}")
    else:
        df_bach = df.copy()

    # Columnas de bachilleres
    from unidecode import unidecode
    def norm(s):
        return unidecode(str(s)).strip().upper() if not pd.isna(s) else ""

    def find_col(cols, *kws):
        for c in cols:
            cn = norm(c)
            if all(norm(k) in cn for k in kws):
                return c
        return None

    cols_orig = df_bach.columns.tolist()
    b1m = find_col(cols_orig, "masculino","primer","bach")
    b1f = find_col(cols_orig, "femenino","primer","bach")
    b2m = find_col(cols_orig, "masculino","segundo","bach")
    b2f = find_col(cols_orig, "femenino","segundo","bach")
    b3m = find_col(cols_orig, "masculino","tercer","bach")
    b3f = find_col(cols_orig, "femenino","tercer","bach")

    print(f"\n  Columnas bachilleres encontradas:")
    print(f"    1er año M: {b1m}  |  F: {b1f}")
    print(f"    2do año M: {b2m}  |  F: {b2f}")
    print(f"    3er año M: {b3m}  |  F: {b3f}")

    def safesum(row, c1, c2):
        v1 = pd.to_numeric(row.get(c1,0), errors="coerce") if c1 else 0
        v2 = pd.to_numeric(row.get(c2,0), errors="coerce") if c2 else 0
        return int((v1 or 0)+(v2 or 0))

    df_bach["bach_3_total"] = df_bach.apply(lambda r: safesum(r,b3m,b3f), axis=1)
    df_bach["bach_1_total"] = df_bach.apply(lambda r: safesum(r,b1m,b1f), axis=1)
    df_bach["bach_2_total"] = df_bach.apply(lambda r: safesum(r,b2m,b2f), axis=1)

    total_bach3 = df_bach["bach_3_total"].sum()
    total_bach_all = df_bach["bach_3_total"].sum() + df_bach["bach_1_total"].sum() + df_bach["bach_2_total"].sum()
    sin_prov = df_bach[col_prov].isna().sum() if col_prov else 0

    print(f"\n  Instituciones (filas bachillerato): {fmt(len(df_bach))}")
    print(f"  Sin provincia (se descartan): {fmt(sin_prov)}")
    print(f"  Total estudiantes 3er año bach: {fmt(total_bach3)}")
    print(f"  Total estudiantes todos años bach: {fmt(total_bach_all)}")

    if col_sost:
        print(f"\n  Por sostenimiento:")
        for s, c in df_bach[col_sost].value_counts().items():
            print(f"    {s}: {fmt(c)}")
    if col_prov:
        print(f"\n  Top 5 provincias (instituciones):")
        print(df_bach[col_prov].value_counts().head(5).to_string())

    print(f"  ✅ Filas → fact_bachilleres (estimado): {fmt(len(df_bach) - sin_prov)}")
except Exception as e:
    print(f"  ❌ ERROR: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# RESUMEN FINAL
# ─────────────────────────────────────────────────────────────────────────────

hdr("RESUMEN FINAL — FILAS ESTIMADAS POR TABLA SILVER")
print("""
  Tabla Silver                    │ Fuente                      │ Filas estimadas
  ──────────────────────────────── │ ─────────────────────────── │ ─────────────────
  dim_tiempo                      │ (generada por ETLs)         │ ~ 600-2,300
  dim_geografia                   │ (generada por ETLs)         │ ~ 300-500
  dim_empresa                     │ bi_compania.csv             │ ~ 337,018
  fact_macro_anual                │ pib_percapita + pib_real    │ ~ 60-65
  fact_indicadores_diarios        │ WTI + riesgo_pais           │ ~ 600-700
  fact_iee_mensual                │ IEE_Nueva_Metodologia       │ ~ 197
  fact_vab_nacional               │ retropolacion (VAB)         │ ~ 4,000-5,000
  fact_vab_provincial             │ Retro_CNR_provinciales      │ ~ 6,000-8,000
  fact_empleo                     │ ENEMDU                      │ ~ 3,000-5,000
  fact_censo_actividad            │ Censo 2022                  │ ~ 200-250
  fact_empresa_ranking            │ bi_ranking.csv (filtrado)   │ ~ 600,000-900,000
  fact_directorio_empresas        │ directorio_companias        │ ~ 222,604
  fact_bachilleres                │ AMIE MINEDUC                │ ~ miles
  ──────────────────────────────────────────────────────────────────────────────
  TOTAL ESTIMADO                  │                             │ > 1,000,000 filas
""")
print("  ✅ Auditoría completada.\n")
