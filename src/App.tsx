import { invoke as tauriInvoke } from "@tauri-apps/api/core";
import {
  Bot,
  Check,
  Cloud,
  Copy,
  Database,
  Eye,
  EyeOff,
  Gauge,
  KeyRound,
  Loader2,
  MessageSquare,
  Pencil,
  Plus,
  RefreshCw,
  Route,
  Save,
  Send,
  Settings2,
  Trash2,
  Wifi,
  WifiOff,
  X,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import type { ApiResult, AppConfig, CompletionPayload, Upstream, UpstreamType } from "./types";

const DEFAULT_USER_AGENT =
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36";

const TYPE_LABELS: Record<UpstreamType, string> = {
  anthropic: "Anthropic",
  openai: "OpenAI",
  newapi: "Gateway",
};

type ConnectionDialog = {
  mode: "new" | "edit";
  name: string;
  originalName?: string;
  upstream: Upstream;
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

function TypeIcon({ type }: { type: UpstreamType }) {
  if (type === "anthropic") {
    return <Bot size={16} />;
  }
  if (type === "newapi") {
    return <Cloud size={16} />;
  }
  return <Database size={16} />;
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
  const [dialog, setDialog] = useState<ConnectionDialog | null>(null);

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

  function nextUpstreamName() {
    let index = upstreamNames.length + 1;
    let name = `upstream-${index}`;
    while (config.upstreams[name]) {
      index += 1;
      name = `upstream-${index}`;
    }
    return name;
  }

  function openNewUpstream() {
    setShowKey(false);
    setDialog({ mode: "new", name: nextUpstreamName(), upstream: blankUpstream("openai") });
  }

  function openEditUpstream() {
    setShowKey(false);
    setDialog({
      mode: "edit",
      name: selected,
      originalName: selected,
      upstream: { ...draft, default_model: model || draft.default_model },
    });
  }

  function updateDialogUpstream<K extends keyof Upstream>(key: K, value: Upstream[K]) {
    setDialog((current) => {
      if (!current) return current;
      const upstream = { ...current.upstream, [key]: value };
      if (key === "type") {
        upstream.chat_path = value === "anthropic" ? "/v1/messages" : "/v1/chat/completions";
        upstream.send_temperature = value !== "anthropic";
      }
      return { ...current, upstream };
    });
  }

  async function saveDialog() {
    if (!dialog) return;
    const name = dialog.name.trim();
    if (!name) {
      setStatus("请输入上游名称");
      return;
    }
    if (name !== dialog.originalName && config.upstreams[name]) {
      setStatus(`上游 ${name} 已存在`);
      return;
    }

    setBusy("save");
    try {
      const next = cloneConfig(config);
      if (dialog.originalName && dialog.originalName !== name) {
        delete next.upstreams[dialog.originalName];
      }
      next.upstreams[name] = dialog.upstream;
      next.default_upstream = name;
      await invokeCommand("save_config", { config: next });
      setConfig(next);
      setSelected(name);
      setDraft(dialog.upstream);
      setModel(dialog.upstream.default_model);
      setModels([]);
      setDialog(null);
      setStatus("连接配置已保存");
    } catch (error) {
      setStatus(`保存失败：${asError(error)}`);
    } finally {
      setBusy(null);
    }
  }

  async function deleteSelectedUpstream() {
    if (!dialog?.originalName) return;
    if (upstreamNames.length <= 1) {
      setStatus("至少保留一个上游配置");
      return;
    }
    setBusy("save");
    try {
      const next = cloneConfig(config);
      delete next.upstreams[dialog.originalName];
      const name = Object.keys(next.upstreams)[0];
      next.default_upstream = name;
      await invokeCommand("save_config", { config: next });
      setConfig(next);
      setSelected(name);
      setDraft(next.upstreams[name]);
      setModel(next.upstreams[name].default_model);
      setModels([]);
      setDialog(null);
      setStatus("连接配置已删除");
    } catch (error) {
      setStatus(`删除失败：${asError(error)}`);
    } finally {
      setBusy(null);
    }
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
            <p>多上游模型测试台</p>
          </div>
        </div>

        <section className="panel upstream-panel">
          <div className="panel-title">
            <span>上游</span>
            <div className="panel-actions">
              <button className="icon-button" onClick={openNewUpstream} title="新建上游">
                <Plus size={18} />
              </button>
              <button className="icon-button" onClick={openEditUpstream} title="编辑选中上游">
                <Pencil size={16} />
              </button>
            </div>
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
            <div className="model-picker">
              <input value={model} placeholder="输入模型 ID" onChange={(event) => setModel(event.target.value)} />
              <select
                value=""
                onChange={(event) => {
                  if (event.target.value) {
                    setModel(event.target.value);
                  }
                }}
              >
                <option value="">选择模型</option>
                {models.map((item) => (
                  <option value={item} key={item}>
                    {item}
                  </option>
                ))}
              </select>
            </div>
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

        <footer className="connection-statusbar" aria-label="当前连接信息">
          <div className="connection-chip type-chip" title={TYPE_LABELS[draft.type]}>
            <TypeIcon type={draft.type} />
          </div>
          <div className="connection-chip" title={draft.base_url || "未设置 Base URL"}>
            <Cloud size={15} />
            <span>{draft.base_url || "-"}</span>
          </div>
          <div className="connection-chip" title={`模型路径：${draft.models_path}`}>
            <Route size={15} />
            <span>{draft.models_path}</span>
          </div>
          <div className="connection-chip" title={`聊天路径：${draft.chat_path}`}>
            <MessageSquare size={15} />
            <span>{draft.chat_path}</span>
          </div>
          <div className="connection-chip" title={draft.no_proxy ? "直连，不使用代理" : "使用系统代理"}>
            {draft.no_proxy ? <WifiOff size={15} /> : <Wifi size={15} />}
            <span>{draft.no_proxy ? "直连" : "系统代理"}</span>
          </div>
        </footer>
      </section>

      {dialog ? (
        <div className="modal-overlay" role="presentation">
          <section className="modal" role="dialog" aria-modal="true" aria-labelledby="connection-dialog-title">
            <header className="modal-header">
              <div>
                <div className="status-pill">{dialog.mode === "new" ? "新建" : "编辑"}</div>
                <h3 id="connection-dialog-title">{dialog.mode === "new" ? "新建上游连接" : "编辑上游连接"}</h3>
              </div>
              <button className="icon-button" onClick={() => setDialog(null)} title="关闭">
                <X size={17} />
              </button>
            </header>

            <div className="connection-form">
              <label>
                上游名称
                <input
                  value={dialog.name}
                  onChange={(event) => setDialog((current) => (current ? { ...current, name: event.target.value } : current))}
                />
              </label>

              <div className="segmented dialog-segmented" aria-label="上游类型">
                {(Object.keys(TYPE_LABELS) as UpstreamType[]).map((type) => (
                  <button
                    className={dialog.upstream.type === type ? "segment active" : "segment"}
                    key={type}
                    onClick={() => updateDialogUpstream("type", type)}
                    type="button"
                  >
                    {TYPE_LABELS[type]}
                  </button>
                ))}
              </div>

              <label className="span-2">
                Base URL
                <input
                  value={dialog.upstream.base_url}
                  onChange={(event) => updateDialogUpstream("base_url", event.target.value)}
                />
              </label>

              <label className="span-2">
                API Key
                <div className="input-with-button">
                  <input
                    type={showKey ? "text" : "password"}
                    value={dialog.upstream.api_key}
                    onChange={(event) => updateDialogUpstream("api_key", event.target.value)}
                  />
                  <button className="icon-button" onClick={() => setShowKey((value) => !value)} title="显示或隐藏密钥">
                    {showKey ? <EyeOff size={17} /> : <Eye size={17} />}
                  </button>
                </div>
              </label>

              <label>
                模型路径
                <input
                  value={dialog.upstream.models_path}
                  onChange={(event) => updateDialogUpstream("models_path", event.target.value)}
                />
              </label>
              <label>
                聊天路径
                <input
                  value={dialog.upstream.chat_path}
                  onChange={(event) => updateDialogUpstream("chat_path", event.target.value)}
                />
              </label>
              <label>
                默认模型
                <input
                  value={dialog.upstream.default_model}
                  onChange={(event) => updateDialogUpstream("default_model", event.target.value)}
                />
              </label>
              <label>
                Max Tokens
                <input
                  type="number"
                  min={1}
                  value={dialog.upstream.max_tokens}
                  onChange={(event) => updateDialogUpstream("max_tokens", Number(event.target.value))}
                />
              </label>
              <label>
                Temperature
                <input
                  type="number"
                  min={0}
                  max={2}
                  step={0.1}
                  value={dialog.upstream.temperature}
                  onChange={(event) => updateDialogUpstream("temperature", Number(event.target.value))}
                />
              </label>
              <label className="check-row dialog-check">
                <input
                  type="checkbox"
                  checked={dialog.upstream.no_proxy}
                  onChange={(event) => updateDialogUpstream("no_proxy", event.target.checked)}
                />
                <span>直连，不使用代理</span>
              </label>
              <label className="span-2">
                User-Agent
                <input
                  value={dialog.upstream.user_agent}
                  onChange={(event) => updateDialogUpstream("user_agent", event.target.value)}
                />
              </label>
            </div>

            <footer className="modal-footer">
              {dialog.mode === "edit" ? (
                <button className="secondary danger" onClick={deleteSelectedUpstream} disabled={busy === "save"}>
                  <Trash2 size={16} />
                  删除
                </button>
              ) : (
                <span />
              )}
              <div className="footer-actions">
                <button className="secondary" onClick={() => setDialog(null)}>
                  取消
                </button>
                <button onClick={saveDialog} disabled={busy === "save"}>
                  {busy === "save" ? <Loader2 className="spin" size={16} /> : <Save size={16} />}
                  保存连接
                </button>
              </div>
            </footer>
          </section>
        </div>
      ) : null}
    </main>
  );
}
