# Pipeline de Datos del Macroentorno Ecuatoriano
**UTPL — Practicum Interno · Línea de Datos · 6to Ciclo**

---

## Descripción

Pipeline ETL completo que procesa **10 fuentes públicas** del Ecuador (BCE, INEC, Supercias, MINEDUC), carga **12 tablas Silver** en PostgreSQL y construye **6 vistas Gold analíticas** para responder las 3 preguntas del dashboard en Power BI.

Implementa el **modelo medallón** (Bronze → Silver → Gold) con un orquestador con modo watchdog para integración automática con el equipo de RPA.

---

## Estructura del proyecto

```
RetoPrac/
├── config/
│   └── settings.py              # Conexión PostgreSQL y rutas de archivos
├── db/
│   ├── create_tables.sql        # DDL: 12 tablas Silver (2 dim + 10 hechos)
│   └── gold_views.sql           # 6 vistas Gold analíticas
├── transform/
│   ├── bce.py                   # ETL Banco Central (PIB, WTI, Riesgo País, IEE, VAB)
│   ├── inec.py                  # ETL INEC (ENEMDU trimestral + Censo 2022)
│   ├── supercias.py             # ETL Supercias (empresas, ranking financiero, directorio)
│   └── mineduc.py               # ETL MINEDUC (AMIE 2023-2024)
├── datos_macroentorno/          # Fuentes de datos (Bronze)
│   ├── Bloque 1  Banco Central del Ecuador/
│   ├── Bloque 2 INEC/
│   └── Bloque 3 Supercias y MINEDUC/
├── pipeline.py                  # Orquestador principal + watchdog RPA
├── requirements.txt
└── README.md
```

---

## Requisitos

- Python 3.10+
- PostgreSQL 14+

```bash
pip install -r requirements.txt
```

---

## Configuración

Edita `config/settings.py` o crea un archivo `.env` en la raíz:

```env
PG_HOST=localhost
PG_PORT=5432
PG_DB=macroentorno_utpl
PG_USER=postgres
PG_PASSWORD=tu_contraseña
```

### Crear la base de datos en PostgreSQL

```sql
CREATE DATABASE macroentorno_utpl;
```

---

## Uso

### Inicialización completa (primera vez)

```bash
python pipeline.py --init
```

Esto ejecuta en orden:
1. Crea el schema `silver` y las 12 tablas con sus índices y FK
2. Carga todas las fuentes (BCE → INEC → Supercias → MINEDUC)
3. Crea las 6 vistas Gold

> ⚠️ **Nota**: La carga de `bi_ranking.csv` (1.6M filas) tarda ~20-40 min dependiendo del equipo.

### Verificar estado de carga

```bash
python pipeline.py --status
```

### Re-ejecutar ETLs (sin recrear tablas)

```bash
python pipeline.py --etl
```

### Recrear solo las vistas Gold

```bash
python pipeline.py --views
```

### Modo watchdog (integración RPA — semana 5)

```bash
python pipeline.py --watch
```

Monitorea la carpeta `datos_macroentorno/` en tiempo real. Cuando el equipo de RPA deposita un archivo nuevo, el pipeline lo detecta y ejecuta automáticamente el ETL correspondiente sin intervención manual.

**Convención de nombres de archivos RPA:**
```
pib_real_20260512.xlsx       → dispara load_pib_percapita
iee_mensual_20260601.xlsx    → dispara load_iee
enemdu_2026Q2.xlsx           → dispara load_enemdu
amie_2024_2025.csv           → dispara load_bachilleres
```

---

## Fuentes de datos

| Bloque | Fuente | Archivo | Filas | Tabla Silver |
|--------|--------|---------|-------|--------------|
| BCE | PIB per cápita nominal | `pib-per-cpita-nominal.xlsx` | 26 | `fact_macro_anual` |
| BCE | PIB real retropolación | `retropolacion_1965_2024p.xlsx` | 60 | `fact_macro_anual` |
| BCE | Precio petróleo WTI | `precio-petrleo-wti.xls.xlsx` | 521 | `fact_indicadores_diarios` |
| BCE | Riesgo país | `riesgo-pas.xlsx` | 431 | `fact_indicadores_diarios` |
| BCE | IEE nueva metodología | `IEE_Nueva_Metodologia.xlsx` | 197 | `fact_iee_mensual` |
| BCE | VAB nacional sectorial | `retropolacion_1965_2024p.xlsx` | 35 sectores × 60 años | `fact_vab_nacional` |
| BCE | VAB provincial CNR | `Retro_CNR provinciales 2007_2018_PUB_valores.xlsx` | ~806 | `fact_vab_provincial` |
| INEC | ENEMDU mercado laboral | `2026_I_trimestre_Tabulados_Mercado_Laboral.xlsx` | 311 × melt | `fact_empleo` |
| INEC | Censo 2022 actividad | `2022_CPV_Trabajo.xlsx` | 241 | `fact_censo_actividad` |
| Supercias | Catálogo empresas | `bi_compania.csv` | 337,018 | `dim_empresa` |
| Supercias | Ranking financiero | `bi_ranking.csv` | 1,672,589 | `fact_empresa_ranking` |
| Supercias | Directorio activas | `directorio_companias.xlsx` | 222,604 | `fact_directorio_empresas` |
| MINEDUC | AMIE 2023-2024 | `2_MINEDUC_RegistrosAdministrativos_2023-2024Inicio.csv` | ~miles | `fact_bachilleres` |

---

## Modelo relacional (Silver)

```
dim_tiempo ──────────────────────────────────────┐
dim_geografia ─────────────────────────┐          │
                                       │          │
                              fact_vab_provincial │
                              fact_censo_actividad│
                              fact_bachilleres    │
                              fact_directorio_emp.│
                                                  │
                                      fact_macro_anual
                                      fact_indicadores_diarios
                                      fact_iee_mensual
                                      fact_vab_nacional
                                      fact_empleo
dim_empresa ──────────────────────────fact_empresa_ranking
```

---

## Vistas Gold

| Vista | Propósito | Dashboard |
|-------|-----------|-----------|
| `gold_pib_tendencia` | PIB real anual + ciclo económico | P1 |
| `gold_empleo_tendencia` | Tasas de empleo/desempleo ENEMDU | P1/P2 |
| `gold_petroleo_30dias` | WTI + Riesgo País con MA-30d | P1 |
| `gold_bachilleres_vs_empresas` | Bachilleres 3er año vs empresas activas | P3 |
| `gold_iee_sectorial_tendencia` ⭐ | IEE por sector + sentimiento + MoM | P1/P2 |
| `gold_vab_provincial_ranking` ⭐ | VAB + empresas + empleo por provincia | P2 |

> ⭐ Vistas propias del 6to ciclo — justificadas en el informe técnico.

---

## Decisiones de limpieza

| Problema | Fuente | Solución |
|----------|--------|----------|
| 6 filas de metadatos antes del header | IEE | `header=None` + búsqueda dinámica de fila header |
| Estructura pivotada doble | ENEMDU | `melt()` sobre columnas de área geográfica |
| Archivo de 373 MB | bi_ranking.csv | `chunksize=50_000` + filtro por años |
| Headers en fila 4 | directorio_companias.xlsx | Búsqueda dinámica del header real |
| Encoding latin-1 | bi_ranking, bi_compania, MINEDUC | `encoding='latin-1'` explícito |
| Nombres de provincia con tildes | Todos | `unidecode()` + `.upper().strip()` |
| Wide format VAB provincial | CNR | `melt()` sobre columnas 2007–2018 |

---

## Criterios de evaluación cubiertos

| Criterio | Peso | Estado |
|----------|------|--------|
| Diagrama de arquitectura + ER | 10% | Pendiente (entregar semana 1) |
| 12 tablas Silver cargadas | 25% | ✅ Implementado |
| FK + 6 vistas Gold | 20% | ✅ Implementado |
| Pipeline watchdog RPA | 20% | ✅ Implementado (`--watch`) |
| Dashboard 3 preguntas | 15% | Pendiente (semanas 5-6) |
| Análisis ejecutivo + acuerdo RPA | 10% | Pendiente (semanas 6-7) |

---

*Desarrollado en el marco del Practicum Interno UTPL — 6to Ciclo — 2026*
