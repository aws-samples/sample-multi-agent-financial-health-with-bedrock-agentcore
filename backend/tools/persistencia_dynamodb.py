# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""
Tool para persistir estados de cuenta en DynamoDB.
"""

import os
import re
import json
import logging
import threading
from typing import Dict, Any
from datetime import datetime, timezone
from decimal import Decimal

import boto3

from strands import tool
from config.constants import DEFAULT_REGION
from config.request_context import (
    get_usuario_actual,
    resolver_usuario_id,
    set_usuario_actual,
)

logger = logging.getLogger(__name__)

# usuario_id (Cognito sub) tiene formato UUID. El orquestador lo inyecta en la
# consulta como "usuario_id: <uuid>" (ver system prompts de los agentes).
_USUARIO_ID_RE = re.compile(
    r"usuario_id\s*[:=]\s*([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})"
)


def set_current_user_id(usuario_id: str) -> None:
    """Publica el usuario_id autenticado de la invocación en curso.

    Lo llama el entrypoint al inicio de cada invoke(), usando el usuario_id del
    payload (derivado del JWT de Cognito). Así las tools tienen una fuente de
    verdad determinística, sin depender de que el LLM propague el usuario_id.

    El almacenamiento vive en config/request_context (ContextVar con respaldo de
    proceso) en lugar de una variable de entorno: os.environ se hereda por
    cualquier subproceso y no distingue contexto. Además, aquí se publica también
    el valor vacío a propósito, para que una invocación sin usuario_id LIMPIE el
    contexto en vez de dejar activo el del usuario anterior en un proceso caliente.
    """
    set_usuario_actual(usuario_id)


def get_current_user_id() -> str:
    """Devuelve el usuario_id autenticado de la invocación en curso (o cadena vacía)."""
    return get_usuario_actual()


def extraer_usuario_id(texto: str) -> str:
    """Resuelve el usuario_id de forma determinística.

    Prioridad:
    1. El usuario_id autenticado de la invocación en curso (env de request),
       que es la fuente de verdad y NO depende del LLM.
    2. Fallback: el patrón "usuario_id: <uuid>" en el texto de la consulta
       (por si el entrypoint no lo publicó, ej. tests o invocaciones directas).

    Returns:
        El usuario_id resuelto, o cadena vacía si no hay ninguno.
    """
    actual = get_current_user_id()
    if actual:
        return actual
    if not texto:
        return ""
    m = _USUARIO_ID_RE.search(texto)
    return m.group(1) if m else ""


def construir_bloque_datos_usuario(usuario_id: str, incluir_movimientos: bool = False) -> str:
    """Pre-carga las tarjetas del usuario desde DynamoDB y arma un bloque de
    contexto para inyectar en el prompt de un sub-agente.

    Esto hace la carga de datos DETERMINÍSTICA (en código, no dependiente de que
    el LLM propague el usuario_id a las tools). Mismo formato que usa
    analisis_paralelo.py.

    Args:
        usuario_id: ID del usuario (Cognito sub).
        incluir_movimientos: si True, incluye los movimientos/transacciones de
            cada tarjeta (necesario para el detective de gastos hormiga).

    Returns:
        Bloque de texto con las tarjetas reales, o cadena vacía si no hay datos.
    """
    if not usuario_id:
        return ""
    try:
        tarjetas = deduplicar_tarjetas(cargar_tarjetas(usuario_id))
        if not tarjetas:
            logger.info("No se encontraron tarjetas en DynamoDB para el bloque de contexto")
            return ""

        resumen = []
        for t in tarjetas:
            entrada = {
                "banco": t.get("banco", ""),
                "ultimos_4_digitos": t.get("ultimos_4_digitos", ""),
                "saldo": t.get("saldo", 0),
                "tcea": t.get("tcea", 0),
                "pago_minimo": t.get("pago_minimo", 0),
                "pago_del_periodo": t.get("pago_del_periodo", 0),
                "fecha_corte": t.get("fecha_corte", ""),
            }
            if incluir_movimientos:
                entrada["movimientos"] = t.get("movimientos", [])
            resumen.append(entrada)

        tarjetas_json = json.dumps(resumen, ensure_ascii=False, indent=2)
        bloque = (
            "\n\n===DATOS REALES DEL USUARIO (de DynamoDB)===\n"
            "ESTAS son las tarjetas REALES del usuario. USA ESTOS DATOS y NO inventes otros.\n"
            f"usuario_id: {usuario_id}\n"
            f"tarjetas:\n{tarjetas_json}\n"
            "===FIN DATOS REALES===\n\n"
            "IMPORTANTE: usa EXACTAMENTE estas tarjetas y este usuario_id al llamar "
            "a las tools. NO inventes tarjetas ni montos diferentes."
        )
        logger.info("Bloque de datos de usuario construido (%d tarjetas)", len(resumen))
        return bloque
    except Exception as e:
        logger.warning("No se pudo construir el bloque de datos del usuario: %s", e)
        return ""

_thread_local = threading.local()


def _get_table():
    """Thread-safe lazy init de DynamoDB table."""
    table_name = os.environ.get('DYNAMODB_TABLE_NAME', '')
    if not table_name:
        raise ValueError("DYNAMODB_TABLE_NAME env var es requerida")
    if not hasattr(_thread_local, 'dynamodb'):
        _thread_local.dynamodb = boto3.resource('dynamodb', region_name=DEFAULT_REGION)
    return _thread_local.dynamodb.Table(table_name)


def _convert_floats(obj):
    """Convierte floats a Decimal para DynamoDB."""
    if isinstance(obj, float):
        return Decimal(str(obj))
    elif isinstance(obj, dict):
        return {k: _convert_floats(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_convert_floats(i) for i in obj]
    return obj


def decimal_to_float(obj):
    """Convierte Decimal a float recursivamente. Usar al leer de DynamoDB."""
    if isinstance(obj, Decimal):
        return float(obj)
    elif isinstance(obj, dict):
        return {k: decimal_to_float(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [decimal_to_float(i) for i in obj]
    return obj


def cargar_tarjetas(usuario_id: str) -> list:
    """Carga tarjetas de un usuario desde DynamoDB. Retorna lista de dicts con floats.

    Punto único de lectura: lo usan analisis_paralelo, diagnosticar_salud_financiera,
    optimizar_plan_pagos, evaluar_alternativas_deuda y simular_escenario. Resolver el
    usuario_id aquí cubre todas esas rutas de una vez.
    """
    usuario_id = resolver_usuario_id(usuario_id)
    if not usuario_id:
        logger.error("cargar_tarjetas sin usuario_id: se devolverá una lista vacía")
        return []
    try:
        table = _get_table()
        response = table.query(
            KeyConditionExpression='usuario_id = :uid',
            ExpressionAttributeValues={':uid': usuario_id}
        )
        tarjetas = [decimal_to_float(item) for item in response.get('Items', [])]
        if tarjetas:
            logger.info("Cargadas %d tarjetas de DynamoDB", len(tarjetas))
        return tarjetas
    except Exception as e:
        logger.warning("No se pudo cargar tarjetas de DynamoDB: %s", e)
        return []


def deduplicar_tarjetas(tarjetas: list) -> list:
    """Deduplica tarjetas por banco+últimos_4_dígitos, quedándose con la fecha_corte más reciente."""
    seen = {}
    for t in tarjetas:
        key = f"{t.get('banco', '')}_{t.get('ultimos_4_digitos', '')}"
        existing = seen.get(key)
        if existing is None:
            seen[key] = t
        else:
            if t.get('fecha_corte', '') > existing.get('fecha_corte', ''):
                seen[key] = t
    return list(seen.values())


def get_pago_base(tarjeta: dict, payment_behavior: str = "minimum") -> float:
    """Retorna el pago base según la conducta del usuario (mínimo o período)."""
    if payment_behavior == "period":
        pago = tarjeta.get("pago_del_periodo", 0)
        if pago and pago > 0:
            return pago
    return tarjeta.get("pago_minimo", 0)


@tool
def guardar_estado_cuenta(usuario_id: str, tarjeta: dict) -> dict:
    """
    Guarda un estado de cuenta en DynamoDB.
    
    Args:
        usuario_id: ID del usuario
        tarjeta: Datos de la tarjeta con movimientos
        
    Returns:
        Dict con resultado de la operación
    """
    usuario_id = resolver_usuario_id(usuario_id)
    if not usuario_id:
        logger.error("guardar_estado_cuenta sin usuario_id: no se puede guardar la tarjeta")
        return {"success": False, "error": "usuario_id no disponible"}

    try:
        table = _get_table()

        # Generar ID de tarjeta
        tarjeta_id = f"{tarjeta['banco']}_{tarjeta.get('ultimos_4_digitos', '0000')}"
        
        # Preparar item (convertir floats a Decimal)
        item = _convert_floats({
            'usuario_id': usuario_id,
            'tarjeta_id': tarjeta_id,
            'banco': tarjeta['banco'],
            'tipo': tarjeta.get('tipo', 'bancaria'),
            'ultimos_4_digitos': tarjeta.get('ultimos_4_digitos', ''),
            'saldo': tarjeta['saldo'],
            'tcea': tarjeta['tcea'],
            'pago_minimo': tarjeta['pago_minimo'],
            'fecha_corte': tarjeta.get('fecha_corte', ''),
            'movimientos': tarjeta.get('movimientos', []),
            'fecha_actualizacion': datetime.now(timezone.utc).isoformat()
        })
        
        table.put_item(Item=item)
        logger.info("Tarjeta %s guardada para usuario %s", tarjeta_id, usuario_id)

        return {"success": True, "tarjeta_id": tarjeta_id}

    except Exception as e:
        logger.error("Error guardando tarjeta para usuario %s: %s", usuario_id, e)
        return {"success": False, "error": str(e)}


@tool
def obtener_estados_cuenta(usuario_id: str) -> dict:
    """
    Obtiene todos los estados de cuenta de un usuario.
    
    Args:
        usuario_id: ID del usuario
        
    Returns:
        Dict con tarjetas y movimientos
    """
    usuario_id = resolver_usuario_id(usuario_id)
    if not usuario_id:
        logger.error("obtener_estados_cuenta sin usuario_id: no se puede consultar")
        return {"success": False, "error": "usuario_id no disponible"}

    try:
        table = _get_table()

        response = table.query(
            KeyConditionExpression='usuario_id = :uid',
            ExpressionAttributeValues={':uid': usuario_id}
        )

        tarjetas = [decimal_to_float(item) for item in response.get('Items', [])]
        logger.info("obtener_estados_cuenta: %d tarjetas para usuario %s", len(tarjetas), usuario_id)

        # Consolidar movimientos
        todos_movimientos = []
        for tarjeta in tarjetas:
            for mov in tarjeta.get('movimientos', []):
                todos_movimientos.append({
                    **mov,
                    'banco': tarjeta['banco']
                })
        
        return {
            "success": True,
            "tarjetas": tarjetas,
            "movimientos": todos_movimientos
        }
        
    except Exception as e:
        return {"success": False, "error": str(e)}
