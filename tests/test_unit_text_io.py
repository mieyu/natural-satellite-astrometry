import tempfile
import unittest
from pathlib import Path


def _require_numpy():
    try:
        import numpy  # noqa: F401
    except ModuleNotFoundError as exc:
        raise unittest.SkipTest(f"requires numpy: {exc}")


class RegFileRoundTripTests(unittest.TestCase):
    def setUp(self):
        _require_numpy()

    def test_write_then_read_preserves_geometry_and_flux(self):
        from adias.io.text_io import read_reg_file, write_reg_file

        stars = [
            {
                "starx": 100.123,
                "stary": 200.456,
                "sumi": 12345.6789,
                "snr": 9.87,
                "star_id": 1,
                "star_pix": 12,
                "overflag": 0,
            },
            {
                "starx": 300.0,
                "stary": 400.5,
                "sumi": 5000.0,
                "snr": 50.0,
                "star_id": 2,
                "star_pix": 20,
                "overflag": 0,
            },
        ]

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "tile.fit.reg"
            n_out = write_reg_file(str(path), stars, bkgd=10.0, bkgdsigma=2.5, snr_threshold=1.0)
            self.assertEqual(n_out, 2)

            det_x, det_y, det_flux, det_snr = read_reg_file(str(path))
            self.assertEqual(len(det_x), 2)
            self.assertAlmostEqual(float(det_x[0]), 100.123, places=3)
            self.assertAlmostEqual(float(det_y[0]), 200.456, places=3)
            self.assertAlmostEqual(float(det_flux[0]), 12345.6789, places=3)
            self.assertAlmostEqual(float(det_snr[0]), 9.87, places=2)

    def test_filters_low_snr_small_pixels_overflag(self):
        from adias.io.text_io import read_reg_file, write_reg_file

        stars = [
            # 通过：snr>1, pix>5, overflag=0
            {"starx": 1.0, "stary": 1.0, "sumi": 100.0, "snr": 5.0,
             "star_id": 1, "star_pix": 10, "overflag": 0},
            # 过滤：snr 太低
            {"starx": 2.0, "stary": 2.0, "sumi": 100.0, "snr": 0.5,
             "star_id": 2, "star_pix": 10, "overflag": 0},
            # 过滤：像素太少
            {"starx": 3.0, "stary": 3.0, "sumi": 100.0, "snr": 5.0,
             "star_id": 3, "star_pix": 3, "overflag": 0},
            # 过滤：饱和
            {"starx": 4.0, "stary": 4.0, "sumi": 100.0, "snr": 5.0,
             "star_id": 4, "star_pix": 10, "overflag": 1},
        ]

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "filtered.fit.reg"
            n_out = write_reg_file(str(path), stars, bkgd=0.0, bkgdsigma=1.0, snr_threshold=1.0)
            self.assertEqual(n_out, 1)

            det_x, _, _, _ = read_reg_file(str(path))
            self.assertEqual(len(det_x), 1)
            self.assertAlmostEqual(float(det_x[0]), 1.0, places=3)


class ObjectOutRoundTripTests(unittest.TestCase):
    def setUp(self):
        _require_numpy()

    def test_write_then_read_residuals(self):
        from adias.io.text_io import read_object_out, write_object_result

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "object_1.out"
            obj_ephra = 100.0
            obj_ephde = -5.0
            # 残差对应 = (obs - eph)*3600*cos(de_rad)
            # 这里制造一个 0.5 角秒 RA 偏差、-0.3 角秒 DE 偏差
            import math
            obj_obsde = obj_ephde + (-0.3 / 3600.0)
            obj_obsra = obj_ephra + (0.5 / 3600.0) / math.cos(obj_ephde * math.pi / 180.0)

            with open(path, "w", encoding="utf-8") as fh:
                write_object_result(
                    fh,
                    year=2024,
                    month=11,
                    obj_T=3.123456,
                    obj_obsra=obj_obsra,
                    obj_obsde=obj_obsde,
                    obj_ephra=obj_ephra,
                    obj_ephde=obj_ephde,
                    sig0=0.05,
                    hh=10,
                    mm=20,
                    ss=30.5,
                    exptime=15.0,
                    objfitsfile="dummy.fit",
                    field_angle=180.0,
                )

            lines, res_ra, res_de = read_object_out(str(path))
            self.assertEqual(len(lines), 1)
            self.assertAlmostEqual(res_ra[0], 0.5, places=2)
            self.assertAlmostEqual(res_de[0], -0.3, places=2)

    def test_large_residual_dropped(self):
        """|残差| ≥ 10″ 时 write_object_result 应丢弃该行。"""
        from adias.io.text_io import read_object_out, write_object_result

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "object_1.out"
            with open(path, "w", encoding="utf-8") as fh:
                write_object_result(
                    fh, 2024, 11, 3.0,
                    100.005, -5.0,  # ra 偏 18 角秒
                    100.0, -5.0,
                    0.05, 10, 20, 30.0, 15.0, "x.fit", 180.0,
                )

            lines, _, _ = read_object_out(str(path))
            self.assertEqual(lines, [])


if __name__ == "__main__":
    unittest.main()
