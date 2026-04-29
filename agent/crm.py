import sqlalchemy
from google import adk
from core.database import obtener_motor_bd, MAPA_ESTADOS, MAPA_ESTADOS_INVERSO

def actualizar_estado_cliente(nombre_cliente: str, nuevo_estado_texto: str) -> str:
    estado_id = MAPA_ESTADOS_INVERSO.get(nuevo_estado_texto.lower())
    if estado_id is None:
        return f"Error: El estado '{nuevo_estado_texto}' no es válido. Los estados válidos son: {list(MAPA_ESTADOS.values())}."

    engine, connector = obtener_motor_bd()
    try:
        with engine.connect() as conn:
            find_query = sqlalchemy.text("SELECT id FROM clientes WHERE nombre ILIKE :nombre LIMIT 2")
            result = conn.execute(find_query, {"nombre": f"%{nombre_cliente}%"}).fetchall()

            if not result:
                return f"No se encontró ningún cliente con el nombre '{nombre_cliente}'."
            if len(result) > 1:
                return f"Se encontraron múltiples clientes con el nombre '{nombre_cliente}'. Por favor, sé más específico."

            cliente_id = result[0][0]
            update_query = sqlalchemy.text("UPDATE clientes SET _estado = :estado, fecha_ultima_actividad = NOW() WHERE id = :id")
            conn.execute(update_query, {"estado": estado_id, "id": cliente_id})
            conn.commit()

            return f"¡Éxito! El cliente '{nombre_cliente}' ha sido actualizado al estado '{nuevo_estado_texto}' (ID: {estado_id})."
    except Exception as e:
        return f"Error al actualizar la base de datos: {e}"
    finally:
        connector.close()

def registrar_seguimiento_cliente(nombre_cliente: str, tipo_contacto: str, descripcion: str) -> str:
    engine, connector = obtener_motor_bd()
    try:
        with engine.connect() as conn:
            find_query = sqlalchemy.text("SELECT id FROM clientes WHERE nombre ILIKE :nombre LIMIT 2")
            result = conn.execute(find_query, {"nombre": f"%{nombre_cliente}%"}).fetchall()
            if not result:
                return f"No se encontró ningún cliente con el nombre '{nombre_cliente}'."
            if len(result) > 1:
                return f"Se encontraron múltiples clientes con el nombre '{nombre_cliente}'. Por favor, sé más específico."
            cliente_id = result[0][0]
            insert_query = sqlalchemy.text("INSERT INTO seguimiento (cliente_id, usuario_id, tipo, descripcion, fecha) VALUES (:cliente_id, 1, :tipo, :descripcion, NOW())")
            conn.execute(insert_query, {"cliente_id": cliente_id, "tipo": tipo_contacto, "descripcion": descripcion})
            conn.commit()
            return f"¡Éxito! Se ha registrado el seguimiento tipo '{tipo_contacto}' para el cliente '{nombre_cliente}'."
    except Exception as e:
        return f"Error al registrar el seguimiento en la base de datos: {e}"
    finally:
        connector.close()

crm_agent = adk.Agent(
    name="CRMAgent",
    model="gemini-1.5-flash",
    instruction="Eres un asistente de CRM. Tu responsabilidad es actualizar el estado de los clientes en el pipeline y registrar seguimientos (llamadas, reuniones, etc.). Confirma siempre la acción realizada de forma clara.",
    tools=[actualizar_estado_cliente, registrar_seguimiento_cliente]
)