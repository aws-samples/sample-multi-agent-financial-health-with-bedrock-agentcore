# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""
Tool que invoca Analista y Detective en paralelo.
Reduce el tiempo total al ejecutar ambos agentes simultáneamente.

IMPORTANTE: Pre-carga tarjetas de DynamoDB ANTES de crear los sub-agentes,
e inyecta los datos reales en el prompt. Esto evita que el LLM invente
datos de tarjetas falsos.
"""

import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

from strands import tool

from config.request_context import resolver_usuario_id

logger = logging.getLogger(__name__)


def _cargar_tarjetas_para_prompt(usuario_id: str) -> str:
    """Carga tarjetas de DynamoDB y las formatea como texto para inyectar en el prompt."""
    if not usuario_id:
        return ""
    try:
        from tools.persistencia_dynamodb import cargar_tarjetas, deduplicar_tarjetas

        tarjetas = cargar_tarjetas(usuario_id)
        if not tarjetas:
            logger.warning("No se encontraron tarjetas en DynamoDB para %s", usuario_id)
            return ""

        tarjetas_unicas = deduplicar_tarjetas(tarjetas)

        # Formatear como JSON limpio para el prompt
        tarjetas_resumen = []
        for t in tarjetas_unicas:
            tarjetas_resumen.append({
                "banco": t.get("banco", ""),
                "ultimos_4_digitos": t.get("ultimos_4_digitos", ""),
                "saldo": t.get("saldo", 0),
                "tcea": t.get("tcea", 0),
                "pago_minimo": t.get("pago_minimo", 0),
                "fecha_corte": t.get("fecha_corte", ""),
            })

        logger.info("Pre-cargadas %d tarjetas de DynamoDB para prompt (usuario %s)",
                     len(tarjetas_resumen), usuario_id)
        return json.dumps(tarjetas_resumen, ensure_ascii=False, indent=2)

    except Exception as e:
        logger.warning("No se pudo pre-cargar tarjetas de DynamoDB: %s", e)
        return ""


@tool
def analisis_y_detective_paralelo(
    consulta_analista: str,
    consulta_detective: str,
    usuario_id: str = ""
) -> dict:
    """
    Ejecuta el agente analista y el agente detective de gastos hormiga EN PARALELO.
    Usa este tool siempre que necesites tanto el análisis financiero como la detección
    de gastos hormiga. Es mucho más rápido que llamarlos por separado.

    Args:
        consulta_analista: Consulta para el agente analista (diagnóstico, plan de pagos, alternativas)
        consulta_detective: Consulta para el agente detective (gastos hormiga, oportunidades de ahorro)
        usuario_id: ID del usuario para cargar datos reales de DynamoDB (OBLIGATORIO para datos correctos)

    Returns:
        Dict con resultado_analista y resultado_detective
    """
    resultados = {}

    # El system prompt del orquestador insiste en que pase usuario_id, pero eso sigue
    # siendo una decisión del LLM. Se resuelve desde el contexto de la petición para
    # que la pre-carga sea realmente determinística.
    usuario_id = resolver_usuario_id(usuario_id)

    # PRE-CARGAR tarjetas de DynamoDB ANTES de crear sub-agentes
    # Esto es determinístico: no depende de que el LLM pase parámetros correctos
    tarjetas_json = _cargar_tarjetas_para_prompt(usuario_id)

    bloque_datos = ""
    if tarjetas_json:
        bloque_datos = (
            "\n\n===DATOS REALES DEL USUARIO (de DynamoDB)===\n"
            "ESTAS son las tarjetas REALES del usuario. USA ESTOS DATOS y NO inventes otros.\n"
            f"usuario_id: {usuario_id}\n"
            f"tarjetas:\n{tarjetas_json}\n"
            "===FIN DATOS REALES===\n\n"
            "IMPORTANTE: Cuando llames a diagnosticar_salud_financiera, optimizar_plan_pagos "
            "o evaluar_alternativas_deuda, pasa EXACTAMENTE estas tarjetas y este usuario_id. "
            "NO inventes tarjetas diferentes."
        )
        logger.info("Datos reales inyectados en prompt del analista (%d chars)", len(bloque_datos))
    else:
        logger.warning("No se pudieron pre-cargar tarjetas de DynamoDB para usuario_id=%s", usuario_id)

    def _run_analista_directo():
        from strands import Agent
        from config.models import worker_model
        from tools.diagnosticar_salud_financiera import diagnosticar_salud_financiera
        from tools.optimizar_plan_pagos import optimizar_plan_pagos
        from tools.evaluar_alternativas_deuda import evaluar_alternativas_deuda
        from tools.persistencia_dynamodb import obtener_estados_cuenta

        agent = Agent(
            system_prompt="Eres un analista financiero especializado en deudas de tarjetas de crédito en Perú. "
            "Diagnostica salud financiera, optimiza planes de pago y evalúa alternativas de deuda. "
            "Usa S/ para soles y TCEA para tasas.\n\n"
            "REGLA CRÍTICA: Si el prompt incluye un bloque ===DATOS REALES DEL USUARIO===, "
            "usa EXCLUSIVAMENTE esas tarjetas. NO inventes otras tarjetas ni otros montos. "
            "Pasa esas tarjetas tal cual a las tools, incluyendo el usuario_id.\n\n"
            "REGLA OBLIGATORIA: Al final de tu respuesta, SIEMPRE incluye un bloque con los datos exactos "
            "que devolvieron las tools, en este formato:\n"
            "---DATOS_TOOLS---\n"
            "deuda_total: [número exacto de diagnosticar_salud_financiera]\n"
            "pago_minimo_total: [número exacto]\n"
            "intereses_mensuales: [número exacto]\n"
            "ratio_deuda_ingreso: [número exacto]\n"
            "proyeccion_minimos_meses: [número exacto de proyeccion_minimos.meses]\n"
            "proyeccion_minimos_costo_total: [número exacto de proyeccion_minimos.costo_total]\n"
            "estrategia_meses: [número exacto de optimizar_plan_pagos.meses]\n"
            "estrategia_costo_total: [número exacto de optimizar_plan_pagos.costo_total]\n"
            "estrategia_metodo: [avalancha o bola_nieve]\n"
            "---FIN_DATOS---\n"
            "Estos datos son CRÍTICOS para que el orquestador no invente números.",
            model=worker_model,
            tools=[diagnosticar_salud_financiera, optimizar_plan_pagos,
                   evaluar_alternativas_deuda, obtener_estados_cuenta],
        )
        prompt_final = consulta_analista + bloque_datos
        return str(agent(prompt_final))

    def _run_detective_directo():
        from strands import Agent
        from config.models import worker_model
        from tools.detectar_gastos_hormiga import detectar_gastos_hormiga
        from tools.persistencia_dynamodb import obtener_estados_cuenta

        agent = Agent(
            system_prompt="Eres un detective de gastos especializado en identificar gastos hormiga "
            "en transacciones de tarjetas de crédito peruanas. Agrupa por categoría, "
            "cuantifica impacto mensual y anual. Usa S/ para soles.\n\n"
            "Si el prompt incluye un bloque ===DATOS REALES DEL USUARIO===, "
            "usa el usuario_id de ahí para llamar a obtener_estados_cuenta.",
            model=worker_model,
            tools=[detectar_gastos_hormiga, obtener_estados_cuenta],
        )
        prompt_final = consulta_detective + bloque_datos
        return str(agent(prompt_final))

    with ThreadPoolExecutor(max_workers=2) as executor:
        future_analista = executor.submit(_run_analista_directo)
        future_detective = executor.submit(_run_detective_directo)

        for future in as_completed([future_analista, future_detective]):
            try:
                result = future.result()
                if future == future_analista:
                    resultados["resultado_analista"] = result
                else:
                    resultados["resultado_detective"] = result
            except Exception as e:
                if future == future_analista:
                    resultados["resultado_analista"] = f"⚠️ Error en análisis: {str(e)}"
                else:
                    resultados["resultado_detective"] = f"⚠️ Error detectando gastos: {str(e)}"

    return resultados
