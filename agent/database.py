import os
import pandas as pd
import sqlalchemy
from google.cloud.sql.connector import Connector, IPTypes

# --- CONSTANTES Y MAPEOS ---
MAPA_ESTADOS = {
    1: 'Nuevo',
    2: 'Contactado',
    3: 'Calificado',
    4: 'En Proceso',
    5: 'Reunión Agendada',
    6: 'Cotizado',
    7: 'En Negociación',
    8: 'Cerrado (Ganado)',
    9: 'Cerrado (Perdido)'
}
# Invertir el mapa para buscar ID por nombre (insensible a mayúsculas)
MAPA_ESTADOS_INVERSO = {v.lower(): k for k, v in MAPA_ESTADOS.items()}

def obtener_motor_bd():
    """Función auxiliar para centralizar la conexión a Cloud SQL."""
    db_user = os.environ.get("DB_USER")
    db_pass = os.environ.get("DB_PASS")
    db_name = os.environ.get("DB_NAME")
    instance_connection_name = os.environ.get("INSTANCE_CONNECTION_NAME")
    if not all([db_user, db_pass, db_name, instance_connection_name]):
        raise ValueError("Faltan variables de entorno para Cloud SQL.")
    
    connector = Connector()
    def getconn():
        return connector.connect(instance_connection_name, "pg8000", user=db_user, password=db_pass, db=db_name, ip_type=IPTypes.PUBLIC)
    return sqlalchemy.create_engine("postgresql+pg8000://", creator=getconn), connector

def consultar_cloud_sql(termino_busqueda: str = "") -> pd.DataFrame:
    engine, connector = obtener_motor_bd()
    termino_limpio = termino_busqueda.strip().lower()
    if not termino_limpio or termino_limpio in ['todos', 'clientes', 'general', 'lista', 'información']:
        query = "SELECT * FROM clientes LIMIT 50"
    else:
        query = f"SELECT * FROM clientes WHERE nombre ILIKE '%{termino_busqueda}%' OR empresa ILIKE '%{termino_busqueda}%' OR notas ILIKE '%{termino_busqueda}%' LIMIT 50"
    
    with engine.connect() as conn:
        df = pd.read_sql(sqlalchemy.text(query), con=conn)
    connector.close()
    return df