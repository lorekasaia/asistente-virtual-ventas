import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import PyPDF2
import docx
import pandas as pd
from PIL import Image
import pytesseract
from google import adk
from core.database import consultar_cloud_sql, MAPA_ESTADOS

def analizar_documento_cliente(nombre_cliente: str, tipo_documento: str) -> str:
    carpeta = "documentos"
    extensiones_validas = ('.pdf', '.docx', '.xlsx', '.png', '.jpg', '.jpeg')
    archivos = [f for f in os.listdir(carpeta) if f.lower().endswith(extensiones_validas)]
    if not archivos:
        return f"La carpeta '{carpeta}/' está vacía. Por favor, coloca archivos PDF, Word, Excel o Imágenes allí."
        
    archivo_encontrado = None
    for arch in archivos:
        if nombre_cliente.lower().replace(" ", "") in arch.lower().replace(" ", ""):
            archivo_encontrado = os.path.join(carpeta, arch)
            break
            
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
            texto_extraido = df_excel.head(100).to_string() 
        elif ext in ['png', 'jpg', 'jpeg']:
            img = Image.open(archivo_encontrado)
            texto_extraido = pytesseract.image_to_string(img)
            if not texto_extraido.strip():
                texto_extraido = "[No se pudo extraer texto de la imagen o no contiene texto legible]"
                
        texto_extraido = texto_extraido[:15000]
        return f"Aquí tienes el contenido del archivo '{os.path.basename(archivo_encontrado)}'. Léelo cuidadosamente y hazle un buen resumen analítico al usuario:\n\n{texto_extraido}"
    except Exception as e:
        return f"Error al intentar leer el archivo {ext}: {e}"

def enviar_correo_cliente(nombre_cliente: str, correo_destino: str, asunto: str, cuerpo: str) -> str:
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
        
        server = smtplib.SMTP('smtp.office365.com', 587)
        server.starttls()
        server.login(email_user, email_pass)
        server.send_message(msg)
        server.quit()
        return f"¡Éxito! El correo con asunto '{asunto}' fue enviado realmente a {nombre_cliente} ({correo_destino})."
    except Exception as e:
        return f"Error al intentar enviar el correo por SMTP: {e}"

def calcular_probabilidad_cierre(nombre_cliente: str) -> str:
    try:
        df = consultar_cloud_sql(nombre_cliente)
        if df.empty:
            return f"No encontré a '{nombre_cliente}' en la base de datos para calcular su Lead Scoring."
        
        cliente = df.iloc[0]
        estado = cliente.get('_estado', 1)
        valor = cliente.get('valor_estimado', 0)
        
        score = 15
        if pd.notna(estado):
            if estado >= 6: score += 60
            elif estado >= 4: score += 35
            elif estado >= 2: score += 15
            
        if pd.notna(valor) and valor > 10000:
            score += 15 
            
        score = min(score, 99) 
        etiqueta = "Alta" if score >= 70 else ("Media" if score >= 40 else "Baja")
        return f"Cálculo de Lead Scoring para **{cliente['nombre']}**: Probabilidad de cierre del **{score}% ({etiqueta})**. (Basado matemáticamente en su estado '{MAPA_ESTADOS.get(estado, 'Desconocido')}' y valor de negocio)."
    except Exception as e:
        return f"Error al calcular el Lead Scoring: {e}"

advanced_ai_agent = adk.Agent(
    name="AdvancedAIAgent",
    model="gemini-1.5-flash",
    instruction="Eres un especialista en tareas complejas de IA. Tus funciones son: analizar documentos (PDF, Word, Excel, Imagen), enviar correos electrónicos reales y calcular la probabilidad de cierre (Lead Scoring). Eres detallado y analítico en tus respuestas.",
    tools=[analizar_documento_cliente, enviar_correo_cliente, calcular_probabilidad_cierre]
)