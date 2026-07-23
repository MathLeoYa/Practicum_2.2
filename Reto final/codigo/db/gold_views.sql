-- =============================================================================
-- gold_views.sql
-- Pipeline Macroentorno Ecuador - 6to Ciclo UTPL
-- 6 Vistas Gold: 4 base del reto + 2 propias justificadas
-- NOTA: la funcion norm_prov se crea ANTES de las vistas que la usan
-- =============================================================================

SET search_path TO silver, public;

CREATE SCHEMA IF NOT EXISTS gold;

-- =============================================================================
-- FUNCION AUXILIAR (declarada primero para que las vistas puedan usarla)
-- =============================================================================
CREATE OR REPLACE FUNCTION silver.norm_prov(s TEXT) RETURNS TEXT AS $$
BEGIN
    RETURN UPPER(TRIM(
        TRANSLATE(
            COALESCE(s, ''),
            'ÁÉÍÓÚÄËÏÖÜáéíóúäëïöüÑñ',
            'AEIOUAEIOUaeiouaeiouNn'
        )
    ));
END;
$$ LANGUAGE plpgsql IMMUTABLE;

-- =============================================================================
-- VISTA 1 (base): Evolucion del PIB con clasificacion de ciclo economico
-- =============================================================================
CREATE OR REPLACE VIEW gold.pib_tendencia AS
SELECT
    t.anio,
    m.pib_real_musd,
    m.pib_percapita_nominal,
    m.variacion_pib_pct,
    CASE
        WHEN m.variacion_pib_pct >  3   THEN 'Crecimiento fuerte'
        WHEN m.variacion_pib_pct >  0   THEN 'Crecimiento moderado'
        WHEN m.variacion_pib_pct =  0   THEN 'Estancamiento'
        WHEN m.variacion_pib_pct < -3   THEN 'Recesion profunda'
        ELSE                                 'Contraccion'
    END AS clasificacion_ciclo,
    LAG(m.pib_real_musd) OVER (ORDER BY t.anio) AS pib_anio_anterior,
    ROUND(
        (m.pib_real_musd - LAG(m.pib_real_musd) OVER (ORDER BY t.anio))
        / NULLIF(LAG(m.pib_real_musd) OVER (ORDER BY t.anio), 0) * 100, 2
    ) AS variacion_calculada_pct
FROM silver.fact_macro_anual m
JOIN silver.dim_tiempo t USING (id_tiempo)
WHERE m.pib_real_musd IS NOT NULL
ORDER BY t.anio;

-- =============================================================================
-- VISTA 2 (base): Tasa de desempleo trimestral historica (ENEMDU)
-- =============================================================================
CREATE OR REPLACE VIEW gold.empleo_tendencia AS
SELECT
    anio,
    trimestre,
    periodo_texto,
    area,
    MAX(CASE WHEN indicador ILIKE '%desempleo (%)%'
              AND indicador NOT ILIKE '%abierto%'
              AND indicador NOT ILIKE '%oculto%'
             THEN valor_pct END) AS tasa_desempleo_pct,
    MAX(CASE WHEN indicador ILIKE '%adecuado%' OR indicador ILIKE '%pleno%'
             THEN valor_pct END) AS tasa_empleo_adecuado_pct,
    MAX(CASE WHEN indicador ILIKE '%subempleo (%)%'
              AND indicador NOT ILIKE '%insuficiencia%'
             THEN valor_pct END) AS tasa_subempleo_pct,
    MAX(CASE WHEN indicador ILIKE '%empleo bruto%'
             THEN valor_pct END) AS tasa_empleo_bruto_pct
FROM silver.fact_empleo
GROUP BY anio, trimestre, periodo_texto, area
ORDER BY anio, trimestre, area;

-- =============================================================================
-- VISTA 3 (base): Promedio movil 30 dias del precio WTI
-- =============================================================================
CREATE OR REPLACE VIEW gold.petroleo_30dias AS
SELECT
    fecha,
    precio_petroleo_wti,
    riesgo_pais_pb,
    ROUND(AVG(precio_petroleo_wti) OVER (
        ORDER BY fecha
        ROWS BETWEEN 29 PRECEDING AND CURRENT ROW
    ), 2) AS wti_promedio_30d,
    ROUND(AVG(riesgo_pais_pb) OVER (
        ORDER BY fecha
        ROWS BETWEEN 29 PRECEDING AND CURRENT ROW
    ), 0) AS riesgo_promedio_30d,
    EXTRACT(YEAR  FROM fecha)::INTEGER AS anio,
    EXTRACT(MONTH FROM fecha)::INTEGER AS mes
FROM silver.fact_indicadores_diarios
WHERE precio_petroleo_wti IS NOT NULL
   OR riesgo_pais_pb IS NOT NULL
ORDER BY fecha;

-- =============================================================================
-- VISTA 4 (base): Bachilleres vs. empresas activas por provincia (P3)
-- Usa norm_prov() definida arriba
-- =============================================================================
CREATE OR REPLACE VIEW gold.bachilleres_vs_empresas AS
WITH bachilleres AS (
    SELECT
        g.provincia,
        SUM(fb.bachilleres_3er_anio)  AS bachilleres_3er_anio,
        SUM(fb.bachilleres_1er_anio)  AS bachilleres_1er_anio,
        SUM(fb.bachilleres_2do_anio)  AS bachilleres_2do_anio,
        SUM(fb.total_estudiantes)     AS total_estudiantes_bach,
        COUNT(DISTINCT fb.amie)       AS instituciones_educativas
    FROM silver.fact_bachilleres fb
    JOIN silver.dim_geografia g ON fb.id_geo = g.id_geo
    WHERE fb.anio_lectivo LIKE '2023-2024%'
    GROUP BY g.provincia
),
empresas AS (
    SELECT
        provincia,
        COUNT(*)                                                    AS total_empresas_activas,
        COUNT(*) FILTER (WHERE tipo ILIKE '%anonima%'
                            OR tipo ILIKE '%anonima%')             AS empresas_anonimas,
        COUNT(*) FILTER (WHERE tipo ILIKE '%responsabilidad%')     AS empresas_srl
    FROM silver.fact_directorio_empresas
    WHERE situacion_legal ILIKE '%activa%'
    GROUP BY provincia
)
SELECT
    COALESCE(b.provincia, e.provincia)      AS provincia,
    COALESCE(b.bachilleres_3er_anio, 0)     AS bachilleres_3er_anio,
    COALESCE(b.total_estudiantes_bach, 0)   AS total_estudiantes_bach,
    COALESCE(b.instituciones_educativas, 0) AS instituciones_educativas,
    COALESCE(e.total_empresas_activas, 0)   AS empresas_activas,
    COALESCE(e.empresas_anonimas, 0)        AS empresas_anonimas,
    CASE
        WHEN COALESCE(e.total_empresas_activas, 0) = 0 THEN NULL
        ELSE ROUND(b.bachilleres_3er_anio::NUMERIC / e.total_empresas_activas, 4)
    END AS ratio_bachilleres_por_empresa,
    RANK() OVER (ORDER BY COALESCE(b.bachilleres_3er_anio, 0) DESC)       AS ranking_bachilleres,
    RANK() OVER (ORDER BY COALESCE(e.total_empresas_activas, 0) DESC)     AS ranking_empresas
FROM bachilleres b
FULL OUTER JOIN empresas e
    ON silver.norm_prov(b.provincia) = silver.norm_prov(e.provincia)
ORDER BY bachilleres_3er_anio DESC NULLS LAST;

-- =============================================================================
-- VISTA 5 (propia 6to ciclo): IEE sectorial con sentimiento y variacion MoM
-- Justificacion: indicador lider que anticipa cambios en PIB.
-- La UTPL puede usarlo para ajustar oferta de programas por sector.
-- =============================================================================
CREATE OR REPLACE VIEW gold.iee_sectorial_tendencia AS
SELECT
    fecha,
    EXTRACT(YEAR  FROM fecha)::INTEGER AS anio,
    EXTRACT(MONTH FROM fecha)::INTEGER AS mes,
    iee_global,
    comercio,
    construccion,
    manufactura,
    servicios,
    ROUND(iee_global   - LAG(iee_global)   OVER (ORDER BY fecha), 2) AS var_mom_global,
    ROUND(comercio     - LAG(comercio)     OVER (ORDER BY fecha), 2) AS var_mom_comercio,
    ROUND(construccion - LAG(construccion) OVER (ORDER BY fecha), 2) AS var_mom_construccion,
    ROUND(manufactura  - LAG(manufactura)  OVER (ORDER BY fecha), 2) AS var_mom_manufactura,
    ROUND(servicios    - LAG(servicios)    OVER (ORDER BY fecha), 2) AS var_mom_servicios,
    CASE
        WHEN iee_global > 55 THEN 'Muy optimista'
        WHEN iee_global > 50 THEN 'Optimista'
        WHEN iee_global = 50 THEN 'Neutral'
        WHEN iee_global > 45 THEN 'Pesimista'
        ELSE                      'Muy pesimista'
    END AS sentimiento,
    (ARRAY['Comercio','Construccion','Manufactura','Servicios'])[
        ARRAY_POSITION(
            ARRAY[comercio, construccion, manufactura, servicios],
            GREATEST(comercio, construccion, manufactura, servicios)
        )
    ] AS sector_lider
FROM silver.fact_iee_mensual
ORDER BY fecha;

-- =============================================================================
-- VISTA 6 (propia 6to ciclo): VAB provincial con ranking y empresas activas
-- Justificacion: cruza productividad (VAB) con empresas para identificar
-- provincias subatendidas: territorios prioritarios de expansion UTPL.
-- =============================================================================
CREATE OR REPLACE VIEW gold.vab_provincial_ranking AS
WITH vab_ultimo AS (
    SELECT
        g.provincia,
        SUM(v.vab_miles_usd) AS vab_total_miles_usd
    FROM silver.fact_vab_provincial v
    JOIN silver.dim_geografia g ON v.id_geo = g.id_geo
    WHERE v.anio = (SELECT MAX(anio) FROM silver.fact_vab_provincial)
    GROUP BY g.provincia
),
empresas_prov AS (
    SELECT
        g.provincia,
        COUNT(*) AS empresas_activas
    FROM silver.fact_directorio_empresas e
    JOIN silver.dim_geografia g ON e.id_geo = g.id_geo
    WHERE e.situacion_legal ILIKE '%activa%'
    GROUP BY g.provincia
),
empleo_prov AS (
    SELECT
        g.provincia,
        SUM(c.ocupada)    AS total_ocupados,
        SUM(c.desocupada) AS total_desocupados,
        ROUND(
            SUM(c.desocupada)::NUMERIC / NULLIF(SUM(c.ocupada + c.desocupada), 0) * 100, 2
        ) AS tasa_desempleo_censo
    FROM silver.fact_censo_actividad c
    JOIN silver.dim_geografia g ON c.id_geo = g.id_geo
    WHERE c.area ILIKE 'total%'
    GROUP BY g.provincia
),
provincias AS (
    SELECT DISTINCT provincia, region 
    FROM silver.dim_geografia 
    WHERE provincia IS NOT NULL AND provincia != ''
)
SELECT
    p.provincia,
    p.region,
    COALESCE(v.vab_total_miles_usd, 0)   AS vab_total_miles_usd,
    COALESCE(ep.empresas_activas, 0)     AS empresas_activas,
    COALESCE(el.total_ocupados, 0)       AS total_ocupados,
    COALESCE(el.total_desocupados, 0)    AS total_desocupados,
    el.tasa_desempleo_censo,
    CASE WHEN COALESCE(ep.empresas_activas, 0) = 0 THEN NULL
         ELSE ROUND(v.vab_total_miles_usd / ep.empresas_activas, 2)
    END AS vab_por_empresa,
    RANK() OVER (ORDER BY COALESCE(v.vab_total_miles_usd, 0) DESC)    AS ranking_vab,
    RANK() OVER (ORDER BY COALESCE(ep.empresas_activas, 0) DESC)      AS ranking_empresas,
    RANK() OVER (ORDER BY COALESCE(el.tasa_desempleo_censo, 100) ASC) AS ranking_empleo
FROM provincias p
LEFT JOIN vab_ultimo    v  ON p.provincia = v.provincia
LEFT JOIN empresas_prov ep ON p.provincia = ep.provincia
LEFT JOIN empleo_prov   el ON p.provincia = el.provincia
ORDER BY vab_total_miles_usd DESC NULLS LAST;
