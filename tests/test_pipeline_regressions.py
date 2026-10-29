"""Regression checks with mocked writes: never delete or rewrite observation data."""

import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import Mock, mock_open, patch

from nspa.config import NspaConfig
from nspa.errors import ConfigError
from nspa.application.pipeline import PipelineRunner, StepResult
from nspa.core import analyzer, detector, matcher, preprocessor, reporter
from ui import inputs_panel as inputs


class CatalogTests(unittest.TestCase):
    def test_q_catalogs_visible_and_complete_without_duplicate_targets(self):
        files = [Path(f"Q_EPH_S{i}_200601.DAT") for i in range(1, 7)]
        files += [Path("EPH_S1_200601.DAT"), Path("Q_GAIA3_S0_200601.DAT")]
        files += [Path("notes.DAT")]
        with patch.object(Path, "is_dir", return_value=True), \
                patch.object(Path, "is_file", return_value=True), \
                patch.object(Path, "iterdir", return_value=iter(files)):
            eph, gaia, _ = inputs.scan_catalog("repo", "S", "2006")
        chosen, count = inputs.select_eph(eph, "200601")
        self.assertEqual(count, 6)
        self.assertTrue(all(Path(p).name.startswith("Q_") for p in chosen))
        self.assertEqual(gaia, ["Q_GAIA3_S0_200601.DAT"])
        name = inputs.matching_gaia_name(gaia, "200601")
        self.assertEqual(inputs.catalog_selection_errors(
            ["200601"], eph, chosen, name, True, gaia), [])

    def test_standard_catalogs_and_wrong_month(self):
        files = ["EPH_U1_202011.DAT", "EPH_U2_202011.DAT"]
        self.assertEqual(inputs.select_eph(files, "202011"), (files, 2))
        self.assertEqual(inputs.select_eph(files, "202012"), ([], 0))

    def test_q_labels_preserve_actual_target(self):
        config = NspaConfig("test")
        config.match.eph_files = ["Q_EPH_S6_200601.DAT"]
        self.assertEqual(reporter._object_labels(config, 1), {1: "S6"})


class ReportTests(unittest.TestCase):
    def discover(self, files, selected=None, total=11):
        with patch.object(Path, "glob", return_value=map(Path, files)), \
                patch.object(Path, "is_file", return_value=True):
            return reporter._discover_dat_files(Path("output"), total, selected)

    def test_latest_batch_excludes_history_and_does_not_fill_missing_targets(self):
        old = "run_20261022_100000_000001_2.dat"
        new = "run_20261023_100000_000001_1.dat"
        found = self.discover(["fits1.dat", old, new])
        self.assertEqual(found[1], [Path(new)])
        self.assertEqual(found[2], [])

    def test_explicit_batch_is_not_replaced_by_latest(self):
        old = Path("run_20261022_100000_000001_1.dat")
        found = self.discover(["run_20261023_100000_000001_1.dat"], [old])
        self.assertEqual(found[1], [old])

    def test_explicit_empty_batch_never_falls_back_to_history(self):
        self.assertTrue(all(not v for v in self.discover(["fits1.dat"], []).values()))

    def test_multidigit_targets(self):
        files = [Path(f"run_20261023_100000_000001_{i}.dat") for i in (1, 10, 11)]
        found = self.discover([], files)
        for i, file in zip((1, 10, 11), files):
            self.assertEqual(found[i], [file])

    def test_legacy_files_still_supported(self):
        found = self.discover(["fits1.dat", "fits10.dat", "fits11.dat"])
        for i in (1, 10, 11):
            self.assertEqual(found[i], [Path(f"fits{i}.dat")])


class FailureTests(unittest.TestCase):
    def config(self):
        config = NspaConfig("test", fitspaths=["missing"])
        return config

    def test_missing_and_empty_inputs_rejected_before_processing(self):
        for exists in (False, True):
            with self.subTest(exists=exists), \
                    patch("nspa.paths.expand_fitspath", return_value=[Path("missing")]), \
                    patch.object(Path, "is_dir", return_value=exists), \
                    patch("nspa.paths.list_fits", return_value=[]):
                with self.assertRaises(ConfigError):
                    self.config().validate(["pre"])

    def test_report_does_not_require_original_images(self):
        config = self.config()
        config.match.obj_total = 1
        config.comoc.output_dir = "output"
        with patch("nspa.paths.expand_fitspath") as expand:
            config.validate(["report"])
        expand.assert_not_called()

    def test_pre_missing_empty_and_intentionally_disabled(self):
        config = self.config()
        with patch.object(Path, "is_dir", return_value=False):
            self.assertFalse(preprocessor.run_pre(config, ["missing"]).success)
        with patch.object(Path, "is_dir", return_value=True), \
                patch.object(preprocessor, "list_fits", return_value=[]):
            self.assertFalse(preprocessor.run_pre(config, ["empty"]).success)
        with patch.object(Path, "is_dir", return_value=True), \
                patch.object(preprocessor, "list_fits", return_value=[Path("a.fit")]):
            self.assertTrue(preprocessor.run_pre(config, ["raw"]).success)

    def test_detect_empty_and_match_empty_catalog_fail(self):
        with patch.object(detector, "list_fits", return_value=[]):
            self.assertFalse(detector._run_detect_isolated(self.config(), ["empty"]).success)
        gaia = Mock()
        gaia.is_empty.return_value = True
        with patch.object(matcher, "_load_gaia", return_value=gaia):
            self.assertFalse(matcher.run_match(self.config(), ["empty"]).success)

    def test_steps_without_inputs_fail(self):
        config = self.config()
        self.assertFalse(preprocessor.run_pre(config, []).success)
        self.assertFalse(detector._run_detect_isolated(config, []).success)
        self.assertFalse(matcher.run_match(config, []).success)

    def test_pipeline_stops_on_explicit_failure_or_failed_items(self):
        for result in (StepResult("pre", success=False),
                       StepResult("pre", failed_items=["bad.fit"])):
            with self.subTest(result=result):
                first, second = Mock(), Mock()
                first.name = "pre"
                first.run.return_value = result
                with patch("nspa.application.pipeline.RunManifest") as manifest:
                    results = PipelineRunner([first, second]).run(Mock())
                self.assertFalse(results[0].success)
                second.run.assert_not_called()
                manifest.return_value.finish.assert_called_once()

    def test_warning_only_does_not_stop_pipeline(self):
        first, second = Mock(), Mock()
        first.run.return_value = StepResult("pre", warnings=["intentionally skipped"])
        second.run.return_value = StepResult("detect")
        with patch("nspa.application.pipeline.RunManifest"):
            self.assertEqual(len(PipelineRunner([first, second]).run(Mock())), 2)


class OutputTests(unittest.TestCase):
    def run_comoc(self, accepted):
        config = NspaConfig("test")
        config.match.obj_total = 1
        config.comoc.output_dir = "output"
        lines = ["row1", "row2"] if accepted else []
        with ExitStack() as stack:
            stack.enter_context(patch.object(Path, "mkdir"))
            stack.enter_context(patch.object(Path, "exists", return_value=True))
            opened = stack.enter_context(patch("builtins.open", mock_open()))
            replacements = {
                "list_fits": Mock(return_value=[]),
                "_observation_date_label": Mock(return_value="20251125"),
                "ensure_dir": lambda p: p,
                "out_dir": lambda p: Path("fake/fits_out"),
                "read_object_out": Mock(return_value=(lines, [], [])),
                "initial_stats": Mock(return_value=(0, 0, 0.1, 0.1)),
                "sigma_clip_oc": Mock(return_value=(lines, [], [], 0, 0, 0.1, 0.1, 0)),
                "write_oc_stat": Mock(), "write_comoc_lines": Mock(),
            }
            for name, value in replacements.items():
                stack.enter_context(patch.object(analyzer, name, value))
            result = analyzer.run_comoc(config, [Path("fake/fits")], "test")
        return result, [str(call.args[0]) for call in opened.call_args_list]

    def test_rejected_day_does_not_advertise_or_rewrite_old_results(self):
        result, opened = self.run_comoc(False)
        self.assertFalse(result.success)
        for marker in ("final_object", "_obsdata_", "202511251.out"):
            self.assertFalse(any(marker in p for p in result.output_files))
            self.assertFalse(any(marker in p for p in opened))

    def test_accepted_day_advertises_new_results(self):
        result, opened = self.run_comoc(True)
        self.assertTrue(result.success)
        for marker in ("final_object", "_obsdata_", "202511251.out"):
            outputs = [p for p in result.output_files if marker in p]
            self.assertEqual(len(outputs), 1)
            self.assertIn(outputs[0], opened)


if __name__ == "__main__":
    unittest.main()
