#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
import urllib.error
from pathlib import Path

from api_tester_core import (
    ApiClient,
    append_history,
    explain_http_error,
    format_meta,
    load_app_config,
    safe_float,
    safe_int,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Cross-platform AI API tester CLI.")
    parser.add_argument("-c", "--config", type=Path, default=Path("api_tester_config.json"))
    parser.add_argument("-u", "--upstream", help="Upstream name from config.")
    parser.add_argument("--list-upstreams", action="store_true")
    parser.add_argument("--list-models", action="store_true")
    parser.add_argument("--model", help="Model id. Defaults to upstream default_model.")
    parser.add_argument("--template", help="Prompt template name from config.")
    parser.add_argument("--prompt", help="User prompt.")
    parser.add_argument("--prompt-file", type=Path, help="Read user prompt from a UTF-8 text file.")
    parser.add_argument("--system", default="", help="Optional system prompt.")
    parser.add_argument("--system-file", type=Path, help="Read system prompt from a UTF-8 text file.")
    parser.add_argument("--max-tokens", type=int)
    parser.add_argument("--temperature", type=float)
    parser.add_argument("--send-temperature", action="store_true")
    parser.add_argument("--no-stream", action="store_true")
    parser.add_argument("--save-history", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = load_app_config(args.config)
    upstreams = config.get("upstreams", {})
    if args.list_upstreams:
        for name in upstreams:
            print(name)
        return 0

    upstream_name = args.upstream or config.get("default_upstream")
    if not upstream_name or upstream_name not in upstreams:
        print("No valid upstream selected. Use --list-upstreams.", file=sys.stderr)
        return 2
    upstream = upstreams[upstream_name]
    client = ApiClient(upstream)

    if args.list_models:
        try:
            for model in client.fetch_models():
                print(model)
            return 0
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            print(explain_http_error(exc.code, body), file=sys.stderr)
            print(body, file=sys.stderr)
            return 1

    prompt = args.prompt or ""
    if args.prompt_file:
        prompt = args.prompt_file.read_text(encoding="utf-8")
    if not prompt and args.template:
        prompt = config.get("templates", {}).get(args.template, "")
    if not prompt:
        prompt = input("Prompt: ").strip()
    if not prompt:
        print("Prompt is required.", file=sys.stderr)
        return 2

    system_prompt = args.system
    if args.system_file:
        system_prompt = args.system_file.read_text(encoding="utf-8")

    payload = {
        "model": args.model or upstream.get("default_model") or "",
        "prompt": prompt,
        "system_prompt": system_prompt,
        "max_tokens": args.max_tokens or safe_int(upstream.get("max_tokens"), 4096),
        "temperature": args.temperature if args.temperature is not None else safe_float(upstream.get("temperature"), 0.7),
        "send_temperature": args.send_temperature or bool(upstream.get("send_temperature", False)),
        "stream": not args.no_stream and bool(upstream.get("stream", True)),
    }
    if not payload["model"]:
        print("Model is required. Pass --model or set default_model in config.", file=sys.stderr)
        return 2

    try:
        result = client.complete(payload, on_text=(lambda text: (print(text, end="", flush=True)) if payload["stream"] else None))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        print(explain_http_error(exc.code, body), file=sys.stderr)
        print(body, file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    if payload["stream"]:
        print()
    else:
        print(result.text)
    print("\n" + format_meta(result.meta), file=sys.stderr)

    if args.save_history:
        append_history({
            "upstream": upstream_name,
            "type": upstream.get("type"),
            "model": payload["model"],
            "system_prompt": system_prompt,
            "prompt": prompt,
            "response": result.text,
            "stop_reason": result.meta.get("stop_reason"),
            "usage": result.meta.get("usage") or {},
            "elapsed": result.elapsed,
            "ok": True,
            "error": "",
        })
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
