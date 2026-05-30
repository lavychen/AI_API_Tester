export type UpstreamType = "anthropic" | "openai" | "newapi";

export interface Upstream {
  type: UpstreamType;
  base_url: string;
  api_key: string;
  models_path: string;
  chat_path: string;
  default_model: string;
  max_tokens: number;
  temperature: number;
  send_temperature?: boolean;
  stream: boolean;
  user_agent: string;
  no_proxy: boolean;
}

export interface AppConfig {
  default_upstream: string;
  upstreams: Record<string, Upstream>;
  templates: Record<string, string>;
}

export interface CompletionPayload {
  upstream_name: string;
  upstream: Upstream;
  model: string;
  system_prompt: string;
  prompt: string;
}

export interface ApiResult {
  text: string;
  meta: Record<string, unknown>;
  elapsed: number;
}
