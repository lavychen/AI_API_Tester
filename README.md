# AI API Tester

AI API Tester 是一个轻量级多上游 AI 接口测试工具，用于快速验证 OpenAI 兼容接口、NewAPI 类网关以及 Anthropic Claude 接口的模型列表、Prompt 请求、流式输出、Token 用量和错误诊断。

当前推荐使用 Tauri + React + TypeScript 桌面版。仓库中也保留了早期 Python PySide6 GUI 和 CLI，便于脚本化和兼容旧流程。

## 下载

Windows 用户可以直接下载绿色版压缩包：

[AI_API_Tester-v0.2.0-windows-portable.zip](https://github.com/lavychen/AI_API_Tester/releases/download/v0.2.0/AI_API_Tester-v0.2.0-windows-portable.zip)

下载后解压，双击 `AI_API_Tester.exe` 即可运行。

注意：

- 目标电脑需要 Microsoft Edge WebView2 Runtime。Windows 10/11 通常已自带。
- 绿色版不需要安装，但应用会在本地保存连接配置和提示词模板。
- 如果换目录运行，配置文件位置可能随运行目录变化。

更多版本见 [GitHub Releases](https://github.com/lavychen/AI_API_Tester/releases)。

## 功能

- 管理多个上游配置，支持新增、编辑、删除和快速切换。
- 支持 OpenAI 兼容接口、NewAPI 类网关和 Anthropic `/v1/messages`。
- 支持刷新模型列表，也可以手动输入模型 ID。
- 支持 System Prompt、用户 Prompt 和可编辑提示词模板。
- 支持流式输出、temperature、max tokens、直连/代理开关和自定义 User-Agent。
- 显示响应正文、耗时、响应模型、结束原因和 Token 使用情况。
- 保留 Python CLI，可用于列出上游、刷新模型、发送 Prompt 和保存历史。

## 目录

```text
AI_API_Tester/
  src/                           # React + TypeScript 前端
  src-tauri/                     # Tauri / Rust 桌面壳和后端命令
  package.json                   # Tauri 桌面版脚本和前端依赖
  TAURI_REACT_TS.md              # Tauri 桌面版补充说明

  api_tester_core.py             # Python API 请求、模型解析、响应解析等核心逻辑
  api_tester_pyside6.py          # Python PySide6 GUI
  api_tester_cli.py              # Python CLI
  api_tester_config.example.json # 配置示例，不包含真实密钥
  requirements-pyside6.txt       # Python GUI 依赖
  assets/                        # Python GUI 资源
```

## 配置

复制示例配置：

```powershell
Copy-Item api_tester_config.example.json api_tester_config.json
```

然后编辑 `api_tester_config.json`，填写你的 `base_url`、`api_key`、默认模型等信息。

OpenAI 兼容接口常见路径：

```json
{
  "type": "openai",
  "models_path": "/v1/models",
  "chat_path": "/v1/chat/completions"
}
```

Anthropic 常见路径：

```json
{
  "type": "anthropic",
  "models_path": "/v1/models",
  "chat_path": "/v1/messages"
}
```

注意：`api_tester_config.json` 已加入 `.gitignore`，不要提交真实 API Key。

## 开发 Tauri 桌面版

环境要求：

- Node.js 20 或更高版本
- Rust stable toolchain
- Windows 需要 WebView2 和 MSVC Build Tools

安装依赖：

```powershell
npm install
```

启动桌面开发版：

```powershell
npm run tauri -- dev
```

仅预览前端：

```powershell
npm run dev
```

构建前端：

```powershell
npm run build
```

构建可直接运行的 Windows exe：

```powershell
npm run tauri -- build --no-bundle
```

产物位于：

```text
src-tauri/target/release/ai-api-tester.exe
```

构建完整安装包：

```powershell
npm run tauri -- build
```

Windows 打安装包时，Tauri 可能会下载 WiX Toolset；如果网络较慢，可以先使用 `--no-bundle` 生成绿色版 exe。

## 发布 Release

仓库已配置 GitHub Actions 自动发布流程。推送版本 tag 后，会自动在 Windows runner 上构建 Tauri exe、打包 portable zip，并创建 GitHub Release。

示例：

```powershell
git tag v0.2.1
git push origin v0.2.1
```

## 运行 Python GUI

环境要求：

- Python 3.10 或更高版本
- Windows / macOS / Linux 均可运行
- GUI 需要安装 PySide6

安装依赖：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-pyside6.txt
```

启动：

```powershell
python api_tester_pyside6.py
```

## 运行 Python CLI

列出上游：

```powershell
python api_tester_cli.py --list-upstreams
```

列出指定上游模型：

```powershell
python api_tester_cli.py --upstream demo-openai --list-models
```

发送一次测试请求：

```powershell
python api_tester_cli.py --upstream demo-openai --model gpt-4.1 --prompt "Reply with: API test OK"
```

使用模板并保存历史：

```powershell
python api_tester_cli.py --upstream demo-anthropic --template smoke --save-history
```

## 打包 Python GUI

也可以继续使用 PyInstaller 打包旧版 Python GUI：

```powershell
pip install pyinstaller
pyinstaller --noconsole --onefile --add-data "assets;assets" api_tester_pyside6.py
```

打包产物位于 `dist/`。

## 安全说明

- 不要提交 `api_tester_config.json`。
- 不要提交 `Data/history/`。
- 不要提交真实 API Key、代理凭据或内部网关地址。
- 如果误提交过 API Key，请立即到服务商后台轮换密钥。

## 开源协议

本项目基于 [MIT License](LICENSE) 开源。
