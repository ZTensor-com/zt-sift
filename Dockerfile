# Build from the project root:  docker buildx build --platform linux/amd64 -f Dockerfile .
FROM public.ecr.aws/lambda/python:3.12

# Every package, including the spaCy model, comes from the project's local wheel cache (../wheels),
# so the build never contacts a package index. The bind mount keeps the wheels out of the image layers.
RUN --mount=type=bind,source=wheels,target=/wheels \
    --mount=type=bind,source=requirements.lock,target=/tmp/requirements.lock \
    python -m pip install --no-index --no-cache-dir --find-links /wheels -r /tmp/requirements.lock

COPY pii_detector/ ${LAMBDA_TASK_ROOT}/pii_detector/
COPY handler.py ${LAMBDA_TASK_ROOT}/
# Lambda runs the function as an unprivileged user: everything installed or copied must be world-readable.
RUN python -c 'import os,pathlib,spacy; roots=[pathlib.Path(os.environ["LAMBDA_TASK_ROOT"])] + [pathlib.Path(spacy.__file__).parents[1]/name for name in ("en_core_web_sm",)]; assert all(r.is_dir() for r in roots); bad=[str(p) for r in roots for p in r.rglob("*") if not (p.stat().st_mode & 4) or (p.is_dir() and not p.stat().st_mode & 1)]; assert not bad, bad[:5]'

CMD ["handler.handler"]
