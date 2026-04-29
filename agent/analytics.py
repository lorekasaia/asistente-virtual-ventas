import os
import uuid
import pandas as pd
import matplotlib.pyplot as plt
from google import adk
from core.database import consultar_cloud_sql, MAPA_ESTADOS

def obtener_resumen_pipeline() -> str:
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
    print(f"[BI API Mock] Solicitando KPI: '{kpi}' con contexto '{contexto}'")
    if kpi == "ventas_totales":
        return f"El Dashboard de BI reporta que las ventas totales para '{contexto}' son de $1,450,000 MXN este trimestre."
    elif kpi == "tasa_conversion":
        return f"Según la plataforma de BI, la tasa de conversión de prospectos a clientes para '{contexto}' se sitúa en un 24.5%."
    elif kpi == "rendimiento_vendedores":
        return "El reporte de BI indica que Lore lidera las ventas con un 120% de alcance de cuota, seguida de cerca por el resto del equipo."
    else:
        return f"Datos del Dashboard para el KPI '{kpi}': Los indicadores están estables y dentro de los rangos esperados para el período actual."

def generar_grafico_analisis(metrica: str) -> str:
    try:
        df = consultar_cloud_sql("") 
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
            estados_texto = df['_estado'].map(MAPA_ESTADOS).fillna('Otro (' + df['_estado'].astype(str) + ')')
            conteo = estados_texto.value_counts()
            conteo.plot(kind='pie', autopct='%1.1f%%', startangle=90)
            plt.title("Proporción de Clientes por Estado Interno")
            plt.ylabel("")
        elif metrica.lower() == "valor" and 'valor_estimado' in df.columns and '_estado' in df.columns:
            df['estado_texto'] = df['_estado'].map(MAPA_ESTADOS).fillna('Otro')
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
            conteo = df['es_cliente'].map({True: 'Cliente Cerrado', False: 'Prospecto Activo'}).value_counts()
            conteo.plot(kind='pie', autopct='%1.1f%%', startangle=90, colors=['#00BCD4', '#FFC107'])
            plt.title("Tasa de Conversión General")
            plt.ylabel("")
        else:
            return f"No se pudo generar el gráfico. Verifica que la métrica '{metrica}' sea una de las permitidas."
        
        filename = f"grafico_{uuid.uuid4().hex[:8]}.png"
        filepath = os.path.join("graficos", filename)
        plt.savefig(filepath, bbox_inches='tight')
        plt.close()
        return f"Gráfico generado con éxito. DEBES responder esto al usuario exactamente así para que vea la imagen: <br><img src='/graficos/{filename}' alt='Gráfico de {metrica}' style='max-width: 100%; border-radius: 8px; margin-top: 10px;'/>"
    except Exception as e:
        return f"Error al procesar y graficar los datos: {e}"

def exportar_datos_excel(termino_busqueda: str = "") -> str:
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

analytics_agent = adk.Agent(
    name="AnalyticsAgent",
    model="gemini-1.5-flash",
    instruction="Eres un analista de datos y BI. Tu propósito es generar resúmenes financieros, crear gráficos visuales (con <img>), exportar datos a Excel (con <a>) y consultar KPIs del dashboard de BI. Proporciona insights y visualizaciones claras.",
    tools=[generar_grafico_analisis, obtener_resumen_pipeline, exportar_datos_excel, consultar_dashboard_bi]
)