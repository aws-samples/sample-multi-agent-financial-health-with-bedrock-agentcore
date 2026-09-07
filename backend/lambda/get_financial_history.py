# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""
Lambda — consulta historial financiero de un usuario desde DynamoDB.
GET /history/{usuario_id}?period=semester|year|5years
"""

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Key

from shared import get_authenticated_user, cors_headers


class DecimalEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, Decimal):
            return float(o)
        return super().default(o)

logger = logging.getLogger()
logger.setLevel(logging.INFO)

TABLE_NAME = os.environ["FINANCIAL_HISTORY_TABLE_NAME"]
dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table(TABLE_NAME)

PERIOD_DAYS = {
    "semester": 180,
    "year": 365,
    "5years": 1825,
}


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

        params = event.get("queryStringParameters") or {}
        period = params.get("period", "year")
        days = PERIOD_DAYS.get(period, 365)

        now = datetime.now(timezone.utc)
        start = (now - timedelta(days=days)).isoformat()

        response = table.query(
            KeyConditionExpression=Key("usuario_id").eq(usuario_id)
            & Key("timestamp").gte(start),
            ScanIndexForward=True,
        )

        items = response.get("Items", [])

        return {
            "statusCode": 200,
            "headers": CORS_HEADERS,
            "body": json.dumps({"history": items, "count": len(items), "period": period}, cls=DecimalEncoder),
        }
    except Exception as e:
        logger.error("Error querying history: %s", e, exc_info=True)
        return {
            "statusCode": 500,
            "headers": CORS_HEADERS,
            "body": json.dumps({"error": "Internal server error"}),
        }
