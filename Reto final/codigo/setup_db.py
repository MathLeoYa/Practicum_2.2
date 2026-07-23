"""Script de setup: crea la BD si no existe y verifica la conexion."""
import sys
sys.path.insert(0, '.')
from sqlalchemy import create_engine, text
from config.settings import DB_CONFIG

user = DB_CONFIG["user"]
pwd  = DB_CONFIG["password"]
host = DB_CONFIG["host"]
port = DB_CONFIG["port"]

admin_url = f"postgresql+psycopg://{user}:{pwd}@{host}:{port}/postgres"
engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")

try:
    with engine.connect() as conn:
        exists = conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname='macroentorno_utpl'")
        ).fetchone()
        if exists:
            print("[OK] Base de datos 'macroentorno_utpl' ya existe.")
        else:
            conn.execute(text("CREATE DATABASE macroentorno_utpl"))
            print("[OK] Base de datos 'macroentorno_utpl' CREADA exitosamente.")
    engine.dispose()

    # Verificar conexion a la BD del proyecto
    from config.settings import DB_URL
    eng2 = create_engine(DB_URL)
    with eng2.connect() as conn:
        conn.execute(text("SELECT 1"))
    print("[OK] Conexion a 'macroentorno_utpl' verificada.")
    eng2.dispose()

except Exception as e:
    print(f"[ERROR] {e}")
    print()
    print("Verifica que:")
    print("  1. PostgreSQL este corriendo (Servicios de Windows)")
    print("  2. El usuario/password en config/settings.py sea correcto")
    sys.exit(1)
