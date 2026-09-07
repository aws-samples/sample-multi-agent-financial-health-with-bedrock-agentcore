# Threat model

`threatmodel.tc.json` holds the threat model for this project. It uses the
[Threat Composer](https://github.com/awslabs/threat-composer) v1 format, and it
validates against the official schema.

Spanish version: [README.es.md](README.es.md)

## Contents

- **20 threats**, identified with the STRIDE method: 8 High and 12 Medium
- **25 mitigations**. Every threat links to at least one mitigation.
- **65 recorded assumptions**
- An architecture description and a data flow diagram

These are the eight High threats:

| STRIDE | Threat |
|---|---|
| S,I | A stolen or leaked JWT gives an actor access to the statements and analysis results of another user. |
| T,I,E | An actor who intercepts a presigned S3 URL uploads a malicious PDF, or downloads the documents of another user. |
| T,I,E | A crafted prompt bypasses the guardrail and extracts data that belongs to other users. |
| I,E | An actor changes `job_id` in a polling request and reads the analysis results of another user. |
| E | Compromised Lambda execution role credentials expose every DynamoDB table and S3 bucket. |
| T,E | A specially crafted PDF exploits the PDF parser or Claude Vision processing. |
| D | Thousands of concurrent requests exhaust Lambda concurrency and Bedrock quotas. |
| T | An actor changes amounts, balances or interest rates in the `estados_cuenta` table. |

## How to view it

Open Threat Composer at <https://awslabs.github.io/threat-composer/>. Select
*Import*, then choose `threatmodel.tc.json`.

## How it was generated

[threat-composer-ai](https://github.com/awslabs/threat-composer/tree/main/packages/threat-composer-ai)
generated this model on 2026-08-17. The tool runs a multi-agent workflow on
Amazon Bedrock with Claude Sonnet 4.5. It analyzed the tracked source code in
this repository.

To generate the model again:

```bash
uv tool install "git+https://github.com/awslabs/threat-composer.git#subdirectory=packages/threat-composer-ai"
threat-composer-ai-cli <path-to-code> -o <output-dir> \
  --aws-profile <profile> --aws-region us-east-1 \
  --aws-model-id "global.anthropic.claude-sonnet-4-5-20250929-v1:0"
```

The tool defaults to Claude Sonnet 4 (20250514). Bedrock marks that model as
Legacy, and inference validation fails. Pass `--aws-model-id` with an active
model instead.

Treat the threat model as a living document. Review it and generate it again
when the architecture changes. Examples of such a change are a new endpoint, a
new agent, a new table, or a new data flow.
