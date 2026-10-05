"""解析 nspa.cfg：表驱动构造类型化 NspaConfig。

cfg 格式约定：
  - 段标题  : [n]####…（仅做注释，不影响解析）
  - 注释行  : 以 ! ; # [ 开头；行内 % 之后视为注释
  - 键值对  : key=value，key 前的数字前缀对应步骤号
  - 多值键  : 同名键追加数字后缀，如 3obj_ephfile1 / 3obj_ephfile2

字段定义集中在 FIELDS 表里：单值键、列表键、与各 SectionConfig 的映射，
均由表自动派生；新增 cfg 字段只需要改一处。
"""

import os
from dataclasses import dataclass, field
from typing import Any

from nspa.application.log import get_logger
from nspa.errors import ConfigError

_log = get_logger("config")


# ── 单值字段表 ────────────────────────────────────────────────────────────
# (cfg_key, section, attr, type, default)
#   section ∈ {"pre", "detect", "match", "comoc", "report", None}
#   None 表示挂在 NspaConfig 顶层。
_SCALAR_FIELDS: list[tuple[str, str | None, str, type, Any]] = [
    ("run_manifest_dir", None, "run_manifest_dir", str, "outputs/runs"),
    # 01pre
    ("1biasflag", "pre", "biasflag", int, 0),
    ("1darkflag", "pre", "darkflag", int, 0),
    ("1flatflag", "pre", "flatflag", int, 0),
    ("1superflag", "pre", "superflag", int, 0),
    ("1med_length", "pre", "med_length", int, 1),
    ("1med_width", "pre", "med_width", int, 25),
    ("1bkgdmode", "pre", "bkgdmode", int, 2),
    ("1enhance_flag", "pre", "enhance_flag", int, 1),
    ("1median_impl", "pre", "median_impl", str, "auto"),
    (
        "1homo_gauss_cutoff",
        "pre",
        "homo_gauss_cutoff",
        float,
        50.0,
    ),  # 同态滤波(mode2)频域高斯截止频率
    (
        "1bssr_gauss_size",
        "pre",
        "bssr_gauss_size",
        int,
        9,
    ),  # BSSR(mode3)空间高斯窗口(奇数)
    # 02detect
    ("2bkgd_threshold", "detect", "bkgd_threshold", float, 5.0),
    ("2snr_threshold", "detect", "snr_threshold", float, 5.0),
    ("2pos_method", "detect", "pos_method", int, 2),
    ("2connectivity", "detect", "connectivity", str, "fortran"),
    ("2detect_workers", "detect", "detect_workers", int, 0),
    # 03match
    ("3tele_label", "match", "tele_label", str, ""),
    ("3tele_focal", "match", "focal_length", float, 0.0),
    ("3ccd_scale", "match", "pixel_scale", float, 0.0),
    ("3ccd_fieldsize", "match", "field_size", int, 0),
    ("3modeltype", "match", "model_type", int, 0),
    ("3plate_angle", "match", "plate_angle", float, 0.0),
    ("3obj_ephsource", "match", "ephsource", str, ""),
    ("3gaia_minmag", "match", "min_mag", float, 0.0),
    ("3gaia_maxmag", "match", "max_mag", float, 0.0),
    ("3match_limit", "match", "match_limit", float, 0.0),
    ("3delta_T", "match", "delta_t", float, 0.0),
    ("3obj_total", "match", "obj_total", int, 0),
    # 04comoc
    ("4specified-output", "comoc", "output_dir", str, ""),
    ("4eps", "comoc", "eps", float, 0.0),
    ("4std_limit", "comoc", "std_limit", float, 0.0),
    ("4mean_limit", "comoc", "mean_limit", float, 0.0),
    ("4del_flag", "comoc", "del_flag", int, 0),
    # 05report
    ("5sat_prefix", "report", "sat_prefix", str, "S"),
]

# ── 列表字段表 ────────────────────────────────────────────────────────────
# (cfg_prefix, section, attr, collapse)
#   collapse=True  → 取首个值（历史上多 obj 共用同一星表）
#   collapse=False → 全部按下标顺序收集为 list
_LIST_FIELDS: list[tuple[str, str | None, str, bool]] = [
    ("1fitspath", None, "fitspaths", False),
    ("3obj_ephfile", "match", "eph_files", False),
    ("3gaia_catfile", "match", "gaia_catfile", True),
]


def _cast(value: str, typ: type) -> Any:
    if typ is str:
        # cfg 在 Windows 上用反斜杠分隔；运行期统一为本系统分隔符
        return value.replace("\\", os.sep)
    return typ(value)


def _strip_comment(s: str) -> str:
    return s.split("%", 1)[0].strip()


# ── 段 dataclass ─────────────────────────────────────────────────────────


@dataclass
class PreConfig:
    biasflag: int = 0
    darkflag: int = 0
    flatflag: int = 0
    superflag: int = 0
    med_length: int = 1
    med_width: int = 25
    bkgdmode: int = 2
    enhance_flag: int = 1
    median_impl: str = "auto"
    homo_gauss_cutoff: float = 50.0  # 同态滤波(mode2)频域高斯截止频率
    bssr_gauss_size: int = 9  # BSSR(mode3)空间高斯窗口(奇数)


@dataclass
class DetectConfig:
    bkgd_threshold: float = 5.0
    snr_threshold: float = 5.0
    pos_method: int = 2
    connectivity: str = "fortran"
    detect_workers: int = 0


@dataclass
class MatchConfig:
    tele_label: str = ""
    focal_length: float = 0.0
    pixel_scale: float = 0.0
    field_size: int = 0
    model_type: int = 0
    plate_angle: float = 0.0
    ephsource: str = ""
    min_mag: float = 0.0
    max_mag: float = 0.0
    match_limit: float = 0.0
    delta_t: float = 0.0
    obj_total: int = 0
    gaia_catfile: str = ""
    eph_files: list[str] = field(default_factory=list)


@dataclass
class ComocConfig:
    output_dir: str = ""
    eps: float = 0.0
    std_limit: float = 0.0
    mean_limit: float = 0.0
    del_flag: int = 0


@dataclass
class ReportConfig:
    output_dir: str = ""
    per_satellite: bool = True
    sat_prefix: str = "S"


_SECTIONS = {
    "pre": PreConfig,
    "detect": DetectConfig,
    "match": MatchConfig,
    "comoc": ComocConfig,
    "report": ReportConfig,
}


@dataclass
class NspaConfig:
    """类型化的运行配置，全流水线唯一参数载体。"""

    config_path: str
    fitspaths: list[str] = field(default_factory=list)
    pre: PreConfig = field(default_factory=PreConfig)
    detect: DetectConfig = field(default_factory=DetectConfig)
    match: MatchConfig = field(default_factory=MatchConfig)
    comoc: ComocConfig = field(default_factory=ComocConfig)
    report: ReportConfig = field(default_factory=ReportConfig)
    run_manifest_dir: str = "outputs/runs"

    def validate(self, steps=None):
        """按本次运行阶段校验配置。配置错误直接阻断启动。"""
        selected = set(steps or ["all"])
        if "all" in selected:
            selected = {"pre", "detect", "match", "comoc", "report"}

        errors = []

        if not self.fitspaths:
            errors.append("cfg 中未配置 1fitspath，无法确定观测目录。")

        if self.pre.superflag not in {0, 1, 2, 3}:
            errors.append("1superflag 必须为 0/1/2/3。")

        if self.pre.median_impl not in {
            "auto",
            "scipy",
            "scipy_threaded",
            "bottleneck",
        }:
            errors.append("1median_impl 必须为 auto/scipy/scipy_threaded/bottleneck。")

        if self.detect.connectivity not in {"fortran", "scipy"}:
            errors.append("2connectivity 必须为 fortran 或 scipy。")

        if self.detect.detect_workers < 0:
            errors.append("2detect_workers 必须为非负整数（0 表示自动）。")

        if selected & {"match", "comoc", "report"}:
            if self.match.obj_total <= 0:
                errors.append("3obj_total 必须大于 0。")

        if "match" in selected:
            if self.match.obj_total != len(self.match.eph_files):
                errors.append("3obj_total 必须等于 3obj_ephfile* 的数量。")
            if self.match.model_type not in {6, 12, 20, 30}:
                errors.append("3modeltype 必须为 6/12/20/30。")
            if not self.match.gaia_catfile:
                errors.append("未配置 3gaia_catfile1。")
            elif not os.path.exists(self.match.gaia_catfile):
                errors.append(f"GAIA 星表不存在：{self.match.gaia_catfile}")
            for eph_file in self.match.eph_files:
                if not os.path.exists(eph_file):
                    errors.append(f"目标历表不存在：{eph_file}")

        if selected & {"comoc", "report"} and not self.comoc.output_dir:
            errors.append("未配置 4specified-output。")

        if errors:
            raise ConfigError("\n".join(errors))


# ── 解析 ─────────────────────────────────────────────────────────────────


def _set_section_attr(config: NspaConfig, section: str | None, attr: str, value: Any):
    target = config if section is None else getattr(config, section)
    setattr(target, attr, value)


def parse_config(config_path: str = "nspa.cfg") -> NspaConfig:
    """解析 nspa.cfg，构造 NspaConfig；配置缺失时使用默认值。"""
    config = NspaConfig(config_path=config_path)

    if not os.path.exists(config_path):
        _log.info(f"警告：配置文件 '{config_path}' 未找到，使用默认参数。")
        return config

    scalar_index = {
        cfg_key: (section, attr, typ)
        for cfg_key, section, attr, typ, _ in _SCALAR_FIELDS
    }
    list_index = {
        prefix: (section, attr, collapse)
        for prefix, section, attr, collapse in _LIST_FIELDS
    }
    list_buckets: dict[str, dict[int, str]] = {prefix: {} for prefix in list_index}

    with open(config_path, "r", encoding="utf-8-sig") as f:
        lines = f.readlines()

    for line in lines:
        line = line.strip()
        if not line or line.startswith(("!", ";", "#", "[")) or "=" not in line:
            continue
        key, raw_val = line.split("=", 1)
        key = key.strip()
        value = _strip_comment(raw_val)
        if not value:
            continue

        if key in scalar_index:
            section, attr, typ = scalar_index[key]
            try:
                _set_section_attr(config, section, attr, _cast(value, typ))
            except ValueError:
                _log.info(f"警告：无法解析 {key}={value}，保留默认值。")
            continue

        # 多值键：匹配前缀，取后面的整数后缀（无后缀视为 1）
        for prefix in list_index:
            if not key.startswith(prefix):
                continue
            suffix = key[len(prefix) :]
            try:
                idx = int(suffix) if suffix else 1
            except ValueError:
                break
            list_buckets[prefix][idx] = _cast(value, str)
            break

    for prefix, (section, attr, collapse) in list_index.items():
        bucket = list_buckets[prefix]
        if not bucket:
            continue
        values = [bucket[k] for k in sorted(bucket.keys())]
        _set_section_attr(config, section, attr, values[0] if collapse else values)

    # report 段沿用 comoc 的输出目录
    config.report.output_dir = config.comoc.output_dir

    return config


def load_config(config_path: str = "nspa.cfg", steps=None) -> NspaConfig:
    """读取 cfg 并返回类型化配置；配置错误时抛 ConfigError。"""
    config = parse_config(config_path)
    config.validate(steps=steps)
    return config
