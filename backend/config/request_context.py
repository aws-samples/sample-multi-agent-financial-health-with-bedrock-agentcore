# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""
Contexto determinístico de la petición en curso.

Motivación
----------
El `usuario_id` es la clave de partición de DynamoDB: sin él no se puede
persistir ni leer nada del usuario. Antes de este módulo, el `usuario_id` tenía
que sobrevivir tres saltos, y dos de ellos eran decisiones de un LLM:

  1. `invoke()` lo recibe en el payload  (código, determinístico)
  2. el orquestador debía copiarlo dentro de la `consulta` en lenguaje natural
     que le pasa a `agente_extractor`                        (decisión del LLM)
  3. el agente extractor debía volver a extraerlo de esa frase y pasarlo como
     argumento a `extraer_multiples_pdfs`                    (decisión del LLM)

Los modelos de lenguaje no son determinísticos: si cualquiera de los dos saltos
se omite, `usuario_id` llega vacío, la persistencia se salta en silencio y todo
turno posterior de la conversación se queda sin datos.

La solución es la misma idea de *grounding determinístico* que ya usa
`analisis_paralelo`: el dato viaja por código, no por el prompt. El entrypoint
fija el usuario una sola vez y las tools de persistencia lo leen de aquí cuando
el LLM no lo aporta.

Resolución
----------
`get_usuario_actual()` no sustituye al argumento explícito. El orden de
precedencia en las tools es:

  argumento explícito del LLM  ->  contextvar  ->  respaldo de proceso

El respaldo de proceso existe porque los `ContextVar` no se propagan a hilos
creados por `ThreadPoolExecutor` (cada hilo arranca con un contexto vacío) y
varias tools extraen en paralelo. Es seguro en este despliegue porque AgentCore
Runtime aísla cada sesión en su propia microVM, así que el proceso atiende a un
único usuario a la vez. Si algún día este código corre en un servidor
multi-tenant compartido, hay que propagar el contexto explícitamente con
`contextvars.copy_context()` al enviar trabajo al executor y eliminar el
respaldo.
"""

import contextvars
import logging

logger = logging.getLogger(__name__)

_usuario_id_var: contextvars.ContextVar = contextvars.ContextVar(
    "request_usuario_id", default=""
)

# Respaldo a nivel de proceso: ver la nota sobre ThreadPoolExecutor arriba.
_usuario_id_proceso: str = ""


def set_usuario_actual(usuario_id: str) -> None:
    """Fija el usuario de la petición en curso. Llamar una vez desde el entrypoint."""
    global _usuario_id_proceso
    usuario_id = (usuario_id or "").strip()
    _usuario_id_var.set(usuario_id)
    _usuario_id_proceso = usuario_id
    if usuario_id:
        logger.info("Contexto de petición fijado para usuario_id=%s", usuario_id)
    else:
        logger.warning("set_usuario_actual recibió un usuario_id vacío")


def get_usuario_actual() -> str:
    """Devuelve el usuario de la petición en curso, o cadena vacía si no hay."""
    try:
        valor = (_usuario_id_var.get() or "").strip()
    except LookupError:
        valor = ""
    return valor or _usuario_id_proceso


def resolver_usuario_id(usuario_id: str = "") -> str:
    """Resuelve el usuario_id efectivo: argumento explícito, luego contexto.

    Las tools deben usar esto en lugar de confiar en que el LLM aporte el
    argumento.
    """
    explicito = (usuario_id or "").strip()
    if explicito:
        return explicito
    del_contexto = get_usuario_actual()
    if del_contexto:
        logger.info(
            "usuario_id no fue aportado por el modelo; usando el contexto de la petición"
        )
    return del_contexto


def limpiar_usuario_actual() -> None:
    """Limpia el contexto. Útil en pruebas y entre peticiones de un proceso reutilizado."""
    global _usuario_id_proceso
    _usuario_id_var.set("")
    _usuario_id_proceso = ""
