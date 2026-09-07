# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""
Constantes del proyecto.
"""

import os

# Región por defecto — importar desde aquí para evitar duplicación
DEFAULT_REGION = os.environ.get("AWS_REGION", "us-east-2")

# Umbrales de salud financiera
RATIO_DEUDA_INGRESO_SALUDABLE = 0.30  # 30%
RATIO_DEUDA_INGRESO_RIESGO = 0.50     # 50%
