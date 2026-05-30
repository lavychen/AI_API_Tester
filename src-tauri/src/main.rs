use reqwest::header::{HeaderMap, HeaderValue, ACCEPT, AUTHORIZATION, CONTENT_TYPE, USER_AGENT};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::collections::BTreeMap;
use std::path::PathBuf;
use std::time::Instant;

const API_VERSION: &str = "2023-06-01";
const DEFAULT_USER_AGENT: &str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36";

#[derive(Debug, Clone, Serialize, Deserialize)]
struct Upstream {
    #[serde(rename = "type")]
    upstream_type: String,
    base_url: String,
    api_key: String,
    models_path: String,
    chat_path: String,
    default_model: String,
    max_tokens: u32,
    temperature: f32,
    #[serde(default)]
    send_temperature: bool,
    #[serde(default)]
    stream: bool,
    #[serde(default = "default_user_agent")]
    user_agent: String,
    #[serde(default)]
    no_proxy: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
struct AppConfig {
    default_upstream: String,
    upstreams: BTreeMap<String, Upstream>,
    templates: BTreeMap<String, String>,
}

#[derive(Debug, Clone, Deserialize)]
struct CompletionPayload {
    upstream_name: String,
    upstream: Upstream,
    model: String,
    system_prompt: String,
    prompt: String,
}

#[derive(Debug, Serialize)]
struct ApiResult {
    text: String,
    meta: Value,
    elapsed: f64,
}

fn default_user_agent() -> String {
    DEFAULT_USER_AGENT.to_string()
}

fn config_path() -> Result<PathBuf, String> {
    let cwd = std::env::current_dir().map_err(|error| error.to_string())?;
    let root_config = cwd.join("api_tester_config.json");
    if root_config.exists() {
        return Ok(root_config);
    }
    let example = cwd.join("api_tester_config.example.json");
    if example.exists() {
        return Ok(root_config);
    }
    Ok(cwd
        .parent()
        .map(PathBuf::from)
        .unwrap_or(cwd)
        .join("api_tester_config.json"))
}

fn example_config_path() -> Result<PathBuf, String> {
    let cwd = std::env::current_dir().map_err(|error| error.to_string())?;
    let root_example = cwd.join("api_tester_config.example.json");
    if root_example.exists() {
        return Ok(root_example);
    }
    Ok(cwd
        .parent()
        .map(PathBuf::from)
        .unwrap_or(cwd)
        .join("api_tester_config.example.json"))
}

fn join_url(base: &str, path: &str) -> String {
    format!("{}/{}", base.trim().trim_end_matches('/'), path.trim().trim_start_matches('/'))
}

fn request_headers(upstream: &Upstream) -> Result<HeaderMap, String> {
    let mut headers = HeaderMap::new();
    headers.insert(ACCEPT, HeaderValue::from_static("application/json"));
    headers.insert(CONTENT_TYPE, HeaderValue::from_static("application/json"));
    headers.insert(
        USER_AGENT,
        HeaderValue::from_str(if upstream.user_agent.trim().is_empty() {
            DEFAULT_USER_AGENT
        } else {
            upstream.user_agent.trim()
        })
        .map_err(|error| error.to_string())?,
    );
    if !upstream.api_key.trim().is_empty() {
        headers.insert(
            AUTHORIZATION,
            HeaderValue::from_str(&format!("Bearer {}", upstream.api_key.trim()))
                .map_err(|error| error.to_string())?,
        );
        headers.insert(
            "x-api-key",
            HeaderValue::from_str(upstream.api_key.trim()).map_err(|error| error.to_string())?,
        );
    }
    if upstream.upstream_type == "anthropic" || upstream.chat_path == "/v1/messages" {
        headers.insert("anthropic-version", HeaderValue::from_static(API_VERSION));
    }
    Ok(headers)
}

fn http_client(upstream: &Upstream) -> Result<reqwest::Client, String> {
    let builder = reqwest::Client::builder();
    let builder = if upstream.no_proxy { builder.no_proxy() } else { builder };
    builder.build().map_err(|error| error.to_string())
}

fn parse_models(value: Value) -> Vec<String> {
    let items = if let Some(items) = value.as_array() {
        items.clone()
    } else if let Some(items) = value.get("data").and_then(Value::as_array) {
        items.clone()
    } else if let Some(items) = value.get("models").and_then(Value::as_array) {
        items.clone()
    } else if let Some(items) = value.get("model").and_then(Value::as_array) {
        items.clone()
    } else {
        Vec::new()
    };
    let mut models = items
        .into_iter()
        .filter_map(|item| {
            item.as_str().map(ToString::to_string).or_else(|| {
                item.get("id")
                    .or_else(|| item.get("name"))
                    .or_else(|| item.get("model"))
                    .and_then(Value::as_str)
                    .map(ToString::to_string)
            })
        })
        .collect::<Vec<_>>();
    models.sort();
    models.dedup();
    models
}

fn extract_text(value: &Value) -> String {
    if let Some(content) = value.get("content").and_then(Value::as_array) {
        return content
            .iter()
            .filter_map(|item| {
                item.as_str().map(ToString::to_string).or_else(|| {
                    item.get("text")
                        .and_then(Value::as_str)
                        .map(ToString::to_string)
                })
            })
            .collect::<Vec<_>>()
            .join("");
    }
    value
        .get("choices")
        .and_then(Value::as_array)
        .and_then(|choices| choices.first())
        .and_then(|choice| {
            choice
                .get("message")
                .and_then(|message| message.get("content"))
                .and_then(Value::as_str)
                .or_else(|| choice.get("text").and_then(Value::as_str))
        })
        .unwrap_or("")
        .to_string()
}

fn response_meta(value: &Value) -> Value {
    let first_choice = value
        .get("choices")
        .and_then(Value::as_array)
        .and_then(|choices| choices.first());
    json!({
        "model": value.get("model").cloned().unwrap_or(Value::Null),
        "usage": value.get("usage").cloned().unwrap_or(Value::Null),
        "stop_reason": value.get("stop_reason").cloned().unwrap_or(Value::Null),
        "finish_reason": first_choice
            .and_then(|choice| choice.get("finish_reason"))
            .cloned()
            .unwrap_or(Value::Null)
    })
}

fn completion_body(payload: &CompletionPayload) -> Value {
    let upstream = &payload.upstream;
    if upstream.upstream_type == "anthropic" || upstream.chat_path == "/v1/messages" {
        let mut body = json!({
            "model": payload.model,
            "max_tokens": upstream.max_tokens,
            "stream": false,
            "messages": [{ "role": "user", "content": payload.prompt }]
        });
        if !payload.system_prompt.trim().is_empty() {
            body["system"] = json!(payload.system_prompt);
        }
        if upstream.send_temperature {
            body["temperature"] = json!(upstream.temperature);
        }
        return body;
    }

    let mut messages = Vec::new();
    if !payload.system_prompt.trim().is_empty() {
        messages.push(json!({ "role": "system", "content": payload.system_prompt }));
    }
    messages.push(json!({ "role": "user", "content": payload.prompt }));
    let mut body = json!({
        "model": payload.model,
        "max_tokens": upstream.max_tokens,
        "stream": false,
        "messages": messages
    });
    if upstream.send_temperature {
        body["temperature"] = json!(upstream.temperature);
    }
    body
}

#[tauri::command]
fn load_config() -> Result<AppConfig, String> {
    let path = config_path()?;
    let source = if path.exists() {
        path
    } else {
        example_config_path()?
    };
    let text = std::fs::read_to_string(source).map_err(|error| error.to_string())?;
    serde_json::from_str(&text).map_err(|error| error.to_string())
}

#[tauri::command]
fn save_config(config: AppConfig) -> Result<(), String> {
    let path = config_path()?;
    let text = serde_json::to_string_pretty(&config).map_err(|error| error.to_string())?;
    std::fs::write(path, text).map_err(|error| error.to_string())
}

#[tauri::command]
async fn fetch_models(upstream: Upstream) -> Result<Vec<String>, String> {
    let response = http_client(&upstream)?
        .get(join_url(&upstream.base_url, &upstream.models_path))
        .headers(request_headers(&upstream)?)
        .send()
        .await
        .map_err(|error| error.to_string())?;
    let status = response.status();
    let text = response.text().await.map_err(|error| error.to_string())?;
    if !status.is_success() {
        return Err(format!("HTTP {}: {}", status.as_u16(), text));
    }
    let value = serde_json::from_str::<Value>(&text).map_err(|error| error.to_string())?;
    Ok(parse_models(value))
}

#[tauri::command]
async fn complete(payload: CompletionPayload) -> Result<ApiResult, String> {
    let started = Instant::now();
    let upstream = &payload.upstream;
    let response = http_client(upstream)?
        .post(join_url(&upstream.base_url, &upstream.chat_path))
        .headers(request_headers(upstream)?)
        .json(&completion_body(&payload))
        .send()
        .await
        .map_err(|error| format!("{} 请求失败：{}", payload.upstream_name, error))?;
    let status = response.status();
    let text = response.text().await.map_err(|error| error.to_string())?;
    if !status.is_success() {
        return Err(format!("HTTP {}: {}", status.as_u16(), text));
    }
    let value = serde_json::from_str::<Value>(&text).map_err(|error| error.to_string())?;
    Ok(ApiResult {
        text: extract_text(&value),
        meta: response_meta(&value),
        elapsed: started.elapsed().as_secs_f64(),
    })
}

fn main() {
    tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![
            load_config,
            save_config,
            fetch_models,
            complete
        ])
        .run(tauri::generate_context!())
        .expect("failed to run AI API Tester");
}
