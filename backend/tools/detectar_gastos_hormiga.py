# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""
Tool para detectar gastos hormiga en transacciones.
"""

import logging
from typing import Dict, Any, List
from collections import defaultdict

from strands import tool

logger = logging.getLogger(__name__)


# Patrones de comercios por categoría.
# NOTA: estos son nombres de comercios REALES usados como EJEMPLOS de patrones de
# coincidencia para categorizar las transacciones reales del usuario. No son datos
# de demo: sirven para mapear el texto de un movimiento a una categoría de gasto.
# AVISO DE MARCAS: los nombres de marcas son solo ejemplos con fines de
# categorización; no implican patrocinio, afiliación ni respaldo de esas marcas.
CATEGORIAS = {
    "delivery": ["rappi", "pedidosya", "uber eats", "glovo", "delivery"],
    "conveniencia": ["tambo", "oxxo", "mass", "listo", "repshop"],
    "cafe": ["starbucks", "juan valdez", "cafe", "coffee"],
    "suscripciones": ["netflix", "spotify", "amazon prime", "gym", "fitness"],
    "transporte": ["uber", "cabify", "beat", "taxi", "indrive"],
    "snacks": ["mcdonald", "kfc", "bembos", "popeyes", "burger"]
}


@tool
def detectar_gastos_hormiga(transacciones: list) -> dict:
    """
    Detecta y categoriza gastos hormiga.
    
    Args:
        transacciones: Lista con {fecha, comercio, monto}
        
    Returns:
        Dict con análisis de gastos hormiga
    """
    gastos_por_categoria = defaultdict(float)
    comercios_frecuentes = defaultdict(lambda: {"count": 0, "total": 0})
    
    # Categorizar transacciones
    for tx in transacciones:
        comercio = tx['comercio'].lower()
        monto = tx['monto']
        
        # Buscar categoría
        categoria_encontrada = "otros"
        for cat, patrones in CATEGORIAS.items():
            if any(patron in comercio for patron in patrones):
                categoria_encontrada = cat
                break
        
        gastos_por_categoria[categoria_encontrada] += monto
        comercios_frecuentes[tx['comercio']]["count"] += 1
        comercios_frecuentes[tx['comercio']]["total"] += monto
    
    # Total de gastos hormiga (excluir "otros")
    total_mensual = sum(v for k, v in gastos_por_categoria.items() if k != "otros")
    
    # Top comercios
    top_comercios = sorted(
        [{"comercio": k, "veces": v["count"], "total": v["total"]} 
         for k, v in comercios_frecuentes.items()],
        key=lambda x: x["total"],
        reverse=True
    )[:10]
    
    # Recomendaciones basadas en datos reales (sin porcentajes inventados)
    recomendaciones = []
    for cat, total in sorted(gastos_por_categoria.items(), key=lambda x: x[1], reverse=True):
        if cat != "otros" and total > 0:
            recomendaciones.append({
                "categoria": cat,
                "gasto_actual": round(total, 2),
                "sugerencia": _generar_sugerencia(cat, total)
            })
    
    return {
        "gastos_por_categoria": {k: round(v, 2) for k, v in gastos_por_categoria.items()},
        "total_mensual": round(total_mensual, 2),
        "proyeccion_anual": round(total_mensual * 12, 2),
        "top_comercios": top_comercios,
        "recomendaciones": recomendaciones[:5]
    }


def _generar_sugerencia(categoria: str, gasto_actual: float) -> str:
    """Genera sugerencia específica por categoría usando el monto real."""
    sugerencias = {
        "delivery": f"Gastas S/ {gasto_actual:.0f}/mes en delivery. Cocinar más en casa reduciría este gasto.",
        "conveniencia": f"Gastas S/ {gasto_actual:.0f}/mes en tiendas de conveniencia. Planificar compras semanales ayudaría.",
        "cafe": f"Gastas S/ {gasto_actual:.0f}/mes en café. Preparar café en casa es una alternativa.",
        "suscripciones": f"Gastas S/ {gasto_actual:.0f}/mes en suscripciones. Revisa cuáles realmente usas.",
        "transporte": f"Gastas S/ {gasto_actual:.0f}/mes en transporte por app. Evalúa alternativas para algunos viajes.",
        "snacks": f"Gastas S/ {gasto_actual:.0f}/mes en comida rápida. Llevar snacks de casa es una opción."
    }
    return sugerencias.get(categoria, f"Gastas S/ {gasto_actual:.0f}/mes en {categoria}. Evalúa si puedes reducirlo.")
