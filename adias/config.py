"""解析 adias.cfg：返回扁平 dict，供 5 步流水线共用。

cfg 格式约定：
  - 段标题  : [n]####...   (仅做注释用，不影响解析)
  - 注释行  : 以 ! ; # [ 开头；行内 % 之后视为注释
  - 键值对  : key=value，key 前的数字前缀对应步骤号
  - 多值键  : 同名键追加数字后缀，如 3obj_ephfile1 / 3obj_ephfile2

使用：
  from adias import parse_config
  config = parse_config("adias2024.cfg")
"""

from dataclasses import dataclass, field
import os

from adias.errors import ConfigError

DEFAULTS = {
    # 01pre
    "biasflag": 0,
    "darkflag": 0,
    "flatflag": 0,
    "superflag": 0,
    "med_length": 1,
    "med_width": 25,
    "bkgdmode": 2,
    "enhance_flag": 1,
    "fitspath": [],
    # 02detect
    "bkgd_threshold": 5.0,
    "snr_threshold": 5.0,
    "pos_method": 2,
    "connectivity": "fortran",
    # 03match
    "tele_label": "",
    "fl": 0.0,
    "pscale": 0.0,
    "fsize": 0,
    "modeltype": 0,
    "field_angle": 0.0,
    "ephsource": "",
    "min_mag": 0.0,
    "max_mag": 0.0,
    "limit_match": 0.0,
    "delta_t": 0.0,
    "gaiacatpath": "",
    "obj_total": 0,
    "ephpath": [],
    # 04comoc
    "newoutfile0": "",
    "eps": 0.0,
    "oc_limit": 0.0,
    "mean_limit": 0.0,
    "del_flag": 0,
}

# cfg 单值键 -> (内部变量名, 类型)
KEY_MAP = {
    "1biasflag": ("biasflag", int),
    "1darkflag": ("darkflag", int),
    "1flatflag": ("flatflag", int),
    "1superflag": ("superflag", int),
    "1med_length": ("med_length", int),
    "1med_width": ("med_width", int),
    "1bkgdmode": ("bkgdmode", int),
    "1enhance_flag": ("enhance_flag", int),
    "2bkgd_threshold": ("bkgd_threshold", float),
    "2snr_threshold": ("snr_threshold", float),
    "2pos_method": ("pos_method", int),
    "2connectivity": ("connectivity", str),
    "3tele_label": ("tele_label", str),
    "3tele_focal": ("fl", float),
    "3ccd_scale": ("pscale", float),
    "3ccd_fieldsize": ("fsize", int),
    "3modeltype": ("modeltype", int),
    "3plate_angle": ("field_angle", float),
    "3obj_ephsource": ("ephsource", str),
    "3gaia_minmag": ("min_mag", float),
    "3gaia_maxmag": ("max_mag", float),
    "3match_limit": ("limit_match", float),
    "3delta_T": ("delta_t", float),
    "3obj_total": ("obj_total", int),
    "4specified-output": ("newoutfile0", str),
    "4eps": ("eps", float),
    "4std_limit": ("oc_limit", float),
    "4mean_limit": ("mean_limit", float),
    "4del_flag": ("del_flag", int),
}

# 带序号后缀的多值键 -> 输出列表名
LIST_KEY_PREFIXES = {
    "1fitspath": "fitspath",
    "3obj_ephfile": "ephpath",
    "3gaia_catfile": "gaiacatpath_list",
}


def _strip_comment(s):
    return s.split("%", 1)[0].strip()


def _cast(value, typ):
    if typ is str:
        # cfg 在 Windows 上用反斜杠分隔；运行期统一为本系统分隔符
        return value.replace("\\", os.sep)
    return typ(value)


def parse_config(config_path="adias.cfg"):
    """解析 adias.cfg，返回完整参数字典。配置缺失时回退到默认值。"""
    params = DEFAULTS.copy()
    params["fitspath"] = []
    params["ephpath"] = []

    if not os.path.exists(config_path):
        print(f"警告：配置文件 '{config_path}' 未找到，使用默认参数。")
        return params

    with open(config_path, "r", encoding="utf-8-sig") as f:
        lines = f.readlines()

    list_buckets = {prefix: {} for prefix in LIST_KEY_PREFIXES}

    for line in lines:
        line = line.strip()
        if not line or line.startswith(("!", ";", "#", "[")) or "=" not in line:
            continue
        key, raw_val = line.split("=", 1)
        key = key.strip()
        value = _strip_comment(raw_val)
        if not value:
            continue

        if key in KEY_MAP:
            var_name, typ = KEY_MAP[key]
            try:
                params[var_name] = _cast(value, typ)
            except ValueError:
                print(f"警告：无法解析 {key}={value}，保留默认值。")
            continue

        # 多值键：匹配前缀，取后面的整数后缀（无后缀视为 1）
        for prefix in LIST_KEY_PREFIXES:
            if not key.startswith(prefix):
                continue
            suffix = key[len(prefix):]
            try:
                idx = int(suffix) if suffix else 1
            except ValueError:
                break
            list_buckets[prefix][idx] = _cast(value, str)
            break

    for prefix, dest in LIST_KEY_PREFIXES.items():
        bucket = list_buckets[prefix]
        if not bucket:
            continue
        values = [bucket[k] for k in sorted(bucket.keys())]
        if dest == "gaiacatpath_list":
            # 历史上 GAIA 只用一份星表（多 obj 共用），取首个
            params["gaiacatpath"] = values[0]
        else:
            params[dest] = values

    return params


@dataclass
class PreConfig:
    biasflag: int
    darkflag: int
    flatflag: int
    superflag: int
    med_length: int
    med_width: int
    bkgdmode: int
    enhance_flag: int


@dataclass
class DetectConfig:
    bkgd_threshold: float
    snr_threshold: float
    pos_method: int
    connectivity: str = "fortran"


@dataclass
class MatchConfig:
    tele_label: str
    focal_length: float
    pixel_scale: float
    field_size: int
    model_type: int
    plate_angle: float
    ephsource: str
    min_mag: float
    max_mag: float
    match_limit: float
    delta_t: float
    gaia_catfile: str
    obj_total: int
    eph_files: list[str]


@dataclass
class ComocConfig:
    output_dir: str
    eps: float
    std_limit: float
    mean_limit: float
    del_flag: int


@dataclass
class ReportConfig:
    output_dir: str
    per_satellite: bool = True


@dataclass
class AdiasConfig:
    """类型化配置，同时保留旧 dict 形态用于第一阶段兼容旧流程。"""

    config_path: str
    fitspaths: list[str]
    pre: PreConfig
    detect: DetectConfig
    match: MatchConfig
    comoc: ComocConfig
    report: ReportConfig
    _legacy: dict = field(default_factory=dict, repr=False)

    @classmethod
    def from_legacy(cls, params, config_path):
        return cls(
            config_path=config_path,
            fitspaths=list(params.get("fitspath", [])),
            pre=PreConfig(
                biasflag=params["biasflag"],
                darkflag=params["darkflag"],
                flatflag=params["flatflag"],
                superflag=params["superflag"],
                med_length=params["med_length"],
                med_width=params["med_width"],
                bkgdmode=params["bkgdmode"],
                enhance_flag=params["enhance_flag"],
            ),
            detect=DetectConfig(
                bkgd_threshold=params["bkgd_threshold"],
                snr_threshold=params["snr_threshold"],
                pos_method=params["pos_method"],
                connectivity=params.get("connectivity", "fortran"),
            ),
            match=MatchConfig(
                tele_label=params["tele_label"],
                focal_length=params["fl"],
                pixel_scale=params["pscale"],
                field_size=params["fsize"],
                model_type=params["modeltype"],
                plate_angle=params["field_angle"],
                ephsource=params["ephsource"],
                min_mag=params["min_mag"],
                max_mag=params["max_mag"],
                match_limit=params["limit_match"],
                delta_t=params["delta_t"],
                gaia_catfile=params["gaiacatpath"],
                obj_total=params["obj_total"],
                eph_files=list(params.get("ephpath", [])),
            ),
            comoc=ComocConfig(
                output_dir=params["newoutfile0"],
                eps=params["eps"],
                std_limit=params["oc_limit"],
                mean_limit=params["mean_limit"],
                del_flag=params["del_flag"],
            ),
            report=ReportConfig(output_dir=params["newoutfile0"]),
            _legacy=params.copy(),
        )

    def to_legacy_dict(self):
        """返回旧流程函数使用的扁平 dict，键名保持原实现兼容。"""
        params = self._legacy.copy()
        params.update(
            {
                "fitspath": list(self.fitspaths),
                "biasflag": self.pre.biasflag,
                "darkflag": self.pre.darkflag,
                "flatflag": self.pre.flatflag,
                "superflag": self.pre.superflag,
                "med_length": self.pre.med_length,
                "med_width": self.pre.med_width,
                "bkgdmode": self.pre.bkgdmode,
                "enhance_flag": self.pre.enhance_flag,
                "bkgd_threshold": self.detect.bkgd_threshold,
                "snr_threshold": self.detect.snr_threshold,
                "pos_method": self.detect.pos_method,
                "connectivity": self.detect.connectivity,
                "tele_label": self.match.tele_label,
                "fl": self.match.focal_length,
                "pscale": self.match.pixel_scale,
                "fsize": self.match.field_size,
                "modeltype": self.match.model_type,
                "field_angle": self.match.plate_angle,
                "ephsource": self.match.ephsource,
                "min_mag": self.match.min_mag,
                "max_mag": self.match.max_mag,
                "limit_match": self.match.match_limit,
                "delta_t": self.match.delta_t,
                "gaiacatpath": self.match.gaia_catfile,
                "obj_total": self.match.obj_total,
                "ephpath": list(self.match.eph_files),
                "newoutfile0": self.comoc.output_dir,
                "eps": self.comoc.eps,
                "oc_limit": self.comoc.std_limit,
                "mean_limit": self.comoc.mean_limit,
                "del_flag": self.comoc.del_flag,
            }
        )
        return params

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

        if self.detect.connectivity not in {"fortran", "scipy"}:
            errors.append("2connectivity 必须为 fortran 或 scipy。")

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


def load_config(config_path="adias.cfg", steps=None):
    """读取 cfg 并返回类型化配置；旧 cfg 格式完全兼容。"""
    params = parse_config(config_path)
    config = AdiasConfig.from_legacy(params, config_path)
    config.validate(steps=steps)
    return config
