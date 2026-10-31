"""Inputs and outputs shared by the desktop UI and reference preparation API."""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


class ReferenceError(ValueError):
    """An incomplete, inconsistent or unavailable reference dataset."""


class PreparationCancelled(ReferenceError):
    pass


@dataclass(frozen=True)
class ReferenceRequest:
    fitspaths: tuple[Path, ...]
    cache_root: Path
    eph_source: str = "inputs"
    gaia_source: str = "inputs"
    local_eph_files: tuple[Path, ...] = ()
    local_gaia_file: Path | None = None
    targets: tuple[str, ...] = ()
    tele_label: str = ""
    observatory: str = ""
    field_half_arcmin: float = 15.0
    delta_t: float = 0.0
    step_seconds: int = 60
    padding_seconds: int = 300
    sky_margin_arcmin: float = 5.0
    network_mode: str = "direct"
    gaia_cone: tuple[float, float, float] | None = None  # RA deg, Dec deg, radius deg


@dataclass(frozen=True)
class ObservationPlan:
    moments: tuple[datetime, ...]
    start: datetime
    stop: datetime
    month: str
    files: int


@dataclass(frozen=True)
class EphemerisRow:
    time: datetime
    ra_hours: str
    dec_degrees: str


@dataclass(frozen=True)
class PreparedReferences:
    eph_files: tuple[Path, ...]
    gaia_catfile: Path
    manifest_path: Path | None

    @property
    def obj_total(self):
        return len(self.eph_files)


def check_cancel(cancel):
    if cancel is not None and cancel.is_set():
        raise PreparationCancelled("已取消星表/历表准备；原有文件保持不动。")
