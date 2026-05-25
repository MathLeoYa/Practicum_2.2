import sys
import os
import pandas as pd
from dotenv import load_dotenv

# 1. Ajuste de ruta para poder importar config.py y el archivo .env
ruta_raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(ruta_raiz)

from config import RUTA_CSV

# Cargar las variables del archivo .env
load_dotenv(os.path.join(ruta_raiz, '.env'))

from extract import extraer_datos_csv
from transform import (
    limpiar_datos_base, 
    construir_dim_ubicacion, 
    construir_dim_institucion, 
    construir_fact_matricula
)
from load import cargar_postgres

def ejecutar_pipeline(ruta_archivo):
    print("Iniciando Pipeline ETL...")
    
    # 1. EXTRACCIÓN
    print("1. Extrayendo datos...")
    df_raw = extraer_datos_csv(ruta_archivo)
    
    # 2. TRANSFORMACIÓN
    print("2. Transformando datos...")
    df_limpio = limpiar_datos_base(df_raw)
    dim_ubicacion = construir_dim_ubicacion(df_limpio)
    dim_institucion = construir_dim_institucion(df_limpio, dim_ubicacion)
    fact_matricula = construir_fact_matricula(df_limpio)
    
    print("Transformación completada con éxito.")
    
    # 3. CARGA 
    print("3. Cargando en PostgreSQL...")
    
    # Armamos el diccionario extrayendo los valores de tu .env
    credenciales_db = {
        'usuario': os.getenv('DB_USER', 'postgres'),
        'password': os.getenv('DB_PASSWORD'),
        'host': os.getenv('DB_HOST', 'localhost'),
        'puerto': os.getenv('DB_PORT', '5432'),
        'bd': os.getenv('DB_NAME')
    }
    
    # Verificación de seguridad rápida
    if not credenciales_db['password'] or not credenciales_db['bd']:
        raise ValueError("Faltan credenciales en el archivo .env")

    # Llamamos a la función enviando el cuarto parámetro
    cargar_postgres(dim_ubicacion, dim_institucion, fact_matricula, credenciales_db)
    
    return dim_ubicacion, dim_institucion, fact_matricula

if __name__ == "__main__":
    dim_ub, dim_inst, fact_mat = ejecutar_pipeline(RUTA_CSV)