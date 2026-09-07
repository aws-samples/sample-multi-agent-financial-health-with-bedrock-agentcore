# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""
Lambda para exportar datos de DynamoDB al data lake S3 en formato Parquet.

Combina datos de EstadosCuenta con perfil de usuario en una tabla
analítica unificada particionada por año/mes.
"""

import os
import io
import logging
from datetime import datetime
from decimal import Decimal

import boto3
import pyarrow as pa
import pyarrow.parquet as pq

logger = logging.getLogger()
logger.setLevel(logging.INFO)

AWS_REGION = os.environ.get("AWS_REGION", "us-east-2")

dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION)
s3 = boto3.client("s3", region_name=AWS_REGION)

DATA_LAKE_BUCKET = os.environ["DATA_LAKE_BUCKET"]
ESTADOS_CUENTA_TABLE = os.environ["ESTADOS_CUENTA_TABLE"]

# Umbrales de salud financiera (mismos que backend/config/constants.py)
RATIO_SALUDABLE = 0.30
RATIO_RIESGO = 0.50


def _decimal_to_float(obj):
    """Convierte Decimal a float recursivamente."""
    if isinstance(obj, Decimal):
        return float(obj)
    elif isinstance(obj, dict):
        return {k: _decimal_to_float(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_decimal_to_float(i) for i in obj]
    return obj


def _calcular_semaforo(ratio: float) -> str:
    """Calcula el semáforo de salud financiera."""
    if ratio < RATIO_SALUDABLE:
        return "verde"
    elif ratio < RATIO_RIESGO:
        return "amarillo"
    return "rojo"


def _scan_all_items(table_name: str) -> list:
    """Escanea todos los items de una tabla DynamoDB."""
    table = dynamodb.Table(table_name)
    items = []
    response = table.scan()
    items.extend(response.get("Items", []))

    while "LastEvaluatedKey" in response:
        response = table.scan(ExclusiveStartKey=response["LastEvaluatedKey"])
        items.extend(response.get("Items", []))

    return [_decimal_to_float(item) for item in items]


def _build_analytics_rows(items: list) -> list:
    """
    Construye filas analíticas combinando estados de cuenta con perfil.

    Agrupa por usuario_id para calcular métricas agregadas y asignar
    datos de perfil (ingreso, presupuesto) a cada fila de tarjeta.
    """
    now = datetime.utcnow()
    rows = []

    # Agrupar por usuario
    usuarios = {}
    for item in items:
        uid = item.get("usuario_id", "unknown")
        if uid not in usuarios:
            usuarios[uid] = []
        usuarios[uid].append(item)

    for usuario_id, tarjetas in usuarios.items():
        # Calcular deuda total del usuario para ratio
        deuda_total = sum(t.get("saldo", 0) for t in tarjetas)

        # Ingreso y presupuesto (del perfil si existe, sino defaults)
        ingreso = tarjetas[0].get("ingreso_mensual", 0) if tarjetas else 0
        presupuesto = tarjetas[0].get("presupuesto_deudas", 0) if tarjetas else 0

        ratio = deuda_total / ingreso if ingreso > 0 else 0
        semaforo = _calcular_semaforo(ratio)

        for tarjeta in tarjetas:
            saldo = tarjeta.get("saldo", 0)
            tcea = tarjeta.get("tcea", 0)
            movimientos = tarjeta.get("movimientos", [])
            interes_mensual = saldo * ((1 + tcea / 100) ** (1/12) - 1) if tcea else 0

            rows.append({
                "usuario_id": usuario_id,
                "ingreso_mensual": ingreso,
                "presupuesto_deudas": presupuesto,
                "tarjeta_id": tarjeta.get("tarjeta_id", ""),
                "banco": tarjeta.get("banco", ""),
                "tipo": tarjeta.get("tipo", ""),
                "ultimos_4_digitos": tarjeta.get("ultimos_4_digitos", ""),
                "saldo": saldo,
                "tcea": tcea,
                "pago_minimo": tarjeta.get("pago_minimo", 0),
                "fecha_corte": tarjeta.get("fecha_corte", ""),
                "num_movimientos": len(movimientos),
                "total_movimientos": sum(
                    abs(m.get("monto", 0)) for m in movimientos
                ),
                "ratio_deuda_ingreso": round(ratio, 4),
                "interes_mensual_estimado": round(interes_mensual, 2),
                "semaforo": semaforo,
                "fecha_exportacion": now.isoformat(),
                "anio": now.strftime("%Y"),
                "mes": now.strftime("%m"),
            })

    return rows


def _write_parquet_to_s3(rows: list, bucket: str) -> str:
    """Escribe filas como Parquet particionado en S3."""
    if not rows:
        logger.info("No hay filas para exportar")
        return "empty"

    now = datetime.utcnow()
    anio = now.strftime("%Y")
    mes = now.strftime("%m")

    schema = pa.schema([
        ("usuario_id", pa.string()),
        ("ingreso_mensual", pa.float64()),
        ("presupuesto_deudas", pa.float64()),
        ("tarjeta_id", pa.string()),
        ("banco", pa.string()),
        ("tipo", pa.string()),
        ("ultimos_4_digitos", pa.string()),
        ("saldo", pa.float64()),
        ("tcea", pa.float64()),
        ("pago_minimo", pa.float64()),
        ("fecha_corte", pa.string()),
        ("num_movimientos", pa.int32()),
        ("total_movimientos", pa.float64()),
        ("ratio_deuda_ingreso", pa.float64()),
        ("interes_mensual_estimado", pa.float64()),
        ("semaforo", pa.string()),
        ("fecha_exportacion", pa.string()),
        ("anio", pa.string()),
        ("mes", pa.string()),
    ])

    # Construir arrays columnar
    arrays = []
    for field in schema:
        values = [row.get(field.name) for row in rows]
        arrays.append(pa.array(values, type=field.type))

    table = pa.table(arrays, schema=schema)

    # Escribir a buffer
    buf = io.BytesIO()
    pq.write_table(table, buf, compression="snappy")
    buf.seek(0)

    # Upload a S3 con particiones Hive-style
    key = (
        f"analytics/estados_cuenta_perfil/"
        f"anio={anio}/mes={mes}/"
        f"export-{now.strftime('%Y%m%d-%H%M%S')}.parquet"
    )
    s3.put_object(Bucket=bucket, Key=key, Body=buf.getvalue())

    logger.info(f"Exportadas {len(rows)} filas a s3://{bucket}/{key}")
    return key


def lambda_handler(event, context):
    """Handler principal: escanea DynamoDB y exporta a S3 Parquet."""
    try:
        logger.info("Iniciando exportación al data lake")

        items = _scan_all_items(ESTADOS_CUENTA_TABLE)
        logger.info(f"Escaneados {len(items)} items de DynamoDB")

        rows = _build_analytics_rows(items)
        logger.info(f"Construidas {len(rows)} filas analíticas")

        key = _write_parquet_to_s3(rows, DATA_LAKE_BUCKET)

        return {
            "statusCode": 200,
            "body": {
                "message": "Exportación completada",
                "rows_exported": len(rows),
                "s3_key": key,
            },
        }

    except Exception as e:
        logger.error("Error en exportación: %s", e, exc_info=True)
        return {
            "statusCode": 500,
            "body": {"error": "Internal server error"},
        }
