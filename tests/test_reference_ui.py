from pathlib import Path
import tempfile
import time
import tkinter as tk
import unittest
from unittest.mock import patch

from nspa.reference_data.models import PreparedReferences
from ui.app import App
from ui.reference_panel import INPUTS, DOWNLOAD
from reference_fixtures import dataset, imcce_fetch, gaia_fetch


class ReferenceUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Aqua Tk supports one application interpreter per process reliably.
        cls.shared_root = tk.Tk()
        cls.shared_root.withdraw()

    @classmethod
    def tearDownClass(cls):
        cls.shared_root.destroy()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.inputs, self.raw, self.eph, self.gaia = dataset(self.base)
        self.outputs = self.base / 'outputs'
        self.root = self.shared_root
        self.addCleanup(self.close_root)
        self.app = App(self.root)
        # Use a real project template but keep local fixture config bytes intact.
        self.app._set_roots(input_root=self.inputs, output_root=self.outputs)
        self.app.params.set_value('3tele_label','km100')
        self.app.params.set_value('3ccd_fieldsize','15')
        self.app.params.set_value('3modeltype','6')
        p = self.app.inputs
        p.var_target.set('U');p._on_target();p.var_epoch.set('2020');p._on_epoch()
        self.config = self.inputs / 'configs/local.cfg'
        self.config_bytes = self.config.read_bytes()
        self.errors = []
        self.root.report_callback_exception = lambda *args: self.errors.append(str(args))
        self.root.tk.createcommand('bgerror', lambda *args: self.errors.append('Tcl background error: ' + str(args)))

    def close_root(self):
        self.app.reference_worker.cancel.set()
        if self.app.reference_worker.running:
            self.app.reference_worker.thread.join(timeout=1)
        self.app.destroy()
        for identifier in self.root.tk.call('after', 'info'):
            self.root.after_cancel(identifier)
        import gc
        gc.collect()

    def finish_preparation(self):
        deadline=time.monotonic()+8
        while self.app._preparing and time.monotonic()<deadline:
            self.root.update()
            time.sleep(.01)
        self.assertFalse(self.app._preparing, 'preparation did not finish')
        self.assertEqual(self.errors,[])

    def test_local_multiselect_survives_both_source_switches(self):
        p=self.app.inputs
        p.set_eph_names(['EPH_U2_202011.DAT'])
        local_gaia=p.var_gaia.get()
        p.references.eph_source.set(DOWNLOAD);p.references.gaia_source.set(DOWNLOAD);p.references.changed()
        p.set_download_targets(['U1','U2'])
        self.assertEqual(p.get_selection()['obj_total'],2)
        self.assertEqual(p.selection_errors('match'),[])
        p.references.eph_source.set(INPUTS);p.references.gaia_source.set(INPUTS);p.references.changed()
        self.assertEqual([Path(p).name for p in p.get_selection()['eph_files']],['EPH_U2_202011.DAT'])
        self.assertEqual(p.var_gaia.get(),local_gaia)
        self.assertEqual(p.get_selection()['obj_total'],1)

    def test_background_download_completion_does_not_start_pipeline(self):
        p=self.app.inputs
        p.references.eph_source.set(DOWNLOAD);p.references.gaia_source.set(DOWNLOAD);p.references.changed()
        with patch('nspa.reference_data.providers.imcce.fetch',side_effect=imcce_fetch), \
             patch('nspa.reference_data.providers.gaia.fetch',side_effect=gaia_fetch), \
             patch.object(self.app.runner,'start') as pipeline, patch('ui.app.messagebox.showerror') as error:
            self.app._prepare_references()
            self.assertTrue(self.app._preparing)
            self.assertEqual(str(p.cb_target['state']),'disabled')
            self.finish_preparation()
            pipeline.assert_not_called();error.assert_not_called()
        self.assertEqual(self.app._resolved_selection['obj_total'],2)
        self.assertIn('就绪',p.references.status.get())
        self.assertEqual(str(p.cb_target['state']),'readonly')
        self.assertEqual(self.config.read_bytes(),self.config_bytes)
        self.assertFalse((self.inputs/'configs/_ui_run.cfg').exists())

    def test_run_prepares_then_passes_all_targets_and_uses_new_output_config(self):
        p=self.app.inputs
        p.references.eph_source.set(DOWNLOAD);p.references.gaia_source.set(DOWNLOAD);p.references.changed()
        self.app.params.load_from_cfg(Path(__file__).resolve().parents[1]/'inputs/configs/nspa202011.cfg')
        self.app.params.set_value('3tele_label','km100')
        with patch('nspa.reference_data.providers.imcce.fetch',side_effect=imcce_fetch), \
             patch('nspa.reference_data.providers.gaia.fetch',side_effect=gaia_fetch), \
             patch.object(self.app.runner,'start') as pipeline, patch('ui.app.messagebox.showerror') as error:
            self.app._run()
            self.finish_preparation()
            pipeline.assert_called_once();error.assert_not_called()
        path=Path(pipeline.call_args.args[0])
        self.assertTrue(path.is_relative_to(self.outputs.resolve()/'runs'))
        from nspa.config import load_config
        cfg=load_config(str(path),steps=['match'])
        self.assertEqual(cfg.match.obj_total,2)
        self.assertEqual(len(cfg.match.eph_files),2)
        self.assertIn('reference_manifest=',path.read_text())
        self.assertEqual(self.config.read_bytes(),self.config_bytes)
        self.assertFalse((self.inputs/'configs/_ui_run.cfg').exists())

    def test_failure_or_cancellation_never_starts_pipeline_or_changes_configs(self):
        from nspa.reference_data import PreparationCancelled
        p=self.app.inputs
        p.references.eph_source.set(DOWNLOAD);p.references.gaia_source.set(DOWNLOAD);p.references.changed()
        for failure in (ValueError('service unavailable'),PreparationCancelled('cancelled')):
            with self.subTest(failure=failure), patch('ui.reference_worker.prepare_references',side_effect=failure), \
                 patch.object(self.app.runner,'start') as pipeline, patch('ui.app.messagebox.showerror'):
                self.app._prepare_references(run_after=True)
                self.finish_preparation()
                pipeline.assert_not_called()
        self.assertEqual(self.config.read_bytes(),self.config_bytes)
        self.assertEqual(list(self.outputs.rglob('config.cfg')),[])

    def test_changing_observation_settings_invalidates_prepared_paths(self):
        p=self.app.inputs;p.references.gaia_source.set(DOWNLOAD);p.references.changed()
        self.app._resolved_selection={'obj_total':1}
        self.app.params.set_value('3delta_T','3')
        self.assertIsNone(self.app._resolved_selection)
        self.assertIn('待准备',p.references.status.get())

    def test_cancel_after_worker_finishes_still_prevents_pipeline_start(self):
        p=self.app.inputs
        p.references.eph_source.set(DOWNLOAD);p.references.gaia_source.set(DOWNLOAD);p.references.changed()
        prepared=PreparedReferences(self.eph,self.gaia,None)
        with patch('ui.reference_worker.prepare_references',return_value=prepared), \
             patch.object(self.app.runner,'start') as pipeline:
            self.app._prepare_references(run_after=True)
            self.app.reference_worker.thread.join(timeout=1)
            self.app._cancel_prepare()
            self.finish_preparation()
            pipeline.assert_not_called()
        self.assertIn('取消',p.references.status.get())

    def test_missing_station_is_rejected_before_starting_worker(self):
        p=self.app.inputs
        p.references.eph_source.set(DOWNLOAD);p.references.gaia_source.set(DOWNLOAD);p.references.changed()
        p.references.observatory.set('')
        with patch.object(self.app.reference_worker,'start') as worker, patch('ui.app.messagebox.showerror') as error:
            self.app._prepare_references()
            worker.assert_not_called();error.assert_called_once()
        self.assertFalse(self.app._preparing)

    def test_preprocessing_step_does_not_trigger_reference_downloads(self):
        p=self.app.inputs
        p.references.eph_source.set(DOWNLOAD);p.references.gaia_source.set(DOWNLOAD);p.references.changed()
        self.app.params.load_from_cfg(Path(__file__).resolve().parents[1]/'inputs/configs/nspa202011.cfg')
        self.app.var_step.set('pre')
        with patch('ui.reference_worker.prepare_references') as prepare, \
             patch.object(self.app.runner,'start') as pipeline, patch('ui.app.messagebox.showerror') as error:
            self.app._run()
            prepare.assert_not_called();pipeline.assert_called_once();error.assert_not_called()
        self.assertFalse(self.app._preparing)

    def test_close_during_preparation_cancels_and_waits_for_worker(self):
        from nspa.reference_data import PreparationCancelled
        p=self.app.inputs
        p.references.eph_source.set(DOWNLOAD);p.references.gaia_source.set(DOWNLOAD);p.references.changed()
        def wait_for_cancel(request, progress, cancel):
            cancel.wait(1)
            raise PreparationCancelled('cancelled')
        with patch('ui.reference_worker.prepare_references',side_effect=wait_for_cancel), \
             patch.object(self.root,'destroy') as close, patch.object(self.app.runner,'start') as pipeline:
            self.app._prepare_references()
            self.app._on_close()
            self.finish_preparation()
            close.assert_called_once();pipeline.assert_not_called()
        self.app._close_pending=False


if __name__=='__main__':unittest.main()
