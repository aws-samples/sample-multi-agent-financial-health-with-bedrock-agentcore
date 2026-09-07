# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""
Lambda — GET /last-analysis/{usuario_id}
Retorna el último análisis completado de un usuario desde la tabla Jobs.
Usa el GSI usuario_id-completed_at-index para buscar eficientemente.
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

JOBS_TABLE = os.environ["JOBS_TABLE_NAME"]
dynamodb = boto3.resource("dynamodb")
jobs_table = dynamodb.Table(JOBS_TABLE)


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

        # Query GSI for last completed job with full presentation (debtComposition chart)
        from boto3.dynamodb.conditions import Attr
        response = jobs_table.query(
            IndexName="usuario_id-completed_at-index",
            KeyConditionExpression=Key("usuario_id").eq(usuario_id),
            ScanIndexForward=False,  # descending — most recent first
            Limit=10,  # scan recent jobs to find one with full analysis
            FilterExpression=Attr("has_presentation").eq(True),
        )

        # Prefer the job with debtComposition (full analysis) over partial ones
        items = response.get("Items", [])
        selected = None
        for item in items:
            result = item.get("result", "")
            if "debtComposition" in result:
                selected = item
                break
        if not selected and items:
            selected = items[0]

        if not selected:
            return {
                "statusCode": 200,
                "headers": CORS_HEADERS,
                "body": json.dumps({"found": False}),
            }

        return {
            "statusCode": 200,
            "headers": CORS_HEADERS,
            "body": json.dumps({
                "found": True,
                "job_id": selected.get("job_id", ""),
                "result": selected.get("result", ""),
                "session_id": selected.get("session_id", ""),
                "completed_at": selected.get("completed_at", 0),
            }, cls=DecimalEncoder),
        }
    except Exception as e:
        logger.error("Error querying last analysis: %s", e, exc_info=True)
        return {
            "statusCode": 500,
            "headers": CORS_HEADERS,
            "body": json.dumps({"error": "Internal server error"}),
        }
