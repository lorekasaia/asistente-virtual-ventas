import re
import logging
import pandas as pd
import sqlalchemy
from google import adk
from database import obtener_motor_bd, consultar_cloud_sql, MAPA_ESTADOS

logger = logging.getLogger("BatiaAgent")

# Compilación de Regex a nivel global para optimizar el rendimiento del CPU
PATRON_PROHIBIDO_DML = re.compile(r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|TRUNCATE|GRANT|REVOKE|EXEC|EXECUTE|MERGE|CALL|COMMIT|ROLLBACK|REPLACE)\b")
PATRON_SISTEMA_PG = re.compile(r"\b(PG_[A-Z0-9_]+|INFORMATION_SCHEMA)\b")

def buscar_clientes_por_criterio(termino_busqueda: str = "") -> str:
    try:
        df = consultar_cloud_sql(termino_busqueda)
        if not df.empty:
            # Ocultar columnas de IDs por privacidad
            cols_privadas = [col for col in df.columns if col.lower() == 'id' or col.lower().endswith('_id')]
            df = df.drop(columns=cols_privadas, errors='ignore')
            return df.to_string()
        return "No se encontraron resultados en la base de datos de producción."
    except Exception as e:
        logger.error(f"Error en buscar_clientes_por_criterio: {e}", exc_info=True)
        return f"Hubo un error al conectar con la base de datos: {e}. Por favor, verifica la configuración."

def ejecutar_consulta_sql_avanzada(query_sql: str) -> str:
    query_limpia = query_sql.strip().upper()
    if not query_limpia.startswith("SELECT"):
        return "Error de seguridad: SÓLO se permiten análisis de lectura. No puedes modificar la base de datos."
    
    # Bloquear ejecución de múltiples sentencias para evitar inyecciones apiladas
    if ";" in query_limpia:
        return "Error de seguridad: No se permiten múltiples sentencias SQL (uso de punto y coma)."
        
    # Bloquear palabras clave que modifican el esquema o los datos (DML/DDL)
    if PATRON_PROHIBIDO_DML.search(query_limpia):
        return "Error de seguridad: La consulta contiene comandos de escritura o modificación no permitidos."
        
    # Bloquear acceso a tablas del sistema de PostgreSQL y funciones peligrosas (Exfiltración de metadatos / DoS / LFI)
    if PATRON_SISTEMA_PG.search(query_limpia):
        return "Error de seguridad: No está permitido consultar catálogos del sistema ni usar funciones internas de PostgreSQL."
    
    engine, connector = obtener_motor_bd()
    try:
        with engine.connect() as conn:
            # fetchmany(50) evita que Pandas colapse la RAM si la IA consulta tablas gigantes
            result = conn.execute(sqlalchemy.text(query_sql))
            rows = result.fetchmany(50)
            if not rows:
                return "El análisis se ejecutó correctamente pero no arrojó resultados."
            df = pd.DataFrame(rows, columns=result.keys())
            # Ocultar columnas de IDs por privacidad
            cols_privadas = [col for col in df.columns if col.lower() == 'id' or col.lower().endswith('_id')]
            df = df.drop(columns=cols_privadas, errors='ignore')
            return "Resultado del análisis predictivo y de ventas (Mostrando max 50 filas):\n" + df.to_string()
    except Exception as e:
        logger.error(f"Error en ejecutar_consulta_sql_avanzada: {e}", exc_info=True)
        return f"Error de sintaxis o al ejecutar el análisis: {e}"

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
        logger.error(f"Error en revisar_clientes_abandonados: {e}", exc_info=True)
        return f"Error al revisar clientes abandonados: {e}"

data_query_agent = adk.Agent(
    name="DataQueryAgent",
    model="gemini-2.5-flash",
    instruction="Eres un especialista en análisis de clientes. Tu única función es usar las herramientas para buscar clientes, hacer predicciones de venta, indicar razones de no venta y/o de contrato, y revisar clientes abandonados. Bajo ninguna circunstancia debes mencionar que haces o ejecutas consultas SQL. Eres analítico y preciso.",
    tools=[buscar_clientes_por_criterio, ejecutar_consulta_sql_avanzada, revisar_clientes_abandonados]
)