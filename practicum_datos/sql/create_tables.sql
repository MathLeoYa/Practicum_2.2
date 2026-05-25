
CREATE TABLE dim_ubicacion (
    id_ubicacion SERIAL PRIMARY KEY,
    provincia VARCHAR(100),
    cod_provincia INTEGER,
    canton VARCHAR(100),
    cod_canton INTEGER,
    parroquia VARCHAR(100),
    zona VARCHAR(50),
    regimen_escolar VARCHAR(50)
);

CREATE TABLE dim_institucion (
    cod_amie VARCHAR(20) PRIMARY KEY,
    nombre_institucion VARCHAR(255),
    sostenimiento VARCHAR(50),
    area VARCHAR(50),
    nivel_educacion VARCHAR(100),
    id_ubicacion INTEGER,
    CONSTRAINT fk_ubicacion FOREIGN KEY (id_ubicacion) REFERENCES dim_ubicacion(id_ubicacion)
);

CREATE TABLE fact_matricula (
    id_matricula SERIAL PRIMARY KEY,
    cod_amie VARCHAR(20),
    anio_lectivo VARCHAR(50),
    total_estudiantes INTEGER,
    estudiantes_f INTEGER,
    estudiantes_m INTEGER,
    total_docentes INTEGER,
    docentes_f INTEGER,
    docentes_m INTEGER,
    ratio_est_docente NUMERIC(10,2),
    CONSTRAINT fk_institucion FOREIGN KEY (cod_amie) REFERENCES dim_institucion(cod_amie)
);