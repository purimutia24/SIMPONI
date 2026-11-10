#!/usr/bin/env python3
"""Smoke-test backend endpoints and write a compact response report.

Examples:
    python scripts/test_endpoints.py
    python scripts/test_endpoints.py --base-url http://127.0.0.1:8000 --token "$TOKEN"
    python scripts/test_endpoints.py --include-write --output endpoint-report.json
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin
from urllib.request import Request, urlopen


WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
SENSITIVE_KEYS = {"access_token", "token", "password", "secret", "authorization"}
PATH_PARAMETER_RE = re.compile(r"{([^}]+)}")


def normalize_token(value):
    token = (value or "").strip()
    if token.lower().startswith("authorization:"):
        token = token.split(":", 1)[1].strip()
    if token.lower().startswith("bearer "):
        token = token[7:].strip()
    return token


def compact(value, limit=240):
    if isinstance(value, dict):
        keys = list(value)
        summary = {"keys": keys[:20]}
        if "detail" in value:
            summary["detail"] = compact(value["detail"], 180)
        return summary
    if isinstance(value, list):
        return {"type": "list", "count": len(value), "sample": compact(value[0], 120) if value else None}
    text = str(value).replace("\n", " ").strip()
    return text if len(text) <= limit else f"{text[:limit - 3]}..."


def redact(value):
    if isinstance(value, dict):
        return {
            key: "***" if key.lower() in SENSITIVE_KEYS else redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


def example_from_schema(schema, schemas):
    if not schema:
        return None
    if "anyOf" in schema:
        for option in schema["anyOf"]:
            if option.get("type") != "null":
                value = example_from_schema(option, schemas)
                if value is not None:
                    return value
        return None
    if "$ref" in schema:
        return example_from_schema(schemas.get(schema["$ref"].split("/")[-1], {}), schemas)
    if "example" in schema:
        return schema["example"]
    if "default" in schema:
        return schema["default"]
    if "enum" in schema and schema["enum"]:
        return schema["enum"][0]
    schema_type = schema.get("type")
    if schema_type == "object" or "properties" in schema:
        return {
            name: example_from_schema(value, schemas)
            for name, value in schema.get("properties", {}).items()
            if example_from_schema(value, schemas) is not None
        }
    if schema_type == "array":
        item = example_from_schema(schema.get("items", {}), schemas)
        return [item] if item is not None else []
    if schema_type == "integer":
        return schema.get("minimum", 1)
    if schema_type == "number":
        return schema.get("minimum", 1)
    if schema_type == "boolean":
        return True
    return "smoke-test@example.invalid" if "email" in str(schema).lower() else "test"


def request_json(url, method="GET", headers=None, body=None):
    request = Request(url, method=method, headers=headers or {}, data=body)
    started = time.perf_counter()
    try:
        with urlopen(request, timeout=20) as response:
            raw = response.read()
            status = response.status
            response_headers = dict(response.headers.items())
    except HTTPError as error:
        raw = error.read()
        status = error.code
        response_headers = dict(error.headers.items())
    except (URLError, TimeoutError, OSError) as error:
        return None, None, time.perf_counter() - started, str(error)

    elapsed = time.perf_counter() - started
    content_type = response_headers.get("Content-Type", "")
    try:
        payload = json.loads(raw.decode("utf-8")) if raw else None
    except (UnicodeDecodeError, json.JSONDecodeError):
        payload = f"<non-JSON response: {len(raw)} bytes>"
    return status, payload, elapsed, content_type


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=os.getenv("API_BASE_URL", "http://127.0.0.1:8000"))
    parser.add_argument("--token", default=os.getenv("API_TOKEN"))
    parser.add_argument("--include-write", action="store_true", help="Also send POST, PUT, PATCH, and DELETE requests.")
    parser.add_argument("--output", default="endpoint-report.json")
    parser.add_argument("--csv", help="Optional CSV output path.")
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/") + "/"
    status, openapi, elapsed, error = request_json(urljoin(base_url, "openapi.json"))
    if error or status != 200 or not isinstance(openapi, dict):
        print(f"Cannot load OpenAPI: status={status}, error={error}", file=sys.stderr)
        return 2

    schemas = openapi.get("components", {}).get("schemas", {})
    results = []
    headers = {"Accept": "application/json", "ngrok-skip-browser-warning": "true"}
    token = normalize_token(args.token)
    if token:
        headers["Authorization"] = f"Bearer {token}"

    for path, path_item in openapi.get("paths", {}).items():
        for method, operation in path_item.items():
            method = method.upper()
            if method not in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
                continue
            if method in WRITE_METHODS and not args.include_write:
                continue

            endpoint = path
            params = {}
            for parameter in operation.get("parameters", []) + path_item.get("parameters", []):
                if parameter.get("in") == "path":
                    value = "1"
                    endpoint = endpoint.replace("{" + parameter["name"] + "}", value)
                elif parameter.get("in") == "query" and parameter.get("required"):
                    params[parameter["name"]] = example_from_schema(parameter.get("schema", {}), schemas)
            url = urljoin(base_url, endpoint.lstrip("/"))
            if params:
                url += "?" + urlencode({key: value for key, value in params.items() if value is not None})

            body = None
            request_headers = dict(headers)
            request_body = operation.get("requestBody", {}).get("content", {})
            json_schema = request_body.get("application/json", {}).get("schema")
            if json_schema:
                payload = example_from_schema(json_schema, schemas)
                body = json.dumps(payload).encode("utf-8")
                request_headers["Content-Type"] = "application/json"

            response_status, payload, duration, content_type = request_json(
                url, method, request_headers, body
            )
            result = {
                "method": method,
                "endpoint": endpoint,
                "parameters": redact(params),
                "status": response_status,
                "ok": response_status is not None and response_status < 500,
                "server_error": response_status is None or response_status >= 500,
                "elapsed_ms": round(duration * 1000, 2),
                "content_type": content_type,
                "response": compact(payload),
            }
            results.append(result)
            print(
                f"{method:6} {endpoint:45} "
                f"{str(response_status):>3} {result['elapsed_ms']:>8.2f} ms "
                f"{compact(payload, 100)}"
            )

    report = {
        "base_url": base_url.rstrip("/"),
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "include_write": args.include_write,
        "total": len(results),
        "passed": sum(item["ok"] for item in results),
        "failed": sum(item["server_error"] for item in results),
        "results": results,
    }
    Path(args.output).write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if args.csv:
        with Path(args.csv).open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=["method", "endpoint", "status", "ok", "elapsed_ms", "content_type"])
            writer.writeheader()
            writer.writerows({key: item[key] for key in writer.fieldnames} for item in results)
    print(f"\nReport: {args.output} | total={len(results)} passed={report['passed']} failed={report['failed']}")
    return 0 if report["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
