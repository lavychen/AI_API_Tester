#!/usr/bin/env python3
from __future__ import annotations

import sys
import threading
import traceback
import urllib.error

try:
    from PySide6.QtCore import QObject, Qt, Signal
    from PySide6.QtWidgets import (
        QApplication,
        QCheckBox,
        QComboBox,
        QFormLayout,
        QGroupBox,
        QGridLayout,
        QHBoxLayout,
        QInputDialog,
        QLabel,
        QLineEdit,
        QListWidget,
        QMainWindow,
        QMessageBox,
        QPushButton,
        QSizePolicy,
        QSplitter,
        QTabWidget,
        QTextEdit,
        QVBoxLayout,
        QWidget,
    )
except ModuleNotFoundError as exc:  # pragma: no cover
    print("PySide6 is not installed. Install it with: pip install -r requirements-pyside6.txt", file=sys.stderr)
    raise SystemExit(2) from exc

from api_tester_core import (
    APP_DIR,
    DEFAULT_USER_AGENT,
    ApiClient,
    explain_http_error,
    format_meta,
    load_app_config,
    safe_float,
    safe_int,
    save_app_config,
)


class Worker(QObject):
    text = Signal(str)
    status = Signal(str)
    done = Signal(str, dict)
    models = Signal(list)
    error = Signal(str)

    def __init__(self, mode: str, upstream: dict, payload: dict | None = None):
        super().__init__()
        self.mode = mode
        self.upstream = upstream
        self.payload = payload or {}

    def run(self) -> None:
        try:
            client = ApiClient(self.upstream)
            if self.mode == "models":
                self.status.emit("正在刷新模型...")
                self.models.emit(client.fetch_models())
                self.status.emit("模型已刷新")
                return
            self.status.emit("请求中...")
            result = client.complete(self.payload, on_text=lambda chunk: self.text.emit(chunk))
            self.done.emit(result.text, result.meta)
            self.status.emit("完成")
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            self.error.emit(explain_http_error(exc.code, body) + "\n\n" + body[:4000])
        except Exception:
            self.error.emit(traceback.format_exc())


class ApiTesterWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AI API 测试器 - PySide6")
        self.resize(1440, 900)
        self.config = load_app_config()
        self.worker_thread: threading.Thread | None = None
        self.build_ui()
        self.apply_style()
        self.load_upstreams()
        self.load_templates()

    def build_ui(self) -> None:
        self.statusBar().showMessage("就绪")

        root = QWidget()
        layout = QHBoxLayout(root)
        layout.setContentsMargins(14, 14, 14, 14)
        self.setCentralWidget(root)

        splitter = QSplitter(Qt.Horizontal)
        layout.addWidget(splitter)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 10, 0)
        left_layout.setSpacing(12)
        left_layout.setAlignment(Qt.AlignTop)
        splitter.addWidget(left)

        config_group = QGroupBox()
        config_layout = QVBoxLayout(config_group)
        config_layout.setContentsMargins(12, 14, 12, 12)
        config_layout.setSpacing(8)
        self.upstream_combo = QComboBox()
        self.upstream_combo.currentTextChanged.connect(self.load_selected_upstream)
        config_layout.addWidget(QLabel("上游"))
        config_layout.addWidget(self.upstream_combo)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignLeft)
        form.setFormAlignment(Qt.AlignTop)
        form.setVerticalSpacing(8)
        self.type_combo = QComboBox()
        self.type_combo.addItems(["anthropic", "openai", "newapi"])
        self.type_combo.currentTextChanged.connect(self.apply_type_defaults)
        self.base_url = QLineEdit()
        self.api_key = QLineEdit()
        self.api_key.setEchoMode(QLineEdit.Password)
        self.models_path = QLineEdit()
        self.chat_path = QLineEdit()
        self.default_model = QLineEdit()
        self.user_agent = QLineEdit()
        self.no_proxy = QCheckBox("直连，不使用代理")
        for label, widget in [
            ("类型", self.type_combo),
            ("Base URL", self.base_url),
            ("API Key", self.api_key),
            ("模型路径", self.models_path),
            ("聊天路径", self.chat_path),
            ("默认模型", self.default_model),
            ("User-Agent", self.user_agent),
        ]:
            form.addRow(label, widget)
        form.addRow("", self.no_proxy)
        config_layout.addLayout(form)

        button_row = QHBoxLayout()
        self.new_upstream_btn = QPushButton("新建")
        self.new_upstream_btn.clicked.connect(self.new_upstream)
        self.refresh_models_btn = QPushButton("刷新模型")
        self.refresh_models_btn.clicked.connect(self.refresh_models)
        self.refresh_models_btn.setObjectName("refreshModelsButton")
        self.save_btn = QPushButton("保存")
        self.save_btn.clicked.connect(self.save_current_upstream)
        button_row.addWidget(self.new_upstream_btn)
        button_row.addWidget(self.save_btn)
        config_layout.addLayout(button_row)
        left_layout.addWidget(config_group)

        upstreams_group = QGroupBox("已配置上游")
        upstreams_layout = QVBoxLayout(upstreams_group)
        upstreams_layout.setContentsMargins(12, 14, 12, 12)
        upstreams_layout.setSpacing(8)
        self.upstream_list = QListWidget()
        self.upstream_list.itemClicked.connect(self.select_upstream_from_list)
        self.upstream_list.itemDoubleClicked.connect(self.select_upstream_from_list)
        upstreams_layout.addWidget(self.upstream_list, 1)

        upstream_actions = QHBoxLayout()
        self.rename_upstream_btn = QPushButton("修改名称")
        self.rename_upstream_btn.clicked.connect(self.rename_upstream)
        self.delete_upstream_btn = QPushButton("删除")
        self.delete_upstream_btn.setObjectName("dangerButton")
        self.delete_upstream_btn.clicked.connect(self.delete_upstream)
        upstream_actions.addWidget(self.rename_upstream_btn)
        upstream_actions.addWidget(self.delete_upstream_btn)
        upstreams_layout.addLayout(upstream_actions)
        left_layout.addWidget(upstreams_group, 1)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        splitter.addWidget(right)
        splitter.setSizes([390, 1050])

        controls = QGridLayout()
        controls.setHorizontalSpacing(10)
        controls.setVerticalSpacing(8)
        self.model_combo = QComboBox()
        self.model_combo.setEditable(True)
        self.model_combo.setMinimumWidth(320)
        self.model_combo.setMaximumWidth(520)
        self.model_combo.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self.max_tokens = QLineEdit("4096")
        self.max_tokens.setFixedWidth(92)
        self.temperature = QLineEdit("0.7")
        self.temperature.setFixedWidth(78)
        self.send_temperature = QCheckBox("发送温度")
        self.stream = QCheckBox("流式")
        self.stream.setChecked(True)
        self.template_combo = QComboBox()
        self.template_combo.setMinimumWidth(150)
        self.template_combo.currentTextChanged.connect(self.apply_template)
        self.run_btn = QPushButton("开始测试")
        self.run_btn.setObjectName("runButton")
        self.run_btn.clicked.connect(self.run_test)

        controls.addWidget(QLabel("模型"), 0, 0)
        controls.addWidget(self.model_combo, 0, 1, 1, 3)
        controls.addWidget(self.refresh_models_btn, 0, 4)
        controls.addWidget(QLabel("模板"), 0, 5)
        controls.addWidget(self.template_combo, 0, 6, 1, 2)
        controls.addWidget(self.run_btn, 0, 8, 1, 2)

        controls.addWidget(QLabel("Max"), 1, 0)
        controls.addWidget(self.max_tokens, 1, 1)
        controls.addWidget(QLabel("温度"), 1, 2)
        controls.addWidget(self.temperature, 1, 3)
        controls.addWidget(self.send_temperature, 1, 4, 1, 2)
        controls.addWidget(self.stream, 1, 6)
        controls.setColumnStretch(1, 3)
        controls.setColumnStretch(2, 1)
        controls.setColumnStretch(7, 2)
        controls.setColumnStretch(9, 1)
        right_layout.addLayout(controls)

        io_splitter = QSplitter(Qt.Horizontal)
        right_layout.addWidget(io_splitter, 1)

        request_tabs = QTabWidget()
        self.user_prompt = QTextEdit()
        self.system_prompt = QTextEdit()
        request_tabs.addTab(self.user_prompt, "用户 Prompt")
        request_tabs.addTab(self.system_prompt, "System Prompt")
        io_splitter.addWidget(request_tabs)

        response_tabs = QTabWidget()
        self.response = QTextEdit()
        self.response.setReadOnly(True)
        self.diagnostics = QTextEdit()
        self.diagnostics.setReadOnly(True)
        response_tabs.addTab(self.response, "响应")
        response_tabs.addTab(self.diagnostics, "诊断")
        io_splitter.addWidget(response_tabs)
        io_splitter.setSizes([560, 700])

    def apply_style(self) -> None:
        arrow_path = (APP_DIR / "assets" / "chevron-down.svg").resolve().as_posix()
        stylesheet = """
            QMainWindow { background: #f4f7fb; }
            QMenuBar { background: #f4f7fb; padding: 4px; }
            QWidget { font-family: "Microsoft YaHei UI", "Segoe UI"; font-size: 13px; color: #172033; }
            QGroupBox {
                background: #ffffff;
                border: 1px solid #d8e2ef;
                border-radius: 8px;
                margin-top: 0;
                padding: 0;
                font-weight: 600;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 6px;
                color: #0f172a;
            }
            QLabel { color: #172033; }
            QLineEdit, QTextEdit, QComboBox {
                background: #ffffff;
                border: 1px solid #d8e2ef;
                border-radius: 7px;
                padding: 7px;
                min-height: 22px;
            }
            QLineEdit:focus, QTextEdit:focus, QComboBox:focus { border: 1px solid #2563eb; }
            QListWidget {
                background: #ffffff;
                border: 1px solid #d8e2ef;
                border-radius: 7px;
                padding: 6px;
                outline: 0;
            }
            QListWidget::item {
                min-height: 30px;
                padding: 5px 8px;
                border-radius: 6px;
            }
            QListWidget::item:hover {
                background: #eef4ff;
            }
            QListWidget::item:selected {
                background: #dbeafe;
                color: #0f172a;
            }
            QComboBox {
                padding-right: 42px;
            }
            QComboBox::drop-down {
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 40px;
                border-left: 1px solid #d8e2ef;
                border-top-right-radius: 7px;
                border-bottom-right-radius: 7px;
                background: #f8fafc;
            }
            QComboBox::drop-down:hover {
                background: #eaf1fb;
            }
            QComboBox::down-arrow {
                image: url("__ARROW_PATH__");
                width: 18px;
                height: 18px;
                margin-right: 11px;
            }
            QComboBox QAbstractItemView {
                border: 1px solid #cbd5e1;
                border-radius: 7px;
                padding: 4px;
                background: #ffffff;
                selection-background-color: #dbeafe;
                selection-color: #0f172a;
                outline: 0;
            }
            QTextEdit { selection-background-color: #2563eb; }
            QPushButton { background: #edf2f7; border: 1px solid #d8e2ef; border-radius: 7px; padding: 8px 12px; min-height: 24px; }
            QPushButton:hover { background: #e2eaf5; }
            QPushButton:pressed { background: #d6e1ee; }
            QPushButton#refreshModelsButton { min-width: 88px; }
            QPushButton#runButton { background: #2563eb; border-color: #1d4ed8; color: #ffffff; font-weight: 600; }
            QPushButton#runButton:hover { background: #1d4ed8; }
            QPushButton#runButton:pressed { background: #1e40af; }
            QPushButton#dangerButton:hover { background: #fee2e2; border-color: #fecaca; color: #991b1b; }
            QPushButton#dangerButton:pressed { background: #fecaca; }
            QTabWidget::pane { border: 1px solid #d8e2ef; border-radius: 8px; background: white; }
            QTabBar::tab { background: #e7eef8; border: 1px solid #d8e2ef; padding: 8px 14px; border-top-left-radius: 6px; border-top-right-radius: 6px; }
            QTabBar::tab:selected { background: white; color: #2563eb; }
            """
        self.setStyleSheet(stylesheet.replace("__ARROW_PATH__", arrow_path))

    def load_upstreams(self) -> None:
        names = list(self.config.get("upstreams", {}).keys())
        selected = self.config.get("default_upstream", "") or (names[0] if names else "")

        self.upstream_combo.blockSignals(True)
        self.upstream_combo.clear()
        self.upstream_combo.addItems(names)
        if selected:
            self.upstream_combo.setCurrentText(selected)
        self.upstream_combo.blockSignals(False)

        self.refresh_upstream_list(selected)
        self.load_selected_upstream()

    def refresh_upstream_list(self, selected: str = "") -> None:
        self.upstream_list.blockSignals(True)
        self.upstream_list.clear()
        self.upstream_list.addItems(list(self.config.get("upstreams", {}).keys()))
        if selected:
            matches = self.upstream_list.findItems(selected, Qt.MatchExactly)
            if matches:
                self.upstream_list.setCurrentItem(matches[0])
        self.upstream_list.blockSignals(False)

    def load_templates(self) -> None:
        self.template_combo.clear()
        self.template_combo.addItems(list(self.config.get("templates", {}).keys()))

    def current_upstream_name(self) -> str:
        return self.upstream_combo.currentText()

    def current_upstream(self) -> dict:
        self.save_form_to_memory()
        return dict(self.config["upstreams"][self.current_upstream_name()])

    def new_upstream(self) -> None:
        name, ok = QInputDialog.getText(self, "新建上游", "上游名称：", text="new-upstream")
        if not ok or not name.strip():
            return
        name = name.strip()
        upstreams = self.config.setdefault("upstreams", {})
        base = name
        index = 2
        while name in upstreams:
            name = f"{base}-{index}"
            index += 1
        upstreams[name] = {
            "type": "openai",
            "base_url": "",
            "api_key": "",
            "models_path": "/v1/models",
            "chat_path": "/v1/chat/completions",
            "default_model": "",
            "max_tokens": 4096,
            "temperature": 0.7,
            "send_temperature": False,
            "stream": True,
            "user_agent": DEFAULT_USER_AGENT,
            "no_proxy": False,
        }
        self.config["default_upstream"] = name
        self.load_upstreams()
        self.upstream_combo.setCurrentText(name)

    def selected_upstream_name(self) -> str:
        item = self.upstream_list.currentItem()
        return item.text() if item else self.current_upstream_name()

    def select_upstream_from_list(self, item) -> None:
        if not item:
            return
        name = item.text()
        self.upstream_combo.setCurrentText(name)
        if self.current_upstream_name() == name:
            self.load_selected_upstream()

    def rename_upstream(self) -> None:
        old_name = self.selected_upstream_name()
        if not old_name:
            return
        new_name, ok = QInputDialog.getText(self, "修改上游名称", "上游名称：", text=old_name)
        if not ok:
            return
        new_name = new_name.strip()
        upstreams = self.config.setdefault("upstreams", {})
        if not new_name or new_name == old_name:
            return
        if new_name in upstreams:
            QMessageBox.warning(self, "名称重复", "这个上游名称已经存在。")
            return
        upstreams[new_name] = upstreams.pop(old_name)
        if self.config.get("default_upstream") == old_name:
            self.config["default_upstream"] = new_name
        self.load_upstreams()
        self.upstream_combo.setCurrentText(new_name)
        save_app_config(self.config)
        self.statusBar().showMessage("上游名称已修改")

    def delete_upstream(self) -> None:
        name = self.selected_upstream_name()
        upstreams = self.config.setdefault("upstreams", {})
        if not name or name not in upstreams:
            return
        if len(upstreams) <= 1:
            QMessageBox.warning(self, "无法删除", "至少需要保留一个上游配置。")
            return
        reply = QMessageBox.question(self, "删除上游", f"确定删除上游「{name}」吗？")
        if reply != QMessageBox.Yes:
            return
        upstreams.pop(name)
        if self.config.get("default_upstream") == name:
            self.config["default_upstream"] = next(iter(upstreams), "")
        self.load_upstreams()
        save_app_config(self.config)
        self.statusBar().showMessage("上游已删除")

    def apply_type_defaults(self, upstream_type: str) -> None:
        if upstream_type in {"openai", "newapi"}:
            self.chat_path.setText("/v1/chat/completions")
        else:
            self.chat_path.setText("/v1/messages")

    def load_selected_upstream(self) -> None:
        name = self.current_upstream_name()
        if name:
            self.config["default_upstream"] = name
            self.refresh_upstream_list(name)
        data = self.config.get("upstreams", {}).get(name, {})
        self.type_combo.setCurrentText(data.get("type", "anthropic"))
        self.base_url.setText(data.get("base_url", ""))
        self.api_key.setText(data.get("api_key", ""))
        self.models_path.setText(data.get("models_path", "/v1/models"))
        self.chat_path.setText(data.get("chat_path", "/v1/messages"))
        self.default_model.setText(data.get("default_model", ""))
        self.user_agent.setText(data.get("user_agent", ""))
        self.no_proxy.setChecked(bool(data.get("no_proxy", False)))
        self.model_combo.setCurrentText(data.get("default_model", ""))
        self.max_tokens.setText(str(data.get("max_tokens", 4096)))
        self.temperature.setText(str(data.get("temperature", 0.7)))
        self.send_temperature.setChecked(bool(data.get("send_temperature", False)))
        self.stream.setChecked(bool(data.get("stream", True)))

    def save_form_to_memory(self) -> None:
        name = self.current_upstream_name()
        if not name:
            return
        self.config.setdefault("upstreams", {}).setdefault(name, {}).update({
            "type": self.type_combo.currentText(),
            "base_url": self.base_url.text().strip(),
            "api_key": self.api_key.text().strip(),
            "models_path": self.models_path.text().strip(),
            "chat_path": self.chat_path.text().strip(),
            "default_model": self.model_combo.currentText().strip() or self.default_model.text().strip(),
            "max_tokens": int(self.max_tokens.text() or 4096),
            "temperature": float(self.temperature.text() or 0.7),
            "send_temperature": self.send_temperature.isChecked(),
            "stream": self.stream.isChecked(),
            "user_agent": self.user_agent.text().strip(),
            "no_proxy": self.no_proxy.isChecked(),
        })

    def save_current_upstream(self) -> None:
        self.save_form_to_memory()
        save_app_config(self.config)
        self.statusBar().showMessage("配置已保存")

    def apply_template(self) -> None:
        text = self.config.get("templates", {}).get(self.template_combo.currentText(), "")
        if text:
            self.user_prompt.setPlainText(text)

    def refresh_models(self) -> None:
        self.start_worker("models", None)

    def run_test(self) -> None:
        payload = {
            "model": self.model_combo.currentText().strip(),
            "prompt": self.user_prompt.toPlainText().strip(),
            "system_prompt": self.system_prompt.toPlainText().strip(),
            "max_tokens": int(self.max_tokens.text() or 4096),
            "temperature": float(self.temperature.text() or 0.7),
            "send_temperature": self.send_temperature.isChecked(),
            "stream": self.stream.isChecked(),
        }
        if not payload["model"] or not payload["prompt"]:
            QMessageBox.warning(self, "缺少输入", "请填写模型和用户 Prompt。")
            return
        self.response.clear()
        self.diagnostics.clear()
        self.start_worker("test", payload)

    def start_worker(self, mode: str, payload: dict | None) -> None:
        worker = Worker(mode, self.current_upstream(), payload)
        worker.text.connect(self.response.insertPlainText)
        worker.status.connect(self.statusBar().showMessage)
        worker.models.connect(self.on_models)
        worker.done.connect(self.on_done)
        worker.error.connect(self.on_error)
        self.worker_thread = threading.Thread(target=worker.run, daemon=True)
        self.worker_ref = worker
        self.worker_thread.start()

    def on_models(self, models: list) -> None:
        self.model_combo.clear()
        self.model_combo.addItems(models)

    def on_done(self, _text: str, meta: dict) -> None:
        self.diagnostics.setPlainText(format_meta(meta))

    def on_error(self, message: str) -> None:
        self.diagnostics.setPlainText(message)
        self.statusBar().showMessage("错误")


def main() -> int:
    app = QApplication(sys.argv)
    window = ApiTesterWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
