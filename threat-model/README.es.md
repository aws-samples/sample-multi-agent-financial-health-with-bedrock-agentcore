# Modelo de amenazas

`threatmodel.tc.json` contiene el modelo de amenazas de este proyecto. Usa el
formato [Threat Composer](https://github.com/awslabs/threat-composer) v1 y valida
contra el esquema oficial.

Versión en inglés: [README.md](README.md)

## Contenido

- **20 amenazas**, identificadas con el método STRIDE: 8 High y 12 Medium
- **25 mitigaciones**. Cada amenaza tiene al menos una mitigación vinculada.
- **65 supuestos** documentados
- Una descripción de la arquitectura y un diagrama de flujo de datos

Estas son las ocho amenazas High:

| STRIDE | Amenaza |
|---|---|
| S,I | Un JWT robado o filtrado da acceso a los estados de cuenta y a los resultados de análisis de otro usuario. |
| T,I,E | Un actor que intercepta una URL prefirmada de S3 sube un PDF malicioso, o descarga los documentos de otro usuario. |
| T,I,E | Un prompt diseñado para el ataque evade el guardrail y extrae datos que pertenecen a otros usuarios. |
| I,E | Un actor cambia `job_id` en una petición de polling y lee los resultados de análisis de otro usuario. |
| E | Unas credenciales comprometidas del rol de ejecución de Lambda exponen todas las tablas de DynamoDB y todos los buckets de S3. |
| T,E | Un PDF diseñado para el ataque explota el parser de PDF o el procesamiento de Claude Vision. |
| D | Miles de peticiones simultáneas agotan la concurrencia de Lambda y las cuotas de Bedrock. |
| T | Un actor cambia montos, saldos o tasas de interés en la tabla `estados_cuenta`. |

## Cómo verlo

Abre Threat Composer en <https://awslabs.github.io/threat-composer/>. Selecciona
*Import* y elige `threatmodel.tc.json`.

## Cómo se generó

[threat-composer-ai](https://github.com/awslabs/threat-composer/tree/main/packages/threat-composer-ai)
generó este modelo el 2026-08-17. La herramienta ejecuta un flujo multi-agente
sobre Amazon Bedrock con Claude Sonnet 4.5. Analizó el código fuente trackeado de
este repositorio.

Para generar el modelo de nuevo:

```bash
uv tool install "git+https://github.com/awslabs/threat-composer.git#subdirectory=packages/threat-composer-ai"
threat-composer-ai-cli <ruta-al-codigo> -o <directorio-salida> \
  --aws-profile <perfil> --aws-region us-east-1 \
  --aws-model-id "global.anthropic.claude-sonnet-4-5-20250929-v1:0"
```

La herramienta usa Claude Sonnet 4 (20250514) por defecto. Bedrock marca ese
modelo como Legacy y la validación de inferencia falla. Pasa `--aws-model-id` con
un modelo activo.

Trata el modelo de amenazas como un documento vivo. Revísalo y genéralo de nuevo
cuando cambie la arquitectura. Ejemplos de ese cambio son un endpoint nuevo, un
agente nuevo, una tabla nueva o un flujo de datos nuevo.
