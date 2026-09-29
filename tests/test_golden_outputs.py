import json
import os
import re
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests._fixtures import (
    REPO_ROOT,
    SOURCE_CATALOG,
    SOURCE_OBS_DAY,
    build_fixture_tree,
    cfg_lines,
    require_runtime_deps,
    require_source_fixture,
)


EXPECTED_ROOT = REPO_ROOT / "tests" / "golden" / "expected"


def _png_size(path):
    with open(path, "rb") as f:
        header = f.read(24)
    if header[:8] != b"\x89PNG\r\n\x1a\n":
        raise AssertionError(f"not a PNG file: {path}")
    return struct.unpack(">II", header[16:24])


def _normalized_text(path):
    text = Path(path).read_text(encoding="utf-8").rstrip() + "\n"
    return re.sub(
        r"\S+/20241103/[Ff][Ii][Tt][Ss]/([^ \n]+?\.fit)",
        r"<FITS_DIR>/\1",
        text,
    )


class GoldenOutputTests(unittest.TestCase):
    maxDiff = None

    def setUp(self):
        require_runtime_deps()
        require_source_fixture()

    def test_full_pipeline_matches_golden_outputs(self):
        with tempfile.TemporaryDirectory() as tmp_name:
            tmp = Path(tmp_name)
            cfg = self._prepare_input_tree(tmp)
            self._run_pipeline(tmp, cfg)
            # 中间产物（fits_reg/ fits_ref/ fits_out/）只有在 expected/ 下有对应
            # 子树时才做对比；MATH/ 和 png/控制台 marker 是最终交付物，必查。
            for stage in ("fits_reg", "fits_ref", "fits_out"):
                expected = EXPECTED_ROOT / "observation" / "20241103" / stage
                if expected.is_dir():
                    self._assert_text_tree(
                        expected,
                        tmp / "input" / "observation" / "20241103" / stage,
                    )
            self._assert_text_tree(
                EXPECTED_ROOT / "MATH", tmp / "actual" / "MATH", allow_extra=True
            )
            self._assert_png_metadata(tmp / "actual" / "MATH")
            self._assert_console_markers(tmp / "控制台输出.txt")

    def _prepare_input_tree(self, tmp):
        _obs_day, catalog_dir, math_dir = build_fixture_tree(tmp)
        cfg = tmp / "input" / "nspa_golden.cfg"
        cfg.write_text(
            "\n".join(cfg_lines(tmp, catalog_dir, math_dir)),
            encoding="utf-8",
        )
        return cfg

    def _run_pipeline(self, tmp, cfg):
        env = os.environ.copy()
        env["PYTHONPATH"] = (
            str(REPO_ROOT)
            if not env.get("PYTHONPATH")
            else f"{REPO_ROOT}{os.pathsep}{env['PYTHONPATH']}"
        )
        env["MPLCONFIGDIR"] = str(tmp / "cache" / "matplotlib")
        env["XDG_CACHE_HOME"] = str(tmp / "cache")
        env["HOME"] = str(tmp)
        (tmp / "cache").mkdir()

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "nspa.main",
                "--config",
                str(cfg),
                "--step",
                "all",
            ],
            cwd=tmp,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=300,
        )
        if result.returncode != 0:
            self.fail(result.stdout)

    def _assert_text_tree(self, expected_dir, actual_dir, allow_extra=False):
        expected_files = sorted(p for p in expected_dir.iterdir() if p.is_file())
        actual_files = sorted(p for p in actual_dir.iterdir() if p.is_file())
        if allow_extra:
            actual_names = {p.name for p in actual_files}
            missing = [p.name for p in expected_files if p.name not in actual_names]
            self.assertEqual([], missing, f"missing expected files in {actual_dir}")
        else:
            self.assertEqual(
                [p.name for p in expected_files],
                [p.name for p in actual_files],
                f"file list mismatch for {actual_dir}",
            )
        for expected in expected_files:
            actual = actual_dir / expected.name
            self.assertEqual(
                _normalized_text(expected),
                _normalized_text(actual),
                f"golden mismatch: {expected.name}",
            )

    def _assert_png_metadata(self, actual_math_dir):
        expected = json.loads(
            (EXPECTED_ROOT / "png_metadata.json").read_text(encoding="utf-8")
        )
        for name, size in expected.items():
            self.assertEqual(tuple(size), _png_size(actual_math_dir / name))

    def _assert_console_markers(self, console_path):
        text = console_path.read_text(encoding="utf-8")
        for marker in (
            "========== 01: 超级背景预处理 ==========",
            "========== 02: 星象检测 ==========",
            "========== 03: 星象匹配归算 ==========",
            "========== 04: O-C 统计 ==========",
            "========== 05: O-C 散点图报告 ==========",
            "总耗时:",
        ):
            self.assertIn(marker, text)


if __name__ == "__main__":
    unittest.main()
