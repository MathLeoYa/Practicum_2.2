"""Verificacion final del pipeline: tablas Silver + vistas Gold."""
import sys; sys.path.insert(0, '.')
from sqlalchemy import create_engine, text
from config.settings import DB_URL

engine = create_engine(DB_URL)

print("\n=== TABLAS SILVER ===")
TABLAS = [
    "dim_geografia","dim_tiempo","dim_empresa",
    "fact_macro_anual","fact_indicadores_diarios","fact_iee_mensual",
    "fact_vab_provincial","fact_empleo","fact_censo_actividad",
    "fact_empresa_ranking","fact_directorio_empresas","fact_bachilleres",
]
with engine.connect() as conn:
    for t in TABLAS:
        n = conn.execute(text(f"SELECT COUNT(*) FROM silver.{t}")).scalar()
        print(f"  {t:<40} {n:>10,}")

print("\n=== VISTAS GOLD ===")
with engine.connect() as conn:
    views = conn.execute(
        text("SELECT viewname FROM pg_views WHERE schemaname='silver' ORDER BY viewname")
    ).fetchall()
    if views:
        for v in views:
            n = conn.execute(text(f"SELECT COUNT(*) FROM silver.{v[0]}")).scalar()
            print(f"  {v[0]:<45} {n:>10,}")
    else:
        print("  (ninguna vista encontrada en schema silver)")

print("\n=== PIPELINE COMPLETADO ===")
