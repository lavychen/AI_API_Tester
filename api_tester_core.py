#!/usr/bin/env python3
from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from json import JSONDecodeError
from pathlib import Path
from typing import Callable, Iterable, Optional


APP_DIR = Path(__file__).resolve().parent
CONFIG_PATH = APP_DIR / "api_tester_config.json"
DATA_DIR = APP_DIR / "Data"
HISTORY_PATH = DATA_DIR / "history" / "api_tester_history.jsonl"
API_VERSION = "2023-06-01"
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

DEFAULT_TEMPLATES = {
    "smoke": "Reply with: API test OK",
    "logic": "请分步骤推导一个逻辑题，并在最终答案前检查隐含假设。",
    "json": '请只返回 JSON：{"status":"ok","items":[1,2,3]}，不要包含 Markdown。',
    "code": "请写一个 Python 函数，并给出简短测试。",
    "long": "请写一篇结构清晰的中文长文。",
}


@dataclass
class ApiResult:
    text: str
    meta: dict
    elapsed: float


def clean_url(value: str) -> str:
    return (value or "").strip().lstrip("\ufeff\u200b\u200c\u200d")


def join_url(base_url: str, path: str) -> str:
    return clean_url(base_url).rstrip("/") + "/" + (path or "").strip().lstrip("/")


def safe_int(value, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def safe_float(value, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    return data if isinstance(data, dict) else {}


def normalize_legacy_config(path: Path) -> Optional[dict]:
    data = read_json(path)
    if not data:
        return None
    env = data.get("env") if isinstance(data.get("env"), dict) else {}
    base_url = data.get("api_url") or data.get("url") or env.get("ANTHROPIC_BASE_URL")
    api_key = data.get("api_key") or data.get("key") or env.get("ANTHROPIC_AUTH_TOKEN")
    if not base_url and not api_key:
        return None
    upstream_type = data.get("type") or ("newapi" if path.stem.lower() == "kelly" else "anthropic")
    chat_path = data.get("chat_path") or ("/v1/chat/completions" if upstream_type in {"openai", "newapi"} else "/v1/messages")
    return {
        "type": upstream_type,
        "base_url": base_url or "",
        "api_key": api_key or "",
        "models_path": data.get("models_path") or "/v1/models",
        "chat_path": chat_path,
        "default_model": data.get("default_model") or data.get("model") or "",
        "max_tokens": safe_int(data.get("max_tokens"), 4096),
        "temperature": safe_float(data.get("temperature"), 0.7),
        "send_temperature": bool(data.get("send_temperature", False)),
        "stream": bool(data.get("stream", True)),
        "user_agent": data.get("user_agent") or DEFAULT_USER_AGENT,
        "no_proxy": bool(data.get("no_proxy", False)),
    }


def default_config() -> dict:
    upstreams = {}
    for name in ("kelly", "unity2", "claude_api_config"):
        item = normalize_legacy_config(APP_DIR / f"{name}.json")
        if item:
            upstreams[name.replace("_api_config", "")] = item
    if not upstreams:
        upstreams["anthropic"] = {
            "type": "anthropic",
            "base_url": "https://api.anthropic.com",
            "api_key": "",
            "models_path": "/v1/models",
            "chat_path": "/v1/messages",
            "default_model": "claude-opus-4-7",
            "max_tokens": 4096,
            "temperature": 0.7,
            "send_temperature": False,
            "stream": True,
            "user_agent": DEFAULT_USER_AGENT,
            "no_proxy": False,
        }
    return {"default_upstream": next(iter(upstreams)), "upstreams": upstreams, "templates": DEFAULT_TEMPLATES.copy()}


def load_app_config(path: Path = CONFIG_PATH) -> dict:
    if path.exists():
        data = read_json(path)
        data.setdefault("upstreams", {})
        data.setdefault("templates", DEFAULT_TEMPLATES.copy())
        if not data.get("default_upstream") and data["upstreams"]:
            data["default_upstream"] = next(iter(data["upstreams"]))
        return data
    return default_config()


def save_app_config(config: dict, path: Path = CONFIG_PATH) -> None:
    with path.open("w", encoding="utf-8") as handle:
        json.dump(config, handle, ensure_ascii=False, indent=2)


def append_history(record: dict, path: Path = HISTORY_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def load_history(limit: int = 200, path: Path = HISTORY_PATH) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            try:
                rows.append(json.loads(line))
            except JSONDecodeError:
                continue
    return rows[-limit:]


def opener_for(no_proxy: bool):
    if no_proxy:
        return urllib.request.build_opener(urllib.request.ProxyHandler({}))
    return urllib.request.build_opener()


def request_headers(upstream: dict) -> dict:
    api_key = upstream.get("api_key", "")
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": upstream.get("user_agent") or DEFAULT_USER_AGENT,
    }
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
        headers["x-api-key"] = api_key
    if upstream.get("type") == "anthropic" or upstream.get("chat_path") == "/v1/messages":
        headers["anthropic-version"] = API_VERSION
    return headers


def parse_models(data) -> list[str]:
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        items = data.get("data") or data.get("models") or data.get("model") or []
    else:
        items = []
    models = []
    for item in items:
        if isinstance(item, str):
            models.append(item)
        elif isinstance(item, dict):
            value = item.get("id") or item.get("name") or item.get("model")
            if value:
                models.append(str(value))
    return sorted(dict.fromkeys(models))


def usage_numbers(usage: dict) -> tuple[object, object, object]:
    input_tokens = usage.get("input_tokens", usage.get("prompt_tokens"))
    output_tokens = usage.get("output_tokens", usage.get("completion_tokens"))
    total_tokens = usage.get("total_tokens")
    if total_tokens is None and isinstance(input_tokens, int) and isinstance(output_tokens, int):
        total_tokens = input_tokens + output_tokens
    return input_tokens, output_tokens, total_tokens


def format_meta(meta: dict) -> str:
    usage = meta.get("usage") or {}
    input_tokens, output_tokens, total_tokens = usage_numbers(usage)
    lines = ["请求结果"]
    lines.append(f"终止原因：{meta.get('stop_reason') or '-'}")
    lines.append(f"响应模型：{meta.get('model') or '-'}")
    if meta.get("elapsed") is not None:
        lines.append(f"耗时：{meta['elapsed']:.2f}s")
    lines.append("")
    lines.append("Token 使用：")
    lines.append(f"  输入 Token：{input_tokens if input_tokens is not None else '-'}")
    lines.append(f"  输出 Token：{output_tokens if output_tokens is not None else '-'}")
    lines.append(f"  总 Token：{total_tokens if total_tokens is not None else '-'}")
    return "\n".join(lines)


def explain_http_error(code: int, body: str) -> str:
    body_text = (body or "").strip()
    if code == 401:
        return "认证失败：API Key 可能无效、过期，或鉴权头格式不被该上游接受。"
    if code == 403 and "1010" in body_text:
        return "请求被 Cloudflare 1010 拦截：可能与代理节点、User-Agent、TLS 指纹或上游防火墙规则有关。"
    if code == 403:
        return "请求被拒绝：上游可能限制了 IP、代理、User-Agent，或当前 Key 没有访问权限。"
    if code == 404:
        return "接口不存在：请检查 Base URL、聊天路径或模型路径。"
    if code == 429:
        return "请求过于频繁或额度不足：请稍后重试，或检查账号额度。"
    if code >= 500:
        return "上游服务异常：通常是网关或模型服务临时故障。"
    return "上游返回了 HTTP 错误，请结合原始响应排查。"


class ApiClient:
    def __init__(self, upstream: dict):
        self.upstream = upstream

    def open(self, request: urllib.request.Request):
        return opener_for(bool(self.upstream.get("no_proxy"))).open(request, timeout=180)

    def fetch_models(self) -> list[str]:
        url = join_url(self.upstream["base_url"], self.upstream.get("models_path") or "/v1/models")
        request = urllib.request.Request(url, method="GET", headers=request_headers(self.upstream))
        with self.open(request) as response:
            raw = response.read().decode("utf-8", errors="replace")
        return parse_models(json.loads(raw))

    def complete(self, payload: dict, on_text: Optional[Callable[[str], None]] = None) -> ApiResult:
        started = time.perf_counter()
        text, meta = self._perform_request(payload, on_text=on_text)
        elapsed = time.perf_counter() - started
        meta["elapsed"] = elapsed
        return ApiResult(text=text, meta=meta, elapsed=elapsed)

    def _perform_request(self, payload: dict, on_text: Optional[Callable[[str], None]]) -> tuple[str, dict]:
        api_type = self.upstream.get("type") or "anthropic"
        chat_path = self.upstream.get("chat_path") or ("/v1/chat/completions" if api_type in {"openai", "newapi"} else "/v1/messages")
        body = self.make_body(api_type, chat_path, payload)
        url = join_url(self.upstream["base_url"], chat_path)
        request = urllib.request.Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            method="POST",
            headers=request_headers(self.upstream),
        )
        with self.open(request) as response:
            content_type = response.headers.get("content-type", "")
            if body.get("stream"):
                if chat_path == "/v1/messages" or api_type == "anthropic":
                    return self.parse_anthropic_stream(response, on_text)
                return self.parse_openai_stream(response, on_text)
            raw = response.read().decode("utf-8", errors="replace")
        if "json" not in content_type.lower():
            raise RuntimeError(f"接口返回非 JSON。\nContent-Type: {content_type}\n{raw[:2000]}")
        result = json.loads(raw)
        return self.extract_text(api_type, chat_path, result), self.result_meta(api_type, chat_path, result)

    def make_body(self, api_type: str, chat_path: str, payload: dict) -> dict:
        prompt = payload["prompt"]
        system_prompt = (payload.get("system_prompt") or "").strip()
        model = payload["model"]
        stream = bool(payload.get("stream"))
        max_tokens = safe_int(payload.get("max_tokens"), 4096)
        if chat_path == "/v1/messages" or api_type == "anthropic":
            body = {
                "model": model,
                "max_tokens": max_tokens,
                "stream": stream,
                "messages": [{"role": "user", "content": prompt}],
            }
            if system_prompt:
                body["system"] = system_prompt
            if payload.get("send_temperature"):
                body["temperature"] = safe_float(payload.get("temperature"), 0.7)
            return body
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        body = {"model": model, "max_tokens": max_tokens, "stream": stream, "messages": messages}
        if payload.get("send_temperature"):
            body["temperature"] = safe_float(payload.get("temperature"), 0.7)
        if stream:
            body["stream_options"] = {"include_usage": True}
        return body

    def extract_text(self, api_type: str, chat_path: str, result: dict) -> str:
        if chat_path == "/v1/messages" or api_type == "anthropic":
            return "".join(block.get("text", "") for block in result.get("content", []) if isinstance(block, dict) and block.get("type") == "text")
        choices = result.get("choices") or []
        if choices:
            return (choices[0].get("message") or {}).get("content", "")
        return json.dumps(result, ensure_ascii=False, indent=2)

    def result_meta(self, api_type: str, chat_path: str, result: dict) -> dict:
        if chat_path == "/v1/messages" or api_type == "anthropic":
            return {"model": result.get("model"), "stop_reason": result.get("stop_reason"), "usage": result.get("usage") or {}}
        choices = result.get("choices") or []
        finish_reason = choices[0].get("finish_reason") if choices else None
        return {"model": result.get("model"), "stop_reason": finish_reason, "usage": result.get("usage") or {}}

    def parse_anthropic_stream(self, response: Iterable[bytes], on_text: Optional[Callable[[str], None]]) -> tuple[str, dict]:
        usage = {}
        stop_reason = None
        model = None
        chunks = []
        for raw_line in response:
            line = raw_line.decode("utf-8", errors="replace").strip()
            if not line or not line.startswith("data:"):
                continue
            data = line.removeprefix("data:").strip()
            if data == "[DONE]":
                break
            event = json.loads(data)
            event_type = event.get("type")
            if event_type == "message_start":
                message = event.get("message") or {}
                model = message.get("model") or model
                usage.update(message.get("usage") or {})
            elif event_type == "content_block_delta":
                delta = event.get("delta") or {}
                if delta.get("type") == "text_delta":
                    text = delta.get("text", "")
                    chunks.append(text)
                    if on_text:
                        on_text(text)
            elif event_type == "message_delta":
                stop_reason = (event.get("delta") or {}).get("stop_reason") or stop_reason
                usage.update(event.get("usage") or {})
            elif event_type == "error":
                raise RuntimeError(json.dumps(event, ensure_ascii=False, indent=2))
        return "".join(chunks), {"model": model, "stop_reason": stop_reason or "unknown", "usage": usage}

    def parse_openai_stream(self, response: Iterable[bytes], on_text: Optional[Callable[[str], None]]) -> tuple[str, dict]:
        usage = {}
        finish_reason = None
        model = None
        chunks = []
        for raw_line in response:
            line = raw_line.decode("utf-8", errors="replace").strip()
            if not line or not line.startswith("data:"):
                continue
            data = line.removeprefix("data:").strip()
            if data == "[DONE]":
                break
            event = json.loads(data)
            model = event.get("model") or model
            usage.update(event.get("usage") or {})
            choices = event.get("choices") or []
            if not choices:
                continue
            delta = choices[0].get("delta") or {}
            content = delta.get("content")
            if content:
                chunks.append(content)
                if on_text:
                    on_text(content)
            finish_reason = choices[0].get("finish_reason") or finish_reason
        return "".join(chunks), {"model": model, "stop_reason": finish_reason or "unknown", "usage": usage}
