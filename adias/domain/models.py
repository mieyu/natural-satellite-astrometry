"""ADIAS 领域数据模型。

第一阶段只建立显式契约；旧格式读写仍由 adapters/io 层负责保持兼容。
"""

from dataclasses import dataclass, field
from pathlib import Path


def _zeros(n):
    try:
        import numpy as np

        return np.zeros(n)
    except ModuleNotFoundError:
        return [0.0] * n


@dataclass
class DetectedStar:
    x: float
    y: float
    flux: float
    snr: float
    star_id: int = 0
    pixel_count: int = 0
    saturated: bool = False


@dataclass
class ReferenceStar:
    x: float
    y: float
    ra: float
    de: float
    mag: float


@dataclass
class GaiaCatalog:
    """逐日重读的 GAIA 全天参考星表（含自行参数）。"""

    count: int
    ra: object  # ndarray[float]
    de: object
    pm_ra: object
    pm_de: object
    mag: object

    @classmethod
    def empty(cls):
        return cls(
            count=0,
            ra=_zeros(0),
            de=_zeros(0),
            pm_ra=_zeros(0),
            pm_de=_zeros(0),
            mag=_zeros(0),
        )

    def is_empty(self):
        return self.count == 0 or self.ra is None

    def iter_stars(self):
        """逐颗遍历 ReferenceStar（不含 x/y，未投影到底片）。"""
        for i in range(self.count):
            yield ReferenceStar(
                x=0.0,
                y=0.0,
                ra=float(self.ra[i]),
                de=float(self.de[i]),
                mag=float(self.mag[i]),
            )


@dataclass
class Ephemeris:
    """单目标 IMCCE 历表：每行 (t, ra, de)。"""

    count: int
    t: object
    ra: object
    de: object

    @classmethod
    def empty(cls):
        return cls(count=0, t=_zeros(0), ra=_zeros(0), de=_zeros(0))

    def is_empty(self):
        return self.count == 0 or self.t is None


@dataclass
class ObjectObservation:
    """单图单目标的归算结果。

    残差不在模型里携带——object_N.out 的列宽与历史一致，
    write_object_result adapter 由 obs_* 与 eph_* 即时算出。
    """

    year: int
    month: int
    day_fraction: float
    obs_ra: float
    obs_de: float
    eph_ra: float
    eph_de: float
    sigma: float
    fits_file: Path | str


@dataclass
class OCStats:
    raw_count: int
    raw_mean_ra: float
    raw_mean_de: float
    raw_std_ra: float
    raw_std_de: float
    kept_count: int
    mean_ra: float
    mean_de: float
    std_ra: float
    std_de: float
    iterations: int


@dataclass
class PlateConstants:
    """单幅图像内复用的底片常数：base_angle 解出后供同图剩余目标走 prepar。"""

    par: object = field(default_factory=lambda: _zeros(30))
    x_center: float = 0.0
    y_center: float = 0.0
    ra_center: float = 0.0
    de_center: float = 0.0
    valid: bool = False

    @classmethod
    def empty(cls):
        return cls()

    @classmethod
    def from_match(cls, match):
        return cls(
            par=match.par1.copy(),
            x_center=match.x_center,
            y_center=match.y_center,
            ra_center=match.ra_center,
            de_center=match.de_center,
            valid=True,
        )


@dataclass
class MatchResult:
    nostar: int = 0
    nopre: int = 0
    obj_x: float = 0.0
    obj_y: float = 0.0
    obj_flux: float = 0.0
    snr: float = 0.0
    obj_obsra: float = 0.0
    obj_obsde: float = 0.0
    n_match1: int = 0
    sig0: float = 0.0
    par1: object = field(default_factory=lambda: _zeros(30))
    x_center: float = 0.0
    y_center: float = 0.0
    ra_center: float = 0.0
    de_center: float = 0.0
    ref_x: object = field(default_factory=lambda: _zeros(0))
    ref_y: object = field(default_factory=lambda: _zeros(0))
    ref_ra: object = field(default_factory=lambda: _zeros(0))
    ref_de: object = field(default_factory=lambda: _zeros(0))
    ref_mag: object = field(default_factory=lambda: _zeros(0))

    @classmethod
    def from_legacy_dict(cls, data):
        return cls(**{k: data[k] for k in cls.__dataclass_fields__ if k in data})

    def to_legacy_dict(self):
        return {
            "nostar": self.nostar,
            "nopre": self.nopre,
            "obj_x": self.obj_x,
            "obj_y": self.obj_y,
            "obj_flux": self.obj_flux,
            "snr": self.snr,
            "obj_obsra": self.obj_obsra,
            "obj_obsde": self.obj_obsde,
            "n_match1": self.n_match1,
            "sig0": self.sig0,
            "par1": self.par1,
            "x_center": self.x_center,
            "y_center": self.y_center,
            "ra_center": self.ra_center,
            "de_center": self.de_center,
            "ref_x": self.ref_x,
            "ref_y": self.ref_y,
            "ref_ra": self.ref_ra,
            "ref_de": self.ref_de,
            "ref_mag": self.ref_mag,
        }
