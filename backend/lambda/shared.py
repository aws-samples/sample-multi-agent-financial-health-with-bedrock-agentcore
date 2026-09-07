# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""Shared utilities for Lambda functions."""

import os

CLOUDFRONT_URL = os.environ.get("CLOUDFRONT_URL", "")


def get_authenticated_user(event: dict) -> str:
    """Extract authenticated usuario_id (sub) from Cognito JWT via API Gateway authorizer.
    Falls back to path parameter if authorizer claims aren't populated (e.g., local testing)."""
    claims = event.get("requestContext", {}).get("authorizer", {}).get("claims", {})
    user = claims.get("sub", "")
    if not user:
        # Fallback: path param (still behind Cognito authorizer at API Gateway level)
        user = event.get("pathParameters", {}).get("usuario_id", "") if event.get("pathParameters") else ""
    return user


def cors_headers() -> dict:
    """Return CORS headers restricted to the CloudFront domain."""
    origin = CLOUDFRONT_URL if CLOUDFRONT_URL else "*"
    return {
        "Content-Type": "application/json",
        "Access-Control-Allow-Origin": origin,
        "Access-Control-Allow-Headers": "Content-Type,Authorization",
        "Access-Control-Allow-Methods": "POST,GET,DELETE,OPTIONS",
    }
