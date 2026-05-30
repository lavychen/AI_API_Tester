# Tauri + React + TypeScript version

This branch contains a desktop rewrite of AI API Tester using Tauri 2, React, TypeScript, and Vite.

## Structure

- `src/`: React + TypeScript user interface.
- `src-tauri/`: Tauri/Rust command layer for config IO and API requests.
- `package.json`: frontend and Tauri CLI scripts.
- `api_tester_config.json`: local runtime config, still ignored by Git.

## Commands

```powershell
npm install
npm run build
npm run dev
```

For the desktop shell:

```powershell
npm run tauri -- dev
npm run tauri -- build
```

The desktop commands require Rust/Cargo. On Windows, install Rust through rustup first:

```powershell
winget install Rustlang.Rustup
```

Then restart the terminal and run:

```powershell
rustup default stable
npm run tauri -- dev
```

## Current coverage

- Manage multiple upstream configs.
- Read and save the existing `api_tester_config.json` format.
- Fetch model lists.
- Send non-streaming test prompts to Anthropic, OpenAI, and NewAPI-compatible endpoints.
- Display response text, elapsed time, model, stop reason, and token usage.

Streaming output is intentionally left for a later pass because the Tauri event bridge needs a separate chunking path.
