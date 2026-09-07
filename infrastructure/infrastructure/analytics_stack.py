# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""
Analytics Stack — S3 DataLake + Glue Catalog + Athena (sin QuickSight).

Exporta datos de DynamoDB a Parquet particionado diariamente.
Athena consulta los datos via Glue Data Catalog.

Cumplimiento / protección de datos:
- El bucket del datalake usa cifrado SSE-S3 (AES-256) en reposo.
- El acceso está restringido por IAM al rol de exportación y al workgroup de Athena.
- Los datos exportados contienen información financiera personal (ingresos, saldos,
  transacciones). Para un despliegue en producción, considerar: cifrado con CMK (KMS),
  políticas de retención/eliminación, controles de acceso a nivel de columna (Lake
  Formation), y evaluación de cumplimiento PCI-DSS si el alcance incluye datos de
  tarjetas completas.
"""

from aws_cdk import (
    Stack,
    RemovalPolicy,
    Duration,
    CfnOutput,
    aws_s3 as s3,
    aws_glue as glue,
    aws_athena as athena,
    aws_lambda as lambda_,
    aws_iam as iam,
    aws_events as events,
    aws_events_targets as targets,
    aws_logs as logs,
)
from constructs import Construct


class AnalyticsStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # ── S3: DataLake bucket ──
        datalake_bucket = s3.Bucket(
            self, "FinancialHealthDataLakeBucket",
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            enforce_ssl=True,
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
            lifecycle_rules=[
                s3.LifecycleRule(
                    id="TransitionToIA",
                    transitions=[
                        s3.Transition(
                            storage_class=s3.StorageClass.INFREQUENT_ACCESS,
                            transition_after=Duration.days(90),
                        )
                    ],
                )
            ],
        )

        # ── S3: Athena query results ──
        athena_results_bucket = s3.Bucket(
            self, "FinancialHealthAthenaResultsBucket",
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            enforce_ssl=True,
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
            lifecycle_rules=[
                s3.LifecycleRule(
                    id="DeleteResultsAfter30Days",
                    expiration=Duration.days(30),
                )
            ],
        )

        # ── Glue Database ──
        glue.CfnDatabase(
            self, "FinancialHealthAnalyticsDatabase",
            catalog_id=self.account,
            database_input=glue.CfnDatabase.DatabaseInputProperty(
                name="financial_health_analytics",
                description="Base de datos analítica - estados de cuenta y perfiles de usuario",
            ),
        )

        # ── Glue Table (Parquet, particionado por anio/mes) ──
        columns = [
            ("usuario_id", "string", "ID del usuario"),
            ("ingreso_mensual", "double", "Ingreso mensual en soles"),
            ("presupuesto_deudas", "double", "Presupuesto mensual para deudas en soles"),
            ("tarjeta_id", "string", "ID de la tarjeta (banco_ultimos4)"),
            ("banco", "string", "Nombre del banco o retailer"),
            ("tipo", "string", "Tipo: bancaria o retail"),
            ("ultimos_4_digitos", "string", "Últimos 4 dígitos de la tarjeta"),
            ("saldo", "double", "Saldo total en soles"),
            ("tcea", "double", "TCEA en porcentaje"),
            ("pago_minimo", "double", "Pago mínimo mensual en soles"),
            ("fecha_corte", "string", "Fecha de corte del estado de cuenta"),
            ("num_movimientos", "int", "Cantidad de movimientos en el período"),
            ("total_movimientos", "double", "Suma total de movimientos en soles"),
            ("ratio_deuda_ingreso", "double", "Ratio deuda/ingreso"),
            ("interes_mensual_estimado", "double", "Interés mensual estimado en soles"),
            ("semaforo", "string", "Semáforo de salud: verde, amarillo, rojo"),
            ("fecha_exportacion", "timestamp", "Fecha de exportación al data lake"),
        ]

        glue.CfnTable(
            self, "FinancialHealthAnalyticsTable",
            catalog_id=self.account,
            database_name="financial_health_analytics",
            table_input=glue.CfnTable.TableInputProperty(
                name="estados_cuenta_perfil",
                description="Tabla analítica unificada: estados de cuenta con perfil de usuario",
                table_type="EXTERNAL_TABLE",
                parameters={
                    "classification": "parquet",
                    "compressionType": "snappy",
                    "typeOfData": "file",
                },
                partition_keys=[
                    glue.CfnTable.ColumnProperty(name="anio", type="string", comment="Año de exportación"),
                    glue.CfnTable.ColumnProperty(name="mes", type="string", comment="Mes de exportación"),
                ],
                storage_descriptor=glue.CfnTable.StorageDescriptorProperty(
                    columns=[
                        glue.CfnTable.ColumnProperty(name=n, type=t, comment=c)
                        for n, t, c in columns
                    ],
                    location=f"s3://{datalake_bucket.bucket_name}/analytics/estados_cuenta_perfil/",
                    input_format="org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat",
                    output_format="org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat",
                    serde_info=glue.CfnTable.SerdeInfoProperty(
                        serialization_library="org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe",
                        parameters={"serialization.format": "1"},
                    ),
                ),
            ),
        )

        # ── Athena WorkGroup ──
        athena.CfnWorkGroup(
            self, "FinancialHealthAthenaWorkgroup",
            name="financial-health-analytics",
            description="Workgroup para consultas analíticas",
            state="ENABLED",
            work_group_configuration=athena.CfnWorkGroup.WorkGroupConfigurationProperty(
                enforce_work_group_configuration=True,
                publish_cloud_watch_metrics_enabled=True,
                bytes_scanned_cutoff_per_query=1_073_741_824,  # 1 GB
                result_configuration=athena.CfnWorkGroup.ResultConfigurationProperty(
                    output_location=f"s3://{athena_results_bucket.bucket_name}/query-results/",
                    encryption_configuration=athena.CfnWorkGroup.EncryptionConfigurationProperty(
                        encryption_option="SSE_S3",
                    ),
                ),
            ),
        )

        # ── Lambda: Export DynamoDB → S3 Parquet ──
        # Tabla DynamoDB del stack principal — recibida como parámetro del app
        estados_cuenta_table_name = self.node.try_get_context("estados_cuenta_table") or "PENDING"

        export_fn = lambda_.Function(
            self, "FinancialHealthExportToDataLakeFunction",
            runtime=lambda_.Runtime.PYTHON_3_13,
            handler="export_to_datalake.lambda_handler",
            code=lambda_.Code.from_asset("../backend/lambda"),
            timeout=Duration.seconds(120),
            memory_size=512,
            layers=[
                lambda_.LayerVersion.from_layer_version_arn(
                    self, "PandasLayer",
                    f"arn:aws:lambda:{self.region}:336392948345:layer:AWSSDKPandas-Python313:1"  # AWS managed layer account,
                ),
            ],
            environment={
                "DATA_LAKE_BUCKET": datalake_bucket.bucket_name,
                "ESTADOS_CUENTA_TABLE": estados_cuenta_table_name,
            },
            log_retention=logs.RetentionDays.ONE_MONTH,
        )

        # Permisos: leer DynamoDB + escribir S3
        export_fn.add_to_role_policy(
            iam.PolicyStatement(
                actions=["dynamodb:Scan", "dynamodb:GetItem", "dynamodb:Query"],
                resources=[
                    f"arn:aws:dynamodb:{self.region}:{self.account}:table/{estados_cuenta_table_name}",
                ],
            )
        )
        datalake_bucket.grant_write(export_fn)

        # ── EventBridge: export diario a las 2 AM UTC ──
        rule = events.Rule(
            self, "FinancialHealthDailyExportRule",
            description="Exportación diaria de DynamoDB a S3 data lake",
            schedule=events.Schedule.cron(hour="2", minute="0"),
        )
        rule.add_target(targets.LambdaFunction(export_fn))

        # ── Outputs ──
        CfnOutput(self, "DataLakeBucketName", value=datalake_bucket.bucket_name)
        CfnOutput(self, "GlueDatabaseName", value="financial_health_analytics")
        CfnOutput(self, "AthenaWorkgroupName", value="financial-health-analytics")
