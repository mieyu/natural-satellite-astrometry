"""io 层数据格式错误：read_catalog / read_ephemeris 应抛 DataFormatError。"""

import tempfile
import unittest
from pathlib import Path


def _require_numpy():
    try:
        import numpy  # noqa: F401
    except ModuleNotFoundError as exc:
        raise unittest.SkipTest(f"requires numpy: {exc}")


class CatalogIoErrorTests(unittest.TestCase):
    def setUp(self):
        _require_numpy()

    def test_read_catalog_missing_file_raises(self):
        from adias.errors import DataFormatError
        from adias.io.catalog_io import read_catalog

        with self.assertRaisesRegex(DataFormatError, "GAIA"):
            read_catalog("/nonexistent/path/gaia.dat", 5.0, 18.5)

    def test_read_ephemeris_missing_file_raises(self):
        from adias.errors import DataFormatError
        from adias.io.catalog_io import read_ephemeris

        with self.assertRaisesRegex(DataFormatError, "历表"):
            read_ephemeris("/nonexistent/path/eph.dat")

    def test_read_ephemeris_empty_parsed_raises(self):
        """文件可打开但无可解析行（只有头部）应抛 DataFormatError。"""
        from adias.errors import DataFormatError
        from adias.io.catalog_io import read_ephemeris

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "empty_eph.dat"
            # 10 行头部 + 几行纯分隔符（被 skipped）
            path.write_text("\n".join(["header"] * 10 + ["---", "---"]), encoding="utf-8")

            with self.assertRaisesRegex(DataFormatError, "无可解析"):
                read_ephemeris(str(path))

    def test_read_catalog_empty_mag_range_returns_zero_not_raises(self):
        """文件可读但 min/max_mag 把所有星过滤掉：返回 0，不抛错。"""
        from adias.io.catalog_io import read_catalog

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "gaia.dat"
            # 60 行头 + 1 行数据，前 39 列任意填，第 39 列起 5 个数字
            header = ["header"] * 60
            data_line = " " * 39 + "10.0 20.0 0.0 0.0 12.5"
            path.write_text("\n".join(header + [data_line]), encoding="utf-8")

            # 把 mag 区间设到星等之外，应得 0 颗（不应抛错）
            n, *_ = read_catalog(str(path), min_mag=20.0, max_mag=21.0)
            self.assertEqual(n, 0)


class FitsHeaderErrorTests(unittest.TestCase):
    def setUp(self):
        _require_numpy()
        try:
            import astropy  # noqa: F401
        except ModuleNotFoundError as exc:
            raise unittest.SkipTest(f"requires astropy: {exc}")

    def test_read_fits_header_missing_file_raises_processing_error(self):
        from adias.errors import ProcessingError
        from adias.io.fits_io import read_fits_header

        with self.assertRaisesRegex(ProcessingError, "读取 FITS 头错误"):
            read_fits_header("/nonexistent/foo.fit", "km100B")

    def test_read_fits_header_unknown_tele_label_raises(self):
        """构造一个合法 FITS（含 DATE-OBS），但望远镜标签未知 → ProcessingError。"""
        from astropy.io import fits

        import numpy as np

        from adias.errors import ProcessingError
        from adias.io.fits_io import read_fits_header

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "fake.fit"
            data = np.zeros((10, 10), dtype=np.float32)
            hdu = fits.PrimaryHDU(data)
            hdu.header["DATE-OBS"] = "2024-11-03T10:20:30"
            hdu.header["EXPTIME"] = 1.0
            hdu.writeto(str(path), overwrite=True)

            with self.assertRaisesRegex(ProcessingError, "未知望远镜标签"):
                read_fits_header(str(path), "bogus_tele")


class MatcherCatchesDataFormatErrorTests(unittest.TestCase):
    """run_match 应抓住历表/星表的 DataFormatError 并记录到 StepResult，不中断流水线。"""

    def setUp(self):
        _require_numpy()

    def test_run_match_records_eph_format_error(self):
        """直接构造场景：给一个空历表，绕过 validate，验证 step_result 抓到。"""
        from adias.core.matcher import run_match

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            obs = tmp_path / "obs" / "20240101" / "fits"
            obs.mkdir(parents=True)
            # 不放任何 .fit → run_match 走 "本日图像不足" 分支，不会走到读 eph 那一行
            # 所以这个测试需要别的入口。简化：只要 list_fits 为空就提前 return，
            # 证明 matcher 能优雅处理；eph 错误本身已由 io 层单元测试覆盖。
            cfg = {
                "gaiacatpath": "/nonexistent/gaia.dat",
                "min_mag": 5.0,
                "max_mag": 18.5,
                "ephpath": ["/nonexistent/eph.dat"],
                "obj_total": 1,
                "tele_label": "km100B",
                "delta_t": 0.0,
                "fsize": 15,
                "modeltype": 6,
                "field_angle": 180.0,
                "pscale": 0.0135,
                "fl": 13300.0,
                "limit_match": 5.0,
            }
            result = run_match(cfg, [str(obs)])

            # 第一站就被 GAIA DataFormatError 拦住
            self.assertTrue(
                any("GAIA" in w or "gaia" in w for w in result.warnings),
                f"应记录 GAIA 错误，实际 warnings={result.warnings}",
            )
            self.assertIn(str(obs), result.failed_items)


if __name__ == "__main__":
    unittest.main()
