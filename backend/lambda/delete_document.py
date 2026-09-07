# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""
Lambda — DELETE /documents/{usuario_id}/{file_hash}
Elimina un documento: PDF de S3, hash de file_hashes, tarjeta de estados_cuenta,
e invalida análisis previos (jobs con has_presentation).
"""

import json
import logging
import os

import boto3
from boto3.dynamodb.conditions import Key, Attr

from shared import get_authenticated_user, cors_headers

logger = logging.getLogger()
logger.setLevel(logging.INFO)

HASHES_TABLE = os.environ["HASHES_TABLE_NAME"]
ESTADOS_TABLE = os.environ["ESTADOS_TABLE_NAME"]
JOBS_TABLE = os.environ["JOBS_TABLE_NAME"]
PDFS_BUCKET = os.environ["PDFS_BUCKET_NAME"]

dynamodb = boto3.resource("dynamodb")
s3 = boto3.client("s3")

hashes_table = dynamodb.Table(HASHES_TABLE)
estados_table = dynamodb.Table(ESTADOS_TABLE)
jobs_table = dynamodb.Table(JOBS_TABLE)


def lambda_handler(event, context):
    CORS_HEADERS = cors_headers()
    try:
        usuario_id = get_authenticated_user(event)
        if not usuario_id:
            return _response(401, {"error": "unauthorized"})

        params = event.get("pathParameters", {})
        file_hash = params.get("file_hash", "")

        if not usuario_id or not file_hash:
            return _response(400, {"error": "file_hash is required"})

        # 1. Try to find in file_hashes by hash
        hash_item = hashes_table.get_item(
            Key={"usuario_id": usuario_id, "file_hash": file_hash}
        ).get("Item")

        s3_key = ""
        if hash_item:
            s3_key = hash_item.get("s3_key", "")
            # 2. Delete PDF from S3
            if s3_key:
                try:
                    s3.delete_object(Bucket=PDFS_BUCKET, Key=s3_key)
                    logger.info("Deleted S3 object: %s", s3_key)
                except Exception as e:
                    logger.warning("Could not delete S3 object %s: %s", s3_key, e)
            # 3. Delete from file_hashes
            hashes_table.delete_item(Key={"usuario_id": usuario_id, "file_hash": file_hash})


        # 4. Delete from estados_cuenta
        deleted_cards = 0
        if hash_item:
            # Delete by file_hash match
            response = estados_table.query(
                KeyConditionExpression=Key("usuario_id").eq(usuario_id),
                FilterExpression=Attr("file_hash").eq(file_hash),
            )
            for item in response.get("Items", []):
                estados_table.delete_item(
                    Key={"usuario_id": usuario_id, "tarjeta_id": item["tarjeta_id"]}
                )
                deleted_cards += 1
                logger.info("Deleted card: %s", item["tarjeta_id"])
        else:
            # Fallback: file_hash param is actually a tarjeta_id
            try:
                estados_table.delete_item(
                    Key={"usuario_id": usuario_id, "tarjeta_id": file_hash}
                )
                deleted_cards = 1
                logger.info("Deleted card by tarjeta_id: %s", file_hash)
            except Exception as e:
                logger.warning("Could not delete by tarjeta_id: %s", e)

        # 5. Invalidate recent analysis jobs (limit to last 10)
        jobs_response = jobs_table.query(
            IndexName="usuario_id-completed_at-index",
            KeyConditionExpression=Key("usuario_id").eq(usuario_id),
            ScanIndexForward=False,
            Limit=10,
            FilterExpression=Attr("has_presentation").eq(True),
        )
        invalidated = 0
        for job in jobs_response.get("Items", []):
            jobs_table.update_item(
                Key={"job_id": job["job_id"]},
                UpdateExpression="REMOVE has_presentation",
            )
            invalidated += 1

        # 6. Count remaining documents
        remaining_response = hashes_table.query(
            KeyConditionExpression=Key("usuario_id").eq(usuario_id),
            Select="COUNT",
        )
        remaining = remaining_response.get("Count", 0)

        return _response(200, {
            "deleted": True,
            "deleted_cards": deleted_cards,
            "invalidated_analyses": invalidated,
            "remaining_documents": remaining,
        })

    except Exception as e:
        logger.error("Error deleting document: %s", e, exc_info=True)
        return _response(500, {"error": "Internal server error"})


def _response(status, body):
    return {"statusCode": status, "headers": cors_headers(), "body": json.dumps(body)}
