# Agente Comercial Batia

Un agente de IA especializado construido con Google's AI Development Kit (ADK) diseñado para ayudar al equipo comercial de Grupo Batia. El agente actúa como un asistente avanzado de CRM, capaz de consultar datos, actualizar estados, generar gráficos y enviar correos.

## Características Principales

- 🔍 **Búsqueda y Consulta**: Acceso en tiempo real a la base de datos de clientes en Google Cloud SQL.
- 📈 **Análisis y Gráficos**: Generación de resúmenes financieros y gráficos visuales (Matplotlib) del pipeline.
- ✍️ **Gestión de CRM**: Actualización de estados y registro de seguimientos de clientes.
- 📧 **Comunicación**: Envío de correos electrónicos a clientes mediante SMTP (Office 365).
- 🧠 **IA Avanzada**: Capacidades (simuladas/en desarrollo) de lectura de PDFs, Lead Scoring y conexión a tableros BI.

## Requisitos Previos

- Python 3.8 o superior.
- Credenciales de Google Cloud y acceso a la base de datos Cloud SQL.

## Configuración Rápida

Instala las dependencias y activa tu entorno virtual:

```bash
pip install -r requirements.txt
```

### What the Script Does

The setup script will:

1.  **Check for Python**: Ensures you have Python 3.8 or higher.
2.  **Create a Virtual Environment**: Sets up a dedicated `.adk_env` directory.
3.  **Install Dependencies**: Installs the required Python packages from `requirements.txt`.
4.  **Prompt for Project ID**: Asks for your Google Cloud Project ID.
5.  **Create `.env` File**: Generates a `.env` file in the root directory with the following configuration:

    ```env
    GOOGLE_GENAI_USE_VERTEXAI=TRUE
    GOOGLE_CLOUD_PROJECT=your_project_id
    GOOGLE_CLOUD_LOCATION=us-central1
    ```

## Running the Agent

After the setup is complete:

1.  **Activate the virtual environment**:

    **Mac/Linux:**
    ```bash
    source .adk_env/bin/activate
    ```

    **Windows:**
    ```cmd
    .adk_env\Scripts\activate
    ```

2.  **Run the ADK web interface**:

    ```bash
    adk web
    ```

## Deactivating the Environment

When you're done, you can deactivate the virtual environment:

```bash
deactivate
```