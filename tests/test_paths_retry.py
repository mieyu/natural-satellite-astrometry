"""Exercise cleanup failures with mocks; no files are deleted by these tests."""

import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from nspa import paths


def windows_error(code):
    error = OSError("simulated Windows file error")
    error.winerror = code
    return error


class CleanupRetryTests(unittest.TestCase):
    def test_success_does_not_sleep(self):
        target = Mock()
        with patch.object(paths.time, "sleep") as sleep:
            paths._unlink_with_retry(target)
        target.unlink.assert_called_once_with()
        sleep.assert_not_called()

    def test_transient_windows_errors_recover(self):
        for code in (5, 32, 33):
            with self.subTest(winerror=code):
                target = Mock()
                target.unlink.side_effect = [windows_error(code), None]
                with patch.object(paths.time, "sleep") as sleep:
                    paths._unlink_with_retry(target)
                self.assertEqual(target.unlink.call_count, 2)
                sleep.assert_called_once_with(0.2)

    def test_persistent_error_is_raised_after_fifteen_retries(self):
        target = Mock()
        error = windows_error(5)
        target.unlink.side_effect = error
        with patch.object(paths.time, "sleep") as sleep:
            with self.assertRaises(OSError) as raised:
                paths._unlink_with_retry(target)
        self.assertIs(raised.exception, error)
        self.assertEqual(target.unlink.call_count, 16)
        self.assertEqual(sleep.call_count, 15)

    def test_other_errors_are_not_retried(self):
        for error in (windows_error(87), PermissionError("denied"), FileNotFoundError()):
            with self.subTest(error=repr(error)):
                target = Mock()
                target.unlink.side_effect = error
                with patch.object(paths.time, "sleep") as sleep:
                    with self.assertRaises(OSError) as raised:
                        paths._unlink_with_retry(target)
                self.assertIs(raised.exception, error)
                target.unlink.assert_called_once_with()
                sleep.assert_not_called()

    def test_pre_cleanup_keeps_originals_and_uses_retry(self):
        directory = Mock()
        original = Path("source.fit")
        processed = Path("source_n.fit")
        directory.iterdir.return_value = [original, processed, Path("notes.txt")]
        with patch.object(paths, "stage_dirs", return_value={paths.PRE_DIR: directory}), \
                patch.object(paths, "_unlink_with_retry") as unlink:
            paths.clean_pre_dir("unused/fits")
        unlink.assert_called_once_with(processed)

    def test_process_cleanup_keeps_output_directory(self):
        directories = {name: Mock() for name in paths.STAGE_DIRS}
        files = []
        for name in (paths.PRE_DIR, paths.DETECT_DIR, paths.REF_DIR):
            entry = Mock()
            entry.is_file.return_value = True
            subdirectory = Mock()
            subdirectory.is_file.return_value = False
            directories[name].iterdir.return_value = [entry, subdirectory]
            files.append(entry)
        with patch.object(paths, "stage_dirs", return_value=directories), \
                patch.object(paths, "_unlink_with_retry") as unlink:
            paths.clean_proc_files("unused/fits")
        self.assertEqual([call.args[0] for call in unlink.call_args_list], files)
        directories[paths.OUT_DIR].iterdir.assert_not_called()


if __name__ == "__main__":
    unittest.main()
