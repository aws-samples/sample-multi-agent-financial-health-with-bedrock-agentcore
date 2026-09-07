# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""
Lambda Poll — GET /job/{job_id}
Retorna el estado del job y el resultado si está completo.
Detecta jobs zombies (PROCESSING por más de MAX_PROCESSING_S) y los marca FAILED.
"""

import json
import logging
import os
import time

import boto3

from shared import cors_headers

logger = logging.getLogger()
logger.setLevel(logging.INFO)

JOBS_TABLE = os.environ["JOBS_TABLE_NAME"]
MAX_PROCESSING_S = 630  # 10.5 min — si la Lambda worker tiene 600s timeout, esto cubre el caso zombie
dynamodb = boto3.resource("dynamodb")
jobs_table = dynamodb.Table(JOBS_TABLE)


def lambda_handler(event, context):
    CORS_HEADERS = cors_headers()
    try:
        job_id = event.get("pathParameters", {}).get("job_id")
        if not job_id:
            return {
                "statusCode": 400,
                "headers": CORS_HEADERS,
                "body": json.dumps({"error": "job_id is required"}),
            }

        response = jobs_table.get_item(Key={"job_id": job_id})
        item = response.get("Item")

        if not item:
            return {
                "statusCode": 404,
                "headers": CORS_HEADERS,
                "body": json.dumps({"error": "Job not found"}),
            }

        result = {
            "job_id": job_id,
            "status": item.get("status", "UNKNOWN"),
            "session_id": item.get("session_id", ""),
        }

        # Detectar jobs zombies: PROCESSING por más de MAX_PROCESSING_S
        if item.get("status") in ("PROCESSING", "PENDING"):
            created_at = int(item.get("created_at", 0) or 0)
            started_at = int(item.get("started_at", 0) or 0)
            ref_time = started_at or created_at
            if ref_time and (time.time() - ref_time) > MAX_PROCESSING_S:
                logger.warning("Zombie job detected: %s (age=%ds)", job_id, time.time() - ref_time)
                jobs_table.update_item(
                    Key={"job_id": job_id},
                    UpdateExpression="SET #s = :s, #e = :e",
                    ExpressionAttributeNames={"#s": "status", "#e": "error"},
                    ExpressionAttributeValues={
                        ":s": "FAILED",
                        ":e": "Timeout: el procesamiento excedió el tiempo máximo. Intenta de nuevo.",
                    },
                )
                result["status"] = "FAILED"
                result["success"] = False
                result["error"] = "Timeout: el procesamiento excedió el tiempo máximo. Intenta de nuevo."
                return {
                    "statusCode": 200,
                    "headers": CORS_HEADERS,
                    "body": json.dumps(result),
                }

        if item.get("status") == "COMPLETED":
            result["success"] = True
            result["result"] = item.get("result", "")
            result["usuario_id"] = item.get("usuario_id", "")

        if item.get("status") == "FAILED":
            result["success"] = False
            result["error"] = item.get("error", "Error desconocido")

        return {
            "statusCode": 200,
            "headers": CORS_HEADERS,
            "body": json.dumps(result),
        }
    except Exception as e:
        logger.error("Poll error: %s", e, exc_info=True)
        return {
            "statusCode": 500,
            "headers": CORS_HEADERS,
            "body": json.dumps({"error": "Internal server error"}),
        }
