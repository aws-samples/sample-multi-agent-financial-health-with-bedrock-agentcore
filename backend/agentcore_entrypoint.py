# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""
Entrypoint para AgentCore Runtime - Orquestador

Workaround: Las llamadas que involucran múltiples tools anidados (extracción +
análisis paralelo) corrompen el historial de conversación del session manager
(toolUse/toolResult mismatch en ConverseStream). Para evitarlo:
- Llamadas pesadas (con PDFs/s3) se ejecutan SIN Memory session manager.
- Llamadas de chat ligeras (follow-up) usan Memory para contexto conversacional.
- Si aún así falla por historial corrupto, se reintenta sin Memory.

Responsible AI / IA de alto riesgo:
- El sistema produce análisis financiero informativo, NO asesoría profesional. Sus
  salidas no deben ser la única base para decisiones financieras; el usuario
  debe validar con un asesor calificado (disclaimer reforzado en el prompt del
  orquestador y en la UI).
- Human-in-the-loop: el usuario revisa los datos extraídos antes de generar
  planes, y toda decisión de acción queda en manos del usuario.
- Guardrails: todas las invocaciones pasan por un Bedrock Guardrail (filtrado
  de contenido + anonimización de PII).
- Sesgo/equidad: el sistema no toma decisiones crediticias automatizadas ni
  clasifica usuarios; solo calcula proyecciones a partir de los datos que el
  propio usuario aporta.

Modelo de confianza / autorización:
- Este runtime NO tiene un JWT authorizer de entrada (ver agentcore.yaml). Es
  invocado por la Lambda worker (autenticada por IAM), que a su vez ya validó
  al usuario vía Cognito en API Gateway. El límite de autorización real está
  aguas arriba (Cognito + IAM).
- La verificación de identidad de abajo es defensa en profundidad: se aplica
  estrictamente SOLO cuando el runtime recibe una identidad propagada (p. ej.
  si se habilita un JWT authorizer). Ver invoke().
"""

import os
import logging

# ── Env vars: leer de SSM Parameter Store, fallback a valores hardcodeados ──
# AgentCore Runtime no hereda env vars de Lambda/CDK.
# SSM Parameter Store elimina la necesidad de hardcodear IDs de recursos.
import boto3


def _load_ssm_params():
    """Carga todos los parámetros SSM en una sola llamada (reduce cold start ~800ms).

    Un fallo aquí NO es benigno: si no se cargan los parámetros, todas las
    variables de entorno quedan vacías y el runtime sigue arrancando con la
    persistencia en DynamoDB, el guardrail, AgentCore Memory y la detección de
    duplicados desactivados en silencio. Antes esto se tragaba con un
    `except: return {}`, así que se perdían datos sin ninguna señal.
    """
    region = os.environ.get("AWS_REGION", "us-east-2")
    prefix = "/financial-health/"
    try:
        ssm = boto3.client("ssm", region_name=region)
        response = ssm.get_parameters_by_path(Path=prefix, Recursive=False)
        params = {}
        for p in response.get("Parameters", []):
            key = p["Name"].replace(prefix, "")
            params[key] = p["Value"]
        if not params:
            logging.getLogger(__name__).error(
                "SSM no devolvió parámetros en %s (región %s). El runtime arrancará "
                "sin tabla de DynamoDB, sin guardrail y sin Memory.", prefix, region
            )
        else:
            logging.getLogger(__name__).info(
                "Cargados %d parámetros SSM desde %s", len(params), prefix
            )
        return params
    except Exception as e:
        # Se registra y se continúa: el runtime debe poder arrancar para devolver un
        # error legible, pero el fallo tiene que ser visible en los logs.
        logging.getLogger(__name__).error(
            "Fallo cargando parámetros SSM desde %s en %s: %s. Se desactivarán "
            "persistencia, guardrail y Memory. Comprueba que el rol de ejecución "
            "tenga ssm:GetParametersByPath.", prefix, region, e, exc_info=True
        )
        return {}


os.environ.setdefault("AWS_REGION", os.environ.get("AWS_REGION", "us-east-2"))
_ssm = _load_ssm_params()
os.environ.setdefault("DYNAMODB_TABLE_NAME", _ssm.get("dynamodb-table-name", ""))
os.environ.setdefault("HASHES_TABLE_NAME", _ssm.get("hashes-table-name", ""))
os.environ.setdefault("GUARDRAIL_ID", _ssm.get("guardrail-id", ""))
os.environ.setdefault("GUARDRAIL_VERSION", _ssm.get("guardrail-version", "DRAFT"))
os.environ.setdefault("MEMORY_ID", _ssm.get("memory-id", ""))

# Diagnóstico de arranque: deja constancia explícita de qué capacidades quedan
# activas. Cada una de estas variables vacía desactiva una función que el README
# y el blog post describen como siempre activa, así que conviene que sea visible
# en el primer log del runtime y no un misterio silencioso.
_capacidades = {
    "persistencia DynamoDB": os.environ.get("DYNAMODB_TABLE_NAME", ""),
    "detección de duplicados": os.environ.get("HASHES_TABLE_NAME", ""),
    "Bedrock Guardrail": os.environ.get("GUARDRAIL_ID", ""),
    "AgentCore Memory": os.environ.get("MEMORY_ID", ""),
}
_faltantes = [nombre for nombre, valor in _capacidades.items() if not valor]
if _faltantes:
    logging.getLogger(__name__).error(
        "Capacidades DESACTIVADAS por configuración ausente: %s", ", ".join(_faltantes)
    )
else:
    logging.getLogger(__name__).info("Todas las capacidades configuradas correctamente")

from bedrock_agentcore.runtime import BedrockAgentCoreApp

from agents.orquestador import crear_orquestador


logger = logging.getLogger(__name__)

app = BedrockAgentCoreApp()


def _is_heavy_analysis(prompt: str) -> bool:
    """Detecta si el prompt involucra análisis pesado con múltiples tools anidados."""
    indicators = ["s3://", "estado(s) de cuenta", "extrae los datos", "PDFs subidos"]
    prompt_lower = prompt.lower()
    return any(ind.lower() in prompt_lower for ind in indicators)


def _is_conversation_history_error(error: Exception) -> bool:
    """Detecta errores de historial de conversación corrupto (toolUse/toolResult mismatch)."""
    msg = str(error).lower()
    return "toolresult" in msg or "tooluse" in msg or "validationexception" in msg


def _sanitize_financial_prompt(prompt: str) -> str:
    """Reformula un prompt financiero legítimo para evitar falsos positivos del guardrail.

    El guardrail de Bedrock puede bloquear prompts financieros legítimos que contienen
    palabras como 'despiden', 'mendigando', etc. Esta función reformula el prompt
    manteniendo la intención financiera pero removiendo triggers innecesarios.

    Returns:
        Prompt reformulado si se hicieron cambios, cadena vacía si no hubo cambios.
    """
    import re

    # Palabras/frases que activan el guardrail pero son contexto financiero legítimo
    sanitizations = [
        (r'\b(me despid[aeno]+|despido|me bot[aeno]+|me ech[aeno]+)\b', 'pierdo mi empleo'),
        (r'\b(mendigando|pidiendo limosna|en la calle)\b', 'con ingresos reducidos'),
        (r'\b(me muero|muera|muerte)\b', 'en caso de emergencia'),
        (r'\b(suicid\w+)\b', ''),
        (r'\b(me amenazan|amenaza\w*|extorsion\w*)\b', 'me presionan por cobros'),
        (r'\b(matar\w*|golpe\w*|violenci\w*)\b', ''),
    ]

    sanitized = prompt
    was_modified = False
    for pattern, replacement in sanitizations:
        new_text = re.sub(pattern, replacement, sanitized, flags=re.IGNORECASE)
        if new_text != sanitized:
            was_modified = True
            sanitized = new_text

    if was_modified:
        logger.info("Prompt sanitizado para retry (se aplicaron %d reglas)", sum(1 for p, r in sanitizations if re.search(p, prompt, re.IGNORECASE)))

    return sanitized if was_modified else ""


def _is_guardrail_blocked(result) -> bool:
    """Detecta si la respuesta fue bloqueada por el guardrail de Bedrock."""
    if hasattr(result, 'stop_reason') and result.stop_reason == "guardrail_intervened":
        return True
    result_str = str(result)
    return "no puedo procesar esa solicitud" in result_str.lower() or \
           "no puedo proporcionar esa información" in result_str.lower()


@app.entrypoint
def invoke(payload, context):
    """
    Entrypoint para AgentCore Runtime.

    Manejo de guardrail: si Bedrock bloquea un prompt financiero legítimo,
    se reformula quitando palabras trigger y se reintenta una vez.
    """
    usuario_id = payload.get("usuario_id", "default_user")
    prompt = payload.get("prompt", "")
    session_id = getattr(context, "session_id", None)

    # Publicar el usuario_id AUTENTICADO como fuente de verdad para las tools.
    # Evita depender de que el LLM propague el usuario_id entre agentes anidados
    # (causa raíz del bug de persistencia/lectura). Ver tools/persistencia_dynamodb,
    # que delega el almacenamiento en config/request_context.
    try:
        from tools.persistencia_dynamodb import set_current_user_id
        set_current_user_id(usuario_id)
    except Exception as e:
        logger.warning("No se pudo publicar el usuario_id de la invocación: %s", e)


    # Defensa en profundidad sobre la autorización.
    # El límite de autorización primario es aguas arriba (Cognito en API Gateway +
    # IAM en la Lambda worker). Este runtime hoy NO tiene JWT authorizer, así que
    # context.identity normalmente viene vacío y el caller (Lambda) es de confianza.
    # Si en el futuro se habilita un JWT authorizer, la identidad propagada SÍ se
    # exige y debe coincidir con el usuario_id del payload.
    identity = getattr(context, "identity", None) or {}
    authenticated_user = identity.get("sub", "") if isinstance(identity, dict) else ""
    if authenticated_user:
        # Identidad presente => exigir coincidencia estricta (rechazar si no coincide).
        if usuario_id != authenticated_user:
            logger.warning("Authorization mismatch for job (identity present, id differs)")
            return {
                "result": "⚠️ No tienes autorización para acceder a estos datos.",
                "usuario_id": usuario_id,
            }

    # Contexto de país/idioma del usuario
    country = payload.get("country", "")
    currency = payload.get("currency", "")
    language = payload.get("language", "")
    payment_behavior = payload.get("payment_behavior", "")

    use_memory = not _is_heavy_analysis(prompt)

    try:
        orquestador = crear_orquestador(
            session_id=session_id if use_memory else None,
            actor_id=usuario_id,
            country=country,
            currency=currency,
            language=language,
            payment_behavior=payment_behavior,
        )
        if not use_memory:
            logger.info("Análisis pesado detectado — ejecutando sin Memory session manager")

        resultado = orquestador(prompt)

        # Si el guardrail bloqueó, intentar reformular y reintentar
        if _is_guardrail_blocked(resultado):
            sanitized = _sanitize_financial_prompt(prompt)
            if sanitized:
                logger.info("Guardrail bloqueó prompt, reintentando con versión sanitizada")
                orquestador2 = crear_orquestador(
                    session_id=None,
                    actor_id=usuario_id,
                    country=country,
                    currency=currency,
                    language=language,
                    payment_behavior=payment_behavior,
                )
                resultado = orquestador2(sanitized)

        return {
            "result": str(resultado),
            "usuario_id": usuario_id,
        }
    except Exception as e:
        # Si falla por historial corrupto, reintentar sin Memory
        if _is_conversation_history_error(e):
            logger.warning("Historial corrupto detectado, reintentando sin Memory: %s", e)
            try:
                orquestador = crear_orquestador(
                    session_id=None,
                    actor_id=usuario_id,
                    country=country,
                    currency=currency,
                    language=language,
                    payment_behavior=payment_behavior,
                )
                resultado = orquestador(prompt)
                return {
                    "result": str(resultado),
                    "usuario_id": usuario_id,
                }
            except Exception as retry_err:
                logger.error("Error en retry sin Memory: %s", retry_err)
                return {
                    "result": "⚠️ Hubo un error procesando tu solicitud. Por favor intenta de nuevo.",
                    "usuario_id": usuario_id,
                }

        logger.error("Error en invoke: %s", e, exc_info=True)
        # NOTE: full traceback stays in structured logger (CloudWatch); removed raw print
        # to avoid unstructured PII leakage in stdout aggregation pipelines.
        return {
            "result": "⚠️ Hubo un error procesando tu solicitud. Por favor intenta de nuevo.",
            "usuario_id": usuario_id,
        }


if __name__ == "__main__":
    app.run()
