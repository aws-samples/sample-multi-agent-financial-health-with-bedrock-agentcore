# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""
Lambda — GET /user-documents/{usuario_id}
Retorna los documentos (tarjetas) de un usuario desde la tabla de estados de cuenta,
más los hashes de archivos ya procesados para control de duplicados.
"""

import json
import logging
import os
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Key

from shared import get_authenticated_user, cors_headers

logger = logging.getLogger()
logger.setLevel(logging.INFO)

TABLE_NAME = os.environ["DYNAMODB_TABLE_NAME"]
HASHES_TABLE = os.environ["HASHES_TABLE_NAME"]
dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table(TABLE_NAME)
hashes_table = dynamodb.Table(HASHES_TABLE)


class DecimalEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, Decimal):
            return float(o)
        return super().default(o)


def lambda_handler(event, context):
    CORS_HEADERS = cors_headers()
    try:
        usuario_id = get_authenticated_user(event)
        if not usuario_id:
            return {
                "statusCode": 401,
                "headers": CORS_HEADERS,
                "body": json.dumps({"error": "unauthorized"}),
            }

        # 1) Obtener tarjetas del usuario (fuente principal de documentos)
        response = table.query(
            KeyConditionExpression=Key("usuario_id").eq(usuario_id),
        )
        items = response.get("Items", [])

        documents = []
        for item in items:
            documents.append({
                "tarjeta_id": item.get("tarjeta_id", ""),
                "banco": item.get("banco", ""),
                "ultimos_4_digitos": item.get("ultimos_4_digitos", ""),
                "saldo": item.get("saldo", 0),
                "fecha_corte": item.get("fecha_corte", ""),
                "status": item.get("status", "analizado"),
                "file_hash": item.get("file_hash", ""),
                "source_s3_key": item.get("source_s3_key", ""),
            })

        # 2) Obtener hashes para deduplicación y bucket para S3 URIs
        hashes_response = hashes_table.query(
            KeyConditionExpression=Key("usuario_id").eq(usuario_id),
        )
        hashes = {}
        for h in hashes_response.get("Items", []):
            hashes[h["file_hash"]] = h.get("filename", "")

        return {
            "statusCode": 200,
            "headers": CORS_HEADERS,
            "body": json.dumps({
                "documents": documents,
                "hashes": hashes,
                "bucket": os.environ.get("PDFS_BUCKET_NAME", ""),
            }, cls=DecimalEncoder),
        }
    except Exception as e:
        logger.error("Error querying user documents: %s", e, exc_info=True)
        return {
            "statusCode": 500,
            "headers": CORS_HEADERS,
            "body": json.dumps({"error": "Internal server error"}),
        }
