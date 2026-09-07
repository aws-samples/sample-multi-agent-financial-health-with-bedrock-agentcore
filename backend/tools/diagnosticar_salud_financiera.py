# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""
Tool para diagnosticar la salud financiera basada en deudas de tarjetas.
"""

import logging
from typing import Dict, Any, List

from strands import tool
from tools.persistencia_dynamodb import cargar_tarjetas, deduplicar_tarjetas, get_pago_base

logger = logging.getLogger(__name__)


@tool
def diagnosticar_salud_financiera(
    tarjetas: list,
    ingreso_mensual: float,
    usuario_id: str = "",
    payment_behavior: str = "minimum"
) -> dict:
    """
    Diagnostica la salud financiera del usuario.

    Args:
        tarjetas: Lista de tarjetas con saldo, tcea, pago_minimo
        ingreso_mensual: Ingreso mensual en soles
        usuario_id: ID del usuario para cargar datos reales de DynamoDB (recomendado)
        payment_behavior: "minimum" o "period" — determina qué pago usar como base

    Returns:
        Dict con diagnóstico completo
    """
    if usuario_id:
        tarjetas_db = cargar_tarjetas(usuario_id)
        if tarjetas_db:
            tarjetas = tarjetas_db

    tarjetas = deduplicar_tarjetas(tarjetas)

    # Calcular totales
    deuda_total = sum(t['saldo'] for t in tarjetas)
    pago_minimo_total = sum(get_pago_base(t, payment_behavior) for t in tarjetas)

    # Calcular intereses mensuales aproximados (tasa mensual correcta desde TCEA)
    intereses_mensuales = sum(
        t['saldo'] * ((1 + t['tcea'] / 100) ** (1 / 12) - 1) for t in tarjetas
    )

    # Ratio deuda/ingreso
    ratio_deuda_ingreso = deuda_total / ingreso_mensual if ingreso_mensual > 0 else 0

    # Semáforo
    if ratio_deuda_ingreso < 0.3:
        semaforo = "verde"
        mensaje = "Tu nivel de endeudamiento es saludable"
    elif ratio_deuda_ingreso < 0.5:
        semaforo = "amarillo"
        mensaje = "Tu nivel de endeudamiento requiere atención"
    else:
        semaforo = "rojo"
        mensaje = "Tu nivel de endeudamiento es crítico"

    # Detectar tarjetas impagables (pago mínimo < interés mensual)
    tarjetas_impagables = []
    for tarjeta in tarjetas:
        tasa_m = (1 + tarjeta['tcea'] / 100) ** (1 / 12) - 1
        interes_mensual = tarjeta['saldo'] * tasa_m
        pago_base = get_pago_base(tarjeta, payment_behavior)
        if pago_base < interes_mensual:
            tarjetas_impagables.append({
                "banco": tarjeta.get('banco', 'Desconocido'),
                "saldo": round(tarjeta['saldo'], 2),
                "pago_minimo": round(pago_base, 2),
                "interes_mensual": round(interes_mensual, 2),
                "deficit": round(interes_mensual - pago_base, 2),
            })

    # Proyección pagando mínimos — con pago mínimo dinámico como los bancos reales
    meses_minimos = 0
    costo_total_minimos = 0
    saldos_simulados = [t['saldo'] for t in tarjetas]
    deuda_crece = False

    while any(s > 1 for s in saldos_simulados) and meses_minimos < 360:
        meses_minimos += 1
        for i, tarjeta in enumerate(tarjetas):
            if saldos_simulados[i] > 1:
                tasa_m = (1 + tarjeta['tcea'] / 100) ** (1 / 12) - 1
                interes = saldos_simulados[i] * tasa_m
                pago_base = get_pago_base(tarjeta, payment_behavior)
                ratio = pago_base / tarjeta['saldo'] if tarjeta['saldo'] > 0 else 0.10
                pago_min_dinamico = max(pago_base, saldos_simulados[i] * ratio)
                pago = min(pago_min_dinamico, saldos_simulados[i] + interes)
                costo_total_minimos += pago
                saldos_simulados[i] = max(0, saldos_simulados[i] + interes - pago)

        # Detectar si después de 12 meses la deuda no ha bajado significativamente
        if meses_minimos == 12:
            saldo_actual = sum(saldos_simulados)
            if saldo_actual >= deuda_total * 0.95:
                deuda_crece = True

    proyeccion = {
        "meses": meses_minimos,
        "costo_total": round(costo_total_minimos, 2),
        "intereses_pagados": round(costo_total_minimos - deuda_total, 2),
    }

    if deuda_crece or meses_minimos >= 360:
        proyeccion["advertencia"] = (
            "Con los pagos mínimos actuales, la deuda tardará mucho en pagarse. "
            "Se recomienda aumentar el monto de pago mensual."
        )

    result = {
        "deuda_total": round(deuda_total, 2),
        "pago_minimo_total": round(pago_minimo_total, 2),
        "intereses_mensuales": round(intereses_mensuales, 2),
        "ratio_deuda_ingreso": round(ratio_deuda_ingreso, 2),
        "semaforo": semaforo,
        "mensaje": mensaje,
        "proyeccion_minimos": proyeccion,
    }

    if tarjetas_impagables:
        result["alerta_tarjetas_impagables"] = tarjetas_impagables

    return result
