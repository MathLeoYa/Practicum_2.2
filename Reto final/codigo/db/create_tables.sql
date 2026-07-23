-- =============================================================================
-- create_tables.sql
-- Pipeline Macroentorno Ecuador · 6to Ciclo UTPL
-- DDL completo: 2 dimensiones + 10 tablas de hechos = 12 tablas Silver
-- =============================================================================

-- Crear schema de trabajo
DROP SCHEMA IF EXISTS silver CASCADE;
CREATE SCHEMA silver;
SET search_path TO silver, public;

-- -----------------------------------------------------------------------------
-- DIMENSIONES
-- -----------------------------------------------------------------------------

-- Dimensión geográfica compartida (VAB provincial, Supercias, MINEDUC)
CREATE TABLE IF NOT EXISTS dim_geografia (
    id_geo        SERIAL PRIMARY KEY,
    provincia     VARCHAR(80)  NOT NULL,
    cod_provincia SMALLINT,
    region        VARCHAR(20),
    canton        VARCHAR(80),
    cod_canton    INTEGER,
    UNIQUE (provincia, canton)
);

-- Dimensión temporal
CREATE TABLE IF NOT EXISTS dim_tiempo (
    id_tiempo  SERIAL PRIMARY KEY,
    fecha      DATE    NOT NULL UNIQUE,
    anio       SMALLINT NOT NULL,
    mes        SMALLINT,
    trimestre  SMALLINT
);

-- -----------------------------------------------------------------------------
-- BLOQUE 1 – BANCO CENTRAL DEL ECUADOR (5 tablas)
-- -----------------------------------------------------------------------------

-- 1. PIB anual (retropolacion_1965_2024p)
CREATE TABLE IF NOT EXISTS fact_macro_anual (
    id                    SERIAL PRIMARY KEY,
    id_tiempo             INTEGER REFERENCES dim_tiempo(id_tiempo) ON DELETE CASCADE,
    pib_real_musd         NUMERIC(16, 2),
    pib_percapita_nominal NUMERIC(10, 2),
    variacion_pib_pct     NUMERIC(7, 4),
    UNIQUE (id_tiempo)
);

-- 2. Indicadores diarios (WTI + Riesgo País)
CREATE TABLE IF NOT EXISTS fact_indicadores_diarios (
    id                  SERIAL PRIMARY KEY,
    fecha               DATE    NOT NULL UNIQUE,
    precio_petroleo_wti NUMERIC(8, 2),
    riesgo_pais_pb      INTEGER
);

-- 3. IEE mensual (Índice Expectativas Empresariales)
CREATE TABLE IF NOT EXISTS fact_iee_mensual (
    id           SERIAL PRIMARY KEY,
    fecha        DATE    NOT NULL UNIQUE,
    iee_global   NUMERIC(6, 2),
    comercio     NUMERIC(6, 2),
    construccion NUMERIC(6, 2),
    manufactura  NUMERIC(6, 2),
    servicios    NUMERIC(6, 2)
);

-- 4. VAB nacional por sector CIIU (anual, real, millones USD)
CREATE TABLE IF NOT EXISTS fact_vab_nacional (
    id          SERIAL PRIMARY KEY,
    anio        SMALLINT     NOT NULL,
    sector_ciiu VARCHAR(10)  NOT NULL,
    sector_nombre VARCHAR(200),
    vab_real_musd   NUMERIC(16, 4),
    vab_nominal_musd NUMERIC(16, 4),
    UNIQUE (anio, sector_ciiu)
);

-- 5. VAB provincial por sector (CNR 2007-2018)
CREATE TABLE IF NOT EXISTS fact_vab_provincial (
    id              SERIAL PRIMARY KEY,
    id_geo          INTEGER REFERENCES dim_geografia(id_geo) ON DELETE CASCADE,
    anio            SMALLINT    NOT NULL,
    sector_ciiu     VARCHAR(10),
    sector_nombre   VARCHAR(200),
    vab_miles_usd   NUMERIC(18, 4),
    UNIQUE (id_geo, anio, sector_ciiu)
);

-- -----------------------------------------------------------------------------
-- BLOQUE 2 – INEC (2 tablas)
-- -----------------------------------------------------------------------------

-- 6. Empleo ENEMDU trimestral
CREATE TABLE IF NOT EXISTS fact_empleo (
    id             SERIAL PRIMARY KEY,
    anio           SMALLINT     NOT NULL,
    trimestre      SMALLINT     NOT NULL,
    periodo_texto  VARCHAR(15),
    indicador      VARCHAR(150) NOT NULL,
    area           VARCHAR(20)  NOT NULL,  -- Nacional, Urbana, Rural, Quito, Guayaquil, Cuenca
    valor_pct      NUMERIC(10, 6),
    UNIQUE (anio, trimestre, indicador, area)
);

-- 7. Censo 2022 – actividad laboral por provincia
CREATE TABLE IF NOT EXISTS fact_censo_actividad (
    id                     SERIAL PRIMARY KEY,
    id_geo                 INTEGER REFERENCES dim_geografia(id_geo) ON DELETE CASCADE,
    area                   VARCHAR(10)  NOT NULL,  -- Total, Urbana, Rural
    sexo                   VARCHAR(10)  NOT NULL,  -- Total, Hombres, Mujeres
    total_personas_15mas   INTEGER,
    ocupada                INTEGER,
    desocupada             INTEGER,
    fuera_fuerza_trabajo   INTEGER,
    UNIQUE (id_geo, area, sexo)
);

-- -----------------------------------------------------------------------------
-- BLOQUE 3 – SUPERCIAS y MINEDUC (3 tablas)
-- -----------------------------------------------------------------------------

-- 8. Dimensión empresa (catálogo bi_compania)
CREATE TABLE IF NOT EXISTS dim_empresa (
    expediente  INTEGER PRIMARY KEY,
    ruc         BIGINT,
    nombre      VARCHAR(250),
    tipo        VARCHAR(50),
    pro_codigo  SMALLINT,
    provincia   VARCHAR(80)
);

-- 9. Ranking financiero Supercias (bi_ranking – años recientes)
CREATE TABLE IF NOT EXISTS fact_empresa_ranking (
    id                  SERIAL PRIMARY KEY,
    anio                SMALLINT  NOT NULL,
    expediente          INTEGER,
    posicion_general    INTEGER,
    ingresos_ventas     NUMERIC(18, 2),
    activos             NUMERIC(18, 2),
    patrimonio          NUMERIC(18, 2),
    utilidad_ejercicio  NUMERIC(18, 2),
    n_empleados         INTEGER,
    ciiu_n1             SMALLINT,
    ciiu_n6             BIGINT,
    roe                 NUMERIC(30, 4),
    roa                 NUMERIC(30, 4),
    UNIQUE (anio, expediente)
);

-- 10. Directorio de empresas activas (directorio_companias – para P3)
CREATE TABLE IF NOT EXISTS fact_directorio_empresas (
    id                 SERIAL PRIMARY KEY,
    expediente         INTEGER,
    ruc                VARCHAR(15),
    nombre             VARCHAR(300),
    situacion_legal    VARCHAR(20),
    fecha_constitucion DATE,
    tipo               VARCHAR(50),
    pais               VARCHAR(50),
    region             VARCHAR(20),
    provincia          VARCHAR(80),
    canton             VARCHAR(80),
    ciudad             VARCHAR(80),
    id_geo             INTEGER REFERENCES dim_geografia(id_geo) ON DELETE SET NULL,
    UNIQUE (expediente)
);

-- 11. Bachilleres por institución MINEDUC (AMIE 2023-2024)
CREATE TABLE IF NOT EXISTS fact_bachilleres (
    id                   SERIAL PRIMARY KEY,
    anio_lectivo         VARCHAR(20)  NOT NULL,
    amie                 VARCHAR(20),
    nombre_institucion   VARCHAR(250),
    id_geo               INTEGER REFERENCES dim_geografia(id_geo) ON DELETE SET NULL,
    nivel_educacion      VARCHAR(100),
    sostenimiento        VARCHAR(30),
    modalidad            VARCHAR(30),
    area                 VARCHAR(10),
    total_estudiantes    INTEGER,
    bachilleres_1er_anio INTEGER,
    bachilleres_2do_anio INTEGER,
    bachilleres_3er_anio INTEGER,   -- proxy de próximos graduandos
    UNIQUE (amie, anio_lectivo)
);

-- -----------------------------------------------------------------------------
-- ÍNDICES para mejorar rendimiento de joins
-- -----------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_fact_macro_anual_tiempo    ON fact_macro_anual(id_tiempo);
CREATE INDEX IF NOT EXISTS idx_fact_diarios_fecha         ON fact_indicadores_diarios(fecha);
CREATE INDEX IF NOT EXISTS idx_fact_iee_fecha             ON fact_iee_mensual(fecha);
CREATE INDEX IF NOT EXISTS idx_fact_vab_nacional_anio     ON fact_vab_nacional(anio);
CREATE INDEX IF NOT EXISTS idx_fact_vab_prov_geo_anio     ON fact_vab_provincial(id_geo, anio);
CREATE INDEX IF NOT EXISTS idx_fact_empleo_anio_trim      ON fact_empleo(anio, trimestre);
CREATE INDEX IF NOT EXISTS idx_fact_censo_geo             ON fact_censo_actividad(id_geo);
CREATE INDEX IF NOT EXISTS idx_fact_ranking_anio_exp      ON fact_empresa_ranking(anio, expediente);
CREATE INDEX IF NOT EXISTS idx_fact_directorio_prov       ON fact_directorio_empresas(provincia);
CREATE INDEX IF NOT EXISTS idx_fact_bachilleres_geo       ON fact_bachilleres(id_geo);
CREATE INDEX IF NOT EXISTS idx_dim_geo_provincia          ON dim_geografia(provincia);
