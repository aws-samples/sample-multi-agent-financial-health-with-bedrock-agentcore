# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
from aws_cdk import (
    Stack,
    RemovalPolicy,
    Duration,
    CfnResource,
    BundlingOptions,
    DockerImage,
    aws_s3 as s3,
    aws_s3_deployment as s3deploy,
    aws_cloudfront as cloudfront,
    aws_cloudfront_origins as origins,
    aws_kms as kms,
    aws_iam as iam,
    aws_lambda as lambda_,
    aws_apigateway as apigw,
    aws_dynamodb as dynamodb,
    aws_cognito as cognito,
    aws_bedrock as bedrock,
)
from constructs import Construct
import os
import sys
import subprocess
import jsii
from aws_cdk import ILocalBundling


@jsii.implements(ILocalBundling)
class _LocalBundling:
    """Fallback local bundling when Docker is not available."""

    def try_bundle(self, output_dir: str, *, image=None, command=None, **kwargs) -> bool:
        """Bundle agent code with Linux ARM64 dependencies for AgentCore Runtime."""
        source = os.path.join(os.path.dirname(__file__), "..", "..", "backend")
        import shutil

        # Install binary dependencies targeting Linux ARM64 (required by AgentCore Runtime).
        # The command and all arguments are static literals (no user/external input) and
        # pip is invoked via the current interpreter instead of resolving "pip3" from PATH,
        # so this subprocess call is not susceptible to untrusted-input execution.
        # Both manylinux baselines are accepted: AgentCore Runtime and the Lambda
        # python3.13 runtime are Amazon Linux 2023 based (glibc 2.34), so the newer
        # manylinux_2_28 tag is satisfied. Some packages (e.g. pyarrow >= 23) publish
        # ARM64 wheels only under manylinux_2_28, while others still ship the older
        # manylinux2014 baseline — pip accepts a wheel matching any listed platform.
        try:
            subprocess.run(  # nosemgrep: python.lang.security.audit.dangerous-subprocess-use-audit
                [sys.executable, "-m", "pip", "install", "-r", "requirements.txt", "-t", output_dir,
                 "--platform", "manylinux_2_28_aarch64",
                 "--platform", "manylinux2014_aarch64",
                 "--implementation", "cp", "--python-version", "3.13",
                 "--only-binary=:all:", "--quiet"],
                cwd=source, check=True, shell=False,
            )  # nosec B603 - static args, shell=False, trusted interpreter
        except subprocess.CalledProcessError:
            # Fallback for any dependency without an ARM64 wheel. Such a package is
            # pure Python by definition, so the platform/interpreter constraints are
            # dropped here — pip rejects --platform unless it is paired with
            # --only-binary=:all: or --no-deps.
            subprocess.run(  # nosemgrep: python.lang.security.audit.dangerous-subprocess-use-audit
                [sys.executable, "-m", "pip", "install", "-r", "requirements.txt", "-t", output_dir,
                 "--quiet"],
                cwd=source, check=True, shell=False,
            )  # nosec B603 - static args, shell=False, trusted interpreter

        # Remove __pycache__ and .pyc — incompatible bytecode breaks AgentCore Runtime
        for root, dirs, files in os.walk(output_dir):
            for d in dirs:
                if d == "__pycache__":
                    import shutil as _shutil
                    _shutil.rmtree(os.path.join(root, d))
            for f in files:
                if f.endswith(".pyc"):
                    os.remove(os.path.join(root, f))

        # Copy agent source files on top of dependencies
        excludes = {"__pycache__", ".venv", ".venv-test", "lambda", ".bedrock_agentcore.yaml"}
        for item in os.listdir(source):
            if item in excludes or item.startswith(".env") or item.endswith((".sh", ".pyc")):
                continue
            if item.startswith("setup-") or item == ".gitignore" or item == "pyproject.toml":
                continue
            src_path = os.path.join(source, item)
            dst_path = os.path.join(output_dir, item)
            if os.path.isdir(src_path):
                shutil.copytree(src_path, dst_path, dirs_exist_ok=True)
            else:
                shutil.copy2(src_path, dst_path)
        return True


class InfrastructureStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # KMS key para cifrado de AgentCore Memory
        memory_key = kms.Key(
            self, "FinancialHealthMemoryKey",
            description="KMS key for AgentCore Memory encryption",
            enable_key_rotation=True,
            removal_policy=RemovalPolicy.DESTROY,
        )

        # ── Bedrock Guardrail ──
        guardrail = bedrock.CfnGuardrail(
            self, "FinancialHealthGuardrail",
            name="financial-health-guardrail",
            description="Guardrail para el asistente financiero",
            blocked_input_messaging="Lo siento, no puedo procesar esa solicitud.",
            blocked_outputs_messaging="Lo siento, no puedo proporcionar esa información.",
            content_policy_config=bedrock.CfnGuardrail.ContentPolicyConfigProperty(
                filters_config=[
                    bedrock.CfnGuardrail.ContentFilterConfigProperty(type="VIOLENCE", input_strength="HIGH", output_strength="HIGH"),
                    bedrock.CfnGuardrail.ContentFilterConfigProperty(type="SEXUAL", input_strength="HIGH", output_strength="HIGH"),
                    bedrock.CfnGuardrail.ContentFilterConfigProperty(type="HATE", input_strength="HIGH", output_strength="HIGH"),
                    bedrock.CfnGuardrail.ContentFilterConfigProperty(type="INSULTS", input_strength="HIGH", output_strength="HIGH"),
                    bedrock.CfnGuardrail.ContentFilterConfigProperty(type="MISCONDUCT", input_strength="LOW", output_strength="LOW"),
                    bedrock.CfnGuardrail.ContentFilterConfigProperty(type="PROMPT_ATTACK", input_strength="NONE", output_strength="NONE"),
                ],
            ),
            sensitive_information_policy_config=bedrock.CfnGuardrail.SensitiveInformationPolicyConfigProperty(
                pii_entities_config=[
                    bedrock.CfnGuardrail.PiiEntityConfigProperty(type="CREDIT_DEBIT_CARD_NUMBER", action="ANONYMIZE"),
                    bedrock.CfnGuardrail.PiiEntityConfigProperty(type="EMAIL", action="ANONYMIZE"),
                    bedrock.CfnGuardrail.PiiEntityConfigProperty(type="PHONE", action="ANONYMIZE"),
                    bedrock.CfnGuardrail.PiiEntityConfigProperty(type="ADDRESS", action="ANONYMIZE"),
                ],
            ),
        )

        # ── AgentCore Memory ──
        agentcore_memory = CfnResource(
            self, "FinancialHealthMemory",
            type="AWS::BedrockAgentCore::Memory",
            properties={
                "Name": "financial_health_memory",
                "Description": "Memory - user preferences, facts and summaries",
                "EventExpiryDuration": 30,
                "EncryptionKeyArn": memory_key.key_arn,
                "MemoryStrategies": [
                    {
                        "UserPreferenceMemoryStrategy": {
                            "Name": "PreferenciasUsuario",
                            "NamespaceTemplates": ["/preferences/{actorId}"],
                        }
                    },
                    {
                        "SemanticMemoryStrategy": {
                            "Name": "DatosFinancieros",
                            "NamespaceTemplates": ["/facts/{actorId}"],
                        }
                    },
                    {
                        "SummaryMemoryStrategy": {
                            "Name": "ResumenSesion",
                            "NamespaceTemplates": ["/summaries/{actorId}/{sessionId}"],
                        }
                    },
                ],
            },
        )
        memory_id = agentcore_memory.get_att("MemoryId").to_string()

        # S3 bucket para frontend (build estático)
        frontend_bucket = s3.Bucket(
            self, "FinancialHealthFrontendBucket",
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            enforce_ssl=True,
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
        )

        # S3 bucket para PDFs de estados de cuenta (permanente)
        pdfs_bucket = s3.Bucket(
            self, "FinancialHealthPdfsBucket",
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            # Deny any non-HTTPS request (adds aws:SecureTransport=false deny policy),
            # so presigned-URL uploads/downloads must use TLS.
            enforce_ssl=True,
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
            cors=[
                # CORS allows any origin because uploads use short-lived presigned URLs
                # (generated server-side after Cognito auth). The presigned URL itself is
                # the access control — a leaked URL expires in <15 min. Restricting origin
                # here would break mobile/webview clients with no security gain.
                s3.CorsRule(
                    allowed_methods=[s3.HttpMethods.GET, s3.HttpMethods.PUT, s3.HttpMethods.POST, s3.HttpMethods.HEAD],
                    allowed_origins=["*"],
                    allowed_headers=["*"],
                    exposed_headers=["ETag", "x-amz-request-id", "x-amz-id-2"],
                    max_age=3000,
                )
            ],
        )

        # ---------------------------------------------------------------------
        # Cumplimiento / protección de datos (responsabilidad del desplegador)
        #
        # Las tablas y buckets definidos en este stack almacenan datos financieros
        # personales y datos relacionados con tarjetas de crédito: saldos, últimos
        # 4 dígitos, historial de transacciones y ratios de endeudamiento (DynamoDB),
        # además de estados de cuenta completos en PDF (S3).
        #
        # Antes de un despliegue en producción, evaluar:
        # - Alcance PCI-DSS: este proyecto NO almacena números de tarjeta completos
        #   (PAN) ni CVV. Si un despliegue derivado llegara a almacenarlos, entraría
        #   en alcance PCI-DSS y requeriría controles adicionales.
        # - GDPR y normativas locales de privacidad: base legal del tratamiento,
        #   minimización de datos y derechos del titular (acceso, rectificación,
        #   supresión) para usuarios en la UE u otras jurisdicciones equivalentes.
        # - Retención y eliminación: definir TTL o políticas de ciclo de vida. Este
        #   stack usa RemovalPolicy.DESTROY, apropiado solo para demos.
        # - Cifrado: las tablas usan claves gestionadas por AWS. Para producción,
        #   considerar CMK (KMS) con rotación y registro de auditoría.
        #
        # Modelo de responsabilidad compartida:
        #   https://aws.amazon.com/compliance/shared-responsibility-model/
        # Recursos de cumplimiento de AWS:
        #   https://aws.amazon.com/compliance/resources/
        # ---------------------------------------------------------------------

        # DynamoDB table para estados de cuenta
        estados_cuenta_table = dynamodb.Table(
            self, "FinancialHealthEstadosCuentaTable",
            partition_key=dynamodb.Attribute(
                name="usuario_id",
                type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="tarjeta_id",
                type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.DESTROY,
            encryption=dynamodb.TableEncryption.AWS_MANAGED,
            point_in_time_recovery=True,
        )

        # DynamoDB table para hashes de archivos (control de duplicados)
        file_hashes_table = dynamodb.Table(
            self, "FinancialHealthFileHashesTable",
            partition_key=dynamodb.Attribute(
                name="usuario_id",
                type=dynamodb.AttributeType.STRING,
            ),
            sort_key=dynamodb.Attribute(
                name="file_hash",
                type=dynamodb.AttributeType.STRING,
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.DESTROY,
        )

        # DynamoDB table para jobs async
        jobs_table = dynamodb.Table(
            self, "FinancialHealthJobsTable",
            partition_key=dynamodb.Attribute(
                name="job_id",
                type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.DESTROY,
        )

        # GSI para buscar último análisis completado por usuario
        jobs_table.add_global_secondary_index(
            index_name="usuario_id-completed_at-index",
            partition_key=dynamodb.Attribute(
                name="usuario_id",
                type=dynamodb.AttributeType.STRING,
            ),
            sort_key=dynamodb.Attribute(
                name="completed_at",
                type=dynamodb.AttributeType.NUMBER,
            ),
            projection_type=dynamodb.ProjectionType.ALL,
        )

        # Origin Access Control para CloudFront
        oac = cloudfront.S3OriginAccessControl(
            self, "FinancialHealthOAC",
            signing=cloudfront.Signing.SIGV4_NO_OVERRIDE,
        )

        # Security headers para CloudFront
        security_headers = cloudfront.ResponseHeadersPolicy(
            self, "FinancialHealthSecurityHeaders",
            response_headers_policy_name="FinancialHealthSecurityHeaders",
            security_headers_behavior=cloudfront.ResponseSecurityHeadersBehavior(
                strict_transport_security=cloudfront.ResponseHeadersStrictTransportSecurity(
                    access_control_max_age=Duration.days(365),
                    include_subdomains=True,
                    override=True,
                ),
                content_type_options=cloudfront.ResponseHeadersContentTypeOptions(override=True),
                frame_options=cloudfront.ResponseHeadersFrameOptions(
                    frame_option=cloudfront.HeadersFrameOption.DENY,
                    override=True,
                ),
                xss_protection=cloudfront.ResponseHeadersXSSProtection(
                    protection=True,
                    mode_block=True,
                    override=True,
                ),
                referrer_policy=cloudfront.ResponseHeadersReferrerPolicy(
                    referrer_policy=cloudfront.HeadersReferrerPolicy.STRICT_ORIGIN_WHEN_CROSS_ORIGIN,
                    override=True,
                ),
            ),
        )

        # CloudFront distribution para frontend
        distribution = cloudfront.Distribution(
            self, "FinancialHealthDistribution",
            default_behavior=cloudfront.BehaviorOptions(
                origin=origins.S3BucketOrigin(
                    frontend_bucket,
                    origin_access_control_id=oac.origin_access_control_id,
                ),
                viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                cache_policy=cloudfront.CachePolicy.CACHING_OPTIMIZED,
                response_headers_policy=security_headers,
            ),
            default_root_object="index.html",
            error_responses=[
                cloudfront.ErrorResponse(
                    http_status=404,
                    response_http_status=200,
                    response_page_path="/index.html",
                    ttl=Duration.minutes(5),
                ),
                cloudfront.ErrorResponse(
                    http_status=403,
                    response_http_status=200,
                    response_page_path="/index.html",
                    ttl=Duration.minutes(5),
                ),
            ],
        )

        # Permitir que CloudFront lea del bucket
        frontend_bucket.add_to_resource_policy(
            iam.PolicyStatement(
                actions=["s3:GetObject"],
                resources=[frontend_bucket.arn_for_objects("*")],
                principals=[iam.ServicePrincipal("cloudfront.amazonaws.com")],
                conditions={
                    "StringEquals": {
                        "AWS:SourceArn": f"arn:aws:cloudfront::{self.account}:distribution/{distribution.distribution_id}"
                    }
                },
            )
        )

        # Deploy frontend: el build se hace en el script deploy.sh con los outputs
        # de CDK (API URL, Cognito IDs) porque son tokens que no se resuelven en synth time.
        # Después del primer deploy, re-ejecutar: cdk deploy --hotswap para subir el build.
        import pathlib
        frontend_dist = pathlib.Path(__file__).parent.parent.parent / "frontend" / "dist"
        if frontend_dist.exists():
            s3deploy.BucketDeployment(
                self, "DeployFrontend",
                sources=[s3deploy.Source.asset("../frontend/dist")],
                destination_bucket=frontend_bucket,
                distribution=distribution,
                distribution_paths=["/*"],
            )

        # Guardrail y Runtime IDs (tokens de CloudFormation, se resuelven en deploy)
        guardrail_id = guardrail.attr_guardrail_id
        guardrail_version = "DRAFT"
        # agent_arn: placeholder que se actualiza post-deploy via SSM Parameter Store
        # Las Lambdas leen el ARN real de SSM en runtime, no de env vars
        agent_arn = f"arn:aws:bedrock-agentcore:{self.region}:{self.account}:runtime/*"

        # ── Lambda Worker: ejecuta AgentCore (async, hasta 10min) ──
        # AgentCore internamente ejecuta múltiples ciclos de agent loop (extractor,
        # análisis paralelo, consolidación). Cada ciclo toma 60-85s.
        # Con 5 ciclos típicos = ~370s, necesitamos margen.
        worker_lambda = lambda_.Function(
            self, "AgentWorkerFunction",
            runtime=lambda_.Runtime.PYTHON_3_13,
            handler="agent_worker.lambda_handler",
            code=lambda_.Code.from_asset("../backend/lambda"),
            timeout=Duration.seconds(600),
            memory_size=512,
            environment={
                "AGENT_ARN": agent_arn,
                "JOBS_TABLE_NAME": jobs_table.table_name,
                "MEMORY_ID": memory_id,
                "GUARDRAIL_ID": guardrail_id,
                "GUARDRAIL_VERSION": guardrail_version,
            },
        )

        # NOTE: InvokeAgentRuntime permission is granted AFTER the runtime is created,
        # scoped to the specific runtime ARN (see below) — avoids a runtime/* wildcard.
        worker_lambda.add_to_role_policy(
            iam.PolicyStatement(
                actions=["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"],
                resources=[
                    f"arn:aws:bedrock:{self.region}::foundation-model/anthropic.claude-*",
                    f"arn:aws:bedrock:{self.region}::foundation-model/us.anthropic.claude-*",
                ],
            )
        )
        jobs_table.grant_read_write_data(worker_lambda)
        pdfs_bucket.grant_read(worker_lambda)

        # ── Lambda Dispatcher: recibe request, crea job, invoca worker async ──
        invoke_lambda = lambda_.Function(
            self, "InvokeAgentFunction",
            runtime=lambda_.Runtime.PYTHON_3_13,
            handler="invoke_agent.lambda_handler",
            code=lambda_.Code.from_asset("../backend/lambda"),
            timeout=Duration.seconds(25),
            memory_size=256,
            environment={
                "AGENT_ARN": agent_arn,
                "JOBS_TABLE_NAME": jobs_table.table_name,
                "WORKER_FUNCTION_NAME": worker_lambda.function_name,
                "DYNAMODB_TABLE_NAME": estados_cuenta_table.table_name,
                "S3_PDFS_BUCKET": pdfs_bucket.bucket_name,
                "MEMORY_ID": memory_id,
                "GUARDRAIL_ID": guardrail_id,
                "GUARDRAIL_VERSION": guardrail_version,
            },
        )

        # Dispatcher puede invocar al worker async
        worker_lambda.grant_invoke(invoke_lambda)
        jobs_table.grant_read_write_data(invoke_lambda)
        estados_cuenta_table.grant_read_write_data(invoke_lambda)
        pdfs_bucket.grant_read_write(invoke_lambda)

        # NOTE: InvokeAgentRuntime granted below, scoped to the specific runtime ARN.
        invoke_lambda.add_to_role_policy(
            iam.PolicyStatement(
                actions=["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"],
                resources=[
                    f"arn:aws:bedrock:{self.region}::foundation-model/anthropic.claude-*",
                    f"arn:aws:bedrock:{self.region}::foundation-model/us.anthropic.claude-*",
                ],
            )
        )

        # ── Lambda para polling de jobs ──
        poll_lambda = lambda_.Function(
            self, "PollJobFunction",
            runtime=lambda_.Runtime.PYTHON_3_13,
            handler="poll_job.lambda_handler",
            code=lambda_.Code.from_asset("../backend/lambda"),
            timeout=Duration.seconds(10),
            memory_size=128,
            environment={
                "JOBS_TABLE_NAME": jobs_table.table_name,
            },
        )
        jobs_table.grant_read_data(poll_lambda)

        # ── API Gateway ──
        # CORS allows all origins because every endpoint requires a valid Cognito JWT.
        # The CloudFront distribution URL is not yet known at this point in the stack
        # (it depends on the API URL). The Cognito authorizer is the access-control
        # boundary — CORS headers alone do not grant data access.
        api = apigw.RestApi(
            self, "FinancialHealthApi",
            rest_api_name="Financial Health API",
            description="API del asistente financiero",
            default_cors_preflight_options=apigw.CorsOptions(
                allow_origins=apigw.Cors.ALL_ORIGINS,
                allow_methods=apigw.Cors.ALL_METHODS,
                allow_headers=["Content-Type", "Authorization"],
            ),
        )

        # Gateway responses para CORS en errores de autenticación
        api.add_gateway_response("GatewayResponse4XX",
            type=apigw.ResponseType.DEFAULT_4_XX,
            response_headers={
                "Access-Control-Allow-Origin": "'*'",
                "Access-Control-Allow-Headers": "'Content-Type,Authorization'",
                "Access-Control-Allow-Methods": "'OPTIONS,POST,GET,DELETE'",
            },
        )
        api.add_gateway_response("GatewayResponseUnauthorized",
            type=apigw.ResponseType.UNAUTHORIZED,
            response_headers={
                "Access-Control-Allow-Origin": "'*'",
                "Access-Control-Allow-Headers": "'Content-Type,Authorization'",
                "Access-Control-Allow-Methods": "'OPTIONS,POST,GET,DELETE'",
            },
        )

        # POST /invoke → dispatcher (crea job, retorna job_id)
        invoke_resource = api.root.add_resource("invoke")
        invoke_resource.add_method("POST", apigw.LambdaIntegration(invoke_lambda))

        # GET /job/{job_id} → polling
        job_resource = api.root.add_resource("job")
        job_id_resource = job_resource.add_resource("{job_id}")
        job_id_resource.add_method("GET", apigw.LambdaIntegration(poll_lambda))

        # Lambda para presigned URLs
        presigned_url_lambda = lambda_.Function(
            self, "PresignedUrlFunction",
            runtime=lambda_.Runtime.PYTHON_3_13,
            handler="generate_presigned_url.lambda_handler",
            code=lambda_.Code.from_asset("../backend/lambda"),
            timeout=Duration.seconds(10),
            memory_size=128,
            environment={
                "PDFS_BUCKET_NAME": pdfs_bucket.bucket_name,
            },
        )
        pdfs_bucket.grant_put(presigned_url_lambda)
        presigned_url_lambda.add_environment("HASHES_TABLE_NAME", file_hashes_table.table_name)
        file_hashes_table.grant_read_write_data(presigned_url_lambda)

        # POST /upload
        upload_resource = api.root.add_resource("upload")
        upload_resource.add_method("POST", apigw.LambdaIntegration(presigned_url_lambda))

        # ── Cognito User Pool ──
        user_pool = cognito.UserPool(
            self, "FinancialHealthUserPool",
            user_pool_name="financial-health-users",
            self_sign_up_enabled=False,
            sign_in_aliases=cognito.SignInAliases(email=True),
            auto_verify=cognito.AutoVerifiedAttrs(email=True),
            standard_attributes=cognito.StandardAttributes(
                email=cognito.StandardAttribute(required=True, mutable=True),
            ),
            custom_attributes={
                "country": cognito.StringAttribute(min_len=2, max_len=3, mutable=True),
                "currency": cognito.StringAttribute(min_len=2, max_len=5, mutable=True),
                "income": cognito.StringAttribute(min_len=0, max_len=20, mutable=True),
                "language": cognito.StringAttribute(min_len=2, max_len=5, mutable=True),
                "payment_behavior": cognito.StringAttribute(min_len=0, max_len=20, mutable=True),
            },
            password_policy=cognito.PasswordPolicy(
                min_length=8,
                require_lowercase=True,
                require_uppercase=True,
                require_digits=True,
                require_symbols=False,
            ),
            account_recovery=cognito.AccountRecovery.EMAIL_ONLY,
            removal_policy=RemovalPolicy.DESTROY,
        )

        user_pool_client = cognito.UserPoolClient(
            self, "FinancialHealthUserPoolClient",
            user_pool=user_pool,
            user_pool_client_name="financial-health-web-client",
            generate_secret=False,
            auth_flows=cognito.AuthFlow(
                user_srp=True,
                user_password=True,
            ),
            # email_verified must be readable, even though the app never uses it
            # directly. The Amplify Authenticator calls fetchUserAttributes() and,
            # when email_verified is absent from the client's read attributes,
            # treats the address as unverified and shows its "Account recovery
            # requires verified contact information" step on *every* sign-in --
            # even for a user whose email_verified is already true in Cognito.
            # It is read-only: Cognito rejects email_verified in write_attributes.
            read_attributes=cognito.ClientAttributes().with_custom_attributes(
                "country", "currency", "income", "language", "payment_behavior"
            ).with_standard_attributes(email=True, email_verified=True),
            write_attributes=cognito.ClientAttributes().with_custom_attributes(
                "country", "currency", "income", "language", "payment_behavior"
            ).with_standard_attributes(email=True),
        )

        # ── Cognito Authorizer para API Gateway ──
        cfn_authorizer = apigw.CfnAuthorizer(
            self, "FinancialHealthApiAuthorizer",
            rest_api_id=api.rest_api_id,
            name="FinancialHealthCognitoAuth",
            type="COGNITO_USER_POOLS",
            identity_source="method.request.header.Authorization",
            provider_arns=[user_pool.user_pool_arn],
        )
        # Apply authorizer to all non-OPTIONS methods
        for child in api.node.find_all():
            if isinstance(child, apigw.Method) and child.http_method != "OPTIONS":
                cfn_method = child.node.default_child
                cfn_method.add_property_override("AuthorizationType", "COGNITO_USER_POOLS")
                cfn_method.add_property_override("AuthorizerId", cfn_authorizer.ref)

        # ── DynamoDB: Historial financiero por usuario ──
        financial_history_table = dynamodb.Table(
            self, "FinancialHealthFinancialHistoryTable",
            partition_key=dynamodb.Attribute(
                name="usuario_id",
                type=dynamodb.AttributeType.STRING,
            ),
            sort_key=dynamodb.Attribute(
                name="timestamp",
                type=dynamodb.AttributeType.STRING,
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.DESTROY,
            point_in_time_recovery=True,
        )

        # Worker Lambda necesita escribir KPIs en historial
        financial_history_table.grant_write_data(worker_lambda)
        worker_lambda.add_environment(
            "FINANCIAL_HISTORY_TABLE_NAME", financial_history_table.table_name
        )

        # Worker Lambda necesita leer fecha_corte de estados de cuenta para el timestamp del snapshot
        estados_cuenta_table.grant_read_data(worker_lambda)
        worker_lambda.add_environment(
            "ESTADOS_TABLE_NAME", estados_cuenta_table.table_name
        )

        # ── Lambda para consultar historial financiero ──
        history_lambda = lambda_.Function(
            self, "GetFinancialHistoryFunction",
            runtime=lambda_.Runtime.PYTHON_3_13,
            handler="get_financial_history.lambda_handler",
            code=lambda_.Code.from_asset("../backend/lambda"),
            timeout=Duration.seconds(10),
            memory_size=128,
            environment={
                "FINANCIAL_HISTORY_TABLE_NAME": financial_history_table.table_name,
            },
        )
        financial_history_table.grant_read_data(history_lambda)

        # GET /history/{usuario_id}
        history_resource = api.root.add_resource("history")
        history_user_resource = history_resource.add_resource("{usuario_id}")
        history_user_resource.add_method("GET", apigw.LambdaIntegration(history_lambda))

        # ── Lambda para obtener último análisis de un usuario ──
        last_analysis_lambda = lambda_.Function(
            self, "GetLastAnalysisFunction",
            runtime=lambda_.Runtime.PYTHON_3_13,
            handler="get_last_analysis.lambda_handler",
            code=lambda_.Code.from_asset("../backend/lambda"),
            timeout=Duration.seconds(10),
            memory_size=128,
            environment={
                "JOBS_TABLE_NAME": jobs_table.table_name,
            },
        )
        jobs_table.grant_read_data(last_analysis_lambda)

        # GET /last-analysis/{usuario_id}
        last_analysis_resource = api.root.add_resource("last-analysis")
        last_analysis_user_resource = last_analysis_resource.add_resource("{usuario_id}")
        last_analysis_user_resource.add_method("GET", apigw.LambdaIntegration(last_analysis_lambda))

        # ── Lambda para obtener documentos y hashes de un usuario ──
        user_documents_lambda = lambda_.Function(
            self, "GetUserDocumentsFunction",
            runtime=lambda_.Runtime.PYTHON_3_13,
            handler="get_user_documents.lambda_handler",
            code=lambda_.Code.from_asset("../backend/lambda"),
            timeout=Duration.seconds(10),
            memory_size=128,
            environment={
                "DYNAMODB_TABLE_NAME": estados_cuenta_table.table_name,
                "HASHES_TABLE_NAME": file_hashes_table.table_name,
                "PDFS_BUCKET_NAME": pdfs_bucket.bucket_name,
            },
        )
        estados_cuenta_table.grant_read_data(user_documents_lambda)
        file_hashes_table.grant_read_data(user_documents_lambda)

        # GET /user-documents/{usuario_id}
        user_docs_resource = api.root.add_resource("user-documents")
        user_docs_user_resource = user_docs_resource.add_resource("{usuario_id}")
        user_docs_user_resource.add_method("GET", apigw.LambdaIntegration(user_documents_lambda))

        # ── Lambda para eliminar un documento del usuario ──
        delete_document_lambda = lambda_.Function(
            self, "DeleteDocumentFunction",
            runtime=lambda_.Runtime.PYTHON_3_13,
            handler="delete_document.lambda_handler",
            code=lambda_.Code.from_asset("../backend/lambda"),
            timeout=Duration.seconds(15),
            memory_size=128,
            environment={
                "HASHES_TABLE_NAME": file_hashes_table.table_name,
                "ESTADOS_TABLE_NAME": estados_cuenta_table.table_name,
                "JOBS_TABLE_NAME": jobs_table.table_name,
                "PDFS_BUCKET_NAME": pdfs_bucket.bucket_name,
            },
        )
        file_hashes_table.grant_read_write_data(delete_document_lambda)
        estados_cuenta_table.grant_read_write_data(delete_document_lambda)
        jobs_table.grant_read_write_data(delete_document_lambda)
        pdfs_bucket.grant_delete(delete_document_lambda)

        # DELETE /documents/{usuario_id}/{file_hash}
        documents_resource = api.root.add_resource("documents")
        documents_user_resource = documents_resource.add_resource("{usuario_id}")
        documents_hash_resource = documents_user_resource.add_resource("{file_hash}")
        documents_hash_resource.add_method("DELETE", apigw.LambdaIntegration(delete_document_lambda))

        # ── CORS: Inject CloudFront URL into all Lambdas for origin restriction ──
        cloudfront_url = f"https://{distribution.distribution_domain_name}"
        for fn in [invoke_lambda, poll_lambda, presigned_url_lambda,
                   history_lambda, last_analysis_lambda, user_documents_lambda, delete_document_lambda]:
            fn.add_environment("CLOUDFRONT_URL", cloudfront_url)

        # ── AgentCore Runtime: IAM Role ──
        from aws_cdk import aws_bedrockagentcore as bedrockagentcore

        agentcore_role = iam.Role(
            self, "FinancialHealthAgentCoreRole",
            assumed_by=iam.ServicePrincipal("bedrock-agentcore.amazonaws.com"),
            description="Execution role for the AgentCore Runtime",
            inline_policies={
                "BedrockAccess": iam.PolicyDocument(statements=[
                    iam.PolicyStatement(
                        actions=["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"],
                        # Cross-region inference profiles (us.anthropic.claude-*) route to the
                        # US geo regions, so foundation-model access is scoped to those specific
                        # regions instead of an all-regions "*" wildcard (least privilege).
                        resources=[
                            f"arn:aws:bedrock:{self.region}::foundation-model/anthropic.claude-*",
                            f"arn:aws:bedrock:{self.region}::foundation-model/us.anthropic.claude-*",
                            f"arn:aws:bedrock:{self.region}:{self.account}:inference-profile/us.anthropic.claude-*",
                            "arn:aws:bedrock:us-east-1::foundation-model/anthropic.claude-*",
                            "arn:aws:bedrock:us-east-2::foundation-model/anthropic.claude-*",
                            "arn:aws:bedrock:us-west-2::foundation-model/anthropic.claude-*",
                        ],
                    ),
                    iam.PolicyStatement(
                        actions=["bedrock:ApplyGuardrail"],
                        # Scoped to this stack's guardrail only, not every guardrail in the account.
                        resources=[guardrail.attr_guardrail_arn],
                    ),
                ]),
                "DynamoDBAccess": iam.PolicyDocument(statements=[
                    iam.PolicyStatement(
                        # No dynamodb:Scan — the agent reads by usuario_id (Query) and PK (GetItem).
                        # Full-table Scan runs only in the export Lambda (separate role).
                        actions=["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:Query", "dynamodb:UpdateItem"],
                        resources=[
                            estados_cuenta_table.table_arn,
                            f"{estados_cuenta_table.table_arn}/index/*",
                            file_hashes_table.table_arn,
                            f"{file_hashes_table.table_arn}/index/*",
                        ],
                    ),
                ]),
                "S3Access": iam.PolicyDocument(statements=[
                    iam.PolicyStatement(
                        actions=["s3:GetObject", "s3:PutObject", "s3:ListBucket"],
                        resources=[pdfs_bucket.bucket_arn, f"{pdfs_bucket.bucket_arn}/*"],
                    ),
                ]),
                "SSMAccess": iam.PolicyDocument(statements=[
                    iam.PolicyStatement(
                        # GetParameter para lecturas puntuales; GetParametersByPath
                        # porque el entrypoint carga toda la config de /financial-health/ en
                        # una sola llamada. Sin GetParametersByPath, esa carga falla
                        # con AccessDenied y TODAS las env vars quedan vacías, lo que
                        # desactiva en silencio la persistencia en DynamoDB, el
                        # guardrail, AgentCore Memory y la detección de duplicados.
                        actions=["ssm:GetParameter", "ssm:GetParameters", "ssm:GetParametersByPath"],
                        # GetParametersByPath se evalúa contra el ARN del path base
                        # (.../parameter/financial-health), no solo contra los parámetros hijos.
                        resources=[
                            f"arn:aws:ssm:{self.region}:{self.account}:parameter/financial-health",
                            f"arn:aws:ssm:{self.region}:{self.account}:parameter/financial-health/*",
                        ],
                    ),
                ]),
                "MemoryAccess": iam.PolicyDocument(statements=[
                    iam.PolicyStatement(
                        actions=[
                            "bedrock-agentcore:GetMemory",
                            "bedrock-agentcore:SearchMemory",
                            "bedrock-agentcore:CreateMemoryEvent",
                            "bedrock-agentcore:ListMemoryEvents",
                        ],
                        resources=[agentcore_memory.ref],
                    ),
                ]),
                "KMSAccess": iam.PolicyDocument(statements=[
                    iam.PolicyStatement(
                        actions=["kms:Decrypt", "kms:GenerateDataKey"],
                        resources=[memory_key.key_arn],
                    ),
                ]),
            },
        )

        # ── AgentCore Runtime: código del agente como S3 Asset ──
        from aws_cdk import aws_s3_assets as s3_assets, AssetHashType

        agent_code_asset = s3_assets.Asset(
            self, "FinancialHealthAgentCodeAsset",
            path=os.path.join(os.path.dirname(__file__), "..", "..", "backend"),
            exclude=["__pycache__", "*.pyc", ".venv", ".env*", "lambda/",
                     "*.sh", "setup-*.py", ".bedrock_agentcore*",
                     ".gitignore", "pyproject.toml"],
            asset_hash_type=AssetHashType.OUTPUT,
            bundling=BundlingOptions(
                image=DockerImage.from_registry("public.ecr.aws/lambda/python:3.13"),
                command=["bash", "-c",
                         "pip install -r requirements.txt -t /asset-output "
                         "--platform manylinux_2_28_aarch64 "
                         "--platform manylinux2014_aarch64 --implementation cp "
                         "--python-version 3.13 --only-binary=:all: --quiet && "
                         "cp -r . /asset-output && "
                         "find /asset-output -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null; true"],
                local=_LocalBundling(),
            ),
        )

        # Grant AgentCore service read access to the asset
        agent_code_asset.grant_read(agentcore_role)

        # ── AgentCore Runtime ──
        agentcore_runtime = bedrockagentcore.CfnRuntime(
            self, "FinancialHealthRuntime",
            agent_runtime_name="financial_health_orquestador",
            agent_runtime_artifact=bedrockagentcore.CfnRuntime.AgentRuntimeArtifactProperty(
                code_configuration=bedrockagentcore.CfnRuntime.CodeConfigurationProperty(
                    code=bedrockagentcore.CfnRuntime.CodeProperty(
                        s3=bedrockagentcore.CfnRuntime.S3LocationProperty(
                            bucket=agent_code_asset.s3_bucket_name,
                            prefix=agent_code_asset.s3_object_key,
                        )
                    ),
                    entry_point=["agentcore_entrypoint.py"],
                    runtime="PYTHON_3_13",
                )
            ),
            network_configuration=bedrockagentcore.CfnRuntime.NetworkConfigurationProperty(
                network_mode="PUBLIC",
            ),
            role_arn=agentcore_role.role_arn,
            description="Asistente financiero multi-agente",
            environment_variables={
                "AWS_REGION": self.region,
            },
        )

        # ── AgentCore Runtime Endpoint (required to invoke the runtime) ──
        agentcore_endpoint = bedrockagentcore.CfnRuntimeEndpoint(
            self, "FinancialHealthRuntimeEndpoint",
            agent_runtime_id=agentcore_runtime.attr_agent_runtime_id,
            name="default",
            description="Default endpoint for the agent",
        )

        # Update Lambda env vars with the real Runtime ARN (resolved at deploy time)
        worker_lambda.add_environment("AGENT_ARN", agentcore_runtime.attr_agent_runtime_arn)
        invoke_lambda.add_environment("AGENT_ARN", agentcore_runtime.attr_agent_runtime_arn)

        # Grant InvokeAgentRuntime scoped to THIS runtime only (least privilege),
        # now that the runtime ARN is known. Replaces the earlier runtime/* wildcard.
        _runtime_arn = agentcore_runtime.attr_agent_runtime_arn
        for _fn in (worker_lambda, invoke_lambda):
            _fn.add_to_role_policy(
                iam.PolicyStatement(
                    actions=["bedrock-agentcore:InvokeAgentRuntime"],
                    resources=[_runtime_arn, f"{_runtime_arn}/*"],
                )
            )

        # ── SSM Parameter Store: IDs de recursos para AgentCore Runtime ──
        from aws_cdk import aws_ssm as ssm

        ssm.StringParameter(
            self, "SsmDynamoDbTableName",
            parameter_name="/financial-health/dynamodb-table-name",
            string_value=estados_cuenta_table.table_name,
            description="DynamoDB table name for estados de cuenta",
        )
        ssm.StringParameter(
            self, "SsmS3PdfsBucket",
            parameter_name="/financial-health/s3-pdfs-bucket",
            string_value=pdfs_bucket.bucket_name,
            description="S3 bucket for temporary PDFs",
        )
        ssm.StringParameter(
            self, "SsmHashesTableName",
            parameter_name="/financial-health/hashes-table-name",
            string_value=file_hashes_table.table_name,
            description="DynamoDB table name for file hashes",
        )
        ssm.StringParameter(
            self, "SsmGuardrailId",
            parameter_name="/financial-health/guardrail-id",
            string_value=guardrail_id,
            description="Bedrock Guardrail ID",
        )
        ssm.StringParameter(
            self, "SsmMemoryId",
            parameter_name="/financial-health/memory-id",
            string_value=memory_id,
            description="AgentCore Memory ID",
        )
        ssm.StringParameter(
            self, "SsmApiUrl",
            parameter_name="/financial-health/api-url",
            string_value=api.url,
            description="API Gateway URL",
        )
        ssm.StringParameter(
            self, "SsmUserPoolId",
            parameter_name="/financial-health/user-pool-id",
            string_value=user_pool.user_pool_id,
            description="Cognito User Pool ID",
        )
        ssm.StringParameter(
            self, "SsmUserPoolClientId",
            parameter_name="/financial-health/user-pool-client-id",
            string_value=user_pool_client.user_pool_client_id,
            description="Cognito User Pool Client ID",
        )

        # Outputs
        from aws_cdk import CfnOutput
        CfnOutput(self, "ApiUrl", value=api.url, description="API Gateway URL")
        CfnOutput(self, "UserPoolId", value=user_pool.user_pool_id, description="Cognito User Pool ID")
        CfnOutput(self, "UserPoolClientId", value=user_pool_client.user_pool_client_id, description="Cognito User Pool Client ID")
        CfnOutput(self, "PdfsBucketName", value=pdfs_bucket.bucket_name, description="S3 Bucket for PDFs")
        CfnOutput(self, "CloudFrontUrl", value=f"https://{distribution.distribution_domain_name}", description="CloudFront URL")
        CfnOutput(self, "FrontendBucketName", value=frontend_bucket.bucket_name, description="Frontend S3 Bucket")
        CfnOutput(self, "DistributionId", value=distribution.distribution_id, description="CloudFront Distribution ID")
        CfnOutput(self, "AgentRuntimeArn", value=agentcore_runtime.attr_agent_runtime_arn, description="AgentCore Runtime ARN")
        CfnOutput(self, "FinancialHistoryTableName", value=financial_history_table.table_name, description="Financial History DynamoDB Table")
        CfnOutput(self, "EstadosCuentaTableName", value=estados_cuenta_table.table_name, description="Estados de Cuenta DynamoDB Table")
