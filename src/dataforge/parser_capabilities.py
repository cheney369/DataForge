from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from threading import Lock
from typing import Any

from .config import Settings


class ParserCapabilities:
    """Detect optional parser runtimes without importing their heavy dependencies."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self._lock = Lock()
        self._mineru: dict[str, Any] | None = None

    def describe(self, *, refresh: bool = False) -> dict[str, Any]:
        return {
            "native": {
                "available": True,
                "in_use": True,
                "supported_suffixes": [
                    ".csv",
                    ".docx",
                    ".json",
                    ".jsonl",
                    ".md",
                    ".pdf",
                    ".txt",
                    ".xlsx",
                ],
            },
            "mineru": self.mineru(refresh=refresh),
        }

    def mineru(self, *, refresh: bool = False) -> dict[str, Any]:
        with self._lock:
            if refresh or self._mineru is None:
                self._mineru = self._probe_mineru()
            return dict(self._mineru)

    def _probe_mineru(self) -> dict[str, Any]:
        base: dict[str, Any] = {
            "mode": self.settings.mineru_mode,
            "available": False,
            "ready_for_activation": False,
            "in_use": False,
            "integration_state": "reserved",
            "command": self.settings.mineru_command,
            "resolved_command": None,
            "version": None,
            "backend": self.settings.mineru_backend,
            "eligible_suffixes": [".pdf"],
        }
        if self.settings.mineru_mode == "disabled":
            return {**base, "integration_state": "disabled", "reason": "已通过配置禁用"}

        resolved = _resolve_command(self.settings.mineru_command)
        if not resolved:
            return {**base, "reason": "未找到 MinerU CLI；当前继续使用原生解析器"}

        base["resolved_command"] = resolved
        try:
            completed = subprocess.run(
                [resolved, "--version"],
                check=False,
                capture_output=True,
                text=True,
                timeout=self.settings.mineru_probe_timeout_seconds,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return {**base, "reason": f"MinerU CLI 探测失败：{exc}"}

        output = (completed.stdout or completed.stderr or "").strip()
        if completed.returncode != 0:
            detail = output.splitlines()[0] if output else f"exit code {completed.returncode}"
            return {**base, "reason": f"MinerU CLI 不可用：{detail}"}

        version = output.splitlines()[0] if output else "unknown"
        return {
            **base,
            "available": True,
            "ready_for_activation": True,
            "version": version,
            "reason": "已检测到本地 MinerU；解析适配器激活前仍使用原生解析器",
        }


def _resolve_command(command: str) -> str | None:
    candidate = Path(command).expanduser()
    if candidate.parent != Path(".") or candidate.is_absolute():
        return str(candidate.resolve()) if candidate.is_file() else None
    return shutil.which(command)
