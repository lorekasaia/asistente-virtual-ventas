import sqlalchemy
from google import adk
from database import obtener_motor_bd, MAPA_ESTADOS, MAPA_ESTADOS_INVERSO

def _obtener_id_cliente(conn, nombre_cliente: str):
    """Función auxiliar para buscar el ID de un cliente de forma única."""
    find_query = sqlalchemy.text("SELECT id FROM clientes WHERE nombre ILIKE :nombre LIMIT 2")
    result = conn.execute(find_query, {"nombre": f"%{nombre_cliente}%"}).fetchall()

    if not result:
        return None, f"No se encontró ningún cliente con el nombre '{nombre_cliente}'."
    if len(result) > 1:
        return None, f"Se encontraron múltiples clientes con el nombre '{nombre_cliente}'. Por favor, sé más específico."
    return result[0][0], None

def actualizar_estado_cliente(nombre_cliente: str, nuevo_estado_texto: str) -> str:
    estado_id = MAPA_ESTADOS_INVERSO.get(nuevo_estado_texto.lower())
    if estado_id is None:
        return f"Error: El estado '{nuevo_estado_texto}' no es válido. Los estados válidos son: {list(MAPA_ESTADOS.values())}."

    engine, connector = obtener_motor_bd()
    try:
        # Se usa begin() para manejo automático de transacciones (commit en éxito, rollback en error)
        with engine.begin() as conn:
            cliente_id, error_msg = _obtener_id_cliente(conn, nombre_cliente)
            if error_msg:
                return error_msg
                
            update_query = sqlalchemy.text("UPDATE clientes SET _estado = :estado, fecha_ultima_actividad = NOW() WHERE id = :id")
            conn.execute(update_query, {"estado": estado_id, "id": cliente_id})

            return f"¡Éxito! El cliente '{nombre_cliente}' ha sido actualizado al estado '{nuevo_estado_texto}' (ID: {estado_id})."
    except Exception as e:
        return f"Error al actualizar la base de datos: {e}"

def registrar_seguimiento_cliente(nombre_cliente: str, tipo_contacto: str, descripcion: str) -> str:
    engine, connector = obtener_motor_bd()
    try:
        with engine.begin() as conn:
            cliente_id, error_msg = _obtener_id_cliente(conn, nombre_cliente)
            if error_msg:
                return error_msg
            
            # Parametrizar el ID de usuario en lugar de usar un "Magic Number" (Hardcoded)
            usuario_sistema_id = 1
            insert_query = sqlalchemy.text("INSERT INTO seguimiento (cliente_id, usuario_id, tipo, descripcion, fecha) VALUES (:cliente_id, :usuario_id, :tipo, :descripcion, NOW())")
            conn.execute(insert_query, {"cliente_id": cliente_id, "usuario_id": usuario_sistema_id, "tipo": tipo_contacto, "descripcion": descripcion})
            return f"¡Éxito! Se ha registrado el seguimiento tipo '{tipo_contacto}' para el cliente '{nombre_cliente}'."
    except Exception as e:
        return f"Error al registrar el seguimiento en la base de datos: {e}"

crm_agent = adk.Agent(
    name="CRMAgent",
    model="gemini-2.5-flash",
    instruction="Eres un asistente de CRM. Tu responsabilidad es actualizar el estado de los clientes en el pipeline y registrar seguimientos (llamadas, reuniones, etc.). Confirma siempre la acción realizada de forma clara.",
    tools=[actualizar_estado_cliente, registrar_seguimiento_cliente]
)