# 解析 adias.cfg：返回扁平 dict，供 5 步流水线共用。
#
# cfg 格式约定：
#   - 段标题  : [n]####...   (仅做注释用，不影响解析)
#   - 注释行  : 以 ! ; # [ 开头；行内 % 之后视为注释
#   - 键值对  : key=value，key 前的数字前缀对应步骤号
#   - 多值键  : 同名键追加数字后缀，如 3obj_ephfile1 / 3obj_ephfile2
#
# 使用：
#   from adias import parse_config
#   config = parse_config("adias2024.cfg")

import os

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

    # 多值键先收集（idx -> value），最后按 idx 排序展开为列表
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

        # 单值键
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

    # 多值键按后缀升序输出为列表
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
