import tempfile
import unittest
from pathlib import Path

from nspa.application.context import build_context
from nspa.config import load_config
from nspa.errors import ConfigError


class ConfigApplicationTests(unittest.TestCase):
    def _write_cfg(self, root, obj_total=1, eph_count=1):
        fitspath = root / "obs"
        gaia = root / "gaia.dat"
        gaia.write_text("", encoding="utf-8")
        eph_files = []
        for idx in range(1, eph_count + 1):
            eph = root / f"eph{idx}.dat"
            eph.write_text("", encoding="utf-8")
            eph_files.append(eph)

        lines = [
            f"1fitspath={fitspath}",
            "1superflag=1",
            "2bkgd_threshold=5.0",
            "2snr_threshold=1.0",
            "2pos_method=1",
            "3tele_label=km100B",
            "3tele_focal=13300.0",
            "3ccd_scale=0.0135",
            "3ccd_fieldsize=15",
            "3modeltype=6",
            "3plate_angle=180.0",
            "3gaia_minmag=5.0",
            "3gaia_maxmag=18.5",
            "3match_limit=5.0",
            f"3obj_total={obj_total}",
            f"3gaia_catfile1={gaia}",
            f"4specified-output={root / 'math'}",
        ]
        lines.extend(
            f"3obj_ephfile{idx}={eph}" for idx, eph in enumerate(eph_files, 1)
        )
        cfg = root / "nspa.cfg"
        cfg.write_text("\n".join(lines), encoding="utf-8")
        return cfg

    def test_load_config_maps_typed_sections(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = self._write_cfg(Path(tmp))
            config = load_config(str(cfg), steps=["match"])

        self.assertEqual(config.pre.superflag, 1)
        self.assertEqual(config.detect.connectivity, "fortran")
        self.assertEqual(config.match.obj_total, 1)
        self.assertEqual(config.match.model_type, 6)

    def test_load_config_rejects_obj_total_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = self._write_cfg(Path(tmp), obj_total=2, eph_count=1)
            with self.assertRaises(ConfigError):
                load_config(str(cfg), steps=["match"])

    def test_build_context_keeps_stage_directory_names(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = self._write_cfg(Path(tmp))
            config = load_config(str(cfg), steps=["pre"])
            ctx = build_context(config, ["pre"])

        self.assertEqual(len(ctx.observation_dirs), 1)
        self.assertEqual(ctx.observation_dirs[0].pre_dir.name, "fits_n")
        self.assertEqual(ctx.observation_dirs[0].reg_dir.name, "fits_reg")
        self.assertEqual(ctx.observation_dirs[0].ref_dir.name, "fits_ref")
        self.assertEqual(ctx.observation_dirs[0].out_dir.name, "fits_out")


if __name__ == "__main__":
    unittest.main()
