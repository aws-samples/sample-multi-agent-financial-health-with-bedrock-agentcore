# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""
Lambda Dispatcher — recibe el request, crea un job en DynamoDB,
invoca al worker de forma asíncrona y retorna el job_id inmediatamente.
"""

import json
import logging
import os
import time
import uuid

import boto3

from shared import get_authenticated_user, cors_headers

logger = logging.getLogger()
logger.setLevel(logging.INFO)

JOBS_TABLE = os.environ["JOBS_TABLE_NAME"]
WORKER_FN = os.environ["WORKER_FUNCTION_NAME"]

dynamodb = boto3.resource("dynamodb")
jobs_table = dynamodb.Table(JOBS_TABLE)
lambda_client = boto3.client("lambda")


def lambda_handler(event, context):
    CORS_HEADERS = cors_headers()
    try:
        body = json.loads(event.get("body", "{}"))
        prompt = body.get("prompt", "")
        # Extract usuario_id from JWT — ignore client-provided value
        usuario_id = get_authenticated_user(event)
        if not usuario_id:
            return {
                "statusCode": 401,
                "headers": CORS_HEADERS,
                "body": json.dumps({"error": "unauthorized"}),
            }
        contexto = body.get("contexto")
        session_id = body.get("session_id") or str(uuid.uuid4())

        if not prompt:
            return {
                "statusCode": 400,
                "headers": CORS_HEADERS,
                "body": json.dumps({"error": "prompt is required"}),
            }

        if len(prompt) > 10000:
            return {
                "statusCode": 400,
                "headers": CORS_HEADERS,
                "body": json.dumps({"error": "prompt exceeds maximum length (10000 chars)"}),
            }

        job_id = str(uuid.uuid4())

        # Guardar job como PENDING (sin TTL — los jobs son registro permanente)
        jobs_table.put_item(Item={
            "job_id": job_id,
            "status": "PENDING",
            "session_id": session_id,
            "usuario_id": usuario_id,
            "created_at": int(time.time()),
        })

        # Invocar worker async
        worker_payload = {
            "job_id": job_id,
            "prompt": prompt,
            "usuario_id": usuario_id,
            "session_id": session_id,
            "authenticated_user": usuario_id,
        }
        if contexto:
            worker_payload["contexto"] = contexto

        # Pasar contexto de país/idioma del usuario
        for key in ("country", "currency", "language", "payment_behavior"):
            val = body.get(key)
            if val:
                worker_payload.setdefault("contexto", {})[key] = val

        lambda_client.invoke(
            FunctionName=WORKER_FN,
            InvocationType="Event",  # async
            Payload=json.dumps(worker_payload).encode(),
        )

        logger.info("Job %s created, worker invoked async", job_id)

        return {
            "statusCode": 202,
            "headers": CORS_HEADERS,
            "body": json.dumps({
                "success": True,
                "job_id": job_id,
                "session_id": session_id,
                "status": "PENDING",
            }),
        }
    except Exception as e:
        logger.error("Error in dispatcher: %s", e, exc_info=True)
        return {
            "statusCode": 500,
            "headers": CORS_HEADERS,
            "body": json.dumps({"success": False, "error": "Internal server error"}),
        }
