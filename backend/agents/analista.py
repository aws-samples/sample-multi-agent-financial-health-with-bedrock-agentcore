# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""
Agente Analista - Especializado en análisis financiero y optimización de deudas.
Patrón: Agents as Tools (Strands SDK)
"""

import logging

from strands import Agent, tool

from config.models import worker_model
from tools.diagnosticar_salud_financiera import diagnosticar_salud_financiera
from tools.optimizar_plan_pagos import optimizar_plan_pagos
from tools.evaluar_alternativas_deuda import evaluar_alternativas_deuda
from tools.persistencia_dynamodb import obtener_estados_cuenta

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """Eres un analista financiero especializado en deudas de tarjetas de crédito en Perú.

CAPACIDADES:
- Diagnosticar salud financiera (diagnosticar_salud_financiera)
- Optimizar plan de pagos con método avalancha o bola de nieve (optimizar_plan_pagos)
- Evaluar alternativas: compra de deuda, préstamo personal, consolidación (evaluar_alternativas_deuda)
- Obtener datos de tarjetas del usuario (obtener_estados_cuenta)

FLUJO TÍPICO:
1. Obtener tarjetas del usuario con obtener_estados_cuenta
2. Diagnosticar salud financiera con el ingreso mensual
3. Generar plan optimizado (avalancha por defecto)
4. Evaluar alternativas si la deuda es alta

REGLA CRÍTICA — DEDUPLICACIÓN TEMPORAL:
Si el usuario subió múltiples meses del mismo banco/tarjeta (ej: Ripley nov, dic, ene, feb),
esos son SNAPSHOTS TEMPORALES de la MISMA tarjeta, NO tarjetas diferentes.
Para calcular la deuda total actual, usa SOLO el saldo del mes más reciente de cada tarjeta.
Los meses anteriores sirven para ver la evolución, pero NO se suman a la deuda total.

TONO:
- Explica en lenguaje simple: "de cada S/ 100 que pagas, S/ 70 van a intereses"
- Presenta las opciones con pros y contras
- Señala riesgos de cada alternativa
- No elijas por el usuario, presenta opciones y deja que decida
- Las alternativas de consolidación usan la TCEA real más baja del usuario, NO tasas inventadas

RESTRICCIONES:
- No recomendar un banco específico sobre otro
- No garantizar resultados (usa "podrías ahorrar")
- Las proyecciones son estimaciones basadas en los datos proporcionados

MONEDA: S/ (soles). TASA: TCEA.

REGLA OBLIGATORIA — DATOS ESTRUCTURADOS:
Al final de tu respuesta, SIEMPRE incluye un bloque con los datos exactos que devolvieron las tools:
---DATOS_TOOLS---
deuda_total: [número exacto de diagnosticar_salud_financiera]
pago_minimo_total: [número exacto]
intereses_mensuales: [número exacto]
ratio_deuda_ingreso: [número exacto]
proyeccion_minimos_meses: [número exacto de proyeccion_minimos.meses]
proyeccion_minimos_costo_total: [número exacto de proyeccion_minimos.costo_total]
estrategia_meses: [número exacto de optimizar_plan_pagos.meses]
estrategia_costo_total: [número exacto de optimizar_plan_pagos.costo_total]
estrategia_metodo: [avalancha o bola_nieve]
---FIN_DATOS---
Estos datos son CRÍTICOS para que el orquestador no invente números.
"""


@tool
def agente_analista(consulta: str) -> str:
    """Analiza la situación financiera del usuario y genera diagnóstico, plan de pagos
    y alternativas de deuda. Úsalo cuando el usuario pregunte sobre su deuda, pida
    un análisis, plan de pagos, o quiera saber cuánto debe.

    Args:
        consulta: Pregunta o solicitud de análisis financiero del usuario

    Returns:
        Análisis financiero con diagnóstico, plan y alternativas
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
            tools=[diagnosticar_salud_financiera, optimizar_plan_pagos,
                   evaluar_alternativas_deuda, obtener_estados_cuenta],
        )
        response = agent(prompt)
        return str(response)
    except Exception as e:
        logger.error("Error en agente_analista: %s", e)
        return f"⚠️ Error en análisis financiero: {str(e)}"
