"""Diagnostico VAB provincial - geo_map matching."""
import sys; sys.path.insert(0, '.')
import pandas as pd
from config.settings import FUENTES, DB_URL
from sqlalchemy import create_engine, text

xf = pd.ExcelFile(FUENTES['vab_provincial'])
hoja = next(s for s in xf.sheet_names if 'retropol' in s.lower() and 'variaci' not in s.lower())
print("Hoja:", hoja)

df = pd.read_excel(xf, sheet_name=hoja, header=None)
start_row = None
for i, row in df.iterrows():
    vals = [str(v).strip().lower() for v in row.values if pd.notna(v)]
    if any('provincia' in v for v in vals):
        start_row = i
        break

print("Header en fila:", start_row)
headers = df.iloc[start_row].tolist()
data    = df.iloc[start_row + 1:].copy()
data.columns = [str(h).strip() for h in headers]

new_cols = []
for c in data.columns:
    try:
        val = float(c)
        new_cols.append(str(int(val)) if 2000 <= val <= 2030 else str(c).strip())
    except Exception:
        new_cols.append(str(c).strip())
data.columns = new_cols

col_prov = next(
    (c for c in data.columns if 'provincia' in c.lower() and 'cod' not in c.lower()),
    data.columns[1]
)
print("col_prov:", col_prov)
data = data[data[col_prov].notna()].copy()
provincias_arch = data[col_prov].astype(str).str.strip().str.upper().unique()
print("Provincias en archivo:", list(provincias_arch[:5]))

engine = create_engine(DB_URL)
with engine.connect() as conn:
    geo_rows = conn.execute(
        text("SELECT provincia, canton, id_geo FROM silver.dim_geografia LIMIT 10")
    ).fetchall()

print("Filas en dim_geografia (muestra):")
for r in geo_rows:
    print(f"  [{r[0]}] canton=[{r[1]}] id={r[2]}")

geo_map = {r[0]: r[2] for r in geo_rows if r[1] == ''}
print("Entradas con canton='' en geo_map:", len(geo_map))
matches = [p for p in provincias_arch if p in geo_map]
print("Coincidencias directas:", len(matches), "de", len(provincias_arch))
