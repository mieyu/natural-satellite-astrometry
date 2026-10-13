"""Known-angle synthetic fields test acquisition and the complete match path."""

import unittest

import numpy as np

from nspa.domain.astrometry import DEG2RAD, xy2rade
from nspa.domain.matching import find_obj_base_angle, _locate_base_angle_target
from nspa.domain.rotation import acquire_rotation, plate_orientation


def field(angle, parity=1, seed=92):
    rng = np.random.default_rng(seed)
    target = np.array([2060., 1970.])
    references = rng.uniform(500, 3500, (35, 2))
    c, s = np.cos(angle * DEG2RAD), np.sin(angle * DEG2RAD)
    par = np.array([parity*c, s, 0, -parity*s, c, 0])
    normalized = (references - target) * .015 / 13216
    ra, de = xy2rade(par, 6, normalized[:, 0], normalized[:, 1],
                     125 * DEG2RAD, 20 * DEG2RAD)
    # Target is absent from GAIA; both lists contain unrelated extra objects.
    det = np.vstack([references + rng.normal(0, .06, references.shape), target,
                     rng.uniform(500, 3500, (8, 2))])
    order = rng.permutation(len(det))
    det = det[order]
    ra = np.r_[ra / DEG2RAD, rng.uniform(124.94, 125.06, 12)]
    de = np.r_[de / DEG2RAD, rng.uniform(19.94, 20.06, 12)]
    mag = rng.uniform(10, 16, len(ra))
    return det, ra, de, mag, target


class RotationAcquisitionTests(unittest.TestCase):
    def acquire(self, angle, parity=1):
        det, ra, de, mag, _ = field(angle, parity)
        return acquire_rotation(det[:, 0], det[:, 1], np.ones(len(det)),
                                .015, 13216, 3, 125, 20, ra, de, mag, 6)

    def test_full_circle_and_wrap_with_noise_and_unmatched_stars(self):
        for expected in (0, 37.25, 91.4, 178, 271.6, 359.8):
            with self.subTest(angle=expected):
                best = self.acquire(expected)
                self.assertIsNotNone(best)
                actual, parity = plate_orientation(best['par'], 6)
                self.assertLess(abs((actual - expected + 180) % 360 - 180), .02)
                self.assertEqual(parity, 1)
                self.assertGreaterEqual(best['used'], 25)

    def test_mirrored_camera(self):
        best = self.acquire(123.4, -1)
        self.assertIsNotNone(best)
        actual, parity = plate_orientation(best['par'], 6)
        self.assertEqual(parity, -1)
        self.assertAlmostEqual(actual, 123.4, delta=.02)

    def test_complete_match_and_plate_constants_without_angle(self):
        for initial, model in ((0, 6), (12, 6), (0, 12), (0, 20), (0, 30)):
            with self.subTest(initial=initial, model=model):
                det, ra, de, mag, target = field(137.35)
                result = find_obj_base_angle(
                    det[:, 0], det[:, 1], np.ones(len(det)), np.ones(len(det))*20,
                    'synthetic.fit', initial, .015, 13216, 3, 125, 20,
                    ra, de, mag, len(ra), model)
                self.assertEqual(result.nopre, 0)
                self.assertEqual(result.nostar, 0)
                self.assertGreaterEqual(result.n_match1, 25)
                self.assertLess(result.sig0, .1)
                np.testing.assert_allclose([result.obj_x, result.obj_y], target, atol=.2)
                angle, parity = plate_orientation(result.par1, model)
                self.assertAlmostEqual(angle, 137.35, delta=.03)
                self.assertEqual(parity, 1)

    def test_unrelated_catalog_is_rejected(self):
        det, ra, de, mag, _ = field(37.25)
        rng = np.random.default_rng(189)
        ra = rng.uniform(124.95, 125.05, len(ra))
        de = rng.uniform(19.95, 20.05, len(de))
        self.assertIsNone(acquire_rotation(det[:, 0], det[:, 1], np.ones(len(det)),
                                          .015, 13216, 3, 125, 20, ra, de, mag, 6))

    def test_distorted_plate_target_inverse_uses_full_polynomial(self):
        par = np.array([1., 0, 0, 100, 20, 0, 0, 1, 0, 0, 10, -80])
        x, y = 2600., 2400.
        xn, yn = (x - 2000)*.015/13216, (y - 2000)*.015/13216
        # Independent forward polynomial followed by the inverse sky projection.
        xi = xn + 100*xn*xn + 20*xn*yn
        eta = yn + 10*xn*yn - 80*yn*yn
        ra, de = xy2rade(np.array([1, 0, 0, 0, 1, 0]), 6, xi, eta,
                         125*DEG2RAD, 20*DEG2RAD)
        target = _locate_base_angle_target(
            np.array([x]), np.array([y]), np.ones(1), np.ones(1), par,
            .015, 13216, 12, 2000, 2000, 125*DEG2RAD, 20*DEG2RAD,
            ra/DEG2RAD, de/DEG2RAD)
        self.assertIsNotNone(target)
        self.assertEqual(target['obj_x_obs'], x)
        self.assertEqual(target['obj_y_obs'], y)

    def test_insufficient_and_collinear_stars_are_rejected(self):
        for count in (4, 20):
            x = np.linspace(-.001, .001, count)
            ra, de = xy2rade(np.array([1, 0, 0, 0, 1, 0]), 6, x, x*2,
                             125*DEG2RAD, 20*DEG2RAD)
            self.assertIsNone(acquire_rotation(x*13216/.015+2000, x*2*13216/.015+2000,
                                              np.ones(count), .015, 13216, 3, 125, 20,
                                              ra/DEG2RAD, de/DEG2RAD, np.ones(count), 6))


if __name__ == '__main__':
    unittest.main()
