# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""
Configuración de modelos de Bedrock para los agentes.

Según la estrategia técnica:
- Orquestador: Claude Sonnet 4 (routing + consolidación) — CON guardrail (punto de entrada del usuario)
- Extractor: Claude Sonnet 4 Vision (extracción de PDFs) — SIN guardrail
- Analista/Detective/Simulador: Claude Haiku 4 (tareas rápidas) — SIN guardrail

El guardrail solo se aplica al orquestador para filtrar input del usuario.
Los agentes internos procesan datos ya validados y no deben ser bloqueados.
"""

import os

from strands.models import BedrockModel
from config.constants import DEFAULT_REGION

_guardrail_id = os.environ.get("GUARDRAIL_ID")
_guardrail_version = os.environ.get("GUARDRAIL_VERSION", "DRAFT")

# Guardrail solo para el orquestador (punto de entrada del usuario)
_guardrail_kwargs = {}
if _guardrail_id:
    _guardrail_kwargs = {
        "guardrail_id": _guardrail_id,
        "guardrail_version": _guardrail_version,
        "guardrail_redact_input": True,
        "guardrail_redact_output": False,
        "guardrail_trace": "enabled",
        # CRÍTICO: Solo evaluar el último mensaje del usuario con el guardrail.
        # Sin esto, el guardrail escanea TODA la conversación y si un mensaje
        # anterior fue bloqueado, contamina todos los mensajes siguientes.
        "guardrail_latest_message": True,
    }

# Orquestador - Sonnet 4 — CON guardrail (filtra input del usuario)
orchestrator_model = BedrockModel(
    model_id=os.environ.get(
        "BEDROCK_ORCHESTRATOR_MODEL", "us.anthropic.claude-sonnet-4-5-20250929-v1:0"
    ),
    region_name=DEFAULT_REGION,
    **_guardrail_kwargs,
)

# Extractor - Sonnet 4 Vision para PDFs — SIN guardrail
extractor_model = BedrockModel(
    model_id=os.environ.get(
        "BEDROCK_EXTRACTOR_MODEL", "us.anthropic.claude-sonnet-4-5-20250929-v1:0"
    ),
    region_name=DEFAULT_REGION,
)

# Workers - Haiku 4 para tareas específicas — SIN guardrail
worker_model = BedrockModel(
    model_id=os.environ.get(
        "BEDROCK_WORKER_MODEL", "us.anthropic.claude-haiku-4-5-20251001-v1:0"
    ),
    region_name=DEFAULT_REGION,
)
