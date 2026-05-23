"""流水线产物落地的目录约定：
  输入  : <day>/fits/*.fit                  (原始观测图)
  01pre : <day>/fits_n/*_n.fit              (扣背景图)
  02det : <day>/fits_reg/*.fit.reg          (检测星表)
  03mat : <day>/fits_ref/*.fitN.ref.reg     (参考星表)
          <day>/fits_out/object_N.out        (匹配结果)
  04com : <day>/fits_out/final_*             (野值剔除过程)
          <specified-output>/*.dat 等        (跨日汇总，路径由 cfg 决定)
"""

import glob
import os
import re
from dataclasses import dataclass
from pathlib import Path

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
        stages = stage_dirs(str(raw_fits_dir))
        return cls(
            raw_fits_dir=Path(raw_fits_dir),
            pre_dir=Path(stages[PRE_DIR]),
            reg_dir=Path(stages[DETECT_DIR]),
            ref_dir=Path(stages[REF_DIR]),
            out_dir=Path(stages[OUT_DIR]),
        )


# ── fitspath 展开与原始 .fit 扫描 ─────────────────────────────────────────

def expand_fitspath(cfg_paths):
    """根据 cfg 的 fitspath 列表展开为实际观测目录（每日一个）。

    支持两种结构：
      1. 直接模式：路径本身就是含 .fit 的目录，原样返回。
      2. 日期子目录模式：路径下存在 YYYYMMDD/fits 或 YYYYMMDD/FITS 时自动展开。
    """
    expanded = []
    for path in cfg_paths:
        daily = _find_daily_dirs(path)
        if daily:
            root_name = os.path.basename(path.rstrip(os.sep))
            print(f"  [{root_name}] 发现 {len(daily)} 个日期子目录，已自动展开。")
            expanded.extend(daily)
        else:
            expanded.append(path)
    return expanded


def _find_daily_dirs(root_path):
    if not os.path.isdir(root_path):
        return []
    found = []
    for entry in sorted(os.listdir(root_path)):
        if not re.match(r"^\d{8}$", entry):
            continue
        day_dir = os.path.join(root_path, entry)
        for name in ("fits", "FITS"):
            sub = os.path.join(day_dir, name)
            if os.path.isdir(sub):
                found.append(sub)
                break
    return found


def list_fits(fitspath):
    """fitspath 下原始 .fit 排序列表（排除 _n.fit）。"""
    if not os.path.isdir(fitspath):
        return []
    return sorted(
        f for f in glob.glob(os.path.join(fitspath, "*.fit"))
        if not f.endswith("_n.fit")
    )


# ── 产物子目录解析 ────────────────────────────────────────────────────────

def stage_dirs(fitspath):
    """该观测目录对应的 4 个产物子目录路径（不创建）。"""
    parent = os.path.dirname(os.path.normpath(fitspath))
    return {name: os.path.join(parent, name) for name in STAGE_DIRS}


def ensure_dir(path):
    os.makedirs(path, exist_ok=True)
    return path


def pre_path(fitspath, fit_basename):
    base, ext = os.path.splitext(fit_basename)
    return os.path.join(stage_dirs(fitspath)[PRE_DIR], f"{base}_n{ext}")


def reg_path(fitspath, fit_basename):
    return os.path.join(stage_dirs(fitspath)[DETECT_DIR], f"{fit_basename}.reg")


def ref_path(fitspath, fit_basename, obj_idx):
    return os.path.join(stage_dirs(fitspath)[REF_DIR], f"{fit_basename}{obj_idx}.ref.reg")


def out_dir(fitspath):
    return stage_dirs(fitspath)[OUT_DIR]


# ── 清理工具 ──────────────────────────────────────────────────────────────

def clean_pre_dir(fitspath):
    """清空 fits_n/ 子目录，确保 pre 阶段每次从干净状态开始。"""
    pre_dir = stage_dirs(fitspath)[PRE_DIR]
    if not os.path.isdir(pre_dir):
        return
    removed = 0
    for fname in os.listdir(pre_dir):
        if fname.endswith(("_n.fit", "_n.fits")):
            os.remove(os.path.join(pre_dir, fname))
            removed += 1
    if removed:
        print(f"已清理旧 _n.fit 共 {removed} 个 <- {pre_dir}")


def clean_proc_files(fitspath):
    """删除过程文件：fits_n/、fits_reg/、fits_ref/ 三个子目录的全部内容。

    供 04comoc 的 del_flag=1 路径使用。fits_out/ 保留（含最终统计文件）。
    """
    removed = 0
    for name in (PRE_DIR, DETECT_DIR, REF_DIR):
        d = stage_dirs(fitspath)[name]
        if not os.path.isdir(d):
            continue
        for fname in os.listdir(d):
            fp = os.path.join(d, fname)
            if os.path.isfile(fp):
                os.remove(fp)
                removed += 1
    print(f"  已删除过程文件 {removed} 个（fits_n / fits_reg / fits_ref）")
