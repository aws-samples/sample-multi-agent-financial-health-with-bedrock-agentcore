# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""
Tool: simular_escenario
Simula cambios en el plan de pagos (ingresos extra, recortes, nuevas compras).
"""

import logging
from typing import Dict, Any, List

from strands import tool

from tools.optimizar_plan_pagos import _optimizar_interno
from tools.persistencia_dynamodb import cargar_tarjetas

logger = logging.getLogger(__name__)


@tool
def simular_escenario(
    tarjetas: list,
    presupuesto_actual: float,
    cambios: dict,
    usuario_id: str = ""
) -> dict:
    """
    Simula un escenario de cambio en el plan de pagos.
    
    Args:
        tarjetas: Lista de tarjetas actuales
        presupuesto_actual: Presupuesto mensual actual
        cambios: Dict con cambios a simular:
            - pago_extra: {monto: float, tarjeta_banco: str} - Pago único
            - presupuesto_extra: float - Aumento mensual permanente
            - recorte_gastos: float - Reducción de gastos (aumenta presupuesto)
            - nueva_compra: {monto: float, cuotas: int, tcea: float} - Nueva deuda
        usuario_id: ID del usuario para cargar datos reales de DynamoDB (recomendado)
            
    Returns:
        Dict con comparación antes/después
    """
    if usuario_id:
        tarjetas_db = cargar_tarjetas(usuario_id)
        if tarjetas_db:
            tarjetas = tarjetas_db
    # Plan actual
    plan_actual = _optimizar_interno(tarjetas, presupuesto_actual, "avalancha")
    
    # Aplicar cambios
    tarjetas_simuladas = [t.copy() for t in tarjetas]
    presupuesto_simulado = presupuesto_actual
    
    # Pago extra único
    if 'pago_extra' in cambios:
        pago = cambios['pago_extra']
        for t in tarjetas_simuladas:
            if t['banco'] == pago['tarjeta_banco']:
                t['saldo'] = max(0, t['saldo'] - pago['monto'])
                break
    
    # Presupuesto extra mensual
    if 'presupuesto_extra' in cambios:
        presupuesto_simulado += cambios['presupuesto_extra']
    
    # Recorte de gastos (libera presupuesto)
    if 'recorte_gastos' in cambios:
        presupuesto_simulado += cambios['recorte_gastos']
    
    # Nueva compra en cuotas
    if 'nueva_compra' in cambios:
        compra = cambios['nueva_compra']
        # Calcular cuota mensual con interés compuesto
        tasa_mensual = (1 + compra['tcea'] / 100) ** (1/12) - 1
        cuota_mensual = compra['monto'] * (tasa_mensual * (1 + tasa_mensual) ** compra['cuotas']) / \
                       ((1 + tasa_mensual) ** compra['cuotas'] - 1)
        
        tarjetas_simuladas.append({
            'banco': 'Nueva compra',
            'saldo': compra['monto'],
            'tcea': compra['tcea'],
            'pago_minimo': round(cuota_mensual, 2)
        })
    
    # Plan simulado
    plan_simulado = _optimizar_interno(tarjetas_simuladas, presupuesto_simulado, "avalancha")
    
    # Comparación
    diferencia_meses = plan_actual['meses'] - plan_simulado['meses']
    diferencia_costo = plan_actual['costo_total'] - plan_simulado['costo_total']
    
    return {
        "plan_actual": {
            "meses": plan_actual['meses'],
            "costo_total": plan_actual['costo_total'],
            "presupuesto_mensual": presupuesto_actual
        },
        "plan_simulado": {
            "meses": plan_simulado['meses'],
            "costo_total": plan_simulado['costo_total'],
            "presupuesto_mensual": presupuesto_simulado
        },
        "impacto": {
            "meses_ahorrados": diferencia_meses,
            "ahorro_total": round(diferencia_costo, 2),
            "mejora": diferencia_meses > 0 or diferencia_costo > 0
        },
        "cambios_aplicados": cambios
    }
