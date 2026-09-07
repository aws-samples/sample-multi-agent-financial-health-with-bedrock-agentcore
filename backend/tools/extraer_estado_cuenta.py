# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""
Tool para extraer datos de estados de cuenta PDF usando Claude Sonnet Vision.
Persiste automaticamente en DynamoDB (fire-and-forget).
"""

import os
import json
import base64
import re
import logging
from typing import Dict, Any

import boto3

from strands import tool
from config.constants import DEFAULT_REGION
from config.request_context import resolver_usuario_id

logger = logging.getLogger(__name__)

EXTRACTOR_MODEL = os.environ.get('BEDROCK_EXTRACTOR_MODEL', 'us.anthropic.claude-sonnet-4-5-20250929-v1:0')
bedrock_runtime = boto3.client('bedrock-runtime', region_name=DEFAULT_REGION)


@tool
def extraer_estado_cuenta(s3_uri: str, usuario_id: str = "") -> dict:
    """
    Extrae informacion de un estado de cuenta PDF.
    Persiste automaticamente en DynamoDB si se proporciona usuario_id.

    Args:
        s3_uri: URI de S3 del PDF
        usuario_id: ID del usuario (para persistencia en DynamoDB)

    Returns:
        Dict con los datos extraidos
    """
    # El modelo puede omitir usuario_id; se resuelve desde el contexto de la petición.
    usuario_id = resolver_usuario_id(usuario_id)

    try:
        # Validar y descargar PDF de S3
        allowed_bucket = os.environ.get("UPLOAD_BUCKET", "")
        if not s3_uri.startswith("s3://"):
            return {"tarjeta": None, "error": "URI de S3 inválida"}
        parts = s3_uri.replace('s3://', '').split('/', 1)
        if len(parts) != 2 or not parts[1]:
            return {"tarjeta": None, "error": "URI de S3 mal formada"}
        if allowed_bucket and parts[0] != allowed_bucket:
            return {"tarjeta": None, "error": f"Bucket no autorizado: {parts[0]}"}
        s3 = boto3.client('s3')
        response = s3.get_object(Bucket=parts[0], Key=parts[1])
        pdf_bytes = response['Body'].read()
        if not pdf_bytes[:4] == b'%PDF':
            return {"tarjeta": None, "error": "El archivo no es un PDF válido"}
        pdf_b64 = base64.b64encode(pdf_bytes).decode('utf-8')
        
        # Invocar Claude
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
                                "data": pdf_b64
                            }
                        },
                        {
                            "type": "text",
                            "text": """Extrae estos datos del estado de cuenta en JSON:
{
  "banco": "nombre del banco/retailer",
  "tipo": "bancaria o retail",
  "titular": "nombre completo del titular de la tarjeta",
  "ultimos_4_digitos": "últimos 4 dígitos",
  "saldo": número,
  "tcea": número,
  "pago_minimo": número,
  "pago_del_periodo": número,
  "fecha_corte": "DD/MM/YYYY",
  "movimientos": [
    {"fecha": "DD/MM/YYYY", "comercio": "nombre", "monto": número}
  ]
}
Extrae TODOS los movimientos/transacciones. Solo JSON, sin texto adicional."""
                        }
                    ]
                }]
            })
        )
        
        # Parsear respuesta
        result = json.loads(response['body'].read())
        content = result['content'][0]['text']
        json_match = re.search(r'\{.*\}', content, re.DOTALL)
        
        if json_match:
            parsed = json.loads(json_match.group())
            # Persistir en DynamoDB de forma síncrona (<50ms)
            if usuario_id and parsed:
                _persistir_tarjeta(usuario_id, parsed)
            elif parsed:
                logger.error(
                    "Tarjeta extraída pero sin usuario_id: no se persistirá y se "
                    "perderá en el siguiente turno"
                )
            return {"tarjeta": parsed, "error": None}
        else:
            return {"tarjeta": None, "error": "No se pudo parsear respuesta"}
            
    except Exception as e:
        return {"tarjeta": None, "error": str(e)}



def _persistir_tarjeta(usuario_id: str, tarjeta: dict):
    """Guarda una tarjeta en DynamoDB de forma síncrona."""
    try:
        from datetime import datetime, timezone
        from tools.persistencia_dynamodb import _get_table, _convert_floats

        table = _get_table()
        tarjeta_id = f"{tarjeta['banco']}_{tarjeta.get('ultimos_4_digitos', '0000')}"
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
        })
        table.put_item(Item=item)
        logger.info("Tarjeta %s persistida para usuario %s", tarjeta_id, usuario_id)
    except Exception as e:
        logger.error("Error persistiendo tarjeta para usuario %s: %s", usuario_id, e, exc_info=True)
