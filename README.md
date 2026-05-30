# AI API Tester

AI API Tester 是一个轻量级多上游 AI 接口测试工具，提供 PySide6 图形界面和命令行两种用法。它适合快速验证 OpenAI 兼容接口、Anthropic Claude 接口以及 NewAPI 类网关的模型列表、流式输出、Token 统计和错误诊断。

## 功能

- 管理多个上游配置，支持新增、保存、重命名、删除和快速切换
- 刷新模型列表，并从下拉框中选择模型
- 支持 OpenAI / NewAPI `/v1/chat/completions`
- 支持 Anthropic `/v1/messages`
- 支持流式输出和非流式输出
- 支持 System Prompt、用户 Prompt、模板 Prompt
- 支持可选 `temperature`、`max_tokens`、代理直连开关和自定义 `User-Agent`
- CLI 可列出上游、刷新模型、发送 Prompt，并按需保存历史

## 目录

```text
AI_API_Tester/
  api_tester_core.py              # API 请求、模型解析、流式响应解析等核心逻辑
  api_tester_pyside6.py           # PySide6 GUI
  api_tester_cli.py               # 命令行入口
  api_tester_config.example.json  # 配置示例，不包含真实密钥
  requirements-pyside6.txt        # GUI 依赖
  assets/                         # GUI 资源
```

## 环境要求

- Python 3.10 或更高版本
- Windows / macOS / Linux 均可运行
- GUI 需要安装 PySide6

## 安装

```bash
cd AI_API_Tester
python -m venv .venv
```

Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
pip install -r requirements-pyside6.txt
```

macOS / Linux:

```bash
source .venv/bin/activate
pip install -r requirements-pyside6.txt
```

## 配置

复制示例配置：

```bash
cp api_tester_config.example.json api_tester_config.json
```

Windows PowerShell:

```powershell
Copy-Item api_tester_config.example.json api_tester_config.json
```

然后编辑 `api_tester_config.json`，填入你的 `base_url`、`api_key`、默认模型等信息。

常见路径：

```json
{
  "type": "openai",
  "models_path": "/v1/models",
  "chat_path": "/v1/chat/completions"
}
```

```json
{
  "type": "anthropic",
  "models_path": "/v1/models",
  "chat_path": "/v1/messages"
}
```

注意：`api_tester_config.json` 已加入 `.gitignore`，请不要提交真实 API Key。

## 运行 GUI

```bash
python api_tester_pyside6.py
```

GUI 中可以：

- 在左侧选择或管理上游配置
- 点击“刷新模型”获取模型列表
- 输入 Prompt 并点击“开始测试”
- 在右侧查看响应和诊断信息

## 运行 CLI

列出上游：

```bash
python api_tester_cli.py --list-upstreams
```

列出指定上游模型：

```bash
python api_tester_cli.py --upstream demo-openai --list-models
```

发送一次测试请求：

```bash
python api_tester_cli.py --upstream demo-openai --model gpt-4.1 --prompt "Reply with: API test OK"
```

使用模板并保存历史：

```bash
python api_tester_cli.py --upstream demo-anthropic --template smoke --save-history
```

## 打包部署

可以用 PyInstaller 打包为本机可执行文件：

```bash
pip install pyinstaller
pyinstaller --noconsole --onefile --add-data "assets;assets" api_tester_pyside6.py
```

macOS / Linux 的 `--add-data` 分隔符使用冒号：

```bash
pyinstaller --noconsole --onefile --add-data "assets:assets" api_tester_pyside6.py
```

打包产物位于 `dist/`。首次运行前请将 `api_tester_config.example.json` 复制为 `api_tester_config.json`，并放在程序同目录或源码目录中使用。

## GitHub 发布流程

初始化仓库并提交：

```bash
git init
git add .
git commit -m "Initial commit"
```

关联 GitHub 空仓库并推送：

```bash
git branch -M main
git remote add origin https://github.com/<your-name>/<repo-name>.git
git push -u origin main
```

如果使用 SSH：

```bash
git remote add origin git@github.com:<your-name>/<repo-name>.git
git push -u origin main
```

## 安全说明

- 不要提交 `api_tester_config.json`
- 不要提交 `Data/history/`
- 如果误提交过 API Key，请立即在服务商后台轮换密钥
