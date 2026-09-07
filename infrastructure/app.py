#!/usr/bin/env python3
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
import os

import aws_cdk as cdk

from infrastructure.infrastructure_stack import InfrastructureStack
from infrastructure.analytics_stack import AnalyticsStack

CDK_ACCOUNT = os.environ.get("CDK_DEFAULT_ACCOUNT")
CDK_REGION = os.environ.get("CDK_DEFAULT_REGION")

if not CDK_ACCOUNT or not CDK_REGION:
    raise SystemExit(
        "Set CDK_DEFAULT_ACCOUNT and CDK_DEFAULT_REGION env vars, or run:\n"
        "  cdk deploy --profile YOUR_PROFILE"
    )

app = cdk.App()

# `stage` selects which stack to synthesize. The main application stack is the
# default, so `cdk deploy` needs no context. Pass `--context stage=analytics`
# to deploy the optional analytics stack instead.
stage = app.node.try_get_context("stage")

ALLOWED_STAGES = {"main", "analytics"}

if stage in (None, "", "main"):
    InfrastructureStack(
        app,
        "FinancialHealthStack",
        env=cdk.Environment(account=CDK_ACCOUNT, region=CDK_REGION),
    )
elif stage == "analytics":
    AnalyticsStack(
        app,
        "AnalyticsStack",
        env=cdk.Environment(account=CDK_ACCOUNT, region=CDK_REGION),
    )
else:
    raise SystemExit(
        f"Unknown stage '{stage}'. "
        f"Allowed values: {', '.join(sorted(ALLOWED_STAGES))}."
    )

app.synth()
