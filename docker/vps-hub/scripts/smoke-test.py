#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from typing import Any


def request_json(
    url: str,
    api_key: str | None,
    payload: dict[str, Any] | None = None,
) -> tuple[int, dict[str, Any] | str]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"Accept": "application/json"}
    if payload is not None:
        headers["Content-Type"] = "application/json"
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    req = urllib.request.Request(
        url,
        data=data,
        headers=headers,
        method="GET" if payload is None else "POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as res:
            body = res.read().decode("utf-8", errors="replace")
            try:
                return res.status, json.loads(body)
            except json.JSONDecodeError:
                return res.status, body
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            return exc.code, json.loads(body)
        except json.JSONDecodeError:
            return exc.code, body


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke test a Headroom VPS hub deployment.")
    parser.add_argument(
        "--base-url",
        required=True,
        help="Public Headroom URL, e.g. https://headroom.example.com",
    )
    parser.add_argument("--api-key", default=None, help="API key accepted by Headroom/9Router")
    parser.add_argument("--model", default="gpt-4o-mini", help="Model name routed by 9Router")
    parser.add_argument("--skip-chat", action="store_true", help="Only check /readyz")
    args = parser.parse_args()

    base = args.base_url.rstrip("/")
    status, ready = request_json(f"{base}/readyz", None)
    if status >= 400:
        print(f"readyz failed: HTTP {status}: {ready}", file=sys.stderr)
        return 1
    print(f"readyz ok: {ready}")

    if args.skip_chat:
        return 0

    payload = {
        "model": args.model,
        "messages": [
            {"role": "system", "content": "You are a concise health-check assistant."},
            {"role": "user", "content": "Reply with exactly: headroom-ok"},
        ],
        "temperature": 0,
        "max_tokens": 20,
    }
    status, body = request_json(f"{base}/v1/chat/completions", args.api_key, payload)
    if status >= 400:
        print(f"chat completion failed: HTTP {status}: {body}", file=sys.stderr)
        return 1

    text = ""
    if isinstance(body, dict):
        choices = body.get("choices") or []
        if choices:
            text = str((choices[0].get("message") or {}).get("content") or "")
    if "headroom-ok" not in text.lower():
        print(f"unexpected chat response: {body}", file=sys.stderr)
        return 1

    print("chat completion ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
