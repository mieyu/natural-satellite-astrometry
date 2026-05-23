"""流水线 Step 协议、运行器与 manifest 记录。"""

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Protocol

from adias.application.log import get_logger


_log = get_logger("pipeline")


@dataclass
class StepResult:
    name: str
    success: bool = True
    warnings: list[str] = field(default_factory=list)
    failed_items: list[str] = field(default_factory=list)
    output_files: list[str] = field(default_factory=list)


class PipelineStep(Protocol):
    name: str
    title: str

    def run(self, ctx) -> StepResult:
        ...


class PipelineRunner:
    def __init__(self, steps):
        self.steps = list(steps)

    def run(self, ctx):
        manifest = RunManifest(ctx)
        manifest.start([step.name for step in self.steps])
        results = []
        try:
            for step in self.steps:
                _log.info(step.title)
                result = step.run(ctx)
                results.append(result)
                manifest.add_result(result)
        except Exception as exc:
            manifest.add_failure("pipeline", str(exc))
            raise
        finally:
            manifest.finish()
        return results


class RunManifest:
    def __init__(self, ctx):
        self.ctx = ctx
        self.path = Path("runs") / ctx.run_id / "manifest.json"
        self.data = {
            "run_id": ctx.run_id,
            "config_file": ctx.config.config_path,
            "steps": [],
            "started_at": "",
            "finished_at": "",
            "input_files": [],
            "output_files": [],
            "warnings": [],
            "failed_items": [],
        }

    def start(self, steps):
        self.data["steps"] = list(steps)
        self.data["started_at"] = datetime.now().isoformat(timespec="seconds")
        self.data["input_files"] = [
            str(obs.raw_fits_dir) for obs in self.ctx.observation_dirs
        ]

    def add_result(self, result):
        self.data["warnings"].extend(result.warnings)
        self.data["failed_items"].extend(result.failed_items)
        self.data["output_files"].extend(result.output_files)

    def add_failure(self, name, message):
        self.data["failed_items"].append(f"{name}: {message}")

    def finish(self):
        self.data["finished_at"] = datetime.now().isoformat(timespec="seconds")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)
