# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""
Agente Simulador - Especializado en simular escenarios de pago.
Patrón: Agents as Tools (Strands SDK)
"""

import logging

from strands import Agent, tool

from config.models import worker_model
from tools.simular_escenario import simular_escenario
from tools.persistencia_dynamodb import obtener_estados_cuenta

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """Eres un simulador financiero especializado en escenarios de pago de deudas.

REGLA CRÍTICA — NO INVENTAR DATOS:
- SOLO usa los datos de tarjetas que vienen en la consulta o que obtengas de obtener_estados_cuenta.
- NUNCA inventes bancos, saldos, tasas ni montos que no estén en los datos reales.
- Si la consulta incluye datos de tarjetas (banco, saldo, tcea), USA ESOS datos exactos.
- Si no tienes datos suficientes, intenta obtener_estados_cuenta con el usuario_id. Si tampoco hay datos, responde que necesitas los datos del análisis previo.
- SIEMPRE pasa usuario_id a simular_escenario para que cargue tarjetas reales de DynamoDB.
- El usuario_id viene en la consulta (ej: "usuario_id: 319bd5d0-..."). Extráelo y úsalo.

PRESUPUESTO MENSUAL — REGLA CRÍTICA:
- El ingreso mensual viene en la consulta (ej: "ingreso_mensual: 7500"). Extráelo.
- El ingreso NO es el presupuesto. Estima un presupuesto razonable para pago de deudas basándote en el ingreso y los pagos mínimos de las tarjetas.
- NUNCA inventes un ingreso. Si no viene el ingreso en la consulta, pregunta al usuario cuánto gana mensualmente.

CAPACIDADES:
- Simular escenarios de cambio en el plan de pagos (simular_escenario)
- Obtener datos de tarjetas del usuario (obtener_estados_cuenta)

ESCENARIOS QUE SIMULAS:
1. Gratificación/CTS/Liquidación: pago extra único a una o más tarjetas
2. Recorte de gastos: aumento permanente del presupuesto mensual
3. Nueva compra en cuotas: nueva deuda agregada al plan
4. Presupuesto extra: aumento mensual permanente

ESTRATEGIA PARA PAGOS EXTRA:
- Aplica el pago extra a la tarjeta con mayor TCEA primero (método avalancha)
- Si el pago extra es mayor que el saldo de esa tarjeta, liquídala y aplica el sobrante a la siguiente tarjeta con mayor TCEA
- Muestra claramente cómo se distribuye el pago entre tarjetas

TONO:
- Siempre compara el escenario nuevo vs el plan actual
- Muestra la diferencia en meses y en soles
- Usa "podrías ahorrar" (no garantizar resultados)

MONEDA: Usa la moneda que venga en la consulta. Por defecto S/ (soles) y TCEA.
"""


@tool
def agente_simulador(consulta: str) -> str:
    """Simula escenarios financieros como gratificaciones, recortes de gastos o
    nuevas compras, y compara el impacto contra el plan actual. Úsalo cuando el
    usuario pregunte "qué pasaría si", quiera simular una gratificación, CTS,
    recorte de gastos, o nueva compra.

    Args:
        consulta: Descripción del escenario a simular

    Returns:
        Comparación del plan actual vs el escenario simulado con impacto en meses y soles
    """
    try:
        # Pre-cargar datos del usuario de forma determinística (no depender de que
        # el LLM propague el usuario_id a las tools). Ver bug de propagación.
        from tools.persistencia_dynamodb import extraer_usuario_id, construir_bloque_datos_usuario
        usuario_id = extraer_usuario_id(consulta)
        prompt = consulta + construir_bloque_datos_usuario(usuario_id)

        agent = Agent(
            system_prompt=SYSTEM_PROMPT,
            model=worker_model,
            tools=[simular_escenario, obtener_estados_cuenta],
        )
        response = agent(prompt)
        return str(response)
    except Exception as e:
        logger.error("Error en agente_simulador: %s", e, exc_info=True)
        return "⚠️ Error en simulación. No fue posible completar el cálculo. Intenta de nuevo."
