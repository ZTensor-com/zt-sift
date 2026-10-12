"""AWS Lambda entry point behind an API Gateway REST API (Lambda proxy integration).

POST /detect with the message as the request body (text/plain, or JSON {"text": "..."}).
Optional query parameters: threshold (default 0.5), entities (comma-separated Presidio entity names),
collapse (true/false; default true keeps the best of overlapping detections).
Returns {"count": <total>, "counts": {<entity>: <number>, ...}, "detections": [{"text", "entity", "start", "end", "score"}, ...]}.

Detection is Presidio with spaCy en_core_web_lg plus the project's custom recognizers
(pii_detector/recognizers.py); there is no neural span model. The analyzer loads once per
execution environment, when this module is imported. A Lambda environment handles one request at a time.
"""
import base64
import binascii
import time
import json
import os
import sys
from collections import Counter

from pii_detector import detect, load_analyzer

MAX_BYTES = int(os.environ.get("MAX_BYTES", "20000"))
analyzer = None


class BadRequest(Exception):
    """Carries a message that is safe to return because it never quotes the analyzed text."""


def load():
    global analyzer
    analyzer = load_analyzer(everything=True, custom=True)
    # The first call pays one-time setup costs; absorb them during initialisation.
    detect(analyzer, "Warm-up message from Jane Doe, jane@example.com, +1 202 555 0143, 12 Main Street, Austin, TX 78701.")


def parse(body, content_type, query):
    try:
        if content_type.split(";")[0].strip().lower() == "application/json":
            text = json.loads(body).get("text")
            if not isinstance(text, str):
                raise BadRequest('JSON body must be {"text": "<message>"}')
        else:
            text = body.decode("utf-8")
    except (ValueError, AttributeError):
        raise BadRequest("Body must be UTF-8 text or JSON of the form {\"text\": \"<message>\"}") from None
    if not text.strip():
        raise BadRequest("No message provided")
    options = {"collapse": True}
    if "threshold" in query:
        try:
            options["threshold"] = float(query["threshold"])
        except ValueError:
            raise BadRequest("threshold must be a number") from None
        if not 0 <= options["threshold"] <= 1:
            raise BadRequest("threshold must be between 0 and 1")
    if "entities" in query:
        names = [name.strip().upper() for name in query["entities"].split(",") if name.strip()]
        unknown = sorted(set(names) - set(analyzer.get_supported_entities(language="en")))
        if unknown:
            raise BadRequest("Unknown entities: " + ", ".join(unknown[:5]))
        if not names:
            raise BadRequest("entities must contain at least one entity name")
        options["entities"] = names
    if "collapse" in query:
        if query["collapse"].lower() not in ("true", "false"):
            raise BadRequest("collapse must be true or false")
        options["collapse"] = query["collapse"].lower() == "true"
    return text, options


def response(code, value):
    return {"statusCode": code, "headers": {"Content-Type": "application/json", "Cache-Control": "no-store"},
            "body": json.dumps(value)}


def metric(name, value, unit):
    """Optional EMF, fixed low-cardinality metrics; never include payloads or entities."""
    if os.environ.get("PII_EMIT_METRICS", "0") != "1":
        return
    print(json.dumps({"_aws": {"Timestamp": int(time.time() * 1000), "CloudWatchMetrics": [
        {"Namespace": "PiiDetection", "Dimensions": [[]], "Metrics": [{"Name": name, "Unit": unit}]}]}, name: value}), flush=True)


def handler(event, context):
    started = time.perf_counter()
    headers = {key.lower(): value for key, value in (event.get("headers") or {}).items()}
    raw = event.get("body") or ""
    try:
        body = base64.b64decode(raw, validate=True) if event.get("isBase64Encoded") else raw.encode("utf-8")
    except (binascii.Error, ValueError, AttributeError, UnicodeError):
        return response(400, {"error": "Body must be valid base64 or UTF-8 text"})
    if len(body) > MAX_BYTES:
        return response(413, {"error": f"Message exceeds {MAX_BYTES} bytes"})
    try:
        text, options = parse(body, headers.get("content-type", ""), event.get("queryStringParameters") or {})
        found = detect(analyzer, text, **options)
    except BadRequest as problem:
        return response(400, {"error": str(problem)})
    except Exception as problem:
        # Never log the message or exception text, which could quote it.
        print(f"detection failed: {type(problem).__name__}", file=sys.stderr, flush=True)
        metric("DetectionFailures", 1, "Count")
        return response(500, {"error": "Detection failed"})
    metric("DetectionDuration", (time.perf_counter() - started) * 1000, "Milliseconds")
    counts = Counter(item["entity"] for item in found)
    return response(200, {"count": len(found), "counts": dict(sorted(counts.items())), "detections": [
        {key: item[key] for key in ("text", "entity", "start", "end", "score")} for item in found]})


if os.environ.get("PII_EAGER_INIT", "1") == "1":
    load()
