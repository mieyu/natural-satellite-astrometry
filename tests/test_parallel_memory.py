"""Process budgeting must prevent CPU count from exhausting image memory."""

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from nspa.utils.parallel import image_worker_limit


class ParallelMemoryTests(unittest.TestCase):
    def plan(self, requested, available_gib, shapes):
        headers = [dict(NAXIS=2, NAXIS1=w, NAXIS2=h) for w, h in shapes]
        with patch('nspa.utils.parallel.os.cpu_count', return_value=24), \
             patch('nspa.utils.parallel.psutil.virtual_memory',
                   return_value=SimpleNamespace(available=int(available_gib * 1024**3))), \
             patch('nspa.utils.parallel.fits.getheader', side_effect=headers):
            return image_worker_limit(requested, 74, range(len(headers)))

    def test_auto_does_not_start_24_workers_on_74_images(self):
        self.assertEqual(self.plan(0, 7, [(1056, 1024)]), 2)

    def test_low_memory_uses_one_worker(self):
        self.assertEqual(self.plan(0, 1, [(1056, 1024)]), 1)

    def test_largest_image_controls_budget(self):
        self.assertEqual(self.plan(0, 7, [(1056, 1024), (4112, 4096)]), 1)

    def test_explicit_24_still_obeys_memory_budget(self):
        self.assertLessEqual(self.plan(24, 7, [(4112, 4096)]), 1)

    def test_missing_header_falls_back_to_serial(self):
        with patch('nspa.utils.parallel.fits.getheader', side_effect=OSError):
            self.assertEqual(image_worker_limit(24, 74, ['missing.fits']), 1)

    def test_manual_serial_does_not_probe_files(self):
        with patch('nspa.utils.parallel.fits.getheader') as read:
            self.assertEqual(image_worker_limit(1, 74, ['missing.fits']), 1)
            read.assert_not_called()


if __name__ == '__main__':
    unittest.main()
