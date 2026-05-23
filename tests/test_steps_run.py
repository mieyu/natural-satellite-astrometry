"""Step 级回归：每个 run_* 在合适输入下能跑通，且 StepResult 有合理内容。

总耗时约等于一次 --step all，因为 5 步顺序复用同一棵 tmp 树。
"""

import os
import tempfile
import unittest
from pathlib import Path

from tests._fixtures import (
    SOURCE_OBS_DAY,
    require_runtime_deps,
    require_source_fixture,
    write_cfg,
)


def _build_config(tmp):
    """搭一棵 tmp 工作树，返回 (AdiasConfig, fitspath_list)。"""
    from adias.config import load_config

    cfg, obs_day, _, _ = write_cfg(tmp, name="adias_steps.cfg")
    config = load_config(str(cfg), steps=["all"])
    fitspath_list = [obs_day / "fits"]
    return config, fitspath_list


class StepSequentialRegressionTests(unittest.TestCase):
    """按顺序跑 pre→detect→match→comoc→report，验证每步 StepResult 合理。"""

    def setUp(self):
        require_runtime_deps()
        require_source_fixture()

    def test_each_step_returns_populated_step_result(self):
        from adias.core.analyzer import run_comoc
        from adias.core.detector import run_detect
        from adias.core.matcher import run_match
        from adias.core.preprocessor import run_pre
        from adias.core.reporter import run_report

        with tempfile.TemporaryDirectory() as tmp_name:
            tmp = Path(tmp_name)
            config, fitspath_list = _build_config(tmp)

            pre_result = run_pre(config, fitspath_list)
            self.assertEqual(pre_result.name, "pre")
            self.assertTrue(pre_result.output_files, "pre 应产出 _n.fit")
            self.assertTrue(
                all(p.endswith("_n.fit") for p in pre_result.output_files)
            )

            det_result = run_detect(config, fitspath_list)
            self.assertEqual(det_result.name, "detect")
            self.assertTrue(det_result.output_files, "detect 应产出 .fit.reg")
            self.assertTrue(
                all(p.endswith(".fit.reg") for p in det_result.output_files)
            )

            match_result = run_match(config, fitspath_list)
            self.assertEqual(match_result.name, "match")
            self.assertTrue(
                any("object_" in p for p in match_result.output_files),
                "match 应产出 object_N.out",
            )

            comoc_result = run_comoc(config, fitspath_list)
            self.assertEqual(comoc_result.name, "comoc")
            self.assertTrue(
                any(p.endswith(".dat") for p in comoc_result.output_files),
                "comoc 应产出 .dat",
            )

            report_result = run_report(config)
            self.assertEqual(report_result.name, "report")
            self.assertTrue(
                any("OC_summary.png" in p for p in report_result.output_files),
                "report 应产出 OC_summary.png",
            )


class PreSuperflagZeroTests(unittest.TestCase):
    """superflag=0：run_pre 应短路、不产出 _n.fit、记录跳过 warning。"""

    def setUp(self):
        require_runtime_deps()
        require_source_fixture()

    def test_superflag_zero_produces_no_pre_outputs(self):
        from adias.config import AdiasConfig, PreConfig
        from adias.core.preprocessor import run_pre

        with tempfile.TemporaryDirectory() as tmp_name:
            tmp = Path(tmp_name)
            obs_day = tmp / "obs" / "20241103"
            obs_day.mkdir(parents=True)
            os.symlink(SOURCE_OBS_DAY / "FITS", obs_day / "fits")

            fitspath = obs_day / "fits"
            config = AdiasConfig(
                config_path="<test>",
                pre=PreConfig(
                    superflag=0, med_length=65, med_width=1,
                    bkgdmode=2, enhance_flag=1,
                ),
            )

            result = run_pre(config, [fitspath])

            self.assertEqual(result.name, "pre")
            self.assertEqual(result.output_files, [])
            self.assertTrue(
                any("superflag=0" in w for w in result.warnings),
                f"应记录 superflag=0 跳过 warning，实际: {result.warnings}",
            )

            pre_dir = obs_day / "fits_n"
            if pre_dir.exists():
                self.assertEqual(list(pre_dir.iterdir()), [])


class EmptyFitspathListSmokeTests(unittest.TestCase):
    """fitspath_list=[] 时各 run_* 应返回空 StepResult 而非抛异常。"""

    def setUp(self):
        require_runtime_deps()

    def test_run_pre_empty_list(self):
        from adias.config import AdiasConfig, PreConfig
        from adias.core.preprocessor import run_pre

        config = AdiasConfig(
            config_path="<test>",
            pre=PreConfig(superflag=1, med_length=65, med_width=1,
                          bkgdmode=2, enhance_flag=1),
        )
        result = run_pre(config, [])
        self.assertEqual(result.name, "pre")
        self.assertEqual(result.output_files, [])

    def test_run_detect_empty_list(self):
        from adias.config import AdiasConfig, DetectConfig, PreConfig
        from adias.core.detector import run_detect

        config = AdiasConfig(
            config_path="<test>",
            pre=PreConfig(superflag=1),
            detect=DetectConfig(
                bkgd_threshold=5.0, snr_threshold=1.0,
                pos_method=1, connectivity="fortran",
            ),
        )
        result = run_detect(config, [])
        self.assertEqual(result.name, "detect")
        self.assertEqual(result.output_files, [])


if __name__ == "__main__":
    unittest.main()
