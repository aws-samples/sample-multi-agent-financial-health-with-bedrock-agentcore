# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""
Tool para optimizar el plan de pagos de deudas.

La lógica interna está en _optimizar_interno() para que pueda ser
reutilizada por simular_escenario sin pasar por el wrapper @tool.
"""

import logging
from typing import Dict, Any, List

from strands import tool
from tools.persistencia_dynamodb import cargar_tarjetas, deduplicar_tarjetas, get_pago_base

logger = logging.getLogger(__name__)


def _optimizar_interno(
    tarjetas: list,
    presupuesto_mensual: float,
    metodo: str = "avalancha",
    payment_behavior: str = "minimum",
) -> dict:
    """Lógica interna de optimización — sin wrapper @tool."""
    tarjetas = deduplicar_tarjetas(tarjetas)

    if metodo == "avalancha":
        tarjetas_ordenadas = sorted(tarjetas, key=lambda t: t['tcea'], reverse=True)
    else:
        tarjetas_ordenadas = sorted(tarjetas, key=lambda t: t['saldo'])

    saldos = {t['banco']: t['saldo'] for t in tarjetas_ordenadas}
    meses = 0
    costo_total = 0
    pagos_por_mes = []

    while any(s > 1 for s in saldos.values()) and meses < 360:
        meses += 1
        presupuesto_restante = presupuesto_mensual
        pagos_mes = {}

        for tarjeta in tarjetas_ordenadas:
            banco = tarjeta['banco']
            if saldos[banco] > 1:
                tasa_mensual = (1 + tarjeta['tcea'] / 100) ** (1 / 12) - 1
                interes = saldos[banco] * tasa_mensual
                pago_base = get_pago_base(tarjeta, payment_behavior)
                ratio = pago_base / tarjeta['saldo'] if tarjeta['saldo'] > 0 else 0.10
                pago_min_dinamico = max(pago_base, saldos[banco] * ratio)
                pago_min = min(pago_min_dinamico, saldos[banco] + interes)
                pago = min(pago_min, presupuesto_restante)

                saldos[banco] = max(0, saldos[banco] + interes - pago)
                presupuesto_restante -= pago
                costo_total += pago
                pagos_mes[banco] = pago

        for tarjeta in tarjetas_ordenadas:
            banco = tarjeta['banco']
            if saldos[banco] > 1 and presupuesto_restante > 0:
                pago_extra = min(presupuesto_restante, saldos[banco])
                saldos[banco] -= pago_extra
                presupuesto_restante -= pago_extra
                costo_total += pago_extra
                pagos_mes[banco] += pago_extra
                break

        pagos_por_mes.append(pagos_mes)

    deuda_total = sum(t['saldo'] for t in tarjetas)

    return {
        "metodo": metodo,
        "meses": meses,
        "costo_total": round(costo_total, 2),
        "intereses_pagados": round(costo_total - deuda_total, 2),
        "orden_pago": [t['banco'] for t in tarjetas_ordenadas],
        "ahorro_vs_minimos": None,
    }


@tool
def optimizar_plan_pagos(
    tarjetas: list,
    presupuesto_mensual: float,
    metodo: str = "avalancha",
    usuario_id: str = ""
) -> dict:
    """
    Optimiza el plan de pagos usando método avalancha o bola de nieve.

    Args:
        tarjetas: Lista de tarjetas con saldo, tcea, pago_minimo, banco
        presupuesto_mensual: Presupuesto disponible para pagar deudas
        metodo: "avalancha" (mayor TCEA primero) o "bola_nieve" (menor saldo primero)
        usuario_id: ID del usuario para cargar datos reales de DynamoDB (recomendado)

    Returns:
        Dict con plan optimizado
    """
    # Si tenemos usuario_id, cargar datos reales de DynamoDB
    if usuario_id:
        tarjetas_db = cargar_tarjetas(usuario_id)
        if tarjetas_db:
            tarjetas = tarjetas_db
    return _optimizar_interno(tarjetas, presupuesto_mensual, metodo)
