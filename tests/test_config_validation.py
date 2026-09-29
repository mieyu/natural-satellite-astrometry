"""cfg validate 各类错误场景：用最小 cfg 覆盖每个 validate 分支。"""

import tempfile
import unittest
from pathlib import Path

from nspa.config import load_config
from nspa.errors import ConfigError


def _write_cfg(root, **overrides):
    """搭一份默认能跑通 match 阶段的最小 cfg；overrides 用于打靶单个字段。"""
    fitspath = root / "obs"
    fitspath.mkdir(parents=True, exist_ok=True)
    gaia = root / "gaia.dat"
    eph = root / "eph.dat"
    for f in (gaia, eph):
        f.write_text("", encoding="utf-8")

    defaults = {
        "1fitspath": str(fitspath),
        "1superflag": "1",
        "2bkgd_threshold": "5.0",
        "2snr_threshold": "1.0",
        "2pos_method": "1",
        "2connectivity": "fortran",
        "3tele_label": "km100B",
        "3tele_focal": "13300.0",
        "3ccd_scale": "0.0135",
        "3ccd_fieldsize": "15",
        "3modeltype": "6",
        "3plate_angle": "180.0",
        "3gaia_minmag": "5.0",
        "3gaia_maxmag": "18.5",
        "3match_limit": "5.0",
        "3obj_total": "1",
        "3gaia_catfile1": str(gaia),
        "3obj_ephfile1": str(eph),
        "4specified-output": str(root / "math"),
    }
    defaults.update(overrides)
    lines = [f"{k}={v}" for k, v in defaults.items() if v is not None]
    cfg = root / "nspa.cfg"
    cfg.write_text("\n".join(lines), encoding="utf-8")
    return cfg


def _load(root, steps, **overrides):
    cfg = _write_cfg(root, **overrides)
    return load_config(str(cfg), steps=steps)


class ConfigValidateBaselineTests(unittest.TestCase):
    """基线 cfg 在所有 step 下都应能加载成功（兜底防回归）。"""

    def test_default_cfg_loads_for_all_steps(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = _load(Path(tmp), steps=["all"])
        self.assertEqual(config.match.obj_total, 1)


class ConfigValidatePreErrorTests(unittest.TestCase):
    def test_missing_fitspath_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ConfigError, "1fitspath"):
                _load(Path(tmp), steps=["pre"], **{"1fitspath": None})

    def test_invalid_superflag_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ConfigError, "1superflag"):
                _load(Path(tmp), steps=["pre"], **{"1superflag": "9"})


class ConfigValidateDetectErrorTests(unittest.TestCase):
    def test_invalid_connectivity_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ConfigError, "2connectivity"):
                _load(Path(tmp), steps=["detect"], **{"2connectivity": "bogus"})


class ConfigValidateMatchErrorTests(unittest.TestCase):
    def test_zero_obj_total_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ConfigError, "3obj_total"):
                _load(Path(tmp), steps=["match"], **{"3obj_total": "0"})

    def test_invalid_modeltype_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ConfigError, "3modeltype"):
                _load(Path(tmp), steps=["match"], **{"3modeltype": "7"})

    def test_missing_gaia_catfile_rejected(self):
        # 给一个不存在的 GAIA 路径
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            with self.assertRaisesRegex(ConfigError, "GAIA"):
                _load(tmp_path, steps=["match"],
                      **{"3gaia_catfile1": str(tmp_path / "missing_gaia.dat")})

    def test_missing_ephemeris_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            with self.assertRaisesRegex(ConfigError, "历表"):
                _load(tmp_path, steps=["match"],
                      **{"3obj_ephfile1": str(tmp_path / "missing_eph.dat")})


class ConfigValidateComocErrorTests(unittest.TestCase):
    def test_missing_specified_output_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ConfigError, "4specified-output"):
                _load(Path(tmp), steps=["comoc"], **{"4specified-output": None})


if __name__ == "__main__":
    unittest.main()
