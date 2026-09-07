# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""
Lambda Worker — invocado async por el dispatcher.
Invoca AgentCore Runtime y guarda el resultado en DynamoDB.

Protección contra timeout: ejecuta AgentCore en un thread con timeout
propio (AGENTCORE_TIMEOUT_S) para poder marcar FAILED antes de que
la Lambda muera.

Responsible AI / Guardrails:
- Todas las invocaciones al modelo pasan por un Bedrock Guardrail (ID en
  env GUARDRAIL_ID) que filtra contenido y anonimiza PII.
- El orquestador incluye un disclaimer de "no asesoría financiera" en su
  prompt de sistema y lo refuerza al usuario en la respuesta.
- Los KPIs financieros almacenados (deuda_total, ratio_deuda_ingreso) son
  derivados agregados — nunca se persiste el PAN completo de una tarjeta.
- Este código no debe retornar datos PII al cliente en errores (ver catch).
"""

import json
import logging
import os
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from urllib.parse import quote

import boto3
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
import urllib.request

logger = logging.getLogger()
logger.setLevel(logging.INFO)

AGENT_ARN = os.environ["AGENT_ARN"]
AWS_REGION = os.environ.get("AWS_REGION", "us-east-2")
JOBS_TABLE = os.environ["JOBS_TABLE_NAME"]
FINANCIAL_HISTORY_TABLE = os.environ.get("FINANCIAL_HISTORY_TABLE_NAME", "")
# Timeout para la llamada a AgentCore — debe ser menor que el timeout de la Lambda
AGENTCORE_TIMEOUT_S = int(os.environ.get("AGENTCORE_TIMEOUT_S", "540"))

SESSION_HEADER = "X-Amzn-Bedrock-AgentCore-Runtime-Session-Id"

boto_session = boto3.Session(region_name=AWS_REGION)
dynamodb = boto3.resource("dynamodb")
jobs_table = dynamodb.Table(JOBS_TABLE)

# SDK client con timeout extendido para llamadas largas a AgentCore
_sdk_client = None
try:
    from botocore.config import Config
    _sdk_config = Config(
        read_timeout=AGENTCORE_TIMEOUT_S,
        connect_timeout=30,
        retries={"max_attempts": 0},  # No reintentar — la Lambda maneja su propio retry
    )
    _sdk_client = boto_session.client("bedrock-agentcore", region_name=AWS_REGION, config=_sdk_config)
    if not hasattr(_sdk_client, "invoke_agent_runtime"):
        _sdk_client = None
except Exception:
    _sdk_client = None

logger.info("Worker using %s for AgentCore (timeout=%ds)", "SDK" if _sdk_client else "HTTP/SigV4", AGENTCORE_TIMEOUT_S)


def _invoke_via_sdk(payload: dict, session_id: str) -> dict:
    body = json.dumps(payload).encode("utf-8")
    response = _sdk_client.invoke_agent_runtime(
        agentRuntimeArn=AGENT_ARN,
        contentType="application/json",
        accept="application/json",
        runtimeSessionId=session_id,
        payload=body,
    )
    response_body = response["response"].read().decode("utf-8")
    return json.loads(response_body)


def _invoke_via_http(payload: dict, session_id: str) -> dict:
    credentials = boto_session.get_credentials().get_frozen_credentials()
    encoded_arn = quote(AGENT_ARN, safe="")
    # URL built from trusted env vars AWS_REGION and AGENT_ARN — not user-controlled
    host = f"bedrock-agentcore.{AWS_REGION}.amazonaws.com"  # nosemgrep: tainted-url-host
    endpoint = f"https://{host}/runtimes/{encoded_arn}/invocations"
    body = json.dumps(payload).encode("utf-8")

    aws_request = AWSRequest(
        method="POST", url=endpoint, data=body,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            SESSION_HEADER: session_id,
        },
    )
    SigV4Auth(credentials, "bedrock-agentcore", AWS_REGION).add_auth(aws_request)

    req = urllib.request.Request(
        endpoint, data=body, headers=dict(aws_request.headers), method="POST",
    )
    with urllib.request.urlopen(req, timeout=AGENTCORE_TIMEOUT_S) as resp:  # nosemgrep: dynamic-urllib-use-detected  # nosec B310 — URL from trusted AWS env vars
        return json.loads(resp.read().decode("utf-8"))


def _invoke_agentcore(payload: dict, session_id: str) -> dict:
    if _sdk_client:
        return _invoke_via_sdk(payload, session_id)
    return _invoke_via_http(payload, session_id)


def _invoke_with_timeout(payload: dict, session_id: str, timeout_s: int) -> dict:
    """Invoca AgentCore en un thread con timeout para evitar que la Lambda muera sin marcar FAILED."""
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(_invoke_agentcore, payload, session_id)
        try:
            return future.result(timeout=timeout_s)
        except FuturesTimeout:
            raise TimeoutError(f"AgentCore no respondió en {timeout_s}s")


def _mark_failed(job_id: str, error_msg: str):
    """Marca un job como FAILED en DynamoDB."""
    try:
        jobs_table.update_item(
            Key={"job_id": job_id},
            UpdateExpression="SET #s = :s, #e = :e, failed_at = :t",
            ExpressionAttributeNames={"#s": "status", "#e": "error"},
            ExpressionAttributeValues={
                ":s": "FAILED",
                ":e": error_msg,
                ":t": int(time.time()),
            },
        )
    except Exception as dynamo_err:
        logger.error("Could not mark job %s as FAILED: %s", job_id, dynamo_err)


def _get_previous_analysis_summary(usuario_id: str) -> str:
    """Recupera un resumen del último análisis completado del usuario para dar contexto de seguimiento.

    Extrae KPIs clave de los charts del análisis anterior para que el orquestador
    pueda comparar con los datos nuevos y mostrar evolución.
    """
    try:
        import re
        import json as _json
        from boto3.dynamodb.conditions import Key

        response = jobs_table.query(
            IndexName="usuario_id-completed_at-index",
            KeyConditionExpression=Key("usuario_id").eq(usuario_id),
            ScanIndexForward=False,
            Limit=1,
            FilterExpression="attribute_exists(#r)",
            ExpressionAttributeNames={"#r": "result"},
        )
        items = response.get("Items", [])
        if not items:
            return ""

        item = items[0]
        prev_result = item.get("result", "")
        completed_at = item.get("completed_at", 0)
        if not prev_result:
            return ""

        # Extraer KPIs de los charts del análisis anterior
        kpis = {}
        chart_blocks = re.findall(r':::chart\s*(\{[\s\S]*?\})\s*:::', prev_result)
        for block in chart_blocks:
            try:
                chart = _json.loads(block)
                ctype = chart.get("type", "")
                data = chart.get("data", [])

                if ctype == "debtComposition" and data:
                    kpis["deuda_total_anterior"] = sum(d.get("saldo", 0) for d in data)
                    kpis["num_tarjetas_anterior"] = len(data)
                    kpis["tarjetas_anterior"] = [
                        {"tarjeta": d.get("tarjeta", ""), "saldo": d.get("saldo", 0), "tcea": d.get("tcea", 0)}
                        for d in data
                    ]

                elif ctype == "alternatives" and data:
                    for row in data:
                        opcion = (row.get("opcion") or "").lower()
                        if "mínimo" in opcion or "minimo" in opcion:
                            kpis["plazo_minimos_anterior"] = row.get("plazo_meses", 0)
                        elif row.get("costo_total", 0) > 0:
                            if "estrategia_anterior" not in kpis or row.get("costo_total", 0) < kpis["estrategia_anterior"].get("costo_total", float("inf")):
                                kpis["estrategia_anterior"] = {
                                    "opcion": row.get("opcion", ""),
                                    "plazo_meses": row.get("plazo_meses", 0),
                                    "costo_total": row.get("costo_total", 0),
                                }

                elif ctype == "spendingPie" and data:
                    kpis["gastos_hormiga_anterior"] = [
                        {"categoria": d.get("categoria", ""), "monto": d.get("monto", 0)}
                        for d in data
                    ]
            except (_json.JSONDecodeError, TypeError, ValueError):
                continue

        if not kpis:
            return ""

        # Formatear fecha del análisis anterior
        from datetime import datetime, timezone
        fecha_str = ""
        if completed_at:
            try:
                fecha = datetime.fromtimestamp(int(completed_at), tz=timezone.utc)
                fecha_str = fecha.strftime("%d/%m/%Y")
            except (ValueError, OSError):
                pass

        # Construir resumen compacto
        lines = [f"\n\n[ANÁLISIS PREVIO del usuario ({fecha_str or 'fecha reciente'}):"]
        if "deuda_total_anterior" in kpis:
            lines.append(f"- Deuda total anterior: S/ {kpis['deuda_total_anterior']:,.0f} en {kpis.get('num_tarjetas_anterior', '?')} tarjetas")
        if "tarjetas_anterior" in kpis:
            for tc in kpis["tarjetas_anterior"]:
                lines.append(f"  · {tc['tarjeta']}: S/ {tc['saldo']:,.0f} (TCEA {tc['tcea']}%)")
        if "estrategia_anterior" in kpis:
            e = kpis["estrategia_anterior"]
            lines.append(f"- Estrategia recomendada: {e['opcion']} ({e['plazo_meses']} meses, costo S/ {e['costo_total']:,.0f})")
        if "gastos_hormiga_anterior" in kpis:
            total_hormiga = sum(g["monto"] for g in kpis["gastos_hormiga_anterior"])
            lines.append(f"- Gastos hormiga identificados: S/ {total_hormiga:,.0f}/mes")
            for g in kpis["gastos_hormiga_anterior"]:
                lines.append(f"  · {g['categoria']}: S/ {g['monto']:,.0f}")
        if "plazo_minimos_anterior" in kpis:
            lines.append(f"- Plazo pagando mínimos: {kpis['plazo_minimos_anterior']} meses")

        lines.append("INSTRUCCIÓN: Este usuario YA tiene un análisis previo. Compara los datos nuevos con los anteriores. Muestra qué mejoró, qué empeoró, y actualiza la estrategia. Usa un tono de seguimiento, NO de primera vez.]")

        summary = "\n".join(lines)
        logger.info("Previous analysis context found (%d chars)", len(summary))
        return summary

    except Exception as e:
        logger.warning("Could not retrieve previous analysis: %s", e)
        return ""


def _fix_alternatives_chart(result_text: str, payment_behavior: str = "") -> str:
    """Post-procesa el resultado para corregir el chart 'alternatives'.

    El LLM a veces inventa números para 'Solo mínimos' (ej: 360 meses, S/ 653k)
    en lugar de usar los valores reales de diagnosticar_salud_financiera.
    Esta función recalcula proyeccion_minimos desde el debtComposition chart
    y parchea el alternatives chart si los números están muy desviados.
    """
    import re
    import json as _json

    try:
        chart_pattern = r'(:::chart\s*)(\{[\s\S]*?\})(\s*:::)'
        charts = {}
        for m in re.finditer(chart_pattern, result_text):
            try:
                chart = _json.loads(m.group(2))
                ctype = chart.get("type", "")
                charts[ctype] = {"match": m, "chart": chart}
            except _json.JSONDecodeError:
                continue

        debt_chart = charts.get("debtComposition")
        alt_chart = charts.get("alternatives")
        if not debt_chart or not alt_chart:
            return result_text

        # Extraer tarjetas del debtComposition
        tarjetas = debt_chart["chart"].get("data", [])
        if not tarjetas:
            return result_text

        saldos = []
        tasas = []
        pagos_min = []
        ratios = []
        for t in tarjetas:
            saldo = t.get("saldo", 0)
            tcea = t.get("tcea", 0)
            if saldo > 0 and tcea > 0:
                saldos.append(saldo)
                tasas.append(tcea)
                # Usar pago_del_periodo si el usuario paga el periodo, sino pago_minimo
                if payment_behavior == "period" and t.get("pago_del_periodo", 0) > 0:
                    pago = t["pago_del_periodo"]
                elif t.get("pago_minimo", 0) > 0:
                    pago = t["pago_minimo"]
                else:
                    # Fallback: estimar 10% del saldo como pago mínimo típico
                    pago = saldo * 0.10
                pagos_min.append(pago)
                # Ratio real del banco: pago_minimo / saldo del documento
                ratios.append(pago / saldo)

        if not saldos:
            return result_text

        # Simular pagando mínimos dinámicos usando la proporción real de cada banco
        saldos_sim = list(saldos)
        meses = 0
        costo_total = 0.0

        while any(s > 1 for s in saldos_sim) and meses < 360:
            meses += 1
            for i in range(len(saldos_sim)):
                if saldos_sim[i] > 1:
                    tasa_m = (1 + tasas[i] / 100) ** (1 / 12) - 1
                    interes = saldos_sim[i] * tasa_m
                    pago_min_dinamico = max(pagos_min[i], saldos_sim[i] * ratios[i])
                    pago = min(pago_min_dinamico, saldos_sim[i] + interes)
                    costo_total += pago
                    saldos_sim[i] = max(0, saldos_sim[i] + interes - pago)

        calc_meses = meses
        calc_costo = round(costo_total, 2)

        # Buscar la fila "Solo mínimos" en alternatives
        alt_data = alt_chart["chart"].get("data", [])
        patched = False
        for row in alt_data:
            opcion = (row.get("opcion") or "").lower()
            if "mínimo" in opcion or "minimo" in opcion:
                llm_meses = row.get("plazo_meses", 0)
                llm_costo = row.get("costo_total", 0)

                # Si el LLM se desvió más de 50% del cálculo real, corregir
                meses_off = abs(llm_meses - calc_meses) > calc_meses * 0.5 if calc_meses > 0 else False
                costo_off = abs(llm_costo - calc_costo) > calc_costo * 0.5 if calc_costo > 0 else False

                if meses_off or costo_off:
                    logger.info(
                        "Fixing alternatives chart: LLM said %d meses / S/ %s, "
                        "recalculated %d meses / S/ %s",
                        llm_meses, llm_costo, calc_meses, calc_costo,
                    )
                    row["plazo_meses"] = calc_meses
                    row["costo_total"] = calc_costo
                    row["ahorro"] = 0
                    patched = True
                break

        if patched:
            # Recalcular ahorro de las otras filas respecto al nuevo costo de mínimos
            for row in alt_data:
                opcion = (row.get("opcion") or "").lower()
                if "mínimo" not in opcion and "minimo" not in opcion:
                    row_costo = row.get("costo_total", 0)
                    if row_costo > 0 and calc_costo > row_costo:
                        row["ahorro"] = round(calc_costo - row_costo, 2)

            # Reemplazar el chart en el texto
            alt_chart["chart"]["data"] = alt_data
            new_json = _json.dumps(alt_chart["chart"], ensure_ascii=False)
            match = alt_chart["match"]
            result_text = (
                result_text[:match.start()]
                + match.group(1) + new_json + match.group(3)
                + result_text[match.end():]
            )
            logger.info("Alternatives chart patched successfully")

        return result_text
    except Exception as e:
        logger.warning("Could not post-process alternatives chart: %s", e)
        return result_text



def _get_user_cards_context(usuario_id: str, ingreso_mensual: str = "", payment_behavior: str = "minimum") -> str:
    """Consulta estados_cuenta y retorna contexto para inyectar en el prompt."""
    try:
        from boto3.dynamodb.conditions import Key

        estados_table_name = os.environ.get("ESTADOS_TABLE_NAME", "")
        if not estados_table_name:
            return ""

        estados_table = dynamodb.Table(estados_table_name)
        response = estados_table.query(
            KeyConditionExpression=Key("usuario_id").eq(usuario_id),
        )
        items = response.get("Items", [])
        if not items:
            return ""

        lines = []
        for item in items:
            banco = item.get("banco", "?")
            saldo = item.get("saldo", 0)
            tcea = item.get("tcea", 0)
            pago_min = item.get("pago_minimo", 0)
            lines.append(f"- {banco}: saldo S/ {saldo:,.0f}, TCEA {tcea}%, pago mínimo S/ {pago_min:,.0f}")

        return (
            "[CONTEXTO DEL USUARIO]\n"
            f"Ingreso mensual del usuario: S/ {ingreso_mensual}\n"
            f"Conducta de pago: {payment_behavior}\n"
            f"El usuario ya tiene {len(items)} tarjeta(s) analizada(s) en el sistema:\n"
            + "\n".join(lines)
            + f"\nusuario_id: {usuario_id}\n"
            + "Usa estos datos para responder. Pasa usuario_id a las tools cuando necesites cargar transacciones o simular escenarios. No pidas documentos nuevos a menos que el usuario quiera actualizar.\n"
            "[FIN CONTEXTO]"
        )
    except Exception as e:
        logger.warning("Could not get user cards context: %s", e)
        return ""


def _get_latest_fecha_corte(usuario_id: str) -> str:
    """Consulta la tabla de estados de cuenta para obtener la fecha_corte más reciente.

    Returns:
        La fecha_corte más reciente en formato DD/MM/YYYY, o cadena vacía si no se encuentra.
    """
    try:
        from boto3.dynamodb.conditions import Key
        from datetime import datetime

        estados_table_name = os.environ.get("ESTADOS_TABLE_NAME", "")
        if not estados_table_name:
            return ""

        estados_table = dynamodb.Table(estados_table_name)
        response = estados_table.query(
            KeyConditionExpression=Key("usuario_id").eq(usuario_id),
        )
        items = response.get("Items", [])
        if not items:
            return ""

        latest_fc = ""
        latest_dt = None
        for item in items:
            fc = item.get("fecha_corte", "")
            if not fc:
                continue
            try:
                parts = fc.split("/")
                if len(parts) == 3:
                    dt = datetime(int(parts[2]), int(parts[1]), int(parts[0]))
                    if latest_dt is None or dt > latest_dt:
                        latest_dt = dt
                        latest_fc = fc
            except (ValueError, IndexError):
                continue

        return latest_fc
    except Exception as e:
        logger.warning("Could not get fecha_corte: %s", e)
        return ""


def _extract_fecha_corte_from_filenames(pdfs: list) -> str:
    """Extrae fecha_corte de los nombres de archivo de los PDFs subidos.

    Los archivos siguen el patrón: 'N-estado-cuenta-banco-TC-usuario-mes-año.pdf'
    Ejemplo: '3 N-estado-cuenta-falabella-TC-gaston-ene-2026.pdf'

    Devuelve la fecha más reciente encontrada en formato DD/MM/YYYY.
    """
    import re

    MESES = {
        "ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6,
        "jul": 7, "ago": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dic": 12,
        "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
        "julio": 7, "agosto": 8, "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
    }

    if not pdfs:
        return ""

    latest_dt = None
    latest_fc = ""

    for pdf_path in pdfs:
        # Extraer solo el nombre del archivo
        filename = pdf_path.split("/")[-1].lower() if "/" in pdf_path else pdf_path.lower()

        # Patrón: mes-año al final del nombre (ej: ene-2026.pdf, nov-2025.pdf)
        pattern = r'(' + '|'.join(MESES.keys()) + r')[\-_\s]*(\d{4})'
        m = re.search(pattern, filename)
        if m:
            mes_num = MESES[m.group(1)]
            anio = int(m.group(2))
            try:
                from datetime import datetime
                dt = datetime(anio, mes_num, 1)
                if latest_dt is None or dt > latest_dt:
                    latest_dt = dt
                    latest_fc = f"01/{mes_num:02d}/{anio}"
            except ValueError:
                continue

    if latest_fc:
        logger.info("Extracted fecha_corte from filenames: %s", latest_fc)
    return latest_fc


def _extract_fecha_corte_from_text(result_text: str) -> str:
    """Fallback: extrae fecha_corte del texto de respuesta del agente.

    Busca patrones como 'fecha de corte: 25/12/2025' o 'noviembre 2025'
    y devuelve en formato DD/MM/YYYY.
    """
    import re

    MESES = {
        "enero": 1, "ene": 1, "febrero": 2, "feb": 2, "marzo": 3, "mar": 3,
        "abril": 4, "abr": 4, "mayo": 5, "may": 5, "junio": 6, "jun": 6,
        "julio": 7, "jul": 7, "agosto": 8, "ago": 8, "septiembre": 9, "sep": 9, "sept": 9,
        "octubre": 10, "oct": 10, "noviembre": 11, "nov": 11, "diciembre": 12, "dic": 12,
    }

    clean = result_text.replace("**", "").lower()

    # Patrón 1: DD/MM/YYYY explícito cerca de "fecha de corte"
    m = re.search(r'fecha\s*(?:de\s*)?corte[:\s]*(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})', clean)
    if m:
        return f"{int(m.group(1)):02d}/{int(m.group(2)):02d}/{m.group(3)}"

    # Patrón 2: "mes año" en texto libre (ej: "noviembre 2025")
    pattern = r'\b(' + '|'.join(MESES.keys()) + r')\b[\s\-/]*(\d{4})'
    m = re.search(pattern, clean)
    if m:
        mes_num = MESES[m.group(1)]
        anio = m.group(2)
        return f"01/{mes_num:02d}/{anio}"

    return ""


def _save_financial_snapshot(usuario_id: str, result_text: str, currency: str = "PEN", pdfs: list = None):
    """Extrae KPIs del resultado y guarda snapshot en historial financiero.

    Cadena de extracción de fecha_corte:
    1. Tabla de estados de cuenta (DynamoDB) — actualmente vacía
    2. Nombres de archivo de los PDFs subidos — más fiable
    3. Texto de respuesta del agente — fallback
    """
    if not FINANCIAL_HISTORY_TABLE:
        return
    try:
        import re
        import json as _json
        from datetime import datetime, timezone
        from decimal import Decimal

        ts = datetime.now(timezone.utc).isoformat()
        fecha_corte = _get_latest_fecha_corte(usuario_id)

        # Fallback 1: extraer de los nombres de archivo (más fiable)
        if not fecha_corte and pdfs:
            fecha_corte = _extract_fecha_corte_from_filenames(pdfs)

        # Fallback 2: extraer del texto de respuesta del agente
        if not fecha_corte:
            fecha_corte = _extract_fecha_corte_from_text(result_text)

        snapshot = {
            "usuario_id": usuario_id,
            "timestamp": ts,
            "moneda": currency,
        }
        if fecha_corte:
            snapshot["fecha_corte"] = fecha_corte

        # ── Estrategia 1: Extraer de bloques :::chart (más fiable) ──
        chart_blocks = re.findall(r':::chart\s*(\{[\s\S]*?\})\s*:::', result_text)
        for block in chart_blocks:
            try:
                chart = _json.loads(block)
                ctype = chart.get("type", "")
                data = chart.get("data", [])

                if ctype == "debtComposition" and data:
                    total = sum(item.get("saldo", 0) for item in data)
                    if total > 0:
                        snapshot["deuda_total"] = Decimal(str(total))
                        snapshot["num_tarjetas"] = len(data)

                elif ctype == "alternatives" and data:
                    # Buscar "Solo mínimos" para plazo y costo
                    for row in data:
                        opcion = (row.get("opcion") or "").lower()
                        if "mínimo" in opcion or "minimo" in opcion:
                            if row.get("plazo_meses"):
                                snapshot["plazo_meses"] = int(row["plazo_meses"])
                            if row.get("costo_total"):
                                snapshot["costo_total_plan"] = Decimal(str(row["costo_total"]))

            except (_json.JSONDecodeError, TypeError, ValueError):
                continue

        # ── Estrategia 2: Regex sobre texto (complementa lo que falte) ──
        # Strip markdown bold markers para facilitar matching
        clean = result_text.replace("**", "")

        if "deuda_total" not in snapshot:
            m = re.search(r'[Dd]euda\s*total[:\s]*(?:S/|USD|\$|R\$|Bs|Q)?\s*([\d,.]+)', clean)
            if m:
                snapshot["deuda_total"] = Decimal(m.group(1).replace(",", ""))

        if "num_tarjetas" not in snapshot:
            m = re.search(r'(\d+)\s*tarjeta', clean, re.IGNORECASE)
            if m:
                snapshot["num_tarjetas"] = int(m.group(1))

        if "plazo_meses" not in snapshot:
            m = re.search(r'(\d+)\s*meses', clean, re.IGNORECASE)
            if m:
                snapshot["plazo_meses"] = int(m.group(1))

        if "intereses_mensuales" not in snapshot:
            m = re.search(r'[Ii]nter[eé]s(?:es)?\s*mensual(?:es)?[:\s]*(?:S/|USD|\$|R\$|Bs|Q)?\s*([\d,.]+)', clean)
            if m:
                snapshot["intereses_mensuales"] = Decimal(m.group(1).replace(",", ""))

        if "ratio_deuda_ingreso" not in snapshot:
            m = re.search(r'[Rr]atio\s*(?:deuda[/\s]*ingreso)?[:\s]*([\d,.]+)', clean)
            if m:
                val = m.group(1).replace(",", ".")
                snapshot["ratio_deuda_ingreso"] = Decimal(val)

        if "costo_total_plan" not in snapshot:
            m = re.search(r'[Cc]osto\s*total[:\s]*(?:S/|USD|\$|R\$|Bs|Q)?\s*([\d,.]+)', clean)
            if m:
                snapshot["costo_total_plan"] = Decimal(m.group(1).replace(",", ""))

        # Solo guardar si hay al menos deuda_total
        if "deuda_total" in snapshot:
            history_table = dynamodb.Table(FINANCIAL_HISTORY_TABLE)
            history_table.put_item(Item=snapshot)
            logger.info("Financial snapshot saved: deuda=%s", snapshot.get("deuda_total"))
        else:
            logger.info("No KPIs extracted, skipping snapshot")
    except Exception as e:
        logger.warning("Could not save financial snapshot: %s", e)



def lambda_handler(event, context):
    """Invoked async by dispatcher. event contains job_id, prompt, etc."""
    job_id = event.get("job_id")
    prompt = event.get("prompt", "")
    usuario_id = event.get("usuario_id", "default_user")
    contexto = event.get("contexto", {})
    session_id = event.get("session_id", str(uuid.uuid4()))

    # Validar que el usuario_id del job coincida con el authenticated_user del dispatcher
    authenticated_user = event.get("authenticated_user", "")
    if authenticated_user and usuario_id != authenticated_user:
        logger.warning("Authorization mismatch: usuario_id=%s, authenticated=%s", usuario_id, authenticated_user)
        _mark_failed(job_id, "No tienes autorización para acceder a estos datos.")
        return

    # Mark job as PROCESSING
    jobs_table.update_item(
        Key={"job_id": job_id},
        UpdateExpression="SET #s = :s, started_at = :t",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={":s": "PROCESSING", ":t": int(time.time())},
    )

    try:
        prompt_completo = prompt
        if contexto:
            extras = []
            if "pdfs" in contexto:
                extras.append(f"PDFs subidos en S3: {contexto['pdfs']}")
            if "ingreso_mensual" in contexto:
                extras.append(f"Ingreso mensual del usuario: {contexto['ingreso_mensual']}")
            if extras:
                prompt_completo += (
                    f"\n\n[Contexto: {'. '.join(extras)}."
                    f" usuario_id: {usuario_id}]"
                )

        # Inyectar resumen del análisis previo para contexto de seguimiento
        if contexto and "pdfs" in contexto:
            prev_summary = _get_previous_analysis_summary(usuario_id)
            if prev_summary:
                prompt_completo += prev_summary
            else:
                prompt_completo += "\n\n[PRIMERA VEZ: Este usuario NO tiene análisis previos. Es su primera interacción. Salúdalo como nuevo usuario, NO digas 'veamos tu progreso' ni 'desde el último análisis'.]"
        else:
            # Chat sin PDFs: inyectar datos existentes del usuario para que el agente tenga contexto
            ingreso = contexto.get("ingreso_mensual", "") if isinstance(contexto, dict) else ""
            pb = contexto.get("payment_behavior", "minimum") if isinstance(contexto, dict) else "minimum"
            user_cards_context = _get_user_cards_context(usuario_id, ingreso, pb)
            if user_cards_context:
                prompt_completo = user_cards_context + "\n\n" + prompt_completo

        payload = {"prompt": prompt_completo, "usuario_id": usuario_id}
        if contexto:
            payload["contexto"] = contexto
            # Pasar contexto de país al AgentCore
            for key in ("country", "currency", "language", "payment_behavior"):
                if key in contexto:
                    payload[key] = contexto[key]

        # Calcular timeout dinámico: dejar 30s de margen antes del timeout de Lambda
        remaining_ms = getattr(context, "get_remaining_time_in_millis", lambda: AGENTCORE_TIMEOUT_S * 1000 + 30000)()
        effective_timeout = max(min(AGENTCORE_TIMEOUT_S, (remaining_ms // 1000) - 30), 60)

        logger.info("Worker processing job %s, timeout %ds", job_id, effective_timeout)
        result = _invoke_with_timeout(payload, session_id, effective_timeout)

        result_text = result.get("result", "")

        # Post-procesar: corregir alternatives chart si el LLM inventó números
        pb = contexto.get("payment_behavior", "") if isinstance(contexto, dict) else ""
        result_text = _fix_alternatives_chart(result_text, payment_behavior=pb)

        # Detectar si AgentCore devolvió un error envuelto como resultado exitoso
        is_error_result = result_text.startswith("⚠️") or result_text.startswith("Error")

        if is_error_result:
            logger.warning("Job %s: AgentCore returned error-like result", job_id)
            _mark_failed(job_id, result_text)
        else:
            has_presentation = ":::chart" in result_text
            jobs_table.update_item(
                Key={"job_id": job_id},
                UpdateExpression="SET #s = :s, #r = :r, #sid = :sid, completed_at = :t, has_presentation = :hp",
                ExpressionAttributeNames={"#s": "status", "#r": "result", "#sid": "session_id"},
                ExpressionAttributeValues={
                    ":s": "COMPLETED",
                    ":r": result_text,
                    ":sid": session_id,
                    ":t": int(time.time()),
                    ":hp": has_presentation,
                },
            )
            logger.info("Job %s completed", job_id)

            # Guardar snapshot de KPIs en historial financiero
            currency = contexto.get("currency", "PEN") if isinstance(contexto, dict) else "PEN"
            pdfs = contexto.get("pdfs", []) if isinstance(contexto, dict) else []
            if isinstance(pdfs, str):
                pdfs = [pdfs]
            _save_financial_snapshot(usuario_id, result_text, currency, pdfs=pdfs)
    except TimeoutError as e:
        logger.error("Worker TIMEOUT for job %s: %s", job_id, e)
        _mark_failed(job_id, f"Timeout: el análisis tardó más de {AGENTCORE_TIMEOUT_S}s. Intenta con menos documentos.")
    except Exception as e:
        logger.error("Worker error for job %s: %s", job_id, e, exc_info=True)
        _mark_failed(job_id, "Error interno al procesar el análisis. Intenta de nuevo.")
