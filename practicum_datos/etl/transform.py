import pandas as pd
import numpy as np
def limpiar_datos_base(df):

    """
    Realiza la limpieza inicial del dataset AMIE basándose en el análisis exploratorio.
    """
    # 1. Eliminar las filas fantasma (120,114 filas completamente vacías)
    df_limpio = df.dropna(how='all').copy()
    
    # 2. Renombrar columnas al formato del modelo relacional (PostgreSQL)
    renombres = {
        'ï»¿Anio_lectivo': 'anio_lectivo',
        'Anio_lectivo': 'anio_lectivo',
        'AMIE': 'cod_amie',
        'Provincia': 'provincia',
        'Cod_Provincia': 'cod_provincia',
        'Canton': 'canton',
        'Cod_Canton': 'cod_canton',
        'Docentes_Femenino': 'docentes_f',    
        'Docentes_Masculino': 'docentes_m',
        'Parroquia': 'parroquia',
        'Nombre_Institucion': 'nombre_institucion',
        'Total_Docentes': 'total_docentes',
        'Total_Estudiantes': 'total_estudiantes',
        'Estudiantes_Femenino': 'estudiantes_f',
        'Estudiantes_Masculino': 'estudiantes_m',
        'Tipo_Educacion': 'nivel_educacion',
        'Sostenimiento': 'sostenimiento',
        'Area': 'area',
        'Regimen_Escolar': 'regimen_escolar'
    }
    df_limpio = df_limpio.rename(columns=renombres)
    df_limpio.columns = [col.lower() for col in df_limpio.columns]
    
    # 3. Corregir tipos de datos (de float64 a int) tras quitar los nulos
    columnas_enteras = [
        'cod_provincia', 'cod_canton', 'total_docentes', 
        'docentes_f', 'docentes_m',
        'total_estudiantes', 'estudiantes_f', 'estudiantes_m'
    ]
    for col in columnas_enteras:
        if col in df_limpio.columns:
            # Llenamos con 0 posibles nulos residuales y convertimos a entero
            df_limpio[col] = df_limpio[col].fillna(0).astype(int)
            
    return df_limpio

def construir_dim_ubicacion(df_limpio):
    """
    Construye la tabla dimensional de ubicaciones únicas y genera su clave primaria.
    """
    # 1. Seleccionamos solo las columnas que pertenecen a esta dimensión
    cols_ubicacion = [
        'provincia', 'cod_provincia', 'canton', 'cod_canton',
        'parroquia', 'zona', 'regimen_escolar'
    ]
    
    # 2. Extraemos los valores únicos (eliminamos duplicados) y reiniciamos el índice
    dim_ub = df_limpio[cols_ubicacion].drop_duplicates().reset_index(drop=True)
    
    # 3. Creamos la clave primaria (id_ubicacion) que PostgreSQL espera como 'serial'
    # Usamos range de 1 hasta la longitud del dataframe + 1
    dim_ub.insert(0, 'id_ubicacion', range(1, len(dim_ub) + 1))
    
    return dim_ub

def construir_dim_institucion(df_limpio, dim_ub):
    """
    Construye la tabla dimensional de instituciones resolviendo la relación con dim_ubicacion,
    y asegurando que se conserve la información más reciente de la institución.
    """
    llaves_merge = [
        'provincia', 'cod_provincia', 'canton', 'cod_canton',
        'parroquia', 'zona', 'regimen_escolar'
    ]
    
    # 1. Hacemos el merge
    df_merged = pd.merge(df_limpio, dim_ub, on=llaves_merge, how='left')
    
    # Añadimos anio_lectivo temporalmente a la lista para poder ordenar
    cols_institucion = [
        'cod_amie', 'nombre_institucion', 'sostenimiento', 
        'area', 'nivel_educacion', 'id_ubicacion'
    ]
    cols_temp = cols_institucion + ['anio_lectivo']
    
    # 2. Extraemos los datos con el año
    df_temp = df_merged[cols_temp].copy()
    
    # 3. ORDENAMOS por anio_lectivo de forma descendente (el año más nuevo queda arriba)
    df_temp = df_temp.sort_values(by='anio_lectivo', ascending=False)
    
    # 4. Eliminamos duplicados por cod_amie quedándonos con el 'first' (el más reciente)
    dim_inst = df_temp[cols_institucion].drop_duplicates(subset=['cod_amie'], keep='first').reset_index(drop=True)
    
    return dim_inst


def construir_fact_matricula(df_limpio):
    """
    Construye la tabla de hechos de matrícula y calcula métricas derivadas.
    """
    # 1. Seleccionamos las columnas de la tabla de hechos
    cols_hechos = [
        'cod_amie', 'anio_lectivo', 'total_estudiantes',
        'docentes_f', 'docentes_m',
        'estudiantes_f', 'estudiantes_m', 'total_docentes'
    ]
    
    # Extraemos solo las columnas que existen en nuestro dataset limpio
    cols_presentes = [col for col in cols_hechos if col in df_limpio.columns]
    fact = df_limpio[cols_presentes].copy()
    
    # 2. TODO: Calcular ratio_est_docente con manejo de división por cero
    # Usamos np.where de NumPy: Si total_docentes es mayor a 0, dividimos; si no, ponemos 0 (o NaN)
    fact['ratio_est_docente'] = np.where(
        fact['total_docentes'] > 0,
        round(fact['total_estudiantes'] / fact['total_docentes'], 2),
        0.0  # Asignamos 0.0 cuando no hay docentes reportados para evitar el error Inf/NaN
    )
    
    # 3. Creamos la clave primaria (id_matricula) tipo serial
    fact.insert(0, 'id_matricula', range(1, len(fact) + 1))
    
    return fact





















