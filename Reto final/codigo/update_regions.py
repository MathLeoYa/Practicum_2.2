import psycopg

conn = psycopg.connect('postgresql://postgres:password@localhost:5432/macroentorno_utpl')
cur = conn.cursor()

query = """
UPDATE silver.dim_geografia SET region = 'Costa' WHERE provincia LIKE 'MANAB%';
"""

cur.execute(query)
conn.commit()

# Recreate the gold views so they pick up the changes if needed
print("Regiones actualizadas en la base de datos.")
