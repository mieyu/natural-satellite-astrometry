"""流水线产物落地的目录约定。

每个观测日构成一棵小树：
  输入  : <day>/fits/*.fit                  原始观测图
  01pre : <day>/fits_n/*_n.fit              扣背景图
  02det : <day>/fits_reg/*.fit.reg          检测星表
  03mat : <day>/fits_ref/*.fitN.ref.reg     参考星表
          <day>/fits_out/object_N.out        匹配结果
  04com : <day>/fits_out/final_*             野值剔除过程
          <specified-output>/*.dat 等        跨日汇总，路径由 cfg 决定

约定：本模块所有路径相关 API 接收/返回 pathlib.Path。
"""

import re
from dataclasses import dataclass
from pathlib import Path

from adias.application.log import get_logger

_log = get_logger("paths")

PRE_DIR = "fits_n"
DETECT_DIR = "fits_reg"
REF_DIR = "fits_ref"
OUT_DIR = "fits_out"
STAGE_DIRS = (PRE_DIR, DETECT_DIR, REF_DIR, OUT_DIR)


@dataclass(frozen=True)
class ObservationDir:
    """单个观测日的原始 FITS 目录与阶段产物目录。"""

    raw_fits_dir: Path
    pre_dir: Path
    reg_dir: Path
    ref_dir: Path
    out_dir: Path

    @classmethod
    def from_raw_fits_dir(cls, raw_fits_dir):
        raw = Path(raw_fits_dir)
        stages = stage_dirs(raw)
        return cls(
            raw_fits_dir=raw,
            pre_dir=stages[PRE_DIR],
            reg_dir=stages[DETECT_DIR],
            ref_dir=stages[REF_DIR],
            out_dir=stages[OUT_DIR],
        )


# ── fitspath 展开与原始 .fit 扫描 ─────────────────────────────────────────


def expand_fitspath(cfg_paths) -> list[Path]:
    """根据 cfg 的 fitspath 列表展开为实际观测目录（每日一个）。

    支持两种结构：
      1. 直接模式：路径本身就是含 .fit 的目录，原样返回。
      2. 日期子目录模式：路径下存在 YYYYMMDD/fits 或 YYYYMMDD/FITS 时自动展开。
    """
    expanded: list[Path] = []
    for cfg_path in cfg_paths:
        path = Path(cfg_path)
        daily = _find_daily_dirs(path)
        if daily:
            _log.info(f"  [{path.name}] 发现 {len(daily)} 个日期子目录，已自动展开。")
            expanded.extend(daily)
        else:
            expanded.append(path)
    return expanded


def _find_daily_dirs(root_path: Path) -> list[Path]:
    if not root_path.is_dir():
        return []
    found: list[Path] = []
    for entry in sorted(p.name for p in root_path.iterdir()):
        if not re.match(r"^\d{6,8}$", entry):
            continue
        day_dir = root_path / entry
        for name in ("fits", "FITS"):
            sub = day_dir / name
            if sub.is_dir():
                found.append(sub)
                break
    return found


def list_fits(fitspath) -> list[Path]:
    """fitspath 下原始 .fit / .fits 排序列表（排除 _n.fit / _n.fits）。"""
    path = Path(fitspath)
    if not path.is_dir():
        return []
    candidates = list(path.glob("*.fit")) + list(path.glob("*.fits"))
    return sorted(
        p
        for p in candidates
        if not p.name.endswith("_n.fit") and not p.name.endswith("_n.fits")
    )


# ── 产物子目录解析 ────────────────────────────────────────────────────────


def stage_dirs(fitspath) -> dict[str, Path]:
    """该观测目录对应的 4 个产物子目录路径（不创建）。"""
    parent = Path(fitspath).parent
    return {name: parent / name for name in STAGE_DIRS}


def ensure_dir(path) -> Path:
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def pre_path(fitspath, fit_basename) -> Path:
    base = Path(fit_basename)
    return stage_dirs(fitspath)[PRE_DIR] / f"{base.stem}_n{base.suffix}"


def reg_path(fitspath, fit_basename) -> Path:
    return stage_dirs(fitspath)[DETECT_DIR] / f"{fit_basename}.reg"


def ref_path(fitspath, fit_basename, obj_idx) -> Path:
    return stage_dirs(fitspath)[REF_DIR] / f"{fit_basename}{obj_idx}.ref.reg"


def out_dir(fitspath) -> Path:
    return stage_dirs(fitspath)[OUT_DIR]


# ── 清理工具 ──────────────────────────────────────────────────────────────


def clean_pre_dir(fitspath):
    """清空 fits_n/ 子目录，确保 pre 阶段每次从干净状态开始。"""
    pre_dir = stage_dirs(fitspath)[PRE_DIR]
    if not pre_dir.is_dir():
        return
    removed = 0
    for entry in pre_dir.iterdir():
        if entry.suffix in (".fit", ".fits") and entry.stem.endswith("_n"):
            entry.unlink()
            removed += 1
    if removed:
        _log.info(f"已清理旧 _n.fit 共 {removed} 个 <- {pre_dir}")


def clean_proc_files(fitspath):
    """删除过程文件：fits_n/、fits_reg/、fits_ref/ 三个子目录的全部内容。

    供 04comoc 的 del_flag=1 路径使用。fits_out/ 保留（含最终统计文件）。
    """
    removed = 0
    for name in (PRE_DIR, DETECT_DIR, REF_DIR):
        d = stage_dirs(fitspath)[name]
        if not d.is_dir():
            continue
        for entry in d.iterdir():
            if entry.is_file():
                entry.unlink()
                removed += 1
    _log.info(f"  已删除过程文件 {removed} 个（fits_n / fits_reg / fits_ref）")
