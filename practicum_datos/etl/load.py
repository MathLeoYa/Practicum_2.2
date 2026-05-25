from sqlalchemy import create_engine
import pandas as pd

def cargar_postgres(dim_ubicacion, dim_institucion, fact_matricula, credenciales):
    """
    Carga los DataFrames transformados en las tablas de PostgreSQL.
    """
    # 1. Cadena de conexión
    # Formato
# Usamos las llaves exactas que armamos en pipeline.py
    conn_string = f"postgresql://{credenciales['usuario']}:{credenciales['password']}@{credenciales['host']}:{credenciales['puerto']}/{credenciales['bd']}"    
    # 2. Motor de conexión
    engine = create_engine(conn_string)
    
    try:
        print("   - Conectando a PostgreSQL...")
        
        # 3. Carga dimensión Ubicación
        # Usamos if_exists='append' porque las tablas ya se crearon en pgadmin
        # Usamos index=False para que no intente subir el índice de Pandas
        print("   - Cargando dim_ubicacion...")
        dim_ubicacion.to_sql('dim_ubicacion', con=engine, if_exists='append', index=False)
        
        # 4. Carga dimensión Institución
        print("   - Cargando dim_institucion...")
        dim_institucion.to_sql('dim_institucion', con=engine, if_exists='append', index=False)
        
        # 5. Carga tabla de Hechos
        print("   - Cargando fact_matricula...")
        fact_matricula.to_sql('fact_matricula', con=engine, if_exists='append', index=False)
        
        print("\n ¡CARGA EXITOSA! Todos los datos están en PostgreSQL.")
        
    except Exception as e:
        print(f"\n Error durante la carga a la base de datos: {e}")
        raise e