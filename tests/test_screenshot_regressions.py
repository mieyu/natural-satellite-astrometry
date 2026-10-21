"""截图暴露的输入月份、日期标记与报告来源回归检查。"""

import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from nspa.application.pipeline import StepResult
from nspa.application.steps import ComocStep, ReportStep
from nspa.core.analyzer import _observation_date_label
from nspa.io.catalog_io import read_catalog
from nspa.core.reporter import _discover_dat_files, _object_labels, run_report
from ui.cfg_writer import build_cfg_text
from ui.inputs_panel import (
    catalog_selection_errors,
    matching_gaia_name,
    observation_months,
    resolve_gaia_name,
    scan_catalog,
    select_eph,
)


class ScreenshotRegressionTests(unittest.TestCase):
    def test_observation_months_uses_actual_fits_names_and_detects_mixed_months(self):
        day = Path("images/S9/2025/fits")
        with patch("ui.inputs_panel.list_fits", return_value=[
            day / "20251125S9-001I.fit", day / "20251218S9-001I.fit"
        ]):
            self.assertEqual(observation_months([day]), ["202511", "202512"])

    def test_observation_months_accepts_historic_2006_filenames(self):
        day = Path("images/S/2006/060127/fits")
        with patch("ui.inputs_panel.list_fits", return_value=[
            day / "S9_SHAO156_156cm_20060127170901.fits"
        ]):
            self.assertEqual(observation_months([day]), ["200601"])

    def test_missing_month_does_not_fall_back_to_old_ephemeris(self):
        files = [
            "EPH_N0_202512.DAT",
            "EPH_N1_202512.DAT",
            "EPH_N2_202410.DAT",
        ]
        selected, count = select_eph(files, "202512")
        self.assertEqual(selected, files[:2])
        self.assertEqual(count, 2)

    def test_gaia_default_uses_matching_month(self):
        files = ["GAIA3_S9_202511.DAT", "GAIA3_S9_202512.DAT"]
        self.assertEqual(matching_gaia_name(files, "202512"), files[1])
        self.assertEqual(matching_gaia_name(files, "202501"), "")
        self.assertEqual(matching_gaia_name(files, "202512", files[0]), files[0])
        self.assertEqual(matching_gaia_name(files, "202512", "missing.DAT"), files[1])
        self.assertEqual(matching_gaia_name([
            "GAIA3_N0_202512.DAT", "GAIA3_N1_202512.DAT"
        ], "202512"), "")

    def test_catalog_validation_allows_selected_cross_month_gaia(self):
        all_eph = ["EPH_N0_202512.DAT", "EPH_N1_202512.DAT", "EPH_N2_202410.DAT"]
        gaia_files = ["GAIA3_N0_202511.DAT", "GAIA3_N0_202512.DAT"]
        errors = catalog_selection_errors(
            ["202512"], all_eph, all_eph[:2], gaia_files[0], True, gaia_files
        )
        self.assertTrue(any("N2" in error for error in errors))
        self.assertFalse(any("GAIA" in error for error in errors))
        self.assertEqual(catalog_selection_errors(
            ["202512"], all_eph[:2], all_eph[:2], gaia_files[0], True, gaia_files
        ), [])
        self.assertTrue(any("没有选中 GAIA" in error for error in catalog_selection_errors(
            ["202512"], all_eph[:2], all_eph[:2], "", True, gaia_files
        )))
        self.assertTrue(any("GAIA" in error for error in catalog_selection_errors(
            ["202512"], all_eph[:2], all_eph[:2], "missing.DAT", True, gaia_files
        )))
        self.assertTrue(any("目标历表与观测月" in error for error in catalog_selection_errors(
            ["202512"], all_eph[:2], ["EPH_N0_202511.DAT"], gaia_files[0],
            False, gaia_files
        )))
        self.assertTrue(catalog_selection_errors(
            ["202511", "202512"], all_eph[:2], all_eph[:2],
            gaia_files[1], True, gaia_files
        ))

    def test_real_november_observation_can_use_october_gaia_catalog(self):
        repo = Path(__file__).resolve().parent.parent
        eph, gaia, _ = scan_catalog(repo, "S9", "2024")
        selected_eph, _ = select_eph(eph, "202411")
        selected_gaia = "GAIA3_S9_202410.DAT"
        self.assertEqual(matching_gaia_name(gaia, "202411"), "")
        self.assertEqual(matching_gaia_name(gaia, "202411", selected_gaia),
                         selected_gaia)
        self.assertEqual(catalog_selection_errors(
            ["202411"], eph, selected_eph, selected_gaia, True, gaia
        ), [])
        selected_path = resolve_gaia_name(gaia, selected_gaia)
        self.assertTrue(Path(selected_path).is_file())
        self.assertGreater(read_catalog(selected_path, 0, 20)[0], 0)
        cfg = build_cfg_text({}, [], selected_eph, selected_path, header=False)
        self.assertIn(f"3gaia_catfile1={selected_path}", cfg)

    def test_report_only_reads_current_run_files_when_given(self):
        outdir = Path("outputs/results/N0/2025")
        current = outdir / "run_20261012_123456_1.dat"
        with patch.object(Path, "is_file", return_value=True):
            selected = _discover_dat_files(outdir, 2, [current])
        self.assertEqual(selected, {1: [current], 2: []})

    def test_report_labels_follow_ephemeris_codes(self):
        config = SimpleNamespace(match=SimpleNamespace(eph_files=[
            "EPH_N0_202512.DAT", "EPH_N1_202512.DAT", "EPH_N2_202512.DAT"
        ]))
        self.assertEqual(_object_labels(config, 3), {1: "N0", 2: "N1", 3: "N2"})

    def test_report_fails_when_current_run_has_no_data_even_if_old_files_exist(self):
        config = SimpleNamespace(
            match=SimpleNamespace(obj_total=1, eph_files=["EPH_S9_202511.DAT"]),
            report=SimpleNamespace(per_satellite=False, sat_prefix="S"),
            comoc=SimpleNamespace(output_dir="outputs/results/S9/2025"),
        )
        outdir = Path("outputs/results/S9/2025")
        with patch.object(Path, "is_dir", return_value=True):
            result = run_report(config, outdir=outdir, dat_files=[])
        self.assertFalse(result.success)
        self.assertFalse(result.output_files)

    def test_report_step_receives_only_this_runs_comoc_files(self):
        current = Path("outputs/results/N0/2025/run_20261012_123456_1.dat")
        ctx = SimpleNamespace(
            config=object(), fitspath_list=[], run_id="20261012_123456",
            selected_steps=["comoc", "report"], report_dat_files=[]
        )
        with patch("nspa.core.analyzer.run_comoc", return_value=StepResult(
            "comoc", output_files=[str(current), "outputs/results/N0/2025/00oc_1.out"]
        )):
            ComocStep().run(ctx)
        self.assertEqual(ctx.report_dat_files, [current])
        with patch("nspa.core.reporter.run_report", return_value=StepResult("report")) as run:
            ReportStep().run(ctx)
        self.assertEqual(run.call_args.kwargs["dat_files"], [current])

    def test_invalid_fits_filename_uses_header_date(self):
        fit = Path("images/N0/2022/202211/fits/2022113N-I_001n.fit")
        with patch("nspa.core.analyzer.read_fits_header", return_value={
            "year": 2022, "month": 11, "day": 30
        }):
            self.assertEqual(
                _observation_date_label(fit.parent, [fit], "km100c", 1), "20221130"
            )


if __name__ == "__main__":
    unittest.main()
