# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""
Agente Extractor - Especializado en extracción de datos de estados de cuenta.
Patrón: Agents as Tools (Strands SDK)

Usa extraer_multiples_pdfs para procesar PDFs en paralelo.
Devuelve solo un RESUMEN CORTO al orquestador — los datos completos
quedan en DynamoDB y los sub-agentes los leen con obtener_estados_cuenta.
"""

import logging

from strands import Agent, tool

from config.models import extractor_model
from tools.extraer_estado_cuenta import extraer_estado_cuenta
from tools.extraer_multiples_pdfs import extraer_multiples_pdfs
from tools.persistencia_dynamodb import guardar_estado_cuenta

logger = logging.getLogger(__name__)

# NOTA: los bancos y retailers listados en "BANCOS QUE CONOCES" son entidades
# REALES incluidas como EJEMPLOS para que el modelo reconozca los estados de
# cuenta reales que suben los usuarios. No son datos de demo.
SYSTEM_PROMPT = """Eres un agente especializado en extraer datos de estados de cuenta de tarjetas de crédito peruanas.

CAPACIDADES:
- Extraer datos de MÚLTIPLES PDFs en paralelo con extraer_multiples_pdfs (PREFERIDO para 2+ PDFs)
- Extraer datos de UN solo PDF con extraer_estado_cuenta
- Persistir los datos extraídos en DynamoDB usando guardar_estado_cuenta

REGLA IMPORTANTE:
- Si recibes 2 o más URIs de S3, usa SIEMPRE extraer_multiples_pdfs pasando la lista completa.
  NO llames extraer_estado_cuenta una por una.
- Si recibes 1 sola URI, usa extraer_estado_cuenta.

BANCOS QUE CONOCES:
- BCP, BBVA, Interbank, Scotiabank (bancarias)
- Falabella, Ripley, Oh! (retail)

FLUJO:
1. Recibe URIs de S3 de los PDFs subidos
2. Extrae datos con extraer_multiples_pdfs (paralelo) o extraer_estado_cuenta (individual)
3. Persiste cada tarjeta con guardar_estado_cuenta
4. Responde con un RESUMEN CORTO (ver formato abajo)

FORMATO DE RESPUESTA — MUY IMPORTANTE:
Tu respuesta debe ser BREVE. Solo un resumen de lo extraído. NO incluyas movimientos ni transacciones.
Formato:
- Titular: [nombre del titular si se encontró]
- Tarjeta 1: [banco] *[últimos 4], saldo S/ [monto], TCEA [%], pago mínimo S/ [monto] — [OK/Error]
- Tarjeta 2: ...
- Total: [N] tarjetas extraídas y guardadas en base de datos.

NO listes movimientos. NO repitas los datos completos. Los datos ya están en DynamoDB
y los agentes analista y detective los leerán de ahí directamente.

MONEDA: S/ (soles). TASA: TCEA.
"""


@tool
def agente_extractor(consulta: str) -> str:
    """Extrae datos de estados de cuenta PDF subidos a S3. Úsalo cuando el usuario
    suba PDFs o pida extraer datos de estados de cuenta. La consulta debe incluir
    las URIs de S3 de los PDFs y el usuario_id.

    Args:
        consulta: Descripción de qué extraer, incluyendo s3_uris y usuario_id

    Returns:
        Resumen corto de la extracción (banco, saldo, TCEA por tarjeta). Los datos
        completos quedan en DynamoDB.
    """
    try:
        import re

        # Resolver el usuario_id de forma determinística desde la consulta, para
        # reforzar la instrucción de persistencia (el guardado en DynamoDB depende
        # de que este usuario_id llegue a las tools de extracción).
        from tools.persistencia_dynamodb import extraer_usuario_id, cargar_tarjetas

        usuario_id = extraer_usuario_id(consulta)
        prompt = consulta
        if usuario_id:
            prompt += (
                f"\n\nOBLIGATORIO: al llamar a extraer_multiples_pdfs (o "
                f"extraer_estado_cuenta), pasa SIEMPRE usuario_id=\"{usuario_id}\" "
                f"para persistir las tarjetas en la base de datos."
            )

        agent = Agent(
            system_prompt=SYSTEM_PROMPT,
            model=extractor_model,
            tools=[extraer_estado_cuenta, extraer_multiples_pdfs, guardar_estado_cuenta],
        )
        response = agent(prompt)

        # Fallback determinístico: si tras la extracción no quedó nada persistido
        # para este usuario, re-ejecutar la extracción/persistencia en código,
        # sin depender de que el LLM haya propagado el usuario_id a las tools.
        if usuario_id and not cargar_tarjetas(usuario_id):
            uris = re.findall(r"s3://[^\s\"'\],]+", consulta)
            if uris:
                logger.warning(
                    "Extractor: 0 tarjetas persistidas tras invocar al agente; "
                    "ejecutando persistencia determinística (%d PDFs)", len(uris)
                )
                from tools.extraer_multiples_pdfs import extraer_multiples_pdfs as _extraer_mult
                fn = getattr(_extraer_mult, "func", None) or getattr(_extraer_mult, "__wrapped__", None) or _extraer_mult
                try:
                    fn(uris, usuario_id)
                except TypeError:
                    _extraer_mult(s3_uris=uris, usuario_id=usuario_id)

        return str(response)
    except Exception as e:
        logger.error("Error en agente_extractor: %s", e)
        return f"⚠️ Error extrayendo datos: {str(e)}"
