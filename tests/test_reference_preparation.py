import dataclasses
from datetime import datetime
import hashlib
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from nspa.reference_data import ReferenceRequest, prepare_references, ReferenceError, PreparationCancelled
from nspa.reference_data.planning import plan_observations, plan_cone
from nspa.reference_data.models import EphemerisRow
from reference_fixtures import dataset, imcce_fetch, gaia_fetch


class PreparationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.inputs, self.raw, eph, gaia = dataset(self.root)
        self.request = ReferenceRequest((self.raw,), self.root / 'cache', local_eph_files=eph,
            local_gaia_file=gaia, targets=('U1', 'U2'), tele_label='km100', observatory='286')
        self.originals = {p:hashlib.sha256(p.read_bytes()).hexdigest() for p in self.inputs.rglob('*') if p.is_file()}

    def assert_originals_unchanged(self):
        self.assertTrue(all(hashlib.sha256(p.read_bytes()).hexdigest() == sha for p, sha in self.originals.items()))

    def test_local_sources_do_not_contact_services_or_rewrite_inputs(self):
        with patch('nspa.reference_data.providers.imcce.fetch') as eph, patch('nspa.reference_data.providers.gaia.fetch') as gaia:
            result = prepare_references(self.request)
        eph.assert_not_called(); gaia.assert_not_called()
        self.assertEqual(result.eph_files, self.request.local_eph_files)
        self.assertEqual(result.gaia_catfile, self.request.local_gaia_file)
        self.assertFalse(self.request.cache_root.exists())
        self.assert_originals_unchanged()

    def test_two_downloads_multiple_targets_roundtrip_and_cache_reuse(self):
        request = dataclasses.replace(self.request, eph_source='download', gaia_source='download')
        with patch('nspa.reference_data.providers.imcce.fetch', side_effect=imcce_fetch) as eph, \
             patch('nspa.reference_data.providers.gaia.fetch', side_effect=gaia_fetch) as gaia:
            result = prepare_references(request)
            self.assertEqual(result.obj_total, 2)
            self.assertTrue(result.manifest_path.is_file())
            self.assertEqual(eph.call_count, 4)
            self.assertEqual(gaia.call_count, 1)
        with patch('nspa.reference_data.providers.imcce.fetch') as eph, patch('nspa.reference_data.providers.gaia.fetch') as gaia:
            again = prepare_references(request)
        eph.assert_not_called(); gaia.assert_not_called()
        self.assertEqual(again.eph_files, result.eph_files)
        self.assertEqual(again.gaia_catfile, result.gaia_catfile)
        self.assert_originals_unchanged()

    def test_sources_can_be_mixed_in_both_directions(self):
        for source in ('ephemeris', 'gaia'):
            request = dataclasses.replace(self.request, eph_source='download' if source == 'ephemeris' else 'inputs',
                                          gaia_source='download' if source == 'gaia' else 'inputs')
            with self.subTest(source=source), \
                 patch('nspa.reference_data.providers.imcce.fetch', side_effect=imcce_fetch) as eph, \
                 patch('nspa.reference_data.providers.gaia.fetch', side_effect=gaia_fetch) as gaia:
                result = prepare_references(request)
                self.assertEqual(result.obj_total, 2)
                self.assertEqual(eph.call_count > 0, source == 'ephemeris')
                self.assertEqual(gaia.call_count > 0, source == 'gaia')
        self.assert_originals_unchanged()

    def test_cancel_before_start_has_no_side_effects(self):
        cancel = threading.Event(); cancel.set()
        with self.assertRaises(PreparationCancelled):
            prepare_references(dataclasses.replace(self.request, eph_source='download'), cancel=cancel)
        self.assertFalse(self.request.cache_root.exists())
        self.assert_originals_unchanged()

    def test_cancel_during_download_removes_unpublished_temporary_files(self):
        cancel = threading.Event()
        def cancelled_fetch(*args, **kwargs):
            result = imcce_fetch(*args, **kwargs)
            cancel.set()
            return result
        with patch('nspa.reference_data.providers.imcce.fetch', side_effect=cancelled_fetch), self.assertRaises(PreparationCancelled):
            prepare_references(dataclasses.replace(self.request, eph_source='download'), cancel=cancel)
        self.assertFalse(list(self.request.cache_root.rglob('manifest.json')))
        self.assertFalse(list(self.request.cache_root.rglob('.preparing-*')))
        self.assert_originals_unchanged()

    def test_corrupted_cache_is_not_used_or_overwritten(self):
        request = dataclasses.replace(self.request, eph_source='download')
        with patch('nspa.reference_data.providers.imcce.fetch', side_effect=imcce_fetch):
            result = prepare_references(request)
        result.eph_files[0].write_text('corrupt')
        with patch('nspa.reference_data.providers.imcce.fetch') as network, self.assertRaisesRegex(ReferenceError, '缓存校验失败'):
            prepare_references(request)
        network.assert_not_called()
        self.assertEqual(result.eph_files[0].read_text(), 'corrupt')
        self.assert_originals_unchanged()

    def test_header_midpoint_and_time_correction_are_in_download_plan(self):
        plan = plan_observations(dataclasses.replace(self.request, delta_t=3.25))
        self.assertEqual(plan.moments[0], datetime(2020, 11, 13, 12, 0, 18, 250000))
        self.assertLess(plan.start, plan.moments[0])
        self.assertGreater(plan.stop, plan.moments[-1])

    def test_appledouble_metadata_is_not_a_fits_observation(self):
        (self.raw / '._20201113-0.fit').write_bytes(b'AppleDouble metadata, not a FITS image')
        self.assertEqual(plan_observations(self.request).files, 2)

    def test_invalid_headers_and_multiple_months_fail_without_network(self):
        from astropy.io import fits
        file = next(self.raw.glob('*.fit'))
        for value in ('bad', '2020-12-13T12:00:00'):
            with fits.open(file, mode='update') as hdul:
                hdul[0].header['DATE-OBS'] = value
            with self.subTest(value=value), self.assertRaises(ReferenceError):
                plan_observations(self.request)

    def test_cone_handles_ra_wrap_and_rejects_insufficient_override(self):
        rows = [EphemerisRow(datetime(2020, 1, 1), str(359.9 / 15), '10'),
                EphemerisRow(datetime(2020, 1, 1), str(.1 / 15), '10')]
        ra, dec, radius = plan_cone(rows, self.request)
        self.assertTrue(ra < 1 or ra > 359)
        self.assertLess(radius, 1)
        with self.assertRaisesRegex(ReferenceError, '未覆盖'):
            plan_cone(rows, dataclasses.replace(self.request, gaia_cone=(180, 10, .5)))


if __name__ == '__main__': unittest.main()
