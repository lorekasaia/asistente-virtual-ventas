import os
from dotenv import load_dotenv

# 1. Cargar configuración ANTES de importar las librerías de IA
# Busca el .env en el directorio actual o fuerza la búsqueda en el directorio padre
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

from fastapi import FastAPI, Request, UploadFile, File
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from google import adk
from google.adk.runners import Runner
import matplotlib
# Configuración para evitar errores de GUI con Matplotlib en servidores
matplotlib.use('Agg')

import uuid
import shutil
import google.generativeai as genai

from google.adk.sessions import DatabaseSessionService

from google.genai.types import Content, Part
import uvicorn
import asyncio

# Importar agentes especializados
from agents.data_query import data_query_agent
from agents.analytics import analytics_agent
from agents.crm import crm_agent
from agents.advanced_ai import advanced_ai_agent

app = FastAPI(title="Batia Agent UI")

# Crear carpeta para guardar los gráficos generados y montarla en la web
os.makedirs("graficos", exist_ok=True)
app.mount("/graficos", StaticFiles(directory="graficos"), name="graficos")

# Crear carpeta para guardar los reportes de Excel generados y montarla en la web
os.makedirs("reportes", exist_ok=True)
app.mount("/reportes", StaticFiles(directory="reportes"), name="reportes")

# Crear carpeta para los documentos PDF de los clientes
os.makedirs("documentos", exist_ok=True)

# 5. Agente Orquestador (Manager)
orchestrator_agent = adk.Agent(
    name="OrchestratorAgent",
    model="gemini-1.5-flash",
    instruction="""Eres el Agente Orquestador (Manager). Tu única responsabilidad es analizar la solicitud del usuario y decidir cuál de los agentes especializados debe resolverla.
Responde ÚNICAMENTE con el nombre exacto de la categoría.

Categorías disponibles:
- DATA_QUERY: Buscar clientes, ejecutar SQL, o revisar clientes abandonados/sin seguimiento.
- ANALYTICS: Resúmenes financieros, gráficos, exportar a Excel, KPIs de BI.
- CRM: Actualizar estados en el pipeline o registrar seguimientos/llamadas/reuniones.
- ADVANCED_AI: Leer o analizar documentos (PDF, Word, Excel, Imagen), enviar correos, calcular lead scoring.

Si la solicitud abarca varias acciones, elige la categoría de la acción principal."""
)

# Diccionario de agentes para el enrutador
AGENTS = {
    "DATA_QUERY": data_query_agent,
    "ANALYTICS": analytics_agent,
    "CRM": crm_agent,
    "ADVANCED_AI": advanced_ai_agent
}

# --- SERVICIOS Y RUNNERS ---

# Servicio de sesión único para mantener un historial de chat coherente
session_service = DatabaseSessionService(db_url="sqlite:///sessions.db")

# Un solo nombre de aplicación para que todos los agentes compartan el mismo historial de conversación
APP_NAME = "BatiaUnifiedAssistant"

# Creamos un Runner para cada agente
RUNNERS = {
    name: Runner(agent=agent, app_name=APP_NAME, session_service=session_service)
    for name, agent in AGENTS.items()
}

# --- Lógica de Enrutamiento ---

async def route_to_agent(prompt: str) -> str:
    """Usa el OrchestratorAgent para clasificar el prompt y dirigirlo al especialista."""
    try:
        # Instanciamos el modelo con las instrucciones del agente orquestador
        routing_model = genai.GenerativeModel(
            model_name=orchestrator_agent.model,
            system_instruction=orchestrator_agent.instruction
        )
        # Pasamos el prompt del usuario directamente para que el orquestador lo evalúe
        response = await routing_model.generate_content_async(prompt)
        category = response.text.strip().upper()
        
        # Verificación flexible por si el modelo añade alguna puntuación extra
        for key in AGENTS.keys():
            if key in category:
                print(f"[Orquestador] Tarea delegada al agente: {key}")
                return key
                
        print(f"[Orquestador] Clasificación inesperada: '{category}'. Usando 'DATA_QUERY' por defecto.")
        return "DATA_QUERY"
    except Exception as e:
        print(f"[Orquestador] Error al enrutar: {e}. Usando 'DATA_QUERY' por defecto.")
        return "DATA_QUERY"

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

    if not session_id:
        session_id = f"web-session-{uuid.uuid4()}"
    if not prompt:
        return {"error": "No se recibió ningún prompt."}
    
    try:
        # 1. Enrutar el prompt al agente correcto
        agent_category = await route_to_agent(prompt)
        selected_runner = RUNNERS[agent_category]
        selected_agent_name = selected_runner.agent.name

        # 2. El input para run_async debe ser un objeto Content
        message = Content(parts=[Part(text=prompt)], role="user")

        # 3. Aseguramos que la sesión exista en la base de datos antes de usarla
        try:
            session = await session_service.get_session(app_name=APP_NAME, user_id="web_user", session_id=session_id)
        except Exception:
            session = None
            
        if not session:
            await session_service.create_session(session_id=session_id, app_name=APP_NAME, user_id="web_user")

        # 4. Usamos el runner seleccionado con reintentos
        max_retries = 3
        for attempt in range(max_retries):
            try:
                full_response = ""
                async for event in selected_runner.run_async(
                    user_id="web_user",
                    session_id=session_id,
                    new_message=message
                ):
                    if event.content:
                        for part in event.content.parts:
                            if hasattr(part, 'text') and part.text:
                                full_response += part.text
                break
            except Exception as e:
                if "503" in str(e) and "UNAVAILABLE" in str(e) and attempt < max_retries - 1:
                    await asyncio.sleep(4)
                    continue
                raise e
        
        if full_response:
            return {"respuesta": full_response, "session_id": session_id}
        else:
            return {"respuesta": f"El agente '{selected_agent_name}' procesó la tarea, pero no devolvió texto.", "session_id": session_id}
            
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