"""带版本迁移和损坏备份的 JSON 配置存储。"""

import json
import os
import shutil
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from qserialtool.domain import (
    AppConfig,
    ConfigIOError,
    SerialConfig,
    SessionPreferences,
    ValidationError,
)

SCHEMA_VERSION = 1


def default_config_path() -> Path:
    """返回当前平台用户配置目录中的设置文件路径。"""
    if sys.platform.startswith("win"):
        base = os.environ.get("APPDATA")
        root = Path(base) if base else Path.home() / "AppData" / "Roaming"
    else:
        base = os.environ.get("XDG_CONFIG_HOME")
        root = Path(base) if base else Path.home() / ".config"
    return root / "QSerialTool" / "settings.json"


class JsonConfigStore:
    """原子写入 `settings.json` 并恢复损坏配置。"""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or default_config_path()

    def load(self) -> AppConfig | None:
        """读取配置；文件缺失时返回 None，损坏时备份后返回 None。"""
        if not self.path.exists():
            return None
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            return self._decode(payload)
        except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError, ValidationError):
            self.backup_corrupt()
            return None

    def save(self, config: AppConfig) -> None:
        """原子保存配置，并保留上一份成功配置备份。"""
        backup_path = self.path.with_suffix(".bak")
        temporary_path = self.path.with_suffix(".tmp")
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            if self.path.exists():
                shutil.copy2(self.path, backup_path)
            serialized = json.dumps(asdict(config), ensure_ascii=False, indent=2)
            with temporary_path.open("w", encoding="utf-8", newline="\n") as stream:
                stream.write(serialized)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary_path, self.path)
        except OSError as exc:
            raise ConfigIOError(f"配置保存失败：{exc}") from exc
        finally:
            if temporary_path.exists():
                temporary_path.unlink(missing_ok=True)

    def backup_corrupt(self) -> Path:
        """备份损坏配置并返回备份路径。"""
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup = self.path.with_name(f"{self.path.stem}.corrupt.{timestamp}{self.path.suffix}")
        counter = 1
        while backup.exists():
            backup = self.path.with_name(
                f"{self.path.stem}.corrupt.{timestamp}.{counter}{self.path.suffix}"
            )
            counter += 1
        try:
            shutil.copy2(self.path, backup)
        except OSError as exc:
            raise ConfigIOError(f"损坏配置备份失败：{exc}") from exc
        return backup

    @staticmethod
    def _decode(payload: Any) -> AppConfig:
        if not isinstance(payload, dict):
            raise TypeError("配置根节点必须是对象。")
        if payload.get("schema_version") != SCHEMA_VERSION:
            raise ValueError("不支持的配置 schema 版本。")
        raw_sessions = payload.get("sessions", [])
        if not isinstance(raw_sessions, list):
            raise TypeError("sessions 必须是数组。")
        sessions: list[SessionPreferences] = []
        for raw_session in raw_sessions:
            try:
                sessions.append(JsonConfigStore._decode_session(raw_session))
            except (KeyError, TypeError, ValueError, ValidationError):
                continue
        raw_active_index = payload.get("active_session_index", 0)
        active_index = min(max(int(raw_active_index), 0), len(sessions) - 1) if sessions else 0
        return AppConfig(
            schema_version=SCHEMA_VERSION,
            theme=payload.get("theme", "system"),
            window_geometry=payload.get("window_geometry"),
            window_state=payload.get("window_state"),
            active_session_index=active_index,
            sessions=tuple(sessions),
            sidebar_visible=payload.get("sidebar_visible", True),
            sidebar_width=payload.get("sidebar_width", 320),
            content_splitter_state=payload.get("content_splitter_state"),
        )

    @staticmethod
    def _decode_session(payload: Any) -> SessionPreferences:
        if not isinstance(payload, dict):
            raise TypeError("会话配置必须是对象。")
        config_payload = payload["config"]
        if not isinstance(config_payload, dict):
            raise TypeError("config 必须是对象。")
        history_payload = payload.get("send_history", [])
        if not isinstance(history_payload, list):
            raise TypeError("send_history 必须是数组。")
        return SessionPreferences(
            title=str(payload["title"]),
            config=SerialConfig(**config_payload),
            display_mode=payload.get("display_mode", "text"),
            show_timestamp=payload.get("show_timestamp", True),
            show_rx=payload.get("show_rx", True),
            show_tx=payload.get("show_tx", True),
            autoscroll=payload.get("autoscroll", True),
            auto_log_enabled=payload.get("auto_log_enabled", False),
            auto_log_format=payload.get("auto_log_format", "csv"),
            auto_log_directory=payload.get("auto_log_directory", ""),
            send_history=tuple(history_payload),
            send_mode=payload.get("send_mode", "text"),
            line_ending=payload.get("line_ending", "none"),
            periodic_interval_ms=payload.get("periodic_interval_ms", 1000),
        )
