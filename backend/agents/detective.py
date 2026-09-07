# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""
Agente Detective - Especializado en detectar gastos hormiga y oportunidades de ahorro.
Patrón: Agents as Tools (Strands SDK)
"""

import logging

from strands import Agent, tool

from config.models import worker_model
from tools.detectar_gastos_hormiga import detectar_gastos_hormiga
from tools.persistencia_dynamodb import obtener_estados_cuenta

logger = logging.getLogger(__name__)

# NOTA: los comercios listados en "CATEGORÍAS QUE DETECTAS" son nombres REALES
# usados como EJEMPLOS de patrones de coincidencia para categorizar las
# transacciones reales del usuario. No son datos de demo.
# AVISO DE MARCAS: los nombres de marcas mencionados son solo ejemplos con fines
# de categorización; no implican patrocinio, afiliación ni respaldo de esas marcas.
SYSTEM_PROMPT = """Eres un detective de gastos especializado en identificar gastos hormiga en transacciones de tarjetas de crédito peruanas.

CAPACIDADES:
- Detectar gastos hormiga por categoría (detectar_gastos_hormiga)
- Obtener movimientos del usuario (obtener_estados_cuenta)

CATEGORÍAS QUE DETECTAS:
- Delivery: Rappi, PedidosYa, Uber Eats, Glovo
- Conveniencia: Tambo, Oxxo, Mass
- Café: Starbucks, Juan Valdez
- Suscripciones: Netflix, Spotify, gym
- Transporte: Uber, Cabify, Beat
- Snacks: McDonald's, KFC, Bembos

TONO:
- Agrupa gastos por categoría, no listes transacción por transacción
- Cuantifica el impacto: total mensual, proyección anual, % del ingreso
- Conecta con el plan de deuda: "si recortas X, te liberas Y meses antes"
- No juzgues los gastos del usuario ("detecté S/ 680/mes en delivery", no "gastas mucho en delivery")

RESTRICCIONES:
- No garantizar resultados
- Las proyecciones son estimaciones

MONEDA: S/ (soles).
"""


@tool
def agente_detective_gastos(consulta: str) -> str:
    """Detecta gastos hormiga en las transacciones del usuario y cuantifica
    oportunidades de ahorro. Úsalo cuando el usuario pregunte sobre gastos
    hormiga, delivery, suscripciones, o quiera saber dónde puede ahorrar.

    Args:
        consulta: Pregunta sobre gastos hormiga o solicitud de análisis de transacciones

    Returns:
        Análisis de gastos hormiga con categorías, montos y sugerencias de ahorro
    """
    try:
        # Pre-cargar datos del usuario de forma determinística, INCLUYENDO
        # movimientos (el detective los necesita para categorizar gastos hormiga).
        # No depender de que el LLM propague el usuario_id a las tools.
        from tools.persistencia_dynamodb import extraer_usuario_id, construir_bloque_datos_usuario
        usuario_id = extraer_usuario_id(consulta)
        prompt = consulta + construir_bloque_datos_usuario(usuario_id, incluir_movimientos=True)

        agent = Agent(
            system_prompt=SYSTEM_PROMPT,
            model=worker_model,
            tools=[detectar_gastos_hormiga, obtener_estados_cuenta],
        )
        response = agent(prompt)
        return str(response)
    except Exception as e:
        logger.error("Error en agente_detective_gastos: %s", e)
        return f"⚠️ Error detectando gastos hormiga: {str(e)}"
