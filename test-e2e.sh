#!/bin/bash
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
# =============================================================
# E2E Test Suite
# =============================================================
# Simula el flujo completo: upload de PDFs + análisis + preguntas de chat.
# Requiere un stack desplegado y un usuario creado.
#
# Uso:
#   export AWS_REGION=us-east-2
#   export AWS_PROFILE=<your-aws-profile>
#   export TEST_EMAIL=<cognito-user-email>
#   export TEST_PASSWORD=<cognito-user-password>
#   ./test-e2e.sh [email] [password]
#
# Credentials are read from args or the TEST_EMAIL / TEST_PASSWORD
# environment variables. Never hardcode real credentials in this file.
#
# Prerequisitos:
#   - Stack FinancialHealthStack desplegado
#   - Usuario Cognito creado con contraseña permanente
#   - PDFs de prueba en demo/pdfs/
#
# Qué se comprueba (y por qué):
#   Un job que termina en COMPLETED no implica una respuesta útil. Este script
#   evalúa el CONTENIDO además del estado:
#     - Análisis: debe incluir bloques :::chart y mencionar una entidad extraída
#       de los PDFs subidos.
#     - Persistencia: los estados de cuenta extraídos deben existir en DynamoDB.
#       Sin esto, el análisis inicial funciona pero los turnos de chat siguientes
#       se quedan sin datos.
#     - Chat: una respuesta que dice no tener los estados de cuenta del usuario
#       cuenta como FALLO, no como éxito.
#   Termina con código distinto de cero si algo falla, para que un CI lo detecte.
# =============================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REGION="${AWS_REGION:?Set AWS_REGION}"
PROFILE="${AWS_PROFILE:-default}"
EMAIL="${1:-${TEST_EMAIL:?Set TEST_EMAIL or pass the email as argument 1}}"
PASSWORD="${2:-${TEST_PASSWORD:?Set TEST_PASSWORD or pass the password as argument 2}}"

# ── Load stack outputs ──
OUTPUTS_FILE="$SCRIPT_DIR/cdk-outputs.json"
if [ ! -f "$OUTPUTS_FILE" ]; then
    echo "ERROR: $OUTPUTS_FILE not found. Deploy the stack first."
    exit 1
fi

API_URL=$(python3 -c "import json;print(json.load(open('$OUTPUTS_FILE'))['FinancialHealthStack']['ApiUrl'])")
CLIENT_ID=$(python3 -c "import json;print(json.load(open('$OUTPUTS_FILE'))['FinancialHealthStack']['UserPoolClientId'])")
CF_URL=$(python3 -c "import json;print(json.load(open('$OUTPUTS_FILE'))['FinancialHealthStack']['CloudFrontUrl'])")
ESTADOS_TABLE=$(python3 -c "import json;print(json.load(open('$OUTPUTS_FILE'))['FinancialHealthStack']['EstadosCuentaTableName'])")

echo ""
echo "═══════════════════════════════════════════"
echo "  🧪 E2E Test Suite"
echo "═══════════════════════════════════════════"
echo "  API:        $API_URL"
echo "  CloudFront: $CF_URL"
echo "  User:       $EMAIL"
echo "  Region:     $REGION"
echo "═══════════════════════════════════════════"
echo ""

# ── Authenticate ──
echo "[1/5] Authenticating..."
TOKEN=$(aws cognito-idp initiate-auth \
    --client-id "$CLIENT_ID" \
    --auth-flow USER_PASSWORD_AUTH \
    --auth-parameters "USERNAME=$EMAIL,PASSWORD=$PASSWORD" \
    --region "$REGION" --profile "$PROFILE" \
    --query "AuthenticationResult.IdToken" --output text 2>/dev/null)

if [ -z "$TOKEN" ] || [ "$TOKEN" = "None" ]; then
    echo "  ❌ FAILED: Could not authenticate. Check credentials."
    exit 1
fi
echo "  ✅ Authenticated (token: ${#TOKEN} chars)"

# El sub del IdToken es el usuario_id real (clave de partición en DynamoDB).
# Se necesita para comprobar que los estados de cuenta se persistieron.
USER_SUB=$(python3 -c "
import base64, json, sys
payload = '$TOKEN'.split('.')[1]
payload += '=' * (-len(payload) % 4)
print(json.loads(base64.urlsafe_b64decode(payload)).get('sub',''))
" 2>/dev/null)
echo "  ✅ usuario_id (sub): $USER_SUB"

# ── Upload PDFs ──
echo ""
echo "[2/5] Uploading PDFs..."
PDFS=(
    "$SCRIPT_DIR/demo/pdfs/Carolina/estado-cuenta-banco-vantia-carolina.pdf"
    "$SCRIPT_DIR/demo/pdfs/Carolina/estado-cuenta-tiendas-orvia-carolina.pdf"
    "$SCRIPT_DIR/demo/pdfs/Carolina/estado-cuenta-tiendas-delsu-carolina.pdf"
)
S3_URIS=()
UPLOAD_PASS=0
UPLOAD_FAIL=0

for PDF in "${PDFS[@]}"; do
    FILENAME=$(basename "$PDF")
    HASH=$(shasum -a 256 "$PDF" | cut -d' ' -f1)

    # Get presigned URL
    RESP=$(curl -s -X POST "${API_URL}upload" \
        -H "Content-Type: application/json" \
        -H "Authorization: $TOKEN" \
        -d "{\"filename\":\"$FILENAME\",\"fileHash\":\"$HASH\"}")

    STATUS=$(echo "$RESP" | python3 -c "import sys,json;d=json.load(sys.stdin);print(d.get('error','ok'))" 2>/dev/null)

    if [ "$STATUS" = "duplicate" ]; then
        echo "  ⚠️  $FILENAME (duplicate — skipped)"
        S3_URI=$(echo "$RESP" | python3 -c "import sys,json;print(json.load(sys.stdin).get('s3Uri',''))" 2>/dev/null)
        # For duplicates we still need the s3Uri from a previous upload — skip in S3_URIS
        continue
    fi

    UPLOAD_URL=$(echo "$RESP" | python3 -c "import sys,json;print(json.load(sys.stdin).get('uploadUrl',''))" 2>/dev/null)
    S3_URI=$(echo "$RESP" | python3 -c "import sys,json;print(json.load(sys.stdin).get('s3Uri',''))" 2>/dev/null)

    if [ -z "$UPLOAD_URL" ]; then
        echo "  ❌ $FILENAME (no presigned URL)"
        UPLOAD_FAIL=$((UPLOAD_FAIL + 1))
        continue
    fi

    # Upload to S3
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" -X PUT "$UPLOAD_URL" \
        -H "Content-Type: application/pdf" \
        --data-binary @"$PDF")

    if [ "$HTTP_CODE" = "200" ]; then
        echo "  ✅ $FILENAME → $S3_URI"
        S3_URIS+=("$S3_URI")
        UPLOAD_PASS=$((UPLOAD_PASS + 1))
    else
        echo "  ❌ $FILENAME (HTTP $HTTP_CODE)"
        UPLOAD_FAIL=$((UPLOAD_FAIL + 1))
    fi
done

echo "  Upload: $UPLOAD_PASS passed, $UPLOAD_FAIL failed"

# ── Run analysis ──
echo ""
echo "[3/5] Running analysis..."

if [ ${#S3_URIS[@]} -eq 0 ]; then
    echo "  ⚠️  No new PDFs uploaded (all duplicates). Skipping analysis."
else
    PDFS_JSON=$(printf '"%s",' "${S3_URIS[@]}" | sed 's/,$//')
    INVOKE_RESP=$(curl -s -X POST "${API_URL}invoke" \
        -H "Content-Type: application/json" \
        -H "Authorization: $TOKEN" \
        -d "{\"prompt\":\"Analiza mis estados de cuenta\",\"contexto\":{\"pdfs\":[$PDFS_JSON],\"ingreso_mensual\":\"7500\",\"country\":\"PE\",\"currency\":\"PEN\",\"language\":\"es\",\"payment_behavior\":\"minimum\"}}")

    JOB_ID=$(echo "$INVOKE_RESP" | python3 -c "import sys,json;print(json.load(sys.stdin).get('job_id',''))" 2>/dev/null)
    echo "  Job: $JOB_ID"
    echo "  Polling (max 240s)..."

    START_TIME=$(date +%s)
    STATUS="PENDING"
    while [ "$STATUS" != "COMPLETED" ] && [ "$STATUS" != "FAILED" ]; do
        sleep 5
        ELAPSED=$(( $(date +%s) - START_TIME ))
        if [ $ELAPSED -gt 240 ]; then
            echo "  ❌ TIMEOUT after 240s"
            STATUS="TIMEOUT"
            break
        fi
        RESULT=$(curl -s "${API_URL}job/$JOB_ID" -H "Authorization: $TOKEN")
        STATUS=$(echo "$RESULT" | python3 -c "import sys,json;print(json.load(sys.stdin).get('status',''))" 2>/dev/null)
    done

    if [ "$STATUS" = "COMPLETED" ]; then
        # No basta con que el job termine: el resultado debe contener gráficos y
        # datos reales extraídos de los PDFs. Un job COMPLETED con una respuesta
        # genérica es un fallo, no un éxito.
        ANALYSIS_EVAL=$(echo "$RESULT" | python3 -c "
import sys, json, re
r = json.load(sys.stdin).get('result','')
charts = ':::chart' in r
entidad = bool(re.search(r'Vantia|Orvia|Delsu', r, re.I))
cifra = bool(re.search(r'18[.,]000|18000', r))
print(f'{len(r)}|{int(charts)}|{int(entidad)}|{int(cifra)}')
" 2>/dev/null)
        A_LEN=$(echo "$ANALYSIS_EVAL" | cut -d'|' -f1)
        A_CHARTS=$(echo "$ANALYSIS_EVAL" | cut -d'|' -f2)
        A_ENTITY=$(echo "$ANALYSIS_EVAL" | cut -d'|' -f3)
        A_FIGURE=$(echo "$ANALYSIS_EVAL" | cut -d'|' -f4)
        echo "  Length: $A_LEN chars | charts: $A_CHARTS | entidad extraída: $A_ENTITY | cifra esperada: $A_FIGURE"
        if [ "$A_CHARTS" = "1" ] && [ "$A_ENTITY" = "1" ]; then
            echo "  ✅ Analysis completed with grounded data (${ELAPSED}s)"
            ANALYSIS_OK=1
        else
            echo "  ❌ Analysis completed but the response is not grounded in the uploaded PDFs"
            ANALYSIS_OK=0
        fi
    else
        echo "  ❌ Analysis $STATUS"
        ANALYSIS_OK=0
    fi
fi

# ── Verify persistence ──
# Comprobación directa del defecto que este test no detectaba: el análisis podía
# completarse y renderizar gráficos mientras los estados de cuenta extraídos nunca
# se escribían en DynamoDB, dejando sin datos a todo turno posterior.
echo ""
echo "[4/5] Verifying persistence in DynamoDB..."
PERSIST_OK=0
if [ -z "$USER_SUB" ]; then
    echo "  ⚠️  No se pudo determinar el sub del usuario; se omite la comprobación"
else
    CARD_COUNT=$(aws dynamodb query \
        --table-name "$ESTADOS_TABLE" \
        --key-condition-expression "usuario_id = :u" \
        --expression-attribute-values "{\":u\":{\"S\":\"$USER_SUB\"}}" \
        --region "$REGION" --profile "$PROFILE" \
        --query 'Count' --output text 2>/dev/null || echo "0")
    echo "  Tarjetas persistidas para $USER_SUB: ${CARD_COUNT:-0}"
    if [ "${CARD_COUNT:-0}" -ge 1 ]; then
        aws dynamodb query \
            --table-name "$ESTADOS_TABLE" \
            --key-condition-expression "usuario_id = :u" \
            --expression-attribute-values "{\":u\":{\"S\":\"$USER_SUB\"}}" \
            --region "$REGION" --profile "$PROFILE" \
            --query 'Items[].{banco:banco.S,saldo:saldo.N,tcea:tcea.N}' --output text 2>/dev/null \
            | sed 's/^/     /'
        echo "  ✅ Estados de cuenta persistidos"
        PERSIST_OK=1
    else
        echo "  ❌ Ninguna tarjeta persistida — los turnos de chat siguientes se quedarán sin datos"
    fi
fi

# ── Chat questions ──
echo ""
echo "[5/5] Testing chat questions..."

QUESTIONS=(
    "¿Cuánto gasto en delivery al mes?"
    "¿Qué suscripciones tengo activas?"
    "Si elimino el delivery por completo, ¿cuántos meses antes me libero de la deuda?"
    "¿Cuáles son mis gastos hormiga más grandes?"
    "¿Detectaste pagos duplicados en mis tarjetas?"
    "¿Qué pasa si recibo una gratificación de S/ 5,000?"
    "Si consigo un ingreso extra de S/ 1,000/mes, ¿en cuánto tiempo salgo de deuda?"
    "¿Cuál tarjeta me conviene pagar primero?"
    "¿Cuánto estoy pagando de intereses al mes?"
    "¿Me conviene consolidar mi deuda?"
)

CHAT_PASS=0
CHAT_FAIL=0
CHAT_TOTAL=${#QUESTIONS[@]}

for Q in "${QUESTIONS[@]}"; do
    JOB=$(curl -s -X POST "${API_URL}invoke" \
        -H "Content-Type: application/json" \
        -H "Authorization: $TOKEN" \
        -d "{\"prompt\":\"$Q\",\"contexto\":{\"ingreso_mensual\":\"7500\",\"country\":\"PE\",\"currency\":\"PEN\",\"payment_behavior\":\"minimum\"}}" \
        | python3 -c "import sys,json;print(json.load(sys.stdin).get('job_id',''))" 2>/dev/null)

    # Poll
    for i in $(seq 1 40); do
        sleep 4
        R=$(curl -s "${API_URL}job/$JOB" -H "Authorization: $TOKEN")
        S=$(echo "$R" | python3 -c "import sys,json;print(json.load(sys.stdin).get('status',''))" 2>/dev/null)
        if [ "$S" = "COMPLETED" ] || [ "$S" = "FAILED" ]; then break; fi
    done

    ANSWER=$(echo "$R" | python3 -c "import sys,json;print(json.load(sys.stdin).get('result',''))" 2>/dev/null)

    # Un job COMPLETED no implica una respuesta útil. Se evalúa el contenido:
    #  - blocked   : el guardrail interceptó la respuesta
    #  - no_data   : el agente dice que no tiene los estados de cuenta del usuario.
    #                Este era el fallo que el test dejaba pasar como éxito.
    EVAL=$(printf '%s' "$ANSWER" | python3 -c "
import sys, re
a = sys.stdin.read()
blocked = bool(re.search(r'no puedo procesar|no puedo proporcionar', a, re.I))
no_data = bool(re.search(
    r'no tengo (acceso|tus|información|los datos)'
    r'|necesito (revisar|conocer|que subas|cargar)'
    r'|no he procesado'
    r'|a[úu]n no (tenemos|tengo|he)'
    r'|no tenemos tus'
    r'|podr[íi]as (compartir|subir)'
    r'|sube tus estados',
    a, re.I))
print(f'{int(blocked)}|{int(no_data)}')
" 2>/dev/null)
    BLOCKED=$(echo "$EVAL" | cut -d'|' -f1)
    NO_DATA=$(echo "$EVAL" | cut -d'|' -f2)

    if [ "$S" != "COMPLETED" ]; then
        echo "  ❌ $Q → ${S:-UNKNOWN}"
        CHAT_FAIL=$((CHAT_FAIL + 1))
    elif [ "$BLOCKED" = "1" ]; then
        echo "  ❌ $Q → bloqueado por el guardrail"
        CHAT_FAIL=$((CHAT_FAIL + 1))
    elif [ "$NO_DATA" = "1" ]; then
        PREVIEW=$(printf '%s' "$ANSWER" | tr '\n' ' ' | cut -c1-110)
        echo "  ❌ $Q → el agente no encuentra los datos del usuario"
        echo "     → $PREVIEW..."
        CHAT_FAIL=$((CHAT_FAIL + 1))
    else
        PREVIEW=$(printf '%s' "$ANSWER" | tr '\n' ' ' | cut -c1-90)
        echo "  ✅ $Q"
        echo "     → $PREVIEW..."
        CHAT_PASS=$((CHAT_PASS + 1))
    fi
done

# ── Summary ──
echo ""
echo "═══════════════════════════════════════════"
echo "  📊 TEST RESULTS"
echo "═══════════════════════════════════════════"
echo "  Upload:      $UPLOAD_PASS/$((UPLOAD_PASS + UPLOAD_FAIL)) passed"
echo "  Analysis:    $([ "${ANALYSIS_OK:-0}" = "1" ] && echo 'grounded' || echo 'FAILED')"
echo "  Persistence: $([ "${PERSIST_OK:-0}" = "1" ] && echo 'ok' || echo 'FAILED')"
echo "  Chat:        $CHAT_PASS/$CHAT_TOTAL passed"
echo ""

TOTAL_PASS=$((UPLOAD_PASS + CHAT_PASS + ${ANALYSIS_OK:-0} + ${PERSIST_OK:-0}))
TOTAL_TESTS=$((UPLOAD_PASS + UPLOAD_FAIL + CHAT_TOTAL + 2))

if [ $CHAT_FAIL -eq 0 ] && [ $UPLOAD_FAIL -eq 0 ] \
   && [ "${ANALYSIS_OK:-0}" = "1" ] && [ "${PERSIST_OK:-0}" = "1" ]; then
    echo "  ✅ ALL TESTS PASSED ($TOTAL_PASS/$TOTAL_TESTS)"
    echo "═══════════════════════════════════════════"
    exit 0
else
    echo "  ❌ SOME TESTS FAILED ($TOTAL_PASS/$TOTAL_TESTS passed)"
    echo "═══════════════════════════════════════════"
    # Salir con código distinto de cero: antes el script terminaba en 0 incluso
    # con fallos, así que ningún CI podía detectarlos.
    exit 1
fi
