# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""
Tool para extraer datos de múltiples PDFs en paralelo usando ThreadPoolExecutor.
Persiste automáticamente en DynamoDB (fire-and-forget) y escribe Parquet al datalake.
"""

import json
import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import List

from strands import tool

from config.request_context import resolver_usuario_id

logger = logging.getLogger(__name__)

# Analytics datalake config (bucket cross-region)
ANALYTICS_BUCKET = os.environ.get("ANALYTICS_BUCKET", "")
ANALYTICS_REGION = os.environ.get("ANALYTICS_REGION", "")
ANALYTICS_PREFIX = "analytics/estados_cuenta_perfil"


@tool
def extraer_multiples_pdfs(s3_uris: List[str], usuario_id: str = "") -> dict:
    """
    Extrae datos de múltiples estados de cuenta PDF en paralelo.
    Persiste cada tarjeta en DynamoDB (fire-and-forget) y escribe Parquet al datalake.

    Args:
        s3_uris: Lista de URIs de S3 de los PDFs a procesar
        usuario_id: ID del usuario (para persistencia en DynamoDB y analytics)

    Returns:
        Dict con resultados por URI y resumen de éxitos/errores
    """
    # El modelo suele omitir usuario_id (tendría que copiarlo desde una frase en
    # lenguaje natural). Se resuelve desde el contexto de la petición, fijado en
    # código por el entrypoint, para que la persistencia no dependa del LLM.
    usuario_id = resolver_usuario_id(usuario_id)

    resultados = {}
    errores = []

    with ThreadPoolExecutor(max_workers=min(len(s3_uris), 5)) as executor:
        futures = {executor.submit(_extraer_directo, uri): uri for uri in s3_uris}
        for future in as_completed(futures):
            uri = futures[future]
            try:
                result = future.result()
                resultados[uri] = result
                if result.get("error"):
                    errores.append(f"{uri}: {result['error']}")
            except Exception as e:
                resultados[uri] = {"tarjeta": None, "error": str(e)}
                errores.append(f"{uri}: {str(e)}")

    # Persistir en DynamoDB + Parquet analytics (síncrono para garantizar integridad)
    exitosos = {u: r for u, r in resultados.items() if r.get("tarjeta")}
    persistidas = 0
    if exitosos and not usuario_id:
        # Antes esto se saltaba en silencio y el usuario perdía sus datos sin
        # ninguna señal. Ahora es un error explícito en los logs.
        logger.error(
            "No se puede persistir: %d tarjetas extraídas pero no hay usuario_id "
            "(ni argumento ni contexto de petición). Los datos se perderán.",
            len(exitosos),
        )
    elif exitosos:
        persistidas = _persistir(usuario_id, exitosos, s3_uris)

    return {
        "resultados": resultados,
        "total": len(s3_uris),
        "exitosos": len(exitosos),
        "fallidos": len(errores),
        "errores": errores,
        "persistidas": persistidas,
    }


def _persistir(usuario_id: str, exitosos: dict, s3_uris: list) -> int:
    """Guarda en DynamoDB y, si procede, escribe Parquet. Devuelve tarjetas guardadas.

    Se ejecuta de forma síncrona: si el LLM responde antes de que la escritura
    termine, el siguiente turno de la conversación no encontraría los datos.
    """
    try:
        guardadas = _persistir_en_dynamodb(usuario_id, exitosos)
        if guardadas == 0:
            logger.error(
                "Ninguna de las %d tarjetas extraídas se pudo guardar en DynamoDB "
                "para usuario %s",
                len(exitosos), usuario_id,
            )
        else:
            logger.info(
                "%d/%d tarjetas persistidas en DynamoDB para usuario %s",
                guardadas, len(exitosos), usuario_id,
            )
        if guardadas > 0 and ANALYTICS_BUCKET:
            _escribir_parquet_analytics(usuario_id, exitosos, s3_uris)
        return guardadas
    except Exception as e:
        logger.error("Error persistiendo estados de cuenta: %s", e, exc_info=True)
        return 0


def _persistir_en_dynamodb(usuario_id: str, resultados: dict) -> int:
    """Guarda cada tarjeta extraida exitosamente en DynamoDB."""
    from tools.persistencia_dynamodb import _get_table, _convert_floats

    guardadas = 0
    try:
        table = _get_table()
    except Exception as e:
        logger.warning("No se pudo conectar a DynamoDB: %s", e)
        return 0

    # Pre-cargar file_hashes para obtener el hash de cada s3_key
    s3_key_to_hash = {}
    try:
        hashes_table_name = os.environ.get("HASHES_TABLE_NAME", "")
        if hashes_table_name:
            import boto3
            from boto3.dynamodb.conditions import Key
            ddb = boto3.resource("dynamodb", region_name=os.environ.get("AWS_REGION", "us-east-2"))
            ht = ddb.Table(hashes_table_name)
            resp = ht.query(KeyConditionExpression=Key("usuario_id").eq(usuario_id))
            for h in resp.get("Items", []):
                if h.get("s3_key"):
                    s3_key_to_hash[h["s3_key"]] = h.get("file_hash", "")
    except Exception as e:
        logger.warning("Could not load file_hashes: %s", e)

    for uri, result in resultados.items():
        tarjeta = result.get("tarjeta")
        if not tarjeta:
            continue
        try:
            tarjeta_id = f"{tarjeta['banco']}_{tarjeta.get('ultimos_4_digitos', '0000')}"
            s3_key = uri.replace("s3://", "").split("/", 1)[1] if "s3://" in uri else ""
            file_hash = s3_key_to_hash.get(s3_key, "")
            item = _convert_floats({
                "usuario_id": usuario_id,
                "tarjeta_id": tarjeta_id,
                "banco": tarjeta["banco"],
                "tipo": tarjeta.get("tipo", "bancaria"),
                "ultimos_4_digitos": tarjeta.get("ultimos_4_digitos", ""),
                "saldo": tarjeta.get("saldo", 0),
                "tcea": tarjeta.get("tcea", 0),
                "pago_minimo": tarjeta.get("pago_minimo", 0),
                "fecha_corte": tarjeta.get("fecha_corte", ""),
                "movimientos": tarjeta.get("movimientos", []),
                "fecha_actualizacion": datetime.now(timezone.utc).isoformat(),
                "source_s3_key": s3_key,
                "file_hash": file_hash,
                "status": "analizado",
            })
            table.put_item(Item=item)
            guardadas += 1
            logger.info("Persistida tarjeta %s para usuario %s", tarjeta_id, usuario_id)
        except Exception as e:
            logger.warning("Error persistiendo tarjeta de %s: %s", uri, e)

    return guardadas



def _escribir_parquet_analytics(usuario_id: str, exitosos: dict, s3_uris: list):
    """Escribe datos extraidos como Parquet al bucket de analytics (cross-region)."""
    try:
        import io
        import boto3
        import pyarrow as pa
        import pyarrow.parquet as pq

        now = datetime.now(timezone.utc)
        anio = str(now.year)
        mes = f"{now.month:02d}"

        rows = []
        for uri, result in exitosos.items():
            tarjeta = result["tarjeta"]
            saldo = tarjeta.get("saldo", 0) or 0
            tcea = tarjeta.get("tcea", 0) or 0
            pago_min = tarjeta.get("pago_minimo", 0) or 0
            movimientos = tarjeta.get("movimientos", []) or []
            num_mov = len(movimientos)
            total_mov = sum(abs(m.get("monto", 0)) for m in movimientos)
            interes_est = round(saldo * ((1 + tcea / 100) ** (1/12) - 1), 2) if tcea > 0 else 0

            rows.append({
                "usuario_id": usuario_id,
                "ingreso_mensual": 0.0,
                "presupuesto_deudas": 0.0,
                "tarjeta_id": f"{tarjeta.get('banco', '')}_{tarjeta.get('ultimos_4_digitos', '0000')}",
                "banco": tarjeta.get("banco", ""),
                "tipo": tarjeta.get("tipo", "bancaria"),
                "ultimos_4_digitos": tarjeta.get("ultimos_4_digitos", ""),
                "saldo": float(saldo),
                "tcea": float(tcea),
                "pago_minimo": float(pago_min),
                "fecha_corte": tarjeta.get("fecha_corte", ""),
                "num_movimientos": num_mov,
                "total_movimientos": float(total_mov),
                "ratio_deuda_ingreso": 0.0,
                "interes_mensual_estimado": float(interes_est),
                "semaforo": "",
                "fecha_exportacion": now,
            })

        if not rows:
            return

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
            ("fecha_exportacion", pa.timestamp("ms")),
        ])

        table = pa.Table.from_pylist(rows, schema=schema)
        buf = io.BytesIO()
        pq.write_table(table, buf, compression="snappy")
        buf.seek(0)

        ts = now.strftime("%Y%m%d_%H%M%S")
        key = f"{ANALYTICS_PREFIX}/anio={anio}/mes={mes}/{usuario_id}_{ts}.snappy.parquet"

        s3_client = boto3.client("s3", region_name=ANALYTICS_REGION) if ANALYTICS_REGION else boto3.client("s3")
        s3_client.put_object(Bucket=ANALYTICS_BUCKET, Key=key, Body=buf.getvalue())
        logger.info("Parquet escrito: s3://%s/%s (%d filas)", ANALYTICS_BUCKET, key, len(rows))

    except ImportError:
        logger.warning("pyarrow no disponible, saltando escritura Parquet")
    except Exception as e:
        logger.warning("Error escribiendo Parquet analytics: %s", e)


def _extraer_directo(s3_uri: str) -> dict:
    """Extraccion directa sin pasar por el wrapper de strands tool."""
    import base64
    import boto3

    EXTRACTOR_MODEL = os.environ.get(
        "BEDROCK_EXTRACTOR_MODEL", "us.anthropic.claude-sonnet-4-5-20250929-v1:0"
    )
    bedrock_runtime = boto3.client(
        "bedrock-runtime", region_name=os.environ.get("AWS_REGION", "us-east-2")
    )

    try:
        # Validar URI de S3
        allowed_bucket = os.environ.get("UPLOAD_BUCKET", "")
        if not s3_uri.startswith("s3://"):
            return {"tarjeta": None, "error": "URI de S3 inválida"}
        parts = s3_uri.replace("s3://", "").split("/", 1)
        if len(parts) != 2 or not parts[1]:
            return {"tarjeta": None, "error": "URI de S3 mal formada"}
        if allowed_bucket and parts[0] != allowed_bucket:
            return {"tarjeta": None, "error": f"Bucket no autorizado: {parts[0]}"}
        s3 = boto3.client("s3")
        response = s3.get_object(Bucket=parts[0], Key=parts[1])
        pdf_bytes = response["Body"].read()
        if not pdf_bytes[:4] == b'%PDF':
            return {"tarjeta": None, "error": "El archivo no es un PDF válido"}
        pdf_b64 = base64.b64encode(pdf_bytes).decode("utf-8")

        response = bedrock_runtime.invoke_model(
            modelId=EXTRACTOR_MODEL,
            body=json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 2000,
                "messages": [{
                    "role": "user",
                    "content": [
                        {
                            "type": "document",
                            "source": {
                                "type": "base64",
                                "media_type": "application/pdf",
                                "data": pdf_b64,
                            },
                        },
                        {
                            "type": "text",
                            "text": """Extrae estos datos del estado de cuenta en JSON:
{
  "banco": "nombre del banco/retailer",
  "tipo": "bancaria o retail",
  "titular": "nombre completo del titular de la tarjeta",
  "ultimos_4_digitos": "ultimos 4 digitos",
  "saldo": numero,
  "tcea": numero,
  "pago_minimo": numero,
  "pago_del_periodo": numero,
  "fecha_corte": "DD/MM/YYYY",
  "movimientos": [
    {"fecha": "DD/MM/YYYY", "comercio": "nombre", "monto": numero}
  ]
}
Extrae TODOS los movimientos/transacciones. Solo JSON, sin texto adicional.""",
                        },
                    ],
                }],
            }),
        )

        result = json.loads(response["body"].read())
        content = result["content"][0]["text"]
        json_match = re.search(r"\{.*\}", content, re.DOTALL)

        if json_match:
            return {"tarjeta": json.loads(json_match.group()), "error": None}
        else:
            return {"tarjeta": None, "error": "No se pudo parsear respuesta"}
    except Exception as e:
        return {"tarjeta": None, "error": str(e)}
