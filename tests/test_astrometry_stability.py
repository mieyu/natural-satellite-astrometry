"""Check plate predictions against known sky coordinates and degenerate fields."""

import unittest
import warnings

import numpy as np

from nspa.domain.astrometry import (
    DEG2RAD, _build_design_matrix, least_squares, rade2ky, sol_par, xy2rade,
)


class AstrometryStabilityTests(unittest.TestCase):
    def test_known_polynomials_at_pixel_and_radian_scales(self):
        rng = np.random.default_rng(431)
        for size in (2000.0, 0.002):
            x, y = rng.uniform(-size, size, (2, 80))
            for nm in (6, 12, 20, 30):
                with self.subTest(size=size, nm=nm), warnings.catch_warnings():
                    warnings.simplefilter('error')
                    A = _build_design_matrix(x, y, len(x), nm)
                    expected = rng.normal(size=nm) * 0.001 / np.linalg.norm(A, axis=0)
                    sky = A @ expected
                    actual, sigma, used = least_squares(A, sky[:, None], nm, len(x))
                    np.testing.assert_allclose(A @ actual, sky, atol=1e-15, rtol=1e-10)
                    np.testing.assert_allclose(actual, expected, rtol=1e-8, atol=1e-20)
                    self.assertEqual(used, len(x))
                    self.assertLess(sigma, 1e-15)

    def test_affine_sky_round_trip(self):
        rng = np.random.default_rng(17)
        x, y = rng.uniform(-0.002, 0.002, (2, 50))
        expected = np.array([-0.99, 0.03, 1e-5, 0.02, 1.01, -2e-5])
        ra, de = xy2rade(expected, 6, x, y, 125 * DEG2RAD, 20 * DEG2RAD)
        actual, sigma, used = sol_par(x, y, ra / DEG2RAD, de / DEG2RAD,
                                      len(x), 125, 20, 6)
        np.testing.assert_allclose(actual, expected, atol=1e-12, rtol=1e-10)
        self.assertEqual(used, len(x))
        self.assertLess(sigma, 1e-14)

    def test_fourth_order_x_and_y_terms_are_distinct_on_sky(self):
        # Independent evaluation: x^4 and y^4 must occupy different columns.
        par = np.zeros(30)
        par[10], par[14], par[25], par[29] = 0.2, 0.7, -0.3, 0.1
        x, y = 0.1, 0.2
        ra, de = xy2rade(par, 30, x, y, 1.0, 0.2)
        xi, eta = rade2ky(ra, de, 1.0, 0.2)
        self.assertAlmostEqual(xi, 0.2*x**4 + 0.7*y**4, places=14)
        self.assertAlmostEqual(eta, -0.3*x**4 + 0.1*y**4, places=14)

    def test_rejects_collinear_and_nearly_collinear_fields(self):
        rng = np.random.default_rng(31)
        x = np.linspace(-0.002, 0.002, 40)
        for perturbation in (0.0, 1e-15):
            y = 2*x + rng.normal(size=40)*perturbation
            A = _build_design_matrix(x, y, len(x), 6)
            with self.assertRaises(np.linalg.LinAlgError):
                least_squares(A, np.ones(80), 6, 40)

    def test_rejects_insufficient_stars_and_nonfinite_data(self):
        A = _build_design_matrix(np.arange(3), np.array([0, 1, 0]), 3, 6)
        with self.assertRaises(np.linalg.LinAlgError):
            least_squares(A, np.ones(6), 6, 3)
        with self.assertRaises(np.linalg.LinAlgError):
            least_squares(np.full((20, 6), np.nan), np.ones(20), 6, 10)

    def test_zero_residual_does_not_remove_every_star(self):
        rng = np.random.default_rng(19)
        x, y = rng.normal(size=(2, 30))
        A = _build_design_matrix(x, y, len(x), 6)
        actual, sigma, used = least_squares(A, np.zeros(60), 6, 30)
        self.assertEqual(used, 30)
        self.assertEqual(sigma, 0)
        np.testing.assert_array_equal(actual, np.zeros(6))

    def test_outlier_removes_both_coordinates_of_one_star(self):
        rng = np.random.default_rng(73)
        x, y = rng.uniform(-1, 1, (2, 100))
        A = _build_design_matrix(x, y, len(x), 6)
        expected = np.array([0.01, 0.02, 0.001, -0.02, 0.01, -0.001])
        sky = A @ expected
        sky[0] += 0.1
        actual, sigma, used = least_squares(A, sky, 6, 100)
        self.assertEqual(used, 99)
        np.testing.assert_allclose(actual, expected, atol=1e-14)
        self.assertLess(sigma, 1e-14)


if __name__ == '__main__':
    unittest.main()
