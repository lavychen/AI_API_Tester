import { invoke as tauriInvoke } from "@tauri-apps/api/core";
import {
  Bot,
  Check,
  Copy,
  Database,
  Eye,
  EyeOff,
  Gauge,
  KeyRound,
  Loader2,
  Plus,
  RefreshCw,
  Save,
  Send,
  Settings2,
  Trash2,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import type { ApiResult, AppConfig, CompletionPayload, Upstream, UpstreamType } from "./types";

const DEFAULT_USER_AGENT =
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36";

const TYPE_LABELS: Record<UpstreamType, string> = {
  anthropic: "Anthropic",
  openai: "OpenAI",
  newapi: "NewAPI",
};

const blankUpstream = (type: UpstreamType = "openai"): Upstream => ({
  type,
  base_url: type === "anthropic" ? "https://api.anthropic.com" : "https://api.openai.com",
  api_key: "",
  models_path: "/v1/models",
  chat_path: type === "anthropic" ? "/v1/messages" : "/v1/chat/completions",
  default_model: type === "anthropic" ? "claude-opus-4-7" : "gpt-4.1",
  max_tokens: 4096,
  temperature: 0.7,
  send_temperature: type !== "anthropic",
  stream: false,
  user_agent: DEFAULT_USER_AGENT,
  no_proxy: false,
});

const fallbackConfig: AppConfig = {
  default_upstream: "demo-openai",
  upstreams: { "demo-openai": blankUpstream("openai") },
  templates: {
    smoke: "Reply with: API test OK",
    json: "请只返回 JSON，不要包含 Markdown。",
    code: "请写一个 Python 函数，并给出简短测试。",
  },
};

declare global {
  interface Window {
    __TAURI_INTERNALS__?: unknown;
  }
}

async function invokeCommand<T>(command: string, args?: Record<string, unknown>): Promise<T> {
  if (!window.__TAURI_INTERNALS__) {
    if (command === "load_config") {
      return fallbackConfig as T;
    }
    throw new Error("当前是浏览器预览模式，请在 Tauri 桌面环境中执行此操作。");
  }
  return tauriInvoke<T>(command, args);
}

function asError(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

function formatMeta(meta: Record<string, unknown>, elapsed?: number): string {
  const usage = (meta.usage ?? {}) as Record<string, unknown>;
  const input = usage.input_tokens ?? usage.prompt_tokens ?? "-";
  const output = usage.output_tokens ?? usage.completion_tokens ?? "-";
  const total = usage.total_tokens ?? "-";
  return [
    `结束原因：${String(meta.stop_reason ?? meta.finish_reason ?? "-")}`,
    `响应模型：${String(meta.model ?? "-")}`,
    `耗时：${typeof elapsed === "number" ? elapsed.toFixed(2) : "-"}s`,
    "",
    "Token 使用：",
    `输入 Token：${String(input)}`,
    `输出 Token：${String(output)}`,
    `总 Token：${String(total)}`,
  ].join("\n");
}

function cloneConfig(config: AppConfig): AppConfig {
  return JSON.parse(JSON.stringify(config)) as AppConfig;
}

export default function App() {
  const [config, setConfig] = useState<AppConfig>(fallbackConfig);
  const [selected, setSelected] = useState(fallbackConfig.default_upstream);
  const [draft, setDraft] = useState<Upstream>(fallbackConfig.upstreams[fallbackConfig.default_upstream]);
  const [models, setModels] = useState<string[]>([]);
  const [model, setModel] = useState(draft.default_model);
  const [systemPrompt, setSystemPrompt] = useState("");
  const [prompt, setPrompt] = useState("Reply with: API test OK");
  const [output, setOutput] = useState("");
  const [diagnostics, setDiagnostics] = useState("");
  const [status, setStatus] = useState("就绪");
  const [busy, setBusy] = useState<"models" | "send" | "save" | null>(null);
  const [showKey, setShowKey] = useState(false);

  const upstreamNames = useMemo(() => Object.keys(config.upstreams), [config.upstreams]);
  const templates = useMemo(() => Object.entries(config.templates ?? {}), [config.templates]);
  const isBusy = busy !== null;

  useEffect(() => {
    invokeCommand<AppConfig>("load_config")
      .then((loaded) => {
        const next = loaded.upstreams && Object.keys(loaded.upstreams).length ? loaded : fallbackConfig;
        const name = next.default_upstream || Object.keys(next.upstreams)[0];
        setConfig(next);
        setSelected(name);
        setDraft(next.upstreams[name]);
        setModel(next.upstreams[name]?.default_model ?? "");
      })
      .catch((error) => {
        setStatus(`读取配置失败：${asError(error)}`);
      });
  }, []);

  function selectUpstream(name: string) {
    const item = config.upstreams[name];
    if (!item) return;
    setSelected(name);
    setDraft({ ...item });
    setModel(item.default_model);
    setModels([]);
    setStatus(`已选择 ${name}`);
  }

  function updateDraft<K extends keyof Upstream>(key: K, value: Upstream[K]) {
    setDraft((current) => {
      const next = { ...current, [key]: value };
      if (key === "type") {
        next.chat_path = value === "anthropic" ? "/v1/messages" : "/v1/chat/completions";
        next.send_temperature = value !== "anthropic";
      }
      return next;
    });
  }

  async function saveConfig() {
    setBusy("save");
    try {
      const next = cloneConfig(config);
      next.default_upstream = selected;
      next.upstreams[selected] = { ...draft, default_model: model || draft.default_model };
      await invokeCommand("save_config", { config: next });
      setConfig(next);
      setStatus("配置已保存");
    } catch (error) {
      setStatus(`保存失败：${asError(error)}`);
    } finally {
      setBusy(null);
    }
  }

  function addUpstream() {
    let index = upstreamNames.length + 1;
    let name = `upstream-${index}`;
    while (config.upstreams[name]) {
      index += 1;
      name = `upstream-${index}`;
    }
    const next = cloneConfig(config);
    next.upstreams[name] = blankUpstream("openai");
    next.default_upstream = name;
    setConfig(next);
    setSelected(name);
    setDraft(next.upstreams[name]);
    setModel(next.upstreams[name].default_model);
    setStatus(`已新建 ${name}，保存后写入配置`);
  }

  function deleteUpstream() {
    if (upstreamNames.length <= 1) {
      setStatus("至少保留一个上游配置");
      return;
    }
    const next = cloneConfig(config);
    delete next.upstreams[selected];
    const name = Object.keys(next.upstreams)[0];
    next.default_upstream = name;
    setConfig(next);
    selectUpstream(name);
    setStatus("已删除当前上游，保存后写入配置");
  }

  async function refreshModels() {
    setBusy("models");
    setStatus("正在刷新模型列表...");
    try {
      const list = await invokeCommand<string[]>("fetch_models", { upstream: draft });
      setModels(list);
      setModel(list.includes(model) ? model : list[0] ?? model);
      setStatus(`模型已刷新，共 ${list.length} 个`);
    } catch (error) {
      setStatus(`刷新失败：${asError(error)}`);
    } finally {
      setBusy(null);
    }
  }

  async function sendPrompt() {
    if (!prompt.trim()) {
      setStatus("请输入 Prompt");
      return;
    }
    setBusy("send");
    setOutput("");
    setDiagnostics("");
    setStatus("请求中...");
    const payload: CompletionPayload = {
      upstream_name: selected,
      upstream: { ...draft, default_model: model || draft.default_model },
      model: model || draft.default_model,
      system_prompt: systemPrompt,
      prompt,
    };
    try {
      const result = await invokeCommand<ApiResult>("complete", { payload });
      setOutput(result.text);
      setDiagnostics(formatMeta(result.meta, result.elapsed));
      setStatus("完成");
    } catch (error) {
      setStatus("请求失败");
      setDiagnostics(asError(error));
    } finally {
      setBusy(null);
    }
  }

  return (
    <main className="app-shell">
      <aside className="sidebar">
        <div className="brand-row">
          <div className="brand-mark">
            <Bot size={24} />
          </div>
          <div>
            <h1>AI API Tester</h1>
            <p>Tauri desktop client</p>
          </div>
        </div>

        <section className="panel upstream-panel">
          <div className="panel-title">
            <span>上游</span>
            <button className="icon-button" onClick={addUpstream} title="新建上游">
              <Plus size={18} />
            </button>
          </div>
          <div className="upstream-list">
            {upstreamNames.map((name) => (
              <button
                className={name === selected ? "upstream-item active" : "upstream-item"}
                key={name}
                onClick={() => selectUpstream(name)}
              >
                <span className="upstream-name">{name}</span>
                <span className="upstream-meta">
                  {TYPE_LABELS[config.upstreams[name].type]}
                  {name === config.default_upstream ? <Check size={14} /> : null}
                </span>
              </button>
            ))}
          </div>
        </section>

        <section className="panel form-panel">
          <div className="panel-title">
            <span>连接</span>
            <Settings2 size={17} />
          </div>

          <div className="segmented" aria-label="上游类型">
            {(Object.keys(TYPE_LABELS) as UpstreamType[]).map((type) => (
              <button
                className={draft.type === type ? "segment active" : "segment"}
                key={type}
                onClick={() => updateDraft("type", type)}
                type="button"
              >
                {TYPE_LABELS[type]}
              </button>
            ))}
          </div>

          <label>
            Base URL
            <input value={draft.base_url} onChange={(event) => updateDraft("base_url", event.target.value)} />
          </label>
          <label>
            API Key
            <div className="input-with-button">
              <input
                type={showKey ? "text" : "password"}
                value={draft.api_key}
                onChange={(event) => updateDraft("api_key", event.target.value)}
              />
              <button className="icon-button" onClick={() => setShowKey((value) => !value)} title="显示或隐藏密钥">
                {showKey ? <EyeOff size={17} /> : <Eye size={17} />}
              </button>
            </div>
          </label>
          <div className="split-fields">
            <label>
              模型路径
              <input value={draft.models_path} onChange={(event) => updateDraft("models_path", event.target.value)} />
            </label>
            <label>
              聊天路径
              <input value={draft.chat_path} onChange={(event) => updateDraft("chat_path", event.target.value)} />
            </label>
          </div>
          <label>
            User-Agent
            <input value={draft.user_agent} onChange={(event) => updateDraft("user_agent", event.target.value)} />
          </label>
          <div className="split-fields">
            <label>
              Max Tokens
              <input
                type="number"
                min={1}
                value={draft.max_tokens}
                onChange={(event) => updateDraft("max_tokens", Number(event.target.value))}
              />
            </label>
            <label>
              Temperature
              <input
                type="number"
                min={0}
                max={2}
                step={0.1}
                value={draft.temperature}
                onChange={(event) => updateDraft("temperature", Number(event.target.value))}
              />
            </label>
          </div>
          <label className="check-row">
            <input
              type="checkbox"
              checked={draft.no_proxy}
              onChange={(event) => updateDraft("no_proxy", event.target.checked)}
            />
            直连，不使用代理
          </label>
          <div className="action-row">
            <button className="secondary danger" onClick={deleteUpstream} title="删除当前上游">
              <Trash2 size={16} />
              删除
            </button>
            <button onClick={saveConfig} disabled={busy === "save"}>
              {busy === "save" ? <Loader2 className="spin" size={16} /> : <Save size={16} />}
              保存
            </button>
          </div>
        </section>
      </aside>

      <section className="workspace">
        <header className="topbar">
          <div>
            <div className={isBusy ? "status-pill active" : "status-pill"}>{status}</div>
            <h2>{selected}</h2>
          </div>
          <div className="top-stats">
            <div className="stat">
              <Database size={16} />
              <span>{models.length ? `${models.length} models` : "models not loaded"}</span>
            </div>
            <div className="stat">
              <KeyRound size={16} />
              <span>{draft.api_key ? "key set" : "no key"}</span>
            </div>
            <div className="stat">
              <Gauge size={16} />
              <span>{draft.max_tokens} tokens</span>
            </div>
          </div>
        </header>

        <div className="command-bar">
          <label className="model-control">
            模型
            <input
              list="model-options"
              value={model}
              placeholder="选择或输入模型 ID"
              onChange={(event) => setModel(event.target.value)}
            />
            <datalist id="model-options">
              {models.map((item) => (
                <option value={item} key={item} />
              ))}
            </datalist>
          </label>
          <button className="secondary" onClick={refreshModels} disabled={busy === "models"}>
            {busy === "models" ? <Loader2 className="spin" size={16} /> : <RefreshCw size={16} />}
            刷新模型
          </button>
          <button className="primary-action" onClick={sendPrompt} disabled={busy === "send"}>
            {busy === "send" ? <Loader2 className="spin" size={16} /> : <Send size={16} />}
            开始测试
          </button>
        </div>

        <div className="prompt-grid">
          <section className="editor-panel">
            <div className="panel-title">
              <span>Prompt</span>
              <select onChange={(event) => event.target.value && setPrompt(event.target.value)} value="">
                <option value="">模板</option>
                {templates.map(([name, value]) => (
                  <option value={value} key={name}>
                    {name}
                  </option>
                ))}
              </select>
            </div>
            <textarea value={prompt} onChange={(event) => setPrompt(event.target.value)} />
          </section>
          <section className="editor-panel">
            <div className="panel-title">
              <span>System Prompt</span>
            </div>
            <textarea value={systemPrompt} onChange={(event) => setSystemPrompt(event.target.value)} />
          </section>
        </div>

        <div className="result-grid">
          <section className="result-panel">
            <div className="panel-title">
              <span>响应</span>
              <button
                className="icon-button"
                onClick={() => navigator.clipboard.writeText(output)}
                title="复制响应"
                disabled={!output}
              >
                <Copy size={17} />
              </button>
            </div>
            <pre>{output || "等待测试结果..."}</pre>
          </section>
          <section className="result-panel diagnostics">
            <div className="panel-title">
              <span>诊断</span>
            </div>
            <pre>{diagnostics || status}</pre>
          </section>
        </div>
      </section>
    </main>
  );
}
