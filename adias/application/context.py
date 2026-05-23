"""流水线运行上下文。"""

from dataclasses import dataclass
from pathlib import Path
from datetime import datetime

from adias.config import AdiasConfig
from adias.paths import ObservationDir, expand_fitspath
from adias.application.output import OutputSink


@dataclass
class PipelineContext:
    config: AdiasConfig
    run_id: str
    observation_dirs: list[ObservationDir]
    output_root: Path
    output: OutputSink
    selected_steps: list[str]

    @property
    def fitspath_list(self):
        return [str(obs.raw_fits_dir) for obs in self.observation_dirs]

    @property
    def legacy_config(self):
        return self.config.to_legacy_dict()


def make_run_id():
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def build_context(config, selected_steps, output=None, run_id=None):
    fitspath_list = expand_fitspath(config.fitspaths)
    observation_dirs = [ObservationDir.from_raw_fits_dir(p) for p in fitspath_list]
    return PipelineContext(
        config=config,
        run_id=run_id or make_run_id(),
        observation_dirs=observation_dirs,
        output_root=Path(config.comoc.output_dir) if config.comoc.output_dir else Path("."),
        output=output or OutputSink(),
        selected_steps=list(selected_steps),
    )
