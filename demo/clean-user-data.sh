#!/bin/bash
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
# ============================================================
# Limpieza de datos de un usuario
#
# Uso: bash demo/clean-user-data.sh <usuario_id>
#
# Borra los datos del usuario en las cuatro tablas de DynamoDB, sus PDFs en S3,
# y sus registros en AgentCore Memory. El usuario de Cognito NO se borra.
#
# Requiere estas variables de entorno, todas presentes en cdk-outputs.json o en
# SSM bajo /financial-health/:
#   AWS_REGION  ESTADOS_TABLE  HASHES_TABLE  HISTORY_TABLE  JOBS_TABLE
#   S3_PDFS_BUCKET  MEMORY_ID
# ============================================================

set -e

PROFILE="${AWS_PROFILE:-default}"
REGION="${AWS_REGION:?Set AWS_REGION}"

# Tablas DynamoDB
ESTADOS_TABLE="${ESTADOS_TABLE:?Set ESTADOS_TABLE}"
HASHES_TABLE="${HASHES_TABLE:?Set HASHES_TABLE}"
HISTORY_TABLE="${HISTORY_TABLE:?Set HISTORY_TABLE}"
JOBS_TABLE="${JOBS_TABLE:?Set JOBS_TABLE}"

# S3 bucket
PDFS_BUCKET="${S3_PDFS_BUCKET:?Set S3_PDFS_BUCKET}"

# AgentCore Memory
MEMORY_ID="${MEMORY_ID:?Set MEMORY_ID}"

USER_ID="$1"

if [ -z "$USER_ID" ]; then
  echo "Uso: bash demo/clean-user-data.sh <usuario_id>"
  echo ""
  echo "El usuario_id es el 'sub' de Cognito. Para obtenerlo:"
  echo "  aws cognito-idp admin-get-user --user-pool-id <POOL> --username <EMAIL> \\"
  echo "    --query 'UserAttributes[?Name==\`sub\`].Value' --output text"
  exit 1
fi

echo "=== Limpiando datos de usuario: $USER_ID ==="
echo ""

# --- Borrar items con PK=usuario_id y SK dado ---
delete_by_userid() {
  local TABLE=$1
  local SK_NAME=$2
  echo ">> $TABLE (PK=usuario_id, SK=$SK_NAME)"

  ITEMS=$(MSYS_NO_PATHCONV=1 aws dynamodb query \
    --table-name "$TABLE" \
    --key-condition-expression "usuario_id = :uid" \
    --expression-attribute-values "{\":uid\":{\"S\":\"$USER_ID\"}}" \
    --profile "$PROFILE" --region "$REGION" --output json 2>/dev/null)

  COUNT=$(echo "$ITEMS" | python3 -c "import sys,json; print(json.load(sys.stdin)['Count'])")

  if [ "$COUNT" = "0" ]; then
    echo "   (0 items)"
    return
  fi

  echo "   $COUNT items — borrando..."
  echo "$ITEMS" | python3 -c "
import sys, json, subprocess, os
data = json.load(sys.stdin)
env = {**os.environ, 'MSYS_NO_PATHCONV': '1'}
for item in data['Items']:
    sk_val = item['$SK_NAME']['S']
    key = json.dumps({'usuario_id':{'S':'$USER_ID'},'$SK_NAME':{'S':sk_val}})
    subprocess.run(['aws','dynamodb','delete-item','--table-name','$TABLE','--key',key,'--profile','$PROFILE','--region','$REGION'], check=True, env=env, capture_output=True)
    print(f'   x {sk_val}')
print(f'   OK ({len(data[\"Items\"])} eliminados)')
"
}

# --- Borrar jobs (PK=job_id, buscar por scan + filter) ---
delete_jobs() {
  echo ">> $JOBS_TABLE (PK=job_id, scan por usuario_id)"

  ITEMS=$(MSYS_NO_PATHCONV=1 aws dynamodb scan \
    --table-name "$JOBS_TABLE" \
    --filter-expression "usuario_id = :uid" \
    --expression-attribute-values "{\":uid\":{\"S\":\"$USER_ID\"}}" \
    --projection-expression "job_id" \
    --profile "$PROFILE" --region "$REGION" --output json 2>/dev/null)

  COUNT=$(echo "$ITEMS" | python3 -c "import sys,json; print(json.load(sys.stdin)['Count'])")

  if [ "$COUNT" = "0" ]; then
    echo "   (0 items)"
    return
  fi

  echo "   $COUNT items — borrando..."
  echo "$ITEMS" | python3 -c "
import sys, json, subprocess, os
data = json.load(sys.stdin)
env = {**os.environ, 'MSYS_NO_PATHCONV': '1'}
for item in data['Items']:
    job_id = item['job_id']['S']
    key = json.dumps({'job_id':{'S':job_id}})
    subprocess.run(['aws','dynamodb','delete-item','--table-name','$JOBS_TABLE','--key',key,'--profile','$PROFILE','--region','$REGION'], check=True, env=env, capture_output=True)
    print(f'   x {job_id}')
print(f'   OK ({len(data[\"Items\"])} eliminados)')
"
}

# --- Ejecutar limpieza ---
delete_by_userid "$HISTORY_TABLE" "timestamp"
delete_by_userid "$ESTADOS_TABLE" "tarjeta_id"
delete_by_userid "$HASHES_TABLE" "file_hash"
delete_jobs

# --- S3 PDFs ---
echo ">> S3: s3://$PDFS_BUCKET/$USER_ID/"
S3_COUNT=$(aws s3 ls "s3://$PDFS_BUCKET/$USER_ID/" --recursive --profile "$PROFILE" --region "$REGION" 2>/dev/null | wc -l)
if [ "$S3_COUNT" = "0" ]; then
  echo "   (0 archivos)"
else
  echo "   $S3_COUNT archivos — borrando..."
  MSYS_NO_PATHCONV=1 aws s3 rm "s3://$PDFS_BUCKET/$USER_ID/" --recursive --profile "$PROFILE" --region "$REGION" 2>/dev/null
  echo "   OK"
fi

# --- AgentCore Memory (STM: sesiones+eventos, LTM: preferences/facts/summaries) ---
echo ">> AgentCore Memory: $MEMORY_ID (actor=$USER_ID)"
AWS_PROFILE="$PROFILE" AWS_REGION="$REGION" python3 -c "
import boto3, sys

memory_id = '$MEMORY_ID'
actor_id = '$USER_ID'
region = '$REGION'
profile = '$PROFILE'

session = boto3.Session(profile_name=profile, region_name=region)
client = session.client('bedrock-agentcore')

# --- 1. STM: Listar sesiones del actor y borrar eventos de cada una ---
stm_deleted = 0
try:
    sessions_resp = client.list_sessions(memoryId=memory_id, actorId=actor_id)
    sessions = sessions_resp.get('sessionSummaries', [])
    print(f'   STM: {len(sessions)} sesiones encontradas')
    for s in sessions:
        sid = s['sessionId']
        # Listar eventos de esta sesion
        try:
            events_resp = client.list_events(memoryId=memory_id, actorId=actor_id, sessionId=sid)
            events = events_resp.get('eventSummaries', [])
            for ev in events:
                eid = ev['eventId']
                try:
                    client.delete_event(memoryId=memory_id, actorId=actor_id, sessionId=sid, eventId=eid)
                    stm_deleted += 1
                except Exception as e:
                    print(f'   ! Error borrando evento {eid}: {e}')
        except Exception as e:
            print(f'   ! Error listando eventos de sesion {sid}: {e}')
    print(f'   STM: {stm_deleted} eventos eliminados')
except Exception as e:
    if 'not found' in str(e).lower() or 'ResourceNotFoundException' in str(e):
        print(f'   STM: (sin sesiones)')
    else:
        print(f'   STM: error listando sesiones: {e}')

# --- 2. LTM: Listar y borrar memory records por namespace ---
ltm_deleted = 0
namespaces = [
    f'/preferences/{actor_id}',
    f'/facts/{actor_id}',
    f'/summaries/{actor_id}',
]
for ns in namespaces:
    try:
        records_resp = client.list_memory_records(memoryId=memory_id, namespace=ns)
        records = records_resp.get('memoryRecordSummaries', [])
        if records:
            print(f'   LTM [{ns}]: {len(records)} records')
            for rec in records:
                rid = rec['memoryRecordId']
                try:
                    client.delete_memory_record(memoryId=memory_id, memoryRecordId=rid)
                    ltm_deleted += 1
                except Exception as e:
                    print(f'   ! Error borrando record {rid}: {e}')
        else:
            print(f'   LTM [{ns}]: (0 records)')
    except Exception as e:
        print(f'   LTM [{ns}]: error: {e}')
print(f'   LTM: {ltm_deleted} records eliminados')
print(f'   OK')
"

echo ""
echo "=== Limpieza completada para $USER_ID ==="
