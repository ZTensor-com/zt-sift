#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
AWS_REGION="${AWS_REGION:-us-west-2}"
DOCKERFILE=Dockerfile
LOCK_FILE=requirements.lock
LOCAL_TAG=pii-presidio-lambda:local
STACK_NAME="${STACK_NAME:-pii-detection-presidio}"
ECR_REPOSITORY_NAME="${ECR_REPOSITORY_NAME:-pii-detection-presidio}"
TIMEOUT_SECONDS="${TIMEOUT_SECONDS:-60}"
STAGE_NAME="${STAGE_NAME:-dev}"
ALARM_EMAIL="${ALARM_EMAIL:-}"
MEMORY_SIZE="${MEMORY_SIZE:-3008}"
PII_SPACY_MODEL="${PII_SPACY_MODEL:-en_core_web_sm}"
EXISTING_LOCAL_IMAGE="${EXISTING_LOCAL_IMAGE:-pii-presidio-lambda:model-test}"
PROVISIONED_CONCURRENCY="${PROVISIONED_CONCURRENCY:-0}"
export AWS_PAGER=""

usage() {
  cat <<'TXT'
Usage: scripts/deploy.sh --validate | --build | --deploy | --deploy-existing-image
  --validate  Local Python/shell checks, unit tests and cfn-lint; no AWS or Docker calls.
  --build     Build the linux/amd64 image locally (tag pii-presidio-lambda:local); no AWS calls.
  --deploy    Create/reuse ECR, build and push the image, create/update the Lambda stack.
  --deploy-existing-image  Push EXISTING_LOCAL_IMAGE and update Lambda; no build or local detection.
Environment: AWS_REGION (us-west-2), STACK_NAME (pii-detection-presidio), ECR_REPOSITORY_NAME, STAGE_NAME (dev),
             MEMORY_SIZE (3008), PII_SPACY_MODEL (en_core_web_sm; opt-in en_core_web_lg),
             PROVISIONED_CONCURRENCY (0; warm instances, billed continuously),
             EXISTING_LOCAL_IMAGE (pii-presidio-lambda:model-test), ALARM_EMAIL (optional), PYTHON_BIN.
TXT
}

check_inputs() {
  python3 - "$PROJECT_DIR" "$LOCK_FILE" <<'PY'
import pathlib
import sys
root = pathlib.Path(sys.argv[1])
lock = root / sys.argv[2]
if not lock.is_file():
    raise SystemExit(f'Missing {sys.argv[2]}: run python3 scripts/build_lock.py')
wheels = [p.name.lower() for p in (root / 'wheels').glob('*.whl')]
missing = []
for line in lock.read_text().splitlines():
    if line and not line.startswith('#'):
        name, version = line.split('==')
        stem = name.replace('-', '_').lower() + '-' + version + '-'
        if not any(w.startswith(stem) for w in wheels):
            missing.append(line)
if missing:
    raise SystemExit('Wheel cache incomplete (see scripts/build_lock.py for the pip download command): ' + ', '.join(missing[:5]))
for name in ('detector.py', 'recognizers.py'):
    if not (root / 'pii_detector' / name).is_file():
        raise SystemExit(f'Missing pii_detector/{name}')
PY
}

if [[ $# != 1 ]]; then usage; exit 2; fi
case "$1" in
  --validate)
    if [[ -n "${PYTHON_BIN:-}" ]]; then
      task_python="$PYTHON_BIN"
    elif [[ -x "$PROJECT_DIR/.venv/bin/python" ]]; then
      task_python="$PROJECT_DIR/.venv/bin/python"
    else
      task_python=python3
    fi
    bash -n "$SCRIPT_DIR/deploy.sh"
    "$task_python" -m py_compile "$PROJECT_DIR/handler.py" "$PROJECT_DIR"/pii_detector/*.py "$SCRIPT_DIR/build_lock.py"
    if [[ -d "$PROJECT_DIR/tests" ]]; then
      (cd "$PROJECT_DIR" && "$task_python" -m unittest discover -s tests -t . -v)
    else
      printf '%s\n' 'No tests/ folder in this checkout (it is not tracked in the repo): unit tests NOT RUN.'
    fi
    if command -v cfn-lint >/dev/null 2>&1; then
      cfn-lint "$PROJECT_DIR/template.yaml"
    else
      printf '%s\n' 'CloudFormation schema lint NOT RUN: cfn-lint is not installed.'
    fi
    printf '%s\n' 'Local validation finished; Docker build and AWS deployment were not run.'
    exit 0
    ;;
  --build)
    check_inputs
    docker buildx build --platform linux/amd64 --provenance=false --load -f "$PROJECT_DIR/$DOCKERFILE" -t "$LOCAL_TAG" "$PROJECT_DIR"
    exit 0
    ;;
  --deploy|--deploy-existing-image) ;;
  --help|-h) usage; exit 0 ;;
  *) usage; exit 2 ;;
esac

[[ "$PII_SPACY_MODEL" == en_core_web_lg || "$PII_SPACY_MODEL" == en_core_web_sm ]] || { printf '%s\n' 'PII_SPACY_MODEL must be en_core_web_lg or en_core_web_sm' >&2; exit 2; }
[[ "$AWS_REGION" =~ ^[a-z0-9-]+$ ]] || { printf '%s\n' 'Invalid AWS_REGION' >&2; exit 2; }
[[ "$STACK_NAME" =~ ^[A-Za-z][A-Za-z0-9-]{0,49}$ ]] || { printf '%s\n' 'Invalid STACK_NAME (maximum 50 characters)' >&2; exit 2; }
[[ "$ECR_REPOSITORY_NAME" =~ ^[a-z0-9][a-z0-9._/-]*$ ]] || { printf '%s\n' 'Invalid ECR_REPOSITORY_NAME' >&2; exit 2; }
[[ "$MEMORY_SIZE" =~ ^[0-9]+$ && "$PROVISIONED_CONCURRENCY" =~ ^[0-9]+$ ]] || { printf '%s\n' 'MEMORY_SIZE and PROVISIONED_CONCURRENCY must be integers' >&2; exit 2; }
for required_command in aws docker python3; do
  command -v "$required_command" >/dev/null || { printf 'Missing prerequisite: %s\n' "$required_command" >&2; exit 1; }
done
docker info >/dev/null
if [[ "$1" == --deploy-existing-image ]]; then
  image_platform="$(docker image inspect "$EXISTING_LOCAL_IMAGE" --format '{{.Os}}/{{.Architecture}}')"
  [[ "$image_platform" == linux/amd64 ]] || { printf '%s\n' 'Existing image must be linux/amd64' >&2; exit 2; }
else
  docker buildx version >/dev/null
  check_inputs
fi

printf 'Deploying billable resources: stack=%s region=%s\n' "$STACK_NAME" "$AWS_REGION"
account_id="$(aws sts get-caller-identity --region "$AWS_REGION" --query Account --output text)"
registry="${account_id}.dkr.ecr.${AWS_REGION}.amazonaws.com"
repository_arn="$(aws ecr describe-repositories --region "$AWS_REGION" --query "repositories[?repositoryName=='${ECR_REPOSITORY_NAME}'].repositoryArn | [0]" --output text)"
if [[ "$repository_arn" == None ]]; then
  aws ecr create-repository --region "$AWS_REGION" --repository-name "$ECR_REPOSITORY_NAME" --image-tag-mutability IMMUTABLE --image-scanning-configuration scanOnPush=true >/dev/null
fi
aws ecr put-lifecycle-policy --region "$AWS_REGION" --repository-name "$ECR_REPOSITORY_NAME" --lifecycle-policy-text \
  '{"rules":[{"rulePriority":1,"description":"Keep the 5 newest images","selection":{"tagStatus":"any","countType":"imageCountMoreThan","countNumber":5},"action":{"type":"expire"}}]}' >/dev/null
image_tag="$(date -u +%Y%m%dT%H%M%SZ)-$(python3 -c 'import uuid; print(uuid.uuid4().hex[:8])')"
image_uri="${registry}/${ECR_REPOSITORY_NAME}:${image_tag}"
aws ecr get-login-password --region "$AWS_REGION" | docker login --username AWS --password-stdin "$registry"
if [[ "$1" == --deploy-existing-image ]]; then
  docker tag "$EXISTING_LOCAL_IMAGE" "$image_uri"
  docker push "$image_uri"
else
  docker buildx build --platform linux/amd64 --provenance=false --push -f "$PROJECT_DIR/$DOCKERFILE" --tag "$image_uri" "$PROJECT_DIR"
fi
aws cloudformation deploy --region "$AWS_REGION" --stack-name "$STACK_NAME" \
  --template-file "$PROJECT_DIR/template.yaml" --capabilities CAPABILITY_IAM \
  --parameter-overrides "ImageUri=$image_uri" "StageName=$STAGE_NAME" "AlarmEmail=$ALARM_EMAIL" \
    "MemorySize=$MEMORY_SIZE" "SpacyModel=$PII_SPACY_MODEL" "TimeoutSeconds=$TIMEOUT_SECONDS" "ProvisionedConcurrency=$PROVISIONED_CONCURRENCY" \
  --no-fail-on-empty-changeset
# CloudFormation never republishes an API Gateway deployment after the first one,
# so publish the current API definition to the stage explicitly.
rest_api_id="$(aws cloudformation describe-stacks --region "$AWS_REGION" --stack-name "$STACK_NAME" --query "Stacks[0].Outputs[?OutputKey=='RestApiId'].OutputValue | [0]" --output text)"
aws apigateway create-deployment --region "$AWS_REGION" --rest-api-id "$rest_api_id" --stage-name "$STAGE_NAME" --description "deploy $image_tag" >/dev/null
aws cloudformation describe-stacks --region "$AWS_REGION" --stack-name "$STACK_NAME" \
  --query 'Stacks[0].Outputs' --output table
printf '%s\n' 'Lambda bills per use. The first request after idle pays a cold start of a few seconds.'
printf '%s\n' 'Retrieve the API key explicitly using the APIKeyId output:'
printf 'export PII_API_KEY="$(aws apigateway get-api-key --region %s --api-key <APIKeyId> --include-value --query value --output text)"\n' "$AWS_REGION"
