from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    project_root: Path
    state_dir: Path
    dataflow_path: Path | None
    mineru_mode: str = "auto"
    mineru_command: str = "mineru"
    mineru_backend: str = "hybrid-auto-engine"
    mineru_probe_timeout_seconds: float = 5.0

    @classmethod
    def load(
        cls,
        project_root: str | Path | None = None,
        dataflow_path: str | Path | None = None,
    ) -> "Settings":
        root = Path(project_root or os.getenv("DATAFORGE_ROOT") or Path.cwd()).resolve()
        state = Path(os.getenv("DATAFORGE_STATE_DIR") or root / ".dataforge").resolve()

        configured_dataflow = dataflow_path or os.getenv("DATAFORGE_DATAFLOW_PATH")
        if configured_dataflow:
            resolved_dataflow: Path | None = Path(configured_dataflow).resolve()
        else:
            conventional = root.parent / "DataFlow"
            resolved_dataflow = conventional.resolve() if conventional.exists() else None

        mineru_mode = (os.getenv("DATAFORGE_MINERU_MODE") or "auto").strip().lower()
        if mineru_mode not in {"auto", "disabled"}:
            raise ValueError("DATAFORGE_MINERU_MODE must be 'auto' or 'disabled'")

        try:
            mineru_probe_timeout = float(
                os.getenv("DATAFORGE_MINERU_PROBE_TIMEOUT_SECONDS") or "5"
            )
        except ValueError as exc:
            raise ValueError("DATAFORGE_MINERU_PROBE_TIMEOUT_SECONDS must be a number") from exc
        if mineru_probe_timeout <= 0:
            raise ValueError("DATAFORGE_MINERU_PROBE_TIMEOUT_SECONDS must be greater than 0")

        return cls(
            project_root=root,
            state_dir=state,
            dataflow_path=resolved_dataflow,
            mineru_mode=mineru_mode,
            mineru_command=(os.getenv("DATAFORGE_MINERU_COMMAND") or "mineru").strip(),
            mineru_backend=(
                os.getenv("DATAFORGE_MINERU_BACKEND") or "hybrid-auto-engine"
            ).strip(),
            mineru_probe_timeout_seconds=mineru_probe_timeout,
        )

    @property
    def database_path(self) -> Path:
        return self.state_dir / "metadata.sqlite3"

    @property
    def blobs_dir(self) -> Path:
        return self.state_dir / "blobs"

    @property
    def runs_dir(self) -> Path:
        return self.state_dir / "runs"

    def ensure_directories(self) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.blobs_dir.mkdir(parents=True, exist_ok=True)
        self.runs_dir.mkdir(parents=True, exist_ok=True)
