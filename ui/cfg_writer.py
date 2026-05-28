"""把 UI 表单值拼成 adias cfg 文本。

沿用现有 cfg key 格式（参考 tests/_fixtures.py:cfg_lines）：
  - 标量键：直接 `<cfg_key>=<value>`，键集合取自 adias.config._SCALAR_FIELDS。
  - 列表键：fitspath / eph 文件按下标展开（1fitspath, 1fitspath2 ...；3obj_ephfile1 ...）。
  - gaia 星表上游会折叠取首个，这里写成 3gaia_catfile1。

只新增、不改动 adias/。仅把 adias.config 当作字段表的唯一来源，避免重复维护。
"""

from pathlib import Path

from adias.config import _SCALAR_FIELDS

# inputs_panel 负责的列表/路径键，不由通用标量表单写出
_INPUT_OWNED_LIST_KEYS = ("1fitspath", "3obj_ephfile", "3gaia_catfile")


def scalar_keys_in_order():
    """返回标量 cfg_key 的有序列表（与 _SCALAR_FIELDS 表顺序一致）。"""
    return [cfg_key for cfg_key, *_ in _SCALAR_FIELDS]


def build_cfg_text(scalars, fitspaths, eph_files, gaia_catfile, header=True):
    """组装 cfg 文本。

    参数
    ----
    scalars : dict[str, str]   标量 cfg_key -> 值（字符串）。空串跳过不写。
    fitspaths : list[str]      观测目录，至少一个。
    eph_files : list[str]      历表文件路径列表（多目标对应多个）。
    gaia_catfile : str         GAIA 星表文件路径。
    """
    lines = []
    if header:
        lines.append("; ==== 由 ADIAS UI 自动生成，请勿手工长期维护 ====")

    for i, fp in enumerate(fitspaths, 1):
        if not fp:
            continue
        key = "1fitspath" if i == 1 else f"1fitspath{i}"
        lines.append(f"{key}={fp}")

    for cfg_key in scalar_keys_in_order():
        val = scalars.get(cfg_key, "")
        if str(val).strip() == "":
            continue
        lines.append(f"{cfg_key}={val}")

    for i, eph in enumerate(eph_files, 1):
        if eph:
            lines.append(f"3obj_ephfile{i}={eph}")

    if gaia_catfile:
        lines.append(f"3gaia_catfile1={gaia_catfile}")

    return "\n".join(lines) + "\n"


def write_cfg(path, scalars, fitspaths, eph_files, gaia_catfile):
    """生成 cfg 并写盘，返回写入的 Path。"""
    text = build_cfg_text(scalars, fitspaths, eph_files, gaia_catfile)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path
