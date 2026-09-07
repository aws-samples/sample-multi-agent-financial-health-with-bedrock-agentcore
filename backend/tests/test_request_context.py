# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""
Pruebas del contexto determinístico de usuario.

Cubren el defecto que motivó el módulo: el usuario_id tenía que sobrevivir dos
saltos de decisión de un LLM y, cuando no lo hacía, la persistencia en DynamoDB
se saltaba en silencio.
"""

import os
import sys
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from config.request_context import (  # noqa: E402
    get_usuario_actual,
    limpiar_usuario_actual,
    resolver_usuario_id,
    set_usuario_actual,
)

USUARIO = "549874d8-b0f1-70d3-d277-9a55f56f29ce"


def setup_function(_):
    limpiar_usuario_actual()


def teardown_function(_):
    limpiar_usuario_actual()


def test_sin_contexto_resuelve_vacio():
    assert resolver_usuario_id() == ""
    assert resolver_usuario_id("") == ""


def test_argumento_explicito_tiene_precedencia():
    set_usuario_actual(USUARIO)
    assert resolver_usuario_id("otro-usuario") == "otro-usuario"


def test_contexto_cubre_al_llm_que_omite_el_argumento():
    """El caso del defecto: el modelo no pasa usuario_id."""
    set_usuario_actual(USUARIO)
    assert resolver_usuario_id() == USUARIO
    assert resolver_usuario_id("") == USUARIO


def test_argumento_en_blanco_se_trata_como_ausente():
    set_usuario_actual(USUARIO)
    assert resolver_usuario_id("   ") == USUARIO


def test_el_contexto_llega_a_hilos_del_executor():
    """analisis_paralelo ejecuta los sub-agentes en ThreadPoolExecutor.

    Los ContextVar no se propagan a hilos nuevos, así que el respaldo de proceso
    es lo que mantiene resuelto el usuario dentro del executor.
    """
    set_usuario_actual(USUARIO)
    with ThreadPoolExecutor(max_workers=2) as ex:
        resultados = list(ex.map(lambda _: resolver_usuario_id(), range(2)))
    assert resultados == [USUARIO, USUARIO]


def test_limpiar_restablece_el_contexto():
    set_usuario_actual(USUARIO)
    assert get_usuario_actual() == USUARIO
    limpiar_usuario_actual()
    assert get_usuario_actual() == ""


# ── API pública que consumen los agentes (tools.persistencia_dynamodb) ──
# set_current_user_id / get_current_user_id / extraer_usuario_id delegan en este
# módulo. Estas pruebas fijan ese contrato para que la delegación no se rompa.

def test_api_de_agentes_delega_en_el_contexto():
    os.environ.setdefault("DYNAMODB_TABLE_NAME", "dummy")
    from tools.persistencia_dynamodb import get_current_user_id, set_current_user_id

    set_current_user_id(USUARIO)
    assert get_current_user_id() == USUARIO
    assert get_usuario_actual() == USUARIO


def test_api_de_agentes_no_contamina_os_environ():
    """El almacenamiento anterior era os.environ, que se hereda por subprocesos."""
    os.environ.setdefault("DYNAMODB_TABLE_NAME", "dummy")
    from tools.persistencia_dynamodb import set_current_user_id

    set_current_user_id(USUARIO)
    assert "CURRENT_USER_ID" not in os.environ


def test_usuario_vacio_limpia_en_vez_de_dejar_el_anterior():
    """Evita que un proceso caliente siga usando el usuario de otra invocación."""
    os.environ.setdefault("DYNAMODB_TABLE_NAME", "dummy")
    from tools.persistencia_dynamodb import get_current_user_id, set_current_user_id

    set_current_user_id(USUARIO)
    set_current_user_id("")
    assert get_current_user_id() == ""


def test_extraer_usuario_id_da_precedencia_al_contexto_sobre_el_texto():
    os.environ.setdefault("DYNAMODB_TABLE_NAME", "dummy")
    from tools.persistencia_dynamodb import extraer_usuario_id, set_current_user_id

    texto = "analiza esto usuario_id: aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    set_current_user_id(USUARIO)
    assert extraer_usuario_id(texto) == USUARIO


def test_extraer_usuario_id_cae_al_regex_del_texto_sin_contexto():
    os.environ.setdefault("DYNAMODB_TABLE_NAME", "dummy")
    from tools.persistencia_dynamodb import extraer_usuario_id

    texto = "analiza esto usuario_id: aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    assert extraer_usuario_id(texto) == "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    assert extraer_usuario_id("sin identificador aquí") == ""
