"""测试共享 fixture：金标准观测日 + GAIA / 历表的 tmp 工作树搭建。"""

import os
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_OBS_DAY = (
    REPO_ROOT / "inputs" / "images" / "S9" / "2024" / "202411" / "20241103"
)
SOURCE_CATALOG = REPO_ROOT / "inputs" / "catalogs" / "S9" / "2024"


def require_runtime_deps():
    try:
        import astropy  # noqa: F401
        import cv2  # noqa: F401
        import matplotlib  # noqa: F401
        import numpy  # noqa: F401
        import scipy  # noqa: F401
    except ModuleNotFoundError as exc:
        raise unittest.SkipTest(f"requires ADIAS runtime deps: {exc}")


def require_source_fixture():
    if not SOURCE_OBS_DAY.exists():
        raise unittest.SkipTest(f"missing source obs day: {SOURCE_OBS_DAY}")
    if not SOURCE_CATALOG.exists():
        raise unittest.SkipTest(f"missing source catalog: {SOURCE_CATALOG}")


def build_fixture_tree(tmp):
    """在 tmp 下搭出 input/observation/20241103/fits + input/catalog/ + actual/MATH/。

    Returns (obs_day, catalog_dir, math_dir)。
    """
    obs_day = tmp / "input" / "observation" / "20241103"
    catalog_dir = tmp / "input" / "catalog"
    math_dir = tmp / "actual" / "MATH"
    obs_day.mkdir(parents=True)
    catalog_dir.mkdir(parents=True)
    math_dir.mkdir(parents=True)

    os.symlink(SOURCE_OBS_DAY / "fits", obs_day / "fits")
    for name in ("GAIA3_S9_202410.DAT", "EPH_S9_202411.DAT"):
        os.symlink(SOURCE_CATALOG / name, catalog_dir / name)

    return obs_day, catalog_dir, math_dir


def cfg_lines(tmp, catalog_dir, math_dir):
    """金标准 cfg 行列表，与原 adias2024.cfg 等价。"""
    return [
        f"1fitspath={tmp / 'input' / 'observation'}",
        "1biasflag=0",
        "1darkflag=0",
        "1flatflag=0",
        "1superflag=1",
        "1med_length=65",
        "1med_width=1",
        "1bkgdmode=2",
        "1enhance_flag=1",
        "2bkgd_threshold=5.0",
        "2snr_threshold=1.0",
        "2pos_method=1",
        "3tele_label=km100B",
        "3tele_focal=13300.0",
        "3ccd_scale=0.0135",
        "3ccd_fieldsize=15",
        "3modeltype=6",
        "3plate_angle=180.0",
        "3obj_ephsource=IMCCE",
        "3gaia_minmag=5.0",
        "3gaia_maxmag=18.5",
        "3match_limit=5.0",
        "3delta_T=0.0",
        "3obj_total=1",
        f"3obj_ephfile1={catalog_dir / 'EPH_S9_202411.DAT'}",
        f"3gaia_catfile1={catalog_dir / 'GAIA3_S9_202410.DAT'}",
        f"4specified-output={math_dir}",
        "4eps=0.2",
        "4std_limit=2.6",
        "4mean_limit=0",
        "4del_flag=0",
    ]


def write_cfg(tmp, name="adias_test.cfg"):
    """完整搭建：tree + cfg 文件。返回 (cfg_path, obs_day, catalog_dir, math_dir)。"""
    obs_day, catalog_dir, math_dir = build_fixture_tree(tmp)
    cfg = tmp / "input" / name
    cfg.write_text("\n".join(cfg_lines(tmp, catalog_dir, math_dir)), encoding="utf-8")
    return cfg, obs_day, catalog_dir, math_dir
