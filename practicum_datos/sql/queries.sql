

-- ------------------------------------------------------------------------------
-- P1: ¿En qué provincias hay mayor carga docente (estudiantes por docente)?
-- Contexto: Analiza el periodo lectivo más reciente para identificar 
--           posibles focos de aulas sobrepobladas.
-- ------------------------------------------------------------------------------
SELECT 
    u.provincia, 
    SUM(f.total_estudiantes) AS total_estudiantes,
    SUM(f.total_docentes) AS total_docentes,
    ROUND(SUM(f.total_estudiantes)::numeric / NULLIF(SUM(f.total_docentes), 0), 1) AS ratio_estudiantes_por_docente
FROM fact_matricula f
JOIN dim_institucion i ON f.cod_amie = i.cod_amie
JOIN dim_ubicacion u ON i.id_ubicacion = u.id_ubicacion
WHERE f.anio_lectivo = '2023-2024 Inicio' 
GROUP BY u.provincia
ORDER BY ratio_estudiantes_por_docente DESC;


-- ------------------------------------------------------------------------------
-- P2: ¿En qué nivel educativo hay mayor brecha de género en la matrícula?
-- Contexto: Evalúa la equidad de género calculando el porcentaje de mujeres
--           matriculadas por nivel de educación en el periodo actual.
-- ------------------------------------------------------------------------------
SELECT 
    i.nivel_educacion, 
    SUM(f.estudiantes_f) AS mujeres, 
    SUM(f.estudiantes_m) AS hombres, 
    ROUND(100.0 * SUM(f.estudiantes_f) / NULLIF(SUM(f.total_estudiantes), 0), 1) AS pct_mujeres
FROM fact_matricula f
JOIN dim_institucion i ON f.cod_amie = i.cod_amie
WHERE f.anio_lectivo = '2023-2024 Inicio'
GROUP BY i.nivel_educacion
ORDER BY pct_mujeres ASC;


-- ------------------------------------------------------------------------------
-- P3: ¿Cómo evolucionó la matrícula en Loja entre 2015 y 2024?
-- Contexto: Análisis de serie de tiempo para visualizar la tendencia de 
--           cierre de instituciones y fluctuación de la matrícula en la provincia.
-- ------------------------------------------------------------------------------
SELECT 
    f.anio_lectivo, 
    COUNT(DISTINCT f.cod_amie) AS instituciones_activas, 
    SUM(f.total_estudiantes) AS total_estudiantes
FROM fact_matricula f
JOIN dim_institucion i ON f.cod_amie = i.cod_amie
JOIN dim_ubicacion u ON i.id_ubicacion = u.id_ubicacion
WHERE u.provincia = 'LOJA' 
  AND f.anio_lectivo >= '2015-2016 Inicio'
GROUP BY f.anio_lectivo
ORDER BY f.anio_lectivo ASC;