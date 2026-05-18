import re
import pandas as pd
import sqlalchemy
from google import adk
from database import obtener_motor_bd, consultar_cloud_sql, MAPA_ESTADOS

def buscar_clientes_por_criterio(termino_busqueda: str = "") -> str:
    try:
        df = consultar_cloud_sql(termino_busqueda)
        return df.to_string() if not df.empty else "No se encontraron resultados en la base de datos de producción."
    except Exception as e:
        print(f"Error al consultar Cloud SQL: {e}")
        return f"Hubo un error al conectar con la base de datos: {e}. Por favor, verifica la configuración."

def ejecutar_consulta_sql_avanzada(query_sql: str) -> str:
    query_limpia = query_sql.strip().upper()
    if not query_limpia.startswith("SELECT"):
        return "Error de seguridad: SÓLO se permiten consultas de tipo SELECT. No puedes modificar la base de datos."
    
    # Bloquear ejecución de múltiples sentencias para evitar inyecciones apiladas
    if ";" in query_limpia:
        return "Error de seguridad: No se permiten múltiples sentencias SQL (uso de punto y coma)."
        
    # Bloquear palabras clave que modifican el esquema o los datos (DML/DDL)
    palabras_prohibidas = r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|TRUNCATE|GRANT|REVOKE|EXEC|EXECUTE|MERGE|CALL|COMMIT|ROLLBACK|REPLACE)\b"
    if re.search(palabras_prohibidas, query_limpia):
        return "Error de seguridad: La consulta contiene comandos de escritura o modificación no permitidos."
        
    # Bloquear acceso a tablas del sistema de PostgreSQL y funciones peligrosas (Exfiltración de metadatos / DoS / LFI)
    palabras_sistema = r"\b(PG_[A-Z0-9_]+|INFORMATION_SCHEMA)\b"
    if re.search(palabras_sistema, query_limpia):
        return "Error de seguridad: No está permitido consultar catálogos del sistema ni usar funciones internas de PostgreSQL."
    
    engine, connector = obtener_motor_bd()
    try:
        with engine.connect() as conn:
            df = pd.read_sql(sqlalchemy.text(query_sql), con=conn)
            if df.empty:
                 return "La consulta se ejecutó correctamente pero no arrojó resultados."
            return "Resultado de la consulta SQL (Mostrando max 50 filas):\n" + df.head(50).to_string()
    except Exception as e:
        return f"Error de sintaxis o ejecución SQL: {e}"

def revisar_clientes_abandonados() -> str:
    engine, connector = obtener_motor_bd()
    try:
        with engine.connect() as conn:
            query = sqlalchemy.text("SELECT nombre, empresa, _estado FROM clientes WHERE _estado < 8 AND fecha_ultima_actividad < NOW() - INTERVAL '7 days'")
            result = conn.execute(query).fetchall()

        if not result:
            return "¡Buenas noticias! No tienes clientes abandonados por más de 7 días. Todos tienen seguimiento reciente."

        alertas = "⚠️ He detectado los siguientes clientes inactivos por más de 7 días:\n"
        for row in result:
            estado_txt = MAPA_ESTADOS.get(row[2], 'Desconocido')
            alertas += f"- **{row[0]}** de {row[1]} (Etapa actual: {estado_txt})\n"
        return alertas + "\nTe sugiero darles seguimiento hoy mismo."
    except Exception as e:
        return f"Error al revisar clientes abandonados: {e}"

data_query_agent = adk.Agent(
    name="DataQueryAgent",
    model="gemini-2.5-flash",
    instruction="Eres un especialista en consultar bases de datos. Tu única función es usar las herramientas para buscar clientes, ejecutar SQL de solo lectura (SELECT) y revisar clientes abandonados. Eres directo y preciso. Usa la herramienta 'revisar_clientes_abandonados' cuando se te pida explícitamente.",
    tools=[buscar_clientes_por_criterio, ejecutar_consulta_sql_avanzada, revisar_clientes_abandonados]
)