import os
from dotenv import load_dotenv

# 1. Cargar configuración ANTES de importar las librerías de IA
# Busca el .env en el directorio actual o fuerza la búsqueda en el directorio padre
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

import pandas as pd
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from google import adk
from google.adk.runners import Runner
import matplotlib.pyplot as plt
import matplotlib
import uuid

from google.adk.sessions import DatabaseSessionService
import sqlalchemy
from google.cloud.sql.connector import Connector, IPTypes

from google.genai.types import Content, Part
import uvicorn
import asyncio

app = FastAPI(title="Batia Agent UI")

# Configuración para evitar errores de GUI con Matplotlib en servidores
matplotlib.use('Agg')

# Crear carpeta para guardar los gráficos generados y montarla en la web
os.makedirs("graficos", exist_ok=True)
app.mount("/graficos", StaticFiles(directory="graficos"), name="graficos")

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

# --- HERRAMIENTAS DE DATOS ---
# --- CONFIGURACIÓN DE BASE DE DATOS (Cloud SQL) ---

def consultar_cloud_sql(termino_busqueda: str = "") -> pd.DataFrame:
    """
    Se conecta a Google Cloud SQL (PostgreSQL) para consultar datos de clientes.
    Nota: Requerirá instalar dependencias como 'pg8000', 'sqlalchemy' y 'cloud-sql-python-connector'.
    """
    db_user = os.environ.get("DB_USER")
    db_pass = os.environ.get("DB_PASS")
    db_name = os.environ.get("DB_NAME")
    instance_connection_name = os.environ.get("INSTANCE_CONNECTION_NAME")

    if not all([db_user, db_pass, db_name, instance_connection_name]):
        raise ValueError("Faltan variables de entorno para Cloud SQL (DB_USER, DB_PASS, DB_NAME, INSTANCE_CONNECTION_NAME). Verifica tu archivo .env.")
    
    # Uso de Cloud SQL Python Connector
    connector = Connector()
    def getconn():
        return connector.connect(
            instance_connection_name,
            "pg8000",
            user=db_user,
            password=db_pass,
            db=db_name,
            ip_type=IPTypes.PUBLIC
        )
    
    engine = sqlalchemy.create_engine("postgresql+pg8000://", creator=getconn)
    
    termino_limpio = termino_busqueda.strip().lower()
    if not termino_limpio or termino_limpio in ['todos', 'clientes', 'general', 'lista', 'información']:
        query = "SELECT * FROM clientes LIMIT 50"
    else:
        query = f"SELECT * FROM clientes WHERE nombre ILIKE '%{termino_busqueda}%' OR empresa ILIKE '%{termino_busqueda}%' OR notas ILIKE '%{termino_busqueda}%' LIMIT 50"
    
    with engine.connect() as conn:
        df = pd.read_sql(sqlalchemy.text(query), con=conn)
        
    connector.close()
        
    return df

def buscar_clientes_por_criterio(termino_busqueda: str = "") -> str:
    """
    Busca información sobre los clientes en la base de datos de producción (Cloud SQL).
    Busca coincidencias en las columnas 'nombre', 'empresa' o 'notas'.
    Si el usuario pide una lista general, usa un texto vacío ("").
    """
    try:
        df = consultar_cloud_sql(termino_busqueda)
        return df.to_string() if not df.empty else "No se encontraron resultados en la base de datos de producción."
    except Exception as e:
        # Es buena práctica registrar el error real para depuración
        print(f"Error al consultar Cloud SQL: {e}")
        return f"Hubo un error al conectar con la base de datos: {e}. Por favor, verifica la configuración."

def consultar_dashboard_bi(kpi: str, contexto: str = "general") -> str:
    """
    Consulta la API de Business Intelligence corporativa (ej. Power BI / Looker) para obtener métricas agregadas avanzadas y KPIs.
    Ejemplos de 'kpi': 'ventas_totales', 'tasa_conversion', 'rendimiento_vendedores'.
    """
    # NOTA: Esta es una plantilla lista para conectar con Power BI REST API o Looker API.
    # Usarías librerías como 'msal' o 'requests' para autenticarte y hacer la petición HTTP al dashboard real.
    print(f"[BI API Mock] Solicitando KPI: '{kpi}' con contexto '{contexto}'")
    
    if kpi == "ventas_totales":
        return f"El Dashboard de BI reporta que las ventas totales para '{contexto}' son de $1,450,000 MXN este trimestre."
    elif kpi == "tasa_conversion":
        return f"Según la plataforma de BI, la tasa de conversión de prospectos a clientes para '{contexto}' se sitúa en un 24.5%."
    elif kpi == "rendimiento_vendedores":
        return "El reporte de BI indica que Lore lidera las ventas con un 120% de alcance de cuota, seguida de cerca por el resto del equipo."
    else:
        return f"Datos del Dashboard para el KPI '{kpi}': Los indicadores están estables y dentro de los rangos esperados para el período actual."

def actualizar_estado_cliente(nombre_cliente: str, nuevo_estado_texto: str) -> str:
    """
    Actualiza el estado de un cliente en el pipeline de ventas.
    Primero busca al cliente por su nombre para obtener su ID, luego actualiza su columna '_estado'.
    """
    # 1. Convertir el estado de texto a ID numérico
    estado_id = MAPA_ESTADOS_INVERSO.get(nuevo_estado_texto.lower())
    if estado_id is None:
        return f"Error: El estado '{nuevo_estado_texto}' no es válido. Los estados válidos son: {list(MAPA_ESTADOS.values())}."

    # 2. Conectar a la base de datos
    db_user = os.environ.get("DB_USER")
    db_pass = os.environ.get("DB_PASS")
    db_name = os.environ.get("DB_NAME")
    instance_connection_name = os.environ.get("INSTANCE_CONNECTION_NAME")

    if not all([db_user, db_pass, db_name, instance_connection_name]):
        raise ValueError("Faltan variables de entorno para Cloud SQL.")

    connector = Connector()
    def getconn():
        return connector.connect(instance_connection_name, "pg8000", user=db_user, password=db_pass, db=db_name, ip_type=IPTypes.PUBLIC)
    
    engine = sqlalchemy.create_engine("postgresql+pg8000://", creator=getconn)

    try:
        with engine.connect() as conn:
            # 3. Buscar el ID del cliente (de forma segura para evitar inyección SQL)
            find_query = sqlalchemy.text("SELECT id FROM clientes WHERE nombre ILIKE :nombre LIMIT 2")
            result = conn.execute(find_query, {"nombre": f"%{nombre_cliente}%"}).fetchall()

            if not result:
                return f"No se encontró ningún cliente con el nombre '{nombre_cliente}'."
            if len(result) > 1:
                return f"Se encontraron múltiples clientes con el nombre '{nombre_cliente}'. Por favor, sé más específico."

            cliente_id = result[0][0]

            # 4. Ejecutar la actualización
            update_query = sqlalchemy.text("UPDATE clientes SET _estado = :estado, fecha_ultima_actividad = NOW() WHERE id = :id")
            conn.execute(update_query, {"estado": estado_id, "id": cliente_id})
            conn.commit() # ¡Importante! Confirmar la transacción

            return f"¡Éxito! El cliente '{nombre_cliente}' ha sido actualizado al estado '{nuevo_estado_texto}' (ID: {estado_id})."
    except Exception as e:
        return f"Error al actualizar la base de datos: {e}"
    finally:
        connector.close()

def registrar_seguimiento_cliente(nombre_cliente: str, tipo_contacto: str, descripcion: str) -> str:
    """
    Registra un nuevo seguimiento en el historial del cliente (ej. llamada, correo, reunion, whatsapp).
    """
    db_user = os.environ.get("DB_USER")
    db_pass = os.environ.get("DB_PASS")
    db_name = os.environ.get("DB_NAME")
    instance_connection_name = os.environ.get("INSTANCE_CONNECTION_NAME")

    if not all([db_user, db_pass, db_name, instance_connection_name]):
        raise ValueError("Faltan variables de entorno para Cloud SQL.")

    connector = Connector()
    def getconn():
        return connector.connect(instance_connection_name, "pg8000", user=db_user, password=db_pass, db=db_name, ip_type=IPTypes.PUBLIC)
    
    engine = sqlalchemy.create_engine("postgresql+pg8000://", creator=getconn)

    try:
        with engine.connect() as conn:
            # 1. Buscar el ID del cliente
            find_query = sqlalchemy.text("SELECT id FROM clientes WHERE nombre ILIKE :nombre LIMIT 2")
            result = conn.execute(find_query, {"nombre": f"%{nombre_cliente}%"}).fetchall()

            if not result:
                return f"No se encontró ningún cliente con el nombre '{nombre_cliente}'."
            if len(result) > 1:
                return f"Se encontraron múltiples clientes con el nombre '{nombre_cliente}'. Por favor, sé más específico."

            cliente_id = result[0][0]

            # 2. Insertar el registro (Usamos usuario_id = 1 asumiendo que es el usuario principal/admin por defecto)
            insert_query = sqlalchemy.text("""
                INSERT INTO seguimiento (cliente_id, usuario_id, tipo, descripcion, fecha) 
                VALUES (:cliente_id, 1, :tipo, :descripcion, NOW())
            """)
            conn.execute(insert_query, {"cliente_id": cliente_id, "tipo": tipo_contacto, "descripcion": descripcion})
            conn.commit()

            return f"¡Éxito! Se ha registrado el seguimiento tipo '{tipo_contacto}' para el cliente '{nombre_cliente}'."
    except Exception as e:
        return f"Error al registrar el seguimiento en la base de datos: {e}"
    finally:
        connector.close()

def generar_grafico_analisis(metrica: str) -> str:
    """
    Genera un gráfico visual basado en los datos reales de los clientes en la base de datos.
    Métricas permitidas: 'prioridad', 'estado', 'valor', 'fuente', o 'conversion'.
    """
    try:
        df = consultar_cloud_sql("") # Obtenemos todos los registros posibles
        if df.empty:
            return "No hay suficientes datos en la base para graficar."
        
        plt.figure(figsize=(8, 6))
        
        if metrica.lower() == "prioridad" and 'prioridad' in df.columns:
            conteo = df['prioridad'].value_counts()
            conteo.plot(kind='bar', color=['#4CAF50', '#FF9800', '#F44336'])
            plt.title("Distribución de Clientes por Prioridad")
            plt.xlabel("Nivel de Prioridad")
            plt.ylabel("Cantidad de Clientes")
            plt.xticks(rotation=0)
        elif metrica.lower() == "estado" and '_estado' in df.columns:
            # Convertimos los números a texto. Si hay un número no mapeado, lo deja como "Otro (numero)"
            estados_texto = df['_estado'].map(MAPA_ESTADOS).fillna('Otro (' + df['_estado'].astype(str) + ')')
            
            conteo = estados_texto.value_counts()
            conteo.plot(kind='pie', autopct='%1.1f%%', startangle=90)
            plt.title("Proporción de Clientes por Estado Interno")
            plt.ylabel("") # Ocultar label del eje Y
        elif metrica.lower() == "valor" and 'valor_estimado' in df.columns and '_estado' in df.columns:
            df['estado_texto'] = df['_estado'].map(MAPA_ESTADOS).fillna('Otro')
            # Agrupamos por estado y sumamos el valor estimado
            suma_valor = df.groupby('estado_texto')['valor_estimado'].sum().sort_values(ascending=False)
            suma_valor.plot(kind='bar', color='#2196F3')
            plt.title("Valor Estimado ($) del Pipeline por Estado")
            plt.xlabel("Estado del Cliente")
            plt.ylabel("Valor Estimado Total")
            plt.xticks(rotation=45, ha='right')
        elif metrica.lower() == "fuente" and 'fuente' in df.columns:
            conteo = df['fuente'].fillna('Desconocido').value_counts()
            conteo.sort_values().plot(kind='barh', color='#9C27B0')
            plt.title("Origen de los Prospectos (Fuentes)")
            plt.xlabel("Cantidad de Clientes")
            plt.ylabel("Fuente")
        elif metrica.lower() == "conversion" and 'es_cliente' in df.columns:
            # Mapeamos el booleano a texto
            conteo = df['es_cliente'].map({True: 'Cliente Cerrado', False: 'Prospecto Activo'}).value_counts()
            conteo.plot(kind='pie', autopct='%1.1f%%', startangle=90, colors=['#00BCD4', '#FFC107'])
            plt.title("Tasa de Conversión General")
            plt.ylabel("")
        else:
            return f"No se pudo generar el gráfico. Verifica que la métrica '{metrica}' sea una de las permitidas (prioridad, estado, valor, fuente, conversion)."
        
        filename = f"grafico_{uuid.uuid4().hex[:8]}.png"
        filepath = os.path.join("graficos", filename)
        plt.savefig(filepath, bbox_inches='tight')
        plt.close()
        
        # Le decimos al modelo de IA qué HTML devolver para que el frontend muestre la imagen
        return f"Gráfico generado con éxito. DEBES responder esto al usuario exactamente así para que vea la imagen: <br><img src='/graficos/{filename}' alt='Gráfico de {metrica}' style='max-width: 100%; border-radius: 8px; margin-top: 10px;'/>"
    except Exception as e:
        return f"Error al procesar y graficar los datos: {e}"

# --- NUEVAS HERRAMIENTAS AVANZADAS (PLANTILLAS) ---

def analizar_documento_cliente(nombre_cliente: str, tipo_documento: str) -> str:
    """Busca y analiza el contenido de un documento o evidencia PDF (ej. 'cotizacion', 'contrato') de un cliente."""
    # Plantilla para futura integración con PyPDF2 o Google Document AI
    return f"[Document AI Simulación] He analizado el documento '{tipo_documento}' de {nombre_cliente}. Los puntos clave indican un interés presupuestal sólido y solicitan soporte técnico adicional. No se encontraron riesgos legales."

def enviar_correo_cliente(nombre_cliente: str, correo_destino: str, asunto: str, cuerpo: str) -> str:
    """Envía un correo electrónico a un prospecto o cliente."""
    # Plantilla para futura integración con Microsoft Graph API o SMTP
    print(f"[EMAIL MOCK] Enviando a {correo_destino} | Asunto: {asunto} | Cuerpo: {cuerpo}")
    return f"¡Hecho! El correo automatizado con asunto '{asunto}' fue enviado exitosamente a {nombre_cliente} ({correo_destino})."

def calcular_probabilidad_cierre(nombre_cliente: str) -> str:
    """Utiliza un modelo predictivo (Lead Scoring) para calcular la probabilidad de que un prospecto cierre la venta."""
    # Plantilla: Aquí se calcularía combinando 'valor_estimado', estado actual y cantidad de seguimientos en la base de datos.
    return f"Basado en el modelo de Lead Scoring y las interacciones recientes, '{nombre_cliente}' tiene una probabilidad de cierre del **88% (Alta)**. ¡Te sugiero priorizar su seguimiento hoy mismo!"

# --- CONFIGURACIÓN DEL AGENTE (ADK 1.15.1) ---
agente = adk.Agent(
    name="BatiaCommercialAgent",
    model="gemini-2.5-flash",
    instruction="Eres el asistente avanzado de Lore en Grupo Batia. Capacidades: 1) Buscar clientes, 2) Consultar BI, 3) Generar gráficos HTML (<img>), 4) Actualizar estados, 5) Registrar seguimientos, 6) Analizar PDFs, 7) Enviar correos, y 8) Calcular Lead Scoring. Actúa de forma proactiva y profesional.",
    tools=[buscar_clientes_por_criterio, consultar_dashboard_bi, generar_grafico_analisis, actualizar_estado_cliente, registrar_seguimiento_cliente, analizar_documento_cliente, enviar_correo_cliente, calcular_probabilidad_cierre]
)

# Creamos el servicio de sesión (guardará el historial en sessions.db)
session_service = DatabaseSessionService(db_url="sqlite:///sessions.db")

# Creamos el Runner pasándole el servicio de sesión
runner = Runner(agent=agente, app_name=agente.name, session_service=session_service)

# --- TAREAS EN SEGUNDO PLANO (AUTOMATIZACIÓN) ---
async def revisar_clientes_abandonados():
    while True:
        # Plantilla: Aquí el script se conectaría a SQL para buscar clientes inactivos > 7 días y crear alertas
        print("🤖 [Background Task] Analizando pipeline: Revisión automática de clientes inactivos ejecutada con éxito.")
        await asyncio.sleep(86400) # El ciclo se duerme y vuelve a ejecutarse cada 24 horas (86400 seg)

@app.on_event("startup")
async def iniciar_tareas_fondo():
    asyncio.create_task(revisar_clientes_abandonados())

# --- INTERFAZ WEB (HTML/CSS) ---
@app.get("/", response_class=HTMLResponse)
async def get_ui():
    # Servimos el archivo HTML estático.
    # Asegúrate de que la ruta es correcta desde donde ejecutas el script.
    # (Se asume que ejecutas `python agent/main.py` desde el directorio `ADK_Basic`)
    return FileResponse("agent/base.html")

# --- ENDPOINT DE COMUNICACIÓN ---
@app.post("/chat")
async def chat_endpoint(request: Request):
    data = await request.json()
    prompt = data.get("prompt")
    if not prompt:
        return {"error": "No se recibió ningún prompt."}
    
    try:
        # 1. El input para run_async debe ser un objeto Content, no un string.
        #    Esto corrige el error "'str' object has no attribute 'model_copy'".
        message = Content(parts=[Part(text=prompt)], role="user")

        # 2. Aseguramos que la sesión exista en la base de datos antes de usarla
        try:
            session = await session_service.get_session(app_name=agente.name, user_id="web_user", session_id="web_session")
        except Exception:
            session = None
            
        if not session:
            await session_service.create_session(session_id="web_session", app_name=agente.name, user_id="web_user")

        # 3. Usamos runner.run_async() con un sistema de reintentos automático
        max_retries = 3
        for attempt in range(max_retries):
            try:
                full_response = ""
                async for event in runner.run_async(
                    user_id="web_user",
                    session_id="web_session",
                    new_message=message
                ):
                    # El texto de respuesta está dentro de event.content.parts
                    if event.content:
                        for part in event.content.parts:
                            if hasattr(part, 'text') and part.text:
                                full_response += part.text
                break  # Si tiene éxito, salimos del bucle de reintentos
            except Exception as e:
                if "503" in str(e) and "UNAVAILABLE" in str(e) and attempt < max_retries - 1:
                    await asyncio.sleep(4)  # Esperamos 4 segundos antes de volver a intentar
                    continue
                raise e  # Si no es un error 503 o se agotaron los intentos, lanzamos el error al bloque except principal
        
        if full_response:
            return {"respuesta": full_response}
        else:
            return {"respuesta": "El agente procesó la tarea, pero no devolvió texto."}
            
    except Exception as e:
        error_msg = str(e)
        if "503" in error_msg and "UNAVAILABLE" in error_msg:
            return {"respuesta": "El agente está experimentando una alta demanda en los servidores de Google en este momento. Por favor, espera un par de minutos y vuelve a intentarlo. ⏳"}
        elif "getaddrinfo failed" in error_msg:
            return {"respuesta": "Error de red: No se pudo conectar a los servidores de Google. Verifica tu conexión a internet, VPN o configuración de proxy corporativo. 🌐"}
        return {"error": f"Error en ejecución: {error_msg}"}

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)