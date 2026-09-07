#!/bin/bash
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
# =============================================================
# Multi-agent financial health analysis — One-command deploy (Full CDK)
# =============================================================
# Usage:
#   export AWS_REGION=us-east-2
#   export AWS_PROFILE=my-profile    # optional, defaults to 'default'
#   ./deploy.sh
#
# For fast iteration (Lambda-only changes, ~5s):
#   cd infrastructure && cdk deploy FinancialHealthStack --hotswap
#
# Prerequisites:
#   - AWS CLI configured with credentials
#   - Node.js 18+ and npm
#   - Python 3.13+ with pip
#   - CDK CLI v2 (pinned): npm install -g aws-cdk@2.1136.0
#   - Docker (for bundling Python dependencies)
#   - Access to Amazon Bedrock (Claude Sonnet 4, Claude 3.5 Haiku)
# =============================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROFILE="${AWS_PROFILE:-default}"
REGION="${AWS_REGION:?ERROR: Set AWS_REGION (e.g. export AWS_REGION=us-east-2)}"
STACK_NAME="FinancialHealthStack"
OUTPUTS_FILE="$SCRIPT_DIR/cdk-outputs.json"

export AWS_PROFILE="$PROFILE"
export AWS_REGION="$REGION"
export CDK_DEFAULT_ACCOUNT=""
export CDK_DEFAULT_REGION="$REGION"

# ── Step 0: Validate prerequisites, credentials, and Bedrock access ──
echo ""
echo "[0/5] Validating prerequisites..."

# Check required tools
MISSING=""
command -v node &>/dev/null || MISSING="$MISSING node"
command -v npm &>/dev/null || MISSING="$MISSING npm"
command -v python3 &>/dev/null || MISSING="$MISSING python3"
command -v aws &>/dev/null || MISSING="$MISSING aws-cli"
command -v cdk &>/dev/null || MISSING="$MISSING cdk(npm install -g aws-cdk@2.1136.0)"

if [ -n "$MISSING" ]; then
    echo "ERROR: Missing required tools:$MISSING"
    exit 1
fi

# Verify CDK CLI is v2+
CDK_VERSION=$(cdk --version 2>/dev/null | grep -oE '^[0-9]+' || echo "0")
if [ "$CDK_VERSION" -lt 2 ]; then
    echo "ERROR: CDK CLI v2+ required (found v$CDK_VERSION). Run: npm install -g aws-cdk@2.1136.0"
    exit 1
fi

# Validate AWS credentials
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text --profile "$PROFILE" 2>/dev/null)
if [ -z "$ACCOUNT_ID" ]; then
    echo "ERROR: Could not resolve AWS Account ID. Check AWS_PROFILE and credentials."
    exit 1
fi
export CDK_DEFAULT_ACCOUNT="$ACCOUNT_ID"

# Validate Bedrock models exist in region
MODELS_OK=true
for MODEL in "anthropic.claude-sonnet-4-5-20250929-v1:0" "anthropic.claude-haiku-4-5-20251001-v1:0"; do
    EXISTS=$(aws bedrock get-foundation-model \
        --model-identifier "$MODEL" --region "$REGION" --profile "$PROFILE" \
        --query "modelDetails.modelId" --output text 2>/dev/null || echo "NOT_FOUND")
    if [ "$EXISTS" = "NOT_FOUND" ]; then
        echo "  ⚠️  Model $MODEL not available in $REGION"
        MODELS_OK=false
    fi
done
if [ "$MODELS_OK" = false ]; then
    echo "ERROR: Required Bedrock models not available in $REGION."
    exit 1
fi

# Check Docker availability
if ! command -v docker &>/dev/null || ! docker info &>/dev/null 2>&1; then
    echo "  ⚠️  Docker not running — using local pip for bundling (may not match linux/arm64)"
fi

echo "  ✓ All prerequisites OK"
echo "  ✓ Credentials OK (Account: $ACCOUNT_ID)"
echo "  ✓ Bedrock models accessible"

echo ""
echo "========================================="
echo "  Full CDK Deploy"
echo "  Region:  $REGION"
echo "  Account: $ACCOUNT_ID"
echo "  Profile: $PROFILE"
echo "========================================="

# ── Step 1: Install dependencies (parallel) ──
echo ""
echo "[1/5] Installing dependencies (CDK + frontend in parallel)..."

# CDK Python deps and frontend npm install run in parallel
(cd "$SCRIPT_DIR/infrastructure" && python3 -m venv .venv 2>/dev/null || true
 cd "$SCRIPT_DIR/infrastructure" && .venv/bin/pip install -q -r requirements.txt 2>/dev/null || \
    pip3 install -q -r requirements.txt) &
PID_CDK=$!

# Use `npm ci` exclusively so installs honor package-lock.json (reproducible,
# pinned). No `npm install` fallback — a missing/stale lockfile should fail loudly.
(cd "$SCRIPT_DIR/frontend" && npm ci --silent) &
PID_NPM=$!

wait $PID_CDK || { echo "ERROR: CDK dependencies failed"; exit 1; }
wait $PID_NPM || { echo "ERROR: Frontend dependencies failed"; exit 1; }
echo "  ✓ Dependencies installed"

# ── Step 2: CDK Bootstrap ──
echo ""
echo "[2/5] CDK bootstrap..."
BOOTSTRAP_EXISTS=$(aws cloudformation describe-stacks \
    --stack-name CDKToolkit --region "$REGION" --profile "$PROFILE" \
    --query "Stacks[0].StackStatus" --output text 2>/dev/null || echo "NOT_FOUND")

if [ "$BOOTSTRAP_EXISTS" = "NOT_FOUND" ]; then
    echo "  Bootstrapping CDK in $REGION..."
    npx cdk bootstrap "aws://$ACCOUNT_ID/$REGION" --profile "$PROFILE"
else
    echo "  ✓ Already bootstrapped"
fi

# ── Step 3: CDK Diff (show what will change) ──
echo ""
echo "[3/5] Checking changes (cdk diff)..."
(cd "$SCRIPT_DIR/infrastructure" && cdk diff "$STACK_NAME" \
    --profile "$PROFILE" 2>&1 | head -40) || true

# ── Step 4: Deploy CDK Stack ──
echo ""
echo "[4/5] Deploying CDK stack (Guardrail + Memory + Runtime + infra)..."
(cd "$SCRIPT_DIR/infrastructure" && cdk deploy "$STACK_NAME" \
    --profile "$PROFILE" \
    --require-approval never \
    --outputs-file "$OUTPUTS_FILE")

# ── Step 5: Build and deploy frontend ──
echo ""
echo "[5/5] Building and deploying frontend..."

# Parse CDK outputs
eval "$(python3 -c "
import json
with open('$OUTPUTS_FILE') as f:
    stack = json.load(f).get('$STACK_NAME', {})
mapping = {
    'ApiUrl': 'CDK_API_URL', 'UserPoolId': 'CDK_USER_POOL_ID',
    'UserPoolClientId': 'CDK_USER_POOL_CLIENT_ID', 'PdfsBucketName': 'CDK_PDFS_BUCKET',
    'CloudFrontUrl': 'CDK_CLOUDFRONT_URL', 'EstadosCuentaTableName': 'CDK_ESTADOS_TABLE',
    'FinancialHistoryTableName': 'CDK_HISTORY_TABLE',
    'FrontendBucketName': 'CDK_FRONTEND_BUCKET', 'DistributionId': 'CDK_DISTRIBUTION_ID',
    'AgentRuntimeArn': 'CDK_AGENT_ARN',
}
for k, v in stack.items():
    for suffix, var in mapping.items():
        if suffix in k:
            print(f'export {var}=\"{v}\"')
")"

# Generate frontend/.env and build
cat > "$SCRIPT_DIR/frontend/.env" <<EOF
VITE_API_URL=${CDK_API_URL}
VITE_USER_POOL_ID=${CDK_USER_POOL_ID}
VITE_USER_POOL_CLIENT_ID=${CDK_USER_POOL_CLIENT_ID}
EOF

(cd "$SCRIPT_DIR/frontend" && npm run build)

# Re-deploy to upload frontend/dist via CDK BucketDeployment
echo "  Uploading frontend via CDK..."
(cd "$SCRIPT_DIR/infrastructure" && PATH=".venv/bin:$PATH" cdk deploy "$STACK_NAME" \
    --profile "$PROFILE" --require-approval never \
    --outputs-file "$OUTPUTS_FILE" 2>&1 | grep -E "(✅|❌)")

echo ""
echo "========================================="
echo "  ✅ DEPLOY COMPLETE"
echo "========================================="
echo ""
echo "  Region:      $REGION"
echo "  Account:     $ACCOUNT_ID"
echo "  API Gateway: ${CDK_API_URL}"
echo "  CloudFront:  ${CDK_CLOUDFRONT_URL}"
echo "  Agent ARN:   ${CDK_AGENT_ARN}"
echo ""
echo "  Frontend:    ${CDK_CLOUDFRONT_URL}"
echo ""
echo "  Test:"
echo "    curl -X POST ${CDK_API_URL}invoke \\"
echo "      -H 'Content-Type: application/json' \\"
echo "      -d '{\"prompt\":\"hola\",\"usuario_id\":\"test\"}'"
echo ""
echo "  Fast iteration (Lambda changes only, ~5s):"
echo "    cd infrastructure && cdk deploy $STACK_NAME --hotswap"
echo ""
echo "  Destroy (removes ALL resources):"
echo "    cd infrastructure && cdk destroy $STACK_NAME"
echo "========================================="
