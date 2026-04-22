import os
import pandas as pd
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, FileResponse
from google import adk
from google.adk.runners import Runner

from google.adk.sessions import DatabaseSessionService

from google.genai.types import Content, Part
from dotenv import load_dotenv
import uvicorn
import asyncio

# 1. Cargar configuración
load_dotenv()

app = FastAPI(title="Batia Agent UI")

# --- HERRAMIENTAS DE DATOS ---
def buscar_clientes_por_criterio(descripcion: str) -> str:
    try:
        # Cargamos tu archivo de datos de prueba
        df = pd.read_csv('datosdeprueba.csv')
        return df.to_string()
    except:
        return "Error: No se encontró el archivo datosdeprueba.csv."

# --- CONFIGURACIÓN DEL AGENTE (ADK 1.15.1) ---
agente = adk.Agent(
    name="BatiaCommercialAgent",
    model="gemini-1.5-flash",
    instruction="Eres el asistente de Lorena Karen en Grupo Batia. Usa datosdeprueba.csv para gestionar ventas.",
    tools=[buscar_clientes_por_criterio]
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
    return FileResponse("agent/templates/base.html")

# --- ENDPOINT DE COMUNICACIÓN ---
@app.post("/chat")
async def chat_endpoint(request: Request):
    data = await request.json()
    prompt = data.get("prompt")
    if not prompt:
        return {"error": "No se recibió ningún prompt."}
    
    try:
        full_response = ""
        # 1. El input para run_async debe ser un objeto Content, no un string.
        #    Esto corrige el error "'str' object has no attribute 'model_copy'".
        message = Content(parts=[Part(text=prompt)], role="user")

        # 2. Aseguramos que la sesión exista en la base de datos antes de usarla
        try:
            session = session_service.get_session(session_id="web_session")
            if session is None:
                session_service.create_session(session_id="web_session", app_name=agente.name, user_id="web_user")
        except Exception:
            try:
                session_service.create_session(session_id="web_session", app_name=agente.name, user_id="web_user")
            except Exception:
                pass

        # 3. Usamos runner.run_async() para interactuar con el agente
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
        
        if full_response:
            return {"respuesta": full_response}
        else:
            return {"respuesta": "El agente procesó la tarea, pero no devolvió texto."}
            
    except Exception as e:
        return {"error": f"Error en ejecución: {str(e)}"}

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)