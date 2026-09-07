# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""
Tool para evaluar alternativas de manejo de deuda.

Las tasas de consolidación se derivan de las tarjetas reales del usuario
(la TCEA más baja que ya tiene), NO de constantes ficticias.
"""

import logging
from typing import Dict, Any, List

from strands import tool
from tools.persistencia_dynamodb import cargar_tarjetas, deduplicar_tarjetas, get_pago_base

logger = logging.getLogger(__name__)


@tool
def evaluar_alternativas_deuda(
    tarjetas: list,
    presupuesto_mensual: float,
    usuario_id: str = ""
) -> dict:
    """
    Evalúa alternativas para manejar la deuda.
    
    Args:
        tarjetas: Lista de tarjetas con saldo, tcea
        presupuesto_mensual: Presupuesto disponible
        usuario_id: ID del usuario para cargar datos reales de DynamoDB (recomendado)
        
    Returns:
        Dict con alternativas evaluadas basadas en datos reales del usuario
    """
    # Si tenemos usuario_id, cargar datos reales de DynamoDB
    if usuario_id:
        tarjetas_db = cargar_tarjetas(usuario_id)
        if tarjetas_db:
            tarjetas = tarjetas_db

    tarjetas = deduplicar_tarjetas(tarjetas)

    deuda_total = sum(t['saldo'] for t in tarjetas)
    if deuda_total <= 0:
        return {
            "alternativas": [],
            "recomendacion": "No tienes deuda registrada. No se requieren alternativas.",
        }

    # Derivar tasas de referencia de los datos reales del usuario
    tceas = sorted([t['tcea'] for t in tarjetas if t.get('tcea', 0) > 0])
    tcea_min = tceas[0] if tceas else 50.0
    tcea_promedio = sum(t['saldo'] * t['tcea'] for t in tarjetas) / deuda_total

    tarjeta_menor_tcea = min(tarjetas, key=lambda t: t.get('tcea', 999))
    banco_menor_tcea = tarjeta_menor_tcea.get('banco', 'tu banco con menor tasa')

    alternativas = []
    
    # 1. Redistribución de pagos (avalancha) — usa tasa promedio ponderada real
    meses_avalancha = _calcular_meses(deuda_total, presupuesto_mensual, tcea_promedio)
    costo_avalancha = _calcular_costo_total(deuda_total, presupuesto_mensual, tcea_promedio, meses_avalancha)
    alternativas.append({
        "nombre": "Redistribución de pagos (avalancha)",
        "descripcion": "Pagar más a la tarjeta con mayor TCEA primero",
        "meses": meses_avalancha,
        "costo_total": costo_avalancha,
        "tcea_usada": round(tcea_promedio, 1),
        "pros": ["No requiere trámites", "Sin costos adicionales", "Empieza hoy mismo"],
        "contras": ["Mantiene las tasas actuales de cada tarjeta"]
    })
    
    # 2. Consolidación — solo si hay más de una tarjeta y la tasa mínima es menor que el promedio
    if len(tarjetas) > 1 and tcea_min < tcea_promedio:
        meses_consolidacion = _calcular_meses(deuda_total, presupuesto_mensual, tcea_min)
        costo_consolidacion = _calcular_costo_total(deuda_total, presupuesto_mensual, tcea_min, meses_consolidacion)
        alternativas.append({
            "nombre": "Consolidación de deuda",
            "descripcion": (
                f"Consolidar toda la deuda a la TCEA de {banco_menor_tcea} ({tcea_min}%), "
                f"tu tarjeta con la tasa más baja. Consulta con {banco_menor_tcea} si ofrecen "
                f"un producto de consolidación, o busca opciones con TCEA igual o menor a {tcea_min}%."
            ),
            "meses": meses_consolidacion,
            "costo_total": costo_consolidacion,
            "tcea_usada": tcea_min,
            "banco_referencia": banco_menor_tcea,
            "pros": ["Un solo pago mensual", f"Basado en tu TCEA real más baja ({tcea_min}%)"],
            "contras": ["Requiere aprobación del banco", "Puede tener comisiones de apertura"],
            "nota": f"La TCEA de {tcea_min}% es la que ya tienes en {banco_menor_tcea}. Busca igualar o mejorar esa tasa."
        })

    mejor = min(alternativas, key=lambda a: a['costo_total']) if alternativas else None
    
    return {
        "alternativas": alternativas,
        "tcea_menor_usuario": tcea_min,
        "banco_menor_tcea": banco_menor_tcea,
        "recomendacion": mejor['nombre'] if mejor else "Avalancha",
        "nota_importante": (
            f"Las tasas usadas son las TCEA reales de tus tarjetas. "
            f"Tu tasa más baja es {tcea_min}% ({banco_menor_tcea}). "
            f"Si encuentras un producto de consolidación con TCEA menor, el ahorro sería aún mayor."
        )
    }


def _calcular_meses(deuda: float, pago_mensual: float, tcea: float) -> int:
    """Calcula meses para pagar deuda con tasa efectiva anual."""
    if pago_mensual <= 0:
        return 999

    # Convertir TCEA (tasa efectiva anual) a tasa mensual correctamente
    tasa_mensual = (1 + tcea / 100) ** (1 / 12) - 1

    # Si el pago no cubre ni el interés del primer mes, la deuda nunca se paga
    interes_inicial = deuda * tasa_mensual
    if pago_mensual <= interes_inicial:
        return 999

    saldo = deuda
    meses = 0

    while saldo > 1 and meses < 360:
        interes = saldo * tasa_mensual
        saldo = saldo + interes - pago_mensual
        meses += 1

        if saldo < 0:
            break

    return meses


def _calcular_costo_total(deuda: float, pago_mensual: float, tcea: float, meses: int) -> float:
    """Calcula el costo total real simulando mes a mes con saldo decreciente."""
    if meses >= 999:
        return 0.0  # No se puede calcular si la deuda es impagable
    tasa_mensual = (1 + tcea / 100) ** (1 / 12) - 1
    saldo = deuda
    total_pagado = 0.0

    for _ in range(meses):
        if saldo <= 0:
            break
        interes = saldo * tasa_mensual
        pago = min(pago_mensual, saldo + interes)
        saldo = saldo + interes - pago
        total_pagado += pago

    return round(total_pagado, 2)
