import unittest


def _require_numpy():
    try:
        import numpy  # noqa: F401
    except ModuleNotFoundError as exc:
        raise unittest.SkipTest(f"requires numpy: {exc}")


class InterpolateTests(unittest.TestCase):
    def setUp(self):
        _require_numpy()

    def test_recovers_node_value(self):
        from nspa.utils.math_utils import interpolate

        x = [0.0, 1.0, 2.0, 3.0]
        y = [0.0, 2.0, 4.0, 6.0]
        self.assertAlmostEqual(interpolate(x, y, 4, 1.0), 2.0, places=6)
        self.assertAlmostEqual(interpolate(x, y, 4, 3.0), 6.0, places=6)

    def test_linear_data_interpolates_linearly(self):
        from nspa.utils.math_utils import interpolate

        x = [0.0, 1.0, 2.0, 3.0]
        y = [0.0, 2.0, 4.0, 6.0]
        self.assertAlmostEqual(interpolate(x, y, 4, 0.5), 1.0, places=6)
        self.assertAlmostEqual(interpolate(x, y, 4, 2.5), 5.0, places=6)


class SigmaClipOcTests(unittest.TestCase):
    def setUp(self):
        _require_numpy()

    def test_clips_outliers_by_sigma_mode(self):
        from nspa.utils.math_utils import sigma_clip_oc

        # 5 个近 0 的样本 + 1 个明显外点
        res_ra = [0.01, -0.02, 0.0, 0.03, -0.01, 5.0]
        res_de = [0.02, 0.0, -0.01, 0.01, 0.02, -4.5]
        lines = [f"line{i}" for i in range(6)]

        kept_lines, new_ra, new_de, mean_ra, mean_de, std_ra, std_de, iloop = (
            sigma_clip_oc(res_ra, res_de, lines, oc_limit=2.0, mean_limit=0.0, eps=10.0)
        )

        self.assertEqual(len(kept_lines), 5)
        self.assertNotIn("line5", kept_lines)
        self.assertLess(abs(mean_ra), 0.05)
        self.assertLess(abs(mean_de), 0.05)
        self.assertGreaterEqual(iloop, 1)

    def test_mean_limit_mode_when_oc_limit_zero(self):
        from nspa.utils.math_utils import sigma_clip_oc

        # 5 个集中样本 + 1 个明显外点；用 mean_limit 模式（oc_limit=0）
        # 初始均值约 0.42（被外点拉偏），mean_limit=0.6 仍允许内点过关，外点被剔除
        res_ra = [0.1, 0.1, 0.1, 0.1, 0.1, 2.0]
        res_de = [0.1, 0.1, 0.1, 0.1, 0.1, 2.0]
        lines = ["a", "b", "c", "d", "e", "outlier"]

        kept_lines, _, _, _, _, _, _, _ = (
            sigma_clip_oc(res_ra, res_de, lines, oc_limit=0.0, mean_limit=0.6, eps=10.0)
        )

        self.assertEqual(kept_lines, ["a", "b", "c", "d", "e"])
        self.assertNotIn("outlier", kept_lines)

    def test_eps_excludes_extreme_residuals_in_sigma_mode(self):
        from nspa.utils.math_utils import sigma_clip_oc

        # 即便外点能通过 sigma 检查，|data| < eps 会兜底排除
        res_ra = [0.0, 0.0, 0.0, 50.0]
        res_de = [0.0, 0.0, 0.0, 50.0]
        lines = ["a", "b", "c", "d"]

        kept_lines, _, _, _, _, _, _, _ = (
            sigma_clip_oc(res_ra, res_de, lines, oc_limit=3.0, mean_limit=0.0, eps=10.0)
        )

        self.assertNotIn("d", kept_lines)


class CalculateBackgroundTests(unittest.TestCase):
    def setUp(self):
        _require_numpy()

    def test_flat_image_returns_constant_background(self):
        import numpy as np

        from nspa.utils.image_utils import calculate_background

        data = np.full((50, 50), 100.0)
        bkgd, sigma = calculate_background(data)
        self.assertAlmostEqual(bkgd, 100.0, places=3)
        self.assertLess(sigma, 1e-3)

    def test_noisy_image_recovers_mean_approximately(self):
        import numpy as np

        from nspa.utils.image_utils import calculate_background

        rng = np.random.default_rng(seed=42)
        data = rng.normal(loc=200.0, scale=5.0, size=(200, 200))
        bkgd, sigma = calculate_background(data)
        self.assertAlmostEqual(bkgd, 200.0, delta=0.5)
        self.assertAlmostEqual(sigma, 5.0, delta=0.5)


class FortranConnectivityTests(unittest.TestCase):
    def setUp(self):
        _require_numpy()

    def test_python_fortran_connectivity_handles_rectangular_images(self):
        import numpy as np

        from nspa.utils.image_utils import _label_connectivity_fortran_python

        abox = np.zeros((4, 6), dtype=np.float32)
        abox[1, 4] = 10.0
        abox[2, 4] = 8.0

        labels = _label_connectivity_fortran_python(abox, 4, 6)

        self.assertEqual(labels.shape, abox.shape)
        self.assertGreater(labels[1, 4], 0)
        self.assertEqual(labels[1, 4], labels[2, 4])


if __name__ == "__main__":
    unittest.main()
