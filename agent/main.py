import os
from dotenv import load_dotenv

# 1. Cargar configuración ANTES de importar las librerías de IA
# Busca el .env en el directorio actual o fuerza la búsqueda en el directorio padre
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

import pandas as pd
from fastapi import FastAPI, Request, UploadFile, File
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from google import adk
from google.adk.runners import Runner
import matplotlib.pyplot as plt
import matplotlib
import uuid
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import PyPDF2
import shutil
import docx
from PIL import Image
import pytesseract

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

# Crear carpeta para guardar los reportes de Excel generados y montarla en la web
os.makedirs("reportes", exist_ok=True)
app.mount("/reportes", StaticFiles(directory="reportes"), name="reportes")

# Crear carpeta para los documentos PDF de los clientes
os.makedirs("documentos", exist_ok=True)

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

def obtener_motor_bd():
    """Función auxiliar para centralizar la conexión a Cloud SQL."""
    db_user = os.environ.get("DB_USER")
    db_pass = os.environ.get("DB_PASS")
    db_name = os.environ.get("DB_NAME")
    instance_connection_name = os.environ.get("INSTANCE_CONNECTION_NAME")

    if not all([db_user, db_pass, db_name, instance_connection_name]):
        raise ValueError("Faltan variables de entorno para Cloud SQL (DB_USER, DB_PASS, DB_NAME, INSTANCE_CONNECTION_NAME).")
    
    connector = Connector()
    def getconn():
        return connector.connect(instance_connection_name, "pg8000", user=db_user, password=db_pass, db=db_name, ip_type=IPTypes.PUBLIC)
    
    engine = sqlalchemy.create_engine("postgresql+pg8000://", creator=getconn)
    return engine, connector

def consultar_cloud_sql(termino_busqueda: str = "") -> pd.DataFrame:
    """
    Se conecta a Google Cloud SQL (PostgreSQL) para consultar datos de clientes.
    Nota: Requerirá instalar dependencias como 'pg8000', 'sqlalchemy' y 'cloud-sql-python-connector'.
    """
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

def obtener_resumen_pipeline() -> str:
    """
    Obtiene un resumen estadístico y financiero del pipeline actual de ventas.
    Calcula el valor total por estado, promedios y cuenta la cantidad de clientes.
    """
    try:
        df = consultar_cloud_sql("")
        if df.empty:
            return "No hay datos suficientes para generar un resumen."
        
        if '_estado' in df.columns and 'valor_estimado' in df.columns:
            df['estado_texto'] = df['_estado'].map(MAPA_ESTADOS).fillna('Desconocido')
            resumen = df.groupby('estado_texto').agg(
                cantidad_clientes=('id', 'count'),
                valor_total_mxn=('valor_estimado', 'sum'),
                ticket_promedio=('valor_estimado', 'mean')
            ).reset_index()
            
            return "Resumen Financiero del Pipeline:\n" + resumen.to_json(orient="records", force_ascii=False)
        else:
            return "La base de datos no contiene las columnas de valor o estado necesarias para este análisis."
    except Exception as e:
        return f"Error al generar el resumen estadístico: {e}"

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

    engine, connector = obtener_motor_bd()

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
    engine, connector = obtener_motor_bd()

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
    """Busca un archivo (PDF, Word, Excel o Imagen) en la carpeta 'documentos/' que coincida con el nombre del cliente o tipo, extrae su texto y lo devuelve para su análisis."""
    carpeta = "documentos"
    
    extensiones_validas = ('.pdf', '.docx', '.xlsx', '.png', '.jpg', '.jpeg')
    archivos = [f for f in os.listdir(carpeta) if f.lower().endswith(extensiones_validas)]
    if not archivos:
        return f"La carpeta '{carpeta}/' está vacía. Por favor, coloca archivos PDF, Word, Excel o Imágenes allí."
        
    archivo_encontrado = None
    # Intentar buscar por nombre de cliente primero
    for arch in archivos:
        if nombre_cliente.lower().replace(" ", "") in arch.lower().replace(" ", ""):
            archivo_encontrado = os.path.join(carpeta, arch)
            break
            
    # Si no, buscar por tipo de documento (ej. 'contrato')
    if not archivo_encontrado:
        for arch in archivos:
            if tipo_documento.lower() in arch.lower():
                archivo_encontrado = os.path.join(carpeta, arch)
                break
                
    if not archivo_encontrado:
        return f"No encontré ningún archivo asociado a '{nombre_cliente}' o que sea un '{tipo_documento}' en la carpeta 'documentos/'."
        
    try:
        ext = archivo_encontrado.split('.')[-1].lower()
        texto_extraido = ""
        
        if ext == 'pdf':
            with open(archivo_encontrado, 'rb') as file:
                lector = PyPDF2.PdfReader(file)
                texto_extraido = "".join([lector.pages[i].extract_text() + "\n" for i in range(min(len(lector.pages), 10))])
        elif ext == 'docx':
            doc = docx.Document(archivo_encontrado)
            texto_extraido = "\n".join([p.text for p in doc.paragraphs])
        elif ext == 'xlsx':
            df_excel = pd.read_excel(archivo_encontrado)
            texto_extraido = df_excel.head(100).to_string() # Limitamos a 100 filas para no saturar al modelo
        elif ext in ['png', 'jpg', 'jpeg']:
            img = Image.open(archivo_encontrado)
            texto_extraido = pytesseract.image_to_string(img)
            if not texto_extraido.strip():
                texto_extraido = "[No se pudo extraer texto de la imagen o no contiene texto legible]"
                
        # Recortar el texto para no exceder los límites del modelo
        texto_extraido = texto_extraido[:15000]
        
        return f"Aquí tienes el contenido del archivo '{os.path.basename(archivo_encontrado)}'. Léelo cuidadosamente y hazle un buen resumen analítico al usuario:\n\n{texto_extraido}"
    except Exception as e:
        return f"Error al intentar leer el archivo {ext}: {e}"

def enviar_correo_cliente(nombre_cliente: str, correo_destino: str, asunto: str, cuerpo: str) -> str:
    """
    Envía un correo electrónico REAL usando el servidor SMTP de Office 365.
    """
    email_user = os.environ.get("EMAIL_USER")
    email_pass = os.environ.get("EMAIL_PASS")
    
    if not email_user or not email_pass:
        return "Error: Faltan las variables EMAIL_USER y EMAIL_PASS en el archivo .env."
        
    try:
        msg = MIMEMultipart()
        msg['From'] = email_user
        msg['To'] = correo_destino
        msg['Subject'] = asunto
        msg.attach(MIMEText(cuerpo, 'plain'))
        
        # Conexión al servidor SMTP de Microsoft (Office 365)
        server = smtplib.SMTP('smtp.office365.com', 587)
        server.starttls()
        server.login(email_user, email_pass)
        server.send_message(msg)
        server.quit()
        
        return f"¡Éxito! El correo con asunto '{asunto}' fue enviado realmente a {nombre_cliente} ({correo_destino})."
    except Exception as e:
        return f"Error al intentar enviar el correo por SMTP: {e}"

def calcular_probabilidad_cierre(nombre_cliente: str) -> str:
    """Utiliza un modelo predictivo (Lead Scoring) para calcular la probabilidad de que un prospecto cierre la venta."""
    try:
        df = consultar_cloud_sql(nombre_cliente)
        if df.empty:
            return f"No encontré a '{nombre_cliente}' en la base de datos para calcular su Lead Scoring."
        
        # Tomamos el primer resultado que coincida
        cliente = df.iloc[0]
        
        # Variables base
        estado = cliente.get('_estado', 1)
        valor = cliente.get('valor_estimado', 0)
        
        # Cálculo de Scoring Básico (Basado en Etapas del Pipeline)
        score = 15 # Base
        if pd.notna(estado):
            if estado >= 6: score += 60  # Cotizado en adelante
            elif estado >= 4: score += 35 # En proceso
            elif estado >= 2: score += 15 # Contactado
            
        # Puntos adicionales por el tamaño de la cuenta (sweet spot)
        if pd.notna(valor) and valor > 10000:
            score += 15 
            
        score = min(score, 99) # Topar a 99% máximo
        etiqueta = "Alta" if score >= 70 else ("Media" if score >= 40 else "Baja")
        
        return f"Cálculo de Lead Scoring para **{cliente['nombre']}**: Probabilidad de cierre del **{score}% ({etiqueta})**. (Basado matemáticamente en su estado '{MAPA_ESTADOS.get(estado, 'Desconocido')}' y valor de negocio)."
    except Exception as e:
        return f"Error al calcular el Lead Scoring: {e}"

def exportar_datos_excel(termino_busqueda: str = "") -> str:
    """
    Busca clientes en la base de datos según un criterio y exporta los resultados a un archivo Excel (.xlsx).
    Devuelve un enlace HTML para que el usuario descargue el archivo.
    """
    try:
        df = consultar_cloud_sql(termino_busqueda)
        if df.empty:
            return "No hay datos en la base de datos que coincidan con ese criterio para exportar."
        
        filename = f"reporte_clientes_{uuid.uuid4().hex[:8]}.xlsx"
        filepath = os.path.join("reportes", filename)
        df.to_excel(filepath, index=False)
        
        return f"Reporte Excel generado con éxito. DEBES responder esto al usuario para que pueda descargarlo: <br><a href='/reportes/{filename}' download style='display: inline-block; padding: 10px 15px; background: #107c41; color: white; text-decoration: none; border-radius: 5px; margin-top: 10px; font-weight: bold;'>📊 Descargar Reporte Excel</a>"
    except Exception as e:
        return f"Error al generar el archivo Excel: {e}"

def ejecutar_consulta_sql_avanzada(query_sql: str) -> str:
    """
    Ejecuta una consulta SQL personalizada de SOLO LECTURA (SELECT) en la base de datos de producción.
    Útil para consultas complejas, sumas condicionales o cruces avanzados que 'buscar_clientes_por_criterio' no cubre.
    Ejemplo: SELECT empresa, valor_estimado FROM clientes WHERE valor_estimado > 50000
    """
    if not query_sql.strip().upper().startswith("SELECT"):
        return "Error de seguridad: SÓLO se permiten consultas de tipo SELECT. No puedes modificar la base de datos."
    
    engine, connector = obtener_motor_bd()
    try:
        with engine.connect() as conn:
            df = pd.read_sql(sqlalchemy.text(query_sql), con=conn)
            if df.empty:
                 return "La consulta se ejecutó correctamente pero no arrojó resultados."
            # Si hay más de 50 filas, devolvemos un resumen para no saturar al modelo
            return "Resultado de la consulta SQL (Mostrando max 50 filas):\n" + df.head(50).to_string()
    except Exception as e:
        return f"Error de sintaxis o ejecución SQL: {e}"
    finally:
        connector.close()

def revisar_clientes_abandonados() -> str:
    """
    Busca en la base de datos clientes activos que no han tenido seguimiento en más de 7 días.
    Útil para alertar al usuario en el chat sobre prospectos abandonados que necesitan atención urgente.
    """
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
    finally:
        connector.close()

# --- CONFIGURACIÓN DEL AGENTE (ADK 1.15.1) ---
agente = adk.Agent(
    name="BatiaCommercialAgent",
    model="gemini-2.5-flash",
    instruction="Eres el asistente avanzado de Lore en Grupo Batia. Capacidades: 1) Buscar clientes, 2) Consultar BI, 3) Generar gráficos HTML (<img>), 4) Actualizar estados, 5) Registrar seguimientos, 6) Analizar PDFs, 7) Enviar correos, 8) Calcular Lead Scoring, 9) Obtener resúmenes financieros, 10) Exportar a Excel (<img>), 11) Ejecutar SQL puro (PostgreSQL, _estado es int 1-9), y 12) Revisar clientes abandonados. Actúa de forma proactiva, analítica y profesional. IMPORTANTE: Para buscar clientes abandonados usa SIEMPRE la herramienta 'revisar_clientes_abandonados'. Usa SQL solo para otras consultas.",
    tools=[buscar_clientes_por_criterio, consultar_dashboard_bi, generar_grafico_analisis, actualizar_estado_cliente, registrar_seguimiento_cliente, analizar_documento_cliente, enviar_correo_cliente, calcular_probabilidad_cierre, obtener_resumen_pipeline, exportar_datos_excel, ejecutar_consulta_sql_avanzada, revisar_clientes_abandonados]
)

# Creamos el servicio de sesión (guardará el historial en sessions.db)
session_service = DatabaseSessionService(db_url="sqlite:///sessions.db")

# Creamos el Runner pasándole el servicio de sesión
runner = Runner(agent=agente, app_name=agente.name, session_service=session_service)

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
    session_id = data.get("session_id")
    # Si el frontend no envía un ID de sesión, creamos uno nuevo.
    # El frontend debería guardar este ID y enviarlo en las siguientes peticiones.
    if not session_id:
        session_id = f"web-session-{uuid.uuid4()}"
    if not prompt:
        return {"error": "No se recibió ningún prompt."}
    
    try:
        # 1. El input para run_async debe ser un objeto Content, no un string.
        #    Esto corrige el error "'str' object has no attribute 'model_copy'".
        message = Content(parts=[Part(text=prompt)], role="user")

        # 2. Aseguramos que la sesión exista en la base de datos antes de usarla
        try:
            session = await session_service.get_session(app_name=agente.name, user_id="web_user", session_id=session_id)
        except Exception:
            session = None
            
        if not session:
            await session_service.create_session(session_id=session_id, app_name=agente.name, user_id="web_user")

        # 3. Usamos runner.run_async() con un sistema de reintentos automático
        max_retries = 3
        for attempt in range(max_retries):
            try:
                full_response = ""
                async for event in runner.run_async(
                    user_id="web_user",
                    session_id=session_id,
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
            return {"respuesta": full_response, "session_id": session_id}
        else:
            return {"respuesta": "El agente procesó la tarea, pero no devolvió texto.", "session_id": session_id}
            
    except Exception as e:
        error_msg = str(e)
        if "503" in error_msg and "UNAVAILABLE" in error_msg:
            return {"respuesta": "El agente está experimentando una alta demanda en los servidores de Google en este momento. Por favor, espera un par de minutos y vuelve a intentarlo. ⏳"}
        elif "getaddrinfo failed" in error_msg:
            return {"respuesta": "Error de red: No se pudo conectar a los servidores de Google. Verifica tu conexión a internet, VPN o configuración de proxy corporativo. 🌐"}
        return {"error": f"Error en ejecución: {error_msg}", "session_id": session_id}

# --- ENDPOINT PARA SUBIR ARCHIVOS (DRAG & DROP) ---
@app.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    try:
        filepath = os.path.join("documentos", file.filename)
        with open(filepath, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        return {"filename": file.filename, "mensaje": "Archivo subido correctamente"}
    except Exception as e:
        return {"error": str(e)}

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)