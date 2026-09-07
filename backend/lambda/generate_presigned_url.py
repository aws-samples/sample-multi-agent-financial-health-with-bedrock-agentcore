# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""
Lambda para generar presigned URLs para upload de PDFs a S3.
Valida duplicados por hash SHA-256 contra DynamoDB antes de permitir el upload.
CORS headers en TODAS las respuestas (200, 400, 500).
"""

import json
import logging
import os
from datetime import datetime

import boto3
from botocore.config import Config as BotoConfig
from boto3.dynamodb.conditions import Key

from shared import get_authenticated_user, cors_headers

logger = logging.getLogger()
logger.setLevel(logging.INFO)

REGION = os.environ.get("AWS_REGION", "us-east-2")
s3_client = boto3.client(
    "s3",
    region_name=REGION,
    config=BotoConfig(
        signature_version="s3v4",
        s3={"addressing_style": "path"},
    ),
    endpoint_url=f"https://s3.{REGION}.amazonaws.com",
)
BUCKET_NAME = os.environ["PDFS_BUCKET_NAME"]
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB

# Tabla de hashes (opcional — si no está configurada, skip validación)
HASHES_TABLE = os.environ.get("HASHES_TABLE_NAME", "")
dynamodb = boto3.resource("dynamodb") if HASHES_TABLE else None
hashes_table = dynamodb.Table(HASHES_TABLE) if dynamodb and HASHES_TABLE else None


def lambda_handler(event, context):
    """Genera presigned URL para upload de PDF. Valida duplicados por hash."""
    CORS_HEADERS = cors_headers()
    try:
        # Auth from JWT
        user_id = get_authenticated_user(event)
        if not user_id:
            return {
                "statusCode": 401,
                "headers": CORS_HEADERS,
                "body": json.dumps({"error": "unauthorized"}),
            }

        body = json.loads(event.get("body", "{}"))
        filename = body.get("filename")
        file_hash = body.get("fileHash")  # SHA-256 del archivo

        if not filename:
            return {
                "statusCode": 400,
                "headers": CORS_HEADERS,
                "body": json.dumps({"error": "filename es requerido"}),
            }

        # Validar duplicado por hash si se proporcionó
        if file_hash and hashes_table:
            try:
                resp = hashes_table.get_item(
                    Key={"usuario_id": user_id, "file_hash": file_hash}
                )
                if "Item" in resp:
                    existing = resp["Item"].get("filename", "archivo previo")
                    return {
                        "statusCode": 409,
                        "headers": CORS_HEADERS,
                        "body": json.dumps({
                            "error": "duplicate",
                            "message": f"Este archivo ya fue procesado anteriormente como: {existing}",
                            "existing_filename": existing,
                        }),
                    }
            except Exception as e:
                # Si falla la validación, permitir el upload de todas formas
                logger.warning("Error checking hash duplicate: %s", e)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        s3_key = f"{user_id}/{timestamp}_{filename}"

        upload_url = s3_client.generate_presigned_url(
            "put_object",
            Params={
                "Bucket": BUCKET_NAME,
                "Key": s3_key,
                "ContentType": "application/pdf",
            },
            ExpiresIn=300,
        )

        # Registrar hash en DynamoDB para futura detección de duplicados
        if file_hash and hashes_table:
            try:
                hashes_table.put_item(Item={
                    "usuario_id": user_id,
                    "file_hash": file_hash,
                    "filename": filename,
                    "s3_key": s3_key,
                    "uploaded_at": datetime.now().isoformat(),
                })
            except Exception as e:
                logger.warning("Error saving hash: %s", e)

        return {
            "statusCode": 200,
            "headers": CORS_HEADERS,
            "body": json.dumps(
                {
                    "uploadUrl": upload_url,
                    "s3Uri": f"s3://{BUCKET_NAME}/{s3_key}",
                    "key": s3_key,
                }
            ),
        }
    except Exception as e:
        logger.error("Error: %s", e, exc_info=True)
        return {
            "statusCode": 500,
            "headers": CORS_HEADERS,
            "body": json.dumps({"error": "Internal server error"}),
        }
