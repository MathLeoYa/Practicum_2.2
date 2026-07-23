"""
Script de diagnóstico rápido del archivo VAB provincial.
Muestra las primeras filas y hojas para identificar la estructura real.
"""
import sys; sys.path.insert(0, '.')
import pandas as pd
from config.settings import FUENTES

path = FUENTES["vab_provincial"]
xf   = pd.ExcelFile(path)

print("Hojas disponibles:", xf.sheet_names)
print()

for hoja in xf.sheet_names:
    df = pd.read_excel(xf, sheet_name=hoja, header=None, nrows=15)
    print(f"=== HOJA: '{hoja}' ===")
    print(df.to_string())
    print()
