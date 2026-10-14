# Opt-in small spaCy model — 14 October 2026

`PII_SPACY_MODEL=en_core_web_sm` selects the bundled small model. The default remains `en_core_web_lg`. No AWS deployment or memory configuration was changed.

Both model packages are pinned to 3.8.0 and installed in the test image; only the selected model is loaded into RAM. Unused parser and sentence-recognition components are excluded at load time. The image still includes the large package on disk for switching back, so this is not a small-only image optimization.

## Accuracy checks

| Check | Large-model baseline | Small model |
|---|---:|---:|
| Existing JSON audit | 425/425 expected spans | 425/425 |
| False detections in ten strong JSON negatives | 0 | 0 |
| Earlier 128-case audit | 191/195 expected spans | 190/195 |
| Original prose sample | 50/50 expected spans, 53 predictions | 50/50 expected spans, 57 predictions |

The small model misses `3M` in the short prose organization fixture. On the original prose sample, its seven unmatched predictions include organization classifications for employee/customer labels, `Bank`, `CVV 737`, a bearer-token span and `VIN`, plus DATE_TIME covering the IMEI label/value. The large model had three unmatched predictions on that sample. These results are evidence of changed free-text precision, despite equal recall on the sample. They do not establish general accuracy or justify silently adopting the small model.

The existing 44 tests and three new model-configuration tests pass locally with both models. A separate deployment test uses mocked AWS/Docker commands to verify that existing-image deployment uploads the saved image, forwards the model/memory parameters and never starts a build or detection container. This targeted test also passes; no real AWS calls occur in it.

## Memory and runtime measurements

The local small-model process peaked at 196.44 MiB across initialization, the prose sample, 190 JSON person records and approximately 20 KB prose/JSON-note inputs. Full observations are in `local_memory.json`.

A Linux/amd64 Lambda-compatible image was built successfully as `pii-presidio-lambda:model-test`, config digest `sha256:6e03ddb7671009c9020713f705a1af9cf7ea97a28dafce6994339c5f15bf601b`.

The capped test used 512 MiB, no swap, UID/GID 1051 and no network. Docker's live reading was 220.6 MiB for this container. However, the Docker engine disconnected before completion (`unexpected EOF`, CLI exit 125); no completed container peak or workload report was returned. The separate Linux regression run was also interrupted. Neither is claimed as a completed pass. No further Docker workloads were run after the user requested testing directly in Lambda.

Local tests ran during a heavily contended build/test session, with native macOS and emulated Linux runtimes. Their wall-clock durations are unsuitable for predicting Lambda latency. A 512 MiB allocation reduces Lambda CPU compared with 3008 MiB, so actual initialization and request latency still need measurement in AWS.

## Deployment without a local rebuild

The new `--deploy-existing-image` mode tags and uploads the already-built `EXISTING_LOCAL_IMAGE` and updates the CloudFormation stack. It does not build an image or execute PII detection locally. Docker Desktop is needed only for the image upload. The saved image must include the small model; changing an older large-only image's environment variable is insufficient.

For an isolated test endpoint/repository:

```bash
STACK_NAME=pii-detection-sm-test ECR_REPOSITORY_NAME=pii-detection-sm-test \
  PII_SPACY_MODEL=en_core_web_sm MEMORY_SIZE=512 PROVISIONED_CONCURRENCY=0 \
  EXISTING_LOCAL_IMAGE=pii-presidio-lambda:model-test \
  scripts/deploy.sh --deploy-existing-image
```

This creates billable test resources when the user runs it. Omitting the stack/repository overrides updates the existing default stack and endpoint. The deployment publishes a new Lambda version with the model in its description and updates the live alias. Switching back to `en_core_web_lg` requires sufficient memory and another version/config deployment.

Shell syntax, source diff whitespace and CloudFormation YAML syntax pass. Full CloudFormation schema lint was unavailable locally. Actual AWS deployment, Lambda peak memory, cold start and live accuracy remain unverified.
