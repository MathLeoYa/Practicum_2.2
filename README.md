# \# Prácticum: Ingeniería de Datos con Dataset AMIE - MINEDUC Ecuador 🇪🇨

# 

# Este repositorio contiene la solución técnica al reto de Ingeniería, Analítica y Visualización de Datos del Prácticum Interno. El proyecto consiste en el diseño, desarrollo y orquestación de un pipeline ETL completo para procesar el Archivo Maestro de Instituciones Educativas (AMIE) del Ecuador, modelarlo en una base de datos relacional y extraer métricas analíticas.

# 

# \## 🎯 Objetivos del Proyecto

# 1\. \*\*Modelado Dimensional:\*\* Diseñar e implementar un modelo en estrella (Star Schema) normalizado a partir de un CSV desnormalizado gubernamental.

# 2\. \*\*Pipeline ETL:\*\* Desarrollar un proceso modular en Python (Extracción, Transformación y Carga) para limpiar datos reales, resolver problemas de calidad (codificación latin-1, valores nulos masivos, llaves duplicadas SCD) y calcular métricas derivadas.

# 3\. \*\*Análisis SQL:\*\* Responder preguntas de negocio sobre el sistema educativo ecuatoriano utilizando `JOINs` y funciones de agregación.

# 

# \## 🛠️ Stack Tecnológico

# \* \*\*Lenguaje:\*\* Python 3.x

# \* \*\*Procesamiento de Datos:\*\* Pandas, NumPy

# \* \*\*Base de Datos:\*\* PostgreSQL

# \* \*\*Conexión a BD:\*\* SQLAlchemy, psycopg2

# \* \*\*Gestión de Entorno:\*\* python-dotenv

# 

# \## 📁 Estructura del Repositorio

# 

# El proyecto sigue una arquitectura modular y organizada:

# 

# ```text

# practicum\_datos/

# ├── notebooks/

# │   └── 01\_exploracion.ipynb    # Análisis Exploratorio de Datos (EDA)

# ├── etl/

# │   ├── extract.py              # Lectura del CSV con encoding específico

# │   ├── transform.py            # Limpieza, normalización y reglas de negocio

# │   ├── load.py                 # Carga de datos hacia PostgreSQL mediante SQLAlchemy

# │   └── pipeline.py             # Orquestador del flujo ETL

# ├── sql/

# │   ├── create\_tables.sql       # DDL: Creación del modelo relacional (PKs y FKs)

# │   └── queries.sql             # Consultas analíticas para el dashboard

# ├── .env.example                # Plantilla de credenciales de base de datos

# ├── config.py                   # Configuración de rutas globales

# ├── requirements.txt            # Dependencias del proyecto

# └── README.md                   # Documentación principal

