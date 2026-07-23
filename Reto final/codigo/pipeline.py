"""
pipeline.py
===========
Orquestador principal del Pipeline Macroentorno Ecuador.
Lee todas las fuentes desde config/registry.py — no hay listas hardcodeadas aquí.

Modos de ejecución:
  python pipeline.py --init      → Crea tablas + carga todas las fuentes + vistas Gold
  python pipeline.py --etl       → Re-ejecuta todos los ETLs (sin recrear tablas)
  python pipeline.py --watch     → Watchdog: monitorea datos_macroentorno/ para archivos RPA
  python pipeline.py --views     → Solo recrea las vistas Gold
  python pipeline.py --status    → Muestra conteo de filas por tabla Silver
  python pipeline.py --list      → Lista todas las fuentes registradas
"""

import argparse
import logging
import sys
import time
from pathlib import Path

from sqlalchemy import create_engine, text
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

sys.path.append(str(Path(__file__).resolve().parent))
from config.settings import DB_URL, DATA_DIR, DB_CONFIG
from config.registry import get_all, find_by_filename, resolve_fn, get_all_tables

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [PIPELINE] %(levelname)s — %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

DDL_PATH   = Path(__file__).parent / "db" / "create_tables.sql"
VIEWS_PATH = Path(__file__).parent / "db" / "gold_views.sql"
SUPPORTED_EXTENSIONS = {".xlsx", ".xls", ".csv"}


# =============================================================================
# Utilidades de base de datos
# =============================================================================

def get_engine():
    return create_engine(DB_URL, echo=False)


def _exec_sql_file(engine, path: Path):
    """
    Ejecuta un archivo SQL completo en una sola transaccion.
    psycopg3 soporta multiples sentencias (incluyendo bloques $$) en execute().
    """
    sql = path.read_text(encoding="utf-8")
    try:
        with engine.begin() as conn:
            # Usar el cursor nativo de psycopg para multi-statement
            raw = conn.connection.cursor()
            raw.execute(sql)
        log.info("SQL ejecutado: %s", path.name)
    except Exception as e:
        log.error("Error ejecutando %s: %s", path.name, str(e)[:200])
        raise


def create_tables(engine):
    log.info("=== Creando tablas Silver en PostgreSQL ===")
    _exec_sql_file(engine, DDL_PATH)
    log.info("Tablas creadas correctamente.")


def create_views(engine):
    log.info("=== Creando/actualizando vistas Gold ===")
    _exec_sql_file(engine, VIEWS_PATH)
    log.info("Vistas Gold listas.")


def show_status(engine):
    """Muestra conteo de filas por tabla. Lee tablas desde el registry."""
    tables = get_all_tables()  # ← viene del registry, sin hardcodear
    print("\n" + "-" * 58)
    print(f"  {'Tabla Silver':<35} {'Filas':>15}")
    print("-" * 58)
    with engine.connect() as conn:
        for t in tables:
            try:
                count = conn.execute(
                    text(f"SELECT COUNT(*) FROM silver.{t}")
                ).scalar()
                print(f"  {t:<35} {count:>15,}")
            except Exception:
                print(f"  {t:<35} {'(no encontrada)':>15}")
                
    print("\n" + "-" * 58)
    print(f"  {'Vista Gold':<35} {'Filas':>15}")
    print("-" * 58)
    gold_views = [
        "pib_tendencia", "empleo_tendencia", "petroleo_30dias",
        "bachilleres_vs_empresas", "iee_sectorial_tendencia", "vab_provincial_ranking"
    ]
    with engine.connect() as conn:
        for v in gold_views:
            try:
                count = conn.execute(
                    text(f"SELECT COUNT(*) FROM gold.{v}")
                ).scalar()
                print(f"  {v:<35} {count:>15,}")
            except Exception:
                print(f"  {v:<35} {'(no encontrada)':>15}")
    print("-" * 58 + "\n")


def list_sources():
    """Muestra todas las fuentes registradas en el registry."""
    sources = get_all()
    print("\n" + "-" * 75)
    print(f"  {'Key':<20} {'Label':<35} {'Tabla'}")
    print("-" * 75)
    for s in sources:
        print(f"  {s['key']:<20} {s['label']:<35} {s['table']}")
    print("-" * 75)
    print(f"  Total: {len(sources)} fuentes registradas\n")


# =============================================================================
# ETL completo — itera sobre el registry
# =============================================================================

def run_all_etl():
    """
    Ejecuta el ETL de cada fuente registrada en config/registry.py.
    Para agregar una nueva fuente, solo registrarla allí. Aquí no cambia nada.
    """
    engine = get_engine()
    sources = get_all()

    log.info("======================================")
    log.info("  INICIANDO ETL COMPLETO (%d fuentes)", len(sources))
    log.info("======================================")
    t0 = time.time()

    # Agrupar por módulo para no reimportar innecesariamente
    seen_modules: dict[str, set] = {}
    for entry in sources:
        mod_key = entry["module"]
        fn_name = entry["fn"]
        if mod_key not in seen_modules:
            seen_modules[mod_key] = set()
        if fn_name in seen_modules[mod_key]:
            continue  # ya ejecutada (ej: load_indicadores_diarios cubre WTI + Riesgo País)
        seen_modules[mod_key].add(fn_name)

        log.info("  ▶ [%s] %s", entry["label"], entry["fn"])
        try:
            fn = resolve_fn(entry)   # import dinámico desde registry
            fn(engine)
        except Exception as e:
            log.error("  ❌ Error en %s: %s", entry["label"], e)

    elapsed = time.time() - t0
    log.info("======================================")
    log.info("  ETL COMPLETADO en %.1f segundos", elapsed)
    log.info("======================================")


# =============================================================================
# Watchdog — integración RPA
# =============================================================================

class RPAFileHandler(FileSystemEventHandler):
    """
    Detecta nuevos archivos de RPA y dispara el ETL correspondiente.
    Las keywords vienen del registry — no hay FUENTE_HANDLERS hardcodeado.
    """

    def __init__(self, engine):
        self.engine = engine
        self._processing: set = set()

    def on_created(self, event):
        if event.is_directory:
            return
        path = Path(event.src_path)
        if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            return
        if path in self._processing:
            return

        self._processing.add(path)
        log.info("🔔 Nuevo archivo RPA detectado: %s", path.name)
        time.sleep(2)  # esperar a que el archivo termine de escribirse

        entry = find_by_filename(path.name)  # ← busca en el registry
        if entry:
            log.info("  → Handler: [%s] %s()", entry["label"], entry["fn"])
            try:
                fn = resolve_fn(entry)
                fn(self.engine)
                log.info("  ✅ Procesado: %s", path.name)
            except Exception as e:
                log.error("  ❌ Error procesando %s: %s", path.name, e)
        else:
            log.warning("  ⚠️  Sin handler registrado para: %s", path.name)
            log.warning("     Agrega la fuente en config/registry.py si corresponde.")

        self._processing.discard(path)


def start_watchdog(engine):
    watch_path = str(DATA_DIR)
    log.info("👀 Watchdog activo — monitoreando: %s", watch_path)
    log.info("   Fuentes registradas: %d", len(get_all()))
    log.info("   Ctrl+C para detener")

    event_handler = RPAFileHandler(engine)
    observer = Observer()
    observer.schedule(event_handler, watch_path, recursive=True)
    observer.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
        log.info("Watchdog detenido.")
    observer.join()


# =============================================================================
# Entry point
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Pipeline Macroentorno Ecuador — UTPL 6to Ciclo"
    )
    parser.add_argument("--init",   action="store_true", help="Crear tablas + ETL completo + vistas")
    parser.add_argument("--etl",    action="store_true", help="Ejecutar todos los ETLs")
    parser.add_argument("--watch",  action="store_true", help="Modo watchdog para archivos RPA")
    parser.add_argument("--views",  action="store_true", help="Recrear vistas Gold")
    parser.add_argument("--status", action="store_true", help="Mostrar conteo de filas por tabla")
    parser.add_argument("--list",   action="store_true", help="Listar fuentes registradas")
    args = parser.parse_args()

    if args.list:
        list_sources()
        return

    engine = get_engine()

    # Verificar conexión
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        log.info("✅ Conexión PostgreSQL OK — BD: %s", DB_CONFIG["dbname"])
    except Exception as e:
        log.error("❌ No se pudo conectar a PostgreSQL: %s", e)
        log.error("   Verifica credenciales en config/settings.py o archivo .env")
        sys.exit(1)

    if args.init:
        create_tables(engine)
        run_all_etl()
        create_views(engine)
        show_status(engine)

    elif args.etl:
        run_all_etl()

    elif args.views:
        create_views(engine)

    elif args.watch:
        start_watchdog(engine)

    elif args.status:
        show_status(engine)

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
