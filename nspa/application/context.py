"""流水线运行上下文：把配置与本次运行的派生信息组合在一起。"""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from nspa.config import NspaConfig
from nspa.paths import ObservationDir, expand_fitspath


@dataclass
class PipelineContext:
    config: NspaConfig
    run_id: str
    observation_dirs: list[ObservationDir]
    output_root: Path
    selected_steps: list[str]

    @property
    def fitspath_list(self) -> list[Path]:
        return [obs.raw_fits_dir for obs in self.observation_dirs]


def make_run_id() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def build_context(config: NspaConfig, selected_steps, run_id=None) -> PipelineContext:
    fitspath_list = expand_fitspath(config.fitspaths)
    observation_dirs = [ObservationDir.from_raw_fits_dir(p) for p in fitspath_list]
    output_root = Path(config.comoc.output_dir) if config.comoc.output_dir else Path(".")
    return PipelineContext(
        config=config,
        run_id=run_id or make_run_id(),
        observation_dirs=observation_dirs,
        output_root=output_root,
        selected_steps=list(selected_steps),
    )
