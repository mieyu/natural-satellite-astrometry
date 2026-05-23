import os
import tempfile
import unittest
from pathlib import Path

from adias.paths import expand_fitspath, stage_dirs


class ExpandFitspathTests(unittest.TestCase):
    def test_date_subdirs_with_lowercase_fits(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for day in ("20240301", "20240302"):
                (root / day / "fits").mkdir(parents=True)

            result = expand_fitspath([str(root)])

            self.assertEqual(
                sorted(result),
                [
                    str(root / "20240301" / "fits"),
                    str(root / "20240302" / "fits"),
                ],
            )

    def test_date_subdirs_with_uppercase_fits(self):
        # 在大小写不敏感的 FS（macOS 默认）上 FITS 和 fits 是同一目录，
        # 这里只验证日期目录被展开且子目录名是 fits/FITS 之一。
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "20241103" / "FITS").mkdir(parents=True)

            result = expand_fitspath([str(root)])

            self.assertEqual(len(result), 1)
            self.assertTrue(result[0].endswith(("/fits", "/FITS")))
            self.assertTrue(result[0].startswith(str(root / "20241103")))

    def test_direct_dir_passthrough(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "obs_direct"
            root.mkdir()

            result = expand_fitspath([str(root)])

            self.assertEqual(result, [str(root)])

    def test_non_date_subdirs_are_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "notes" / "fits").mkdir(parents=True)
            (root / "20240301" / "fits").mkdir(parents=True)

            result = expand_fitspath([str(root)])

            self.assertEqual(result, [str(root / "20240301" / "fits")])


class StageDirsTests(unittest.TestCase):
    def test_stage_dirs_siblings_of_input(self):
        fitspath = "/tmp/obs/20240301/fits"
        stages = stage_dirs(fitspath)

        parent = os.path.dirname(fitspath)
        self.assertEqual(stages["fits_n"], os.path.join(parent, "fits_n"))
        self.assertEqual(stages["fits_reg"], os.path.join(parent, "fits_reg"))
        self.assertEqual(stages["fits_ref"], os.path.join(parent, "fits_ref"))
        self.assertEqual(stages["fits_out"], os.path.join(parent, "fits_out"))


if __name__ == "__main__":
    unittest.main()
