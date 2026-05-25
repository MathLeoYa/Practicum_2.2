import pandas as pd
import logging

# Configuración básica de logging para buenas prácticas
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

def extraer_datos_csv(ruta_archivo: str) -> pd.DataFrame:
    
    try:
        
        # Lectura del CSV o
        df = pd.read_csv(
            ruta_archivo,
            sep=';', 
            encoding='latin-1',
            low_memory=False # Evita warnings de tipos de datos mixtos en archivos grandes
        )
        
        logging.info(f"Extracción exitosa. Filas: {df.shape[0]}, Columnas: {df.shape[1]}")
        return df
        
    except FileNotFoundError:
        logging.error(f"Error: No se encontró el archivo en la ruta {ruta_archivo}.")
        raise
    except Exception as e:
        logging.error(f"Error inesperado durante la extracción: {e}")
        raise