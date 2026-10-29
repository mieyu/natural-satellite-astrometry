"""只读检查日期选择，不读取图像内容、不运行流水线。"""

import tkinter as tk
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ui import inputs_panel
from ui.cfg_writer import write_cfg
from nspa.config import load_config


class DaySelectionTests(unittest.TestCase):
    def test_nested_choices_keep_relative_paths_and_exclude_outputs(self):
        base = Path("example")
        tree = {base: ["202011"], base / "202011": ["20201113", "20201114"],
                base / "202011/20201113": ["fits", "fits_n"],
                base / "202011/20201114": ["fits", "fits_out"]}
        with patch.object(inputs_panel, "_subdir_names", side_effect=lambda p: tree.get(p, [])), \
             patch.object(inputs_panel, "list_fits", return_value=[]):
            self.assertEqual(inputs_panel.data_subdir_choices(base),
                             ["202011", "202011/20201113", "202011/20201114"])

    def test_existing_uranus_all_single_day_and_switch_back(self):
        repo = Path(__file__).resolve().parents[1]
        base = repo / "inputs/images/U/2020"
        days, _ = inputs_panel.resolve_fitspath(base)
        if len(days) < 2:
            self.skipTest("本机未提供多日天王星试用图像")
        root = tk.Tk()
        root.withdraw()
        try:
            panel = inputs_panel.build_widget(root, repo, lambda: None)
            panel.var_target.set("U")
            panel._on_target()
            panel.var_epoch.set("2020")
            panel._on_epoch()
            options = tuple(panel.cb_sub["values"])
            self.assertEqual(panel.var_sub.get(), inputs_panel._ALL_DAYS_CHOICE)
            self.assertEqual(len(panel._preview_days), len(days))
            for day in days[:2]:
                name = day.parent.name
                self.assertIn(name, options)
                panel.var_sub.set(name)
                panel._on_sub()
                self.assertEqual(panel._preview_days, [day])
                selected = panel.get_selection()
                expanded = inputs_panel.expand_fitspath([repo / selected["fitspaths"][0]])
                self.assertEqual(expanded, [day])
                self.assertEqual(tuple(panel.cb_sub["values"]), options)
            panel.var_sub.set(inputs_panel._ALL_DAYS_CHOICE)
            panel._on_sub()
            self.assertEqual(len(panel._preview_days), len(days))
        finally:
            root.destroy()


class EphemerisMultiSelectionTests(unittest.TestCase):
    """用临时空文件验证 UI 到流水线配置的多目标传递，不运行算法。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name) / "repo"
        self.inputs = Path(self.tmp.name) / "external data/inputs"
        self.outputs = Path(self.tmp.name) / "external data/outputs"
        for date in ("20170511", "20170512", "20170601"):
            day = self.inputs / "images/S/2017" / date[:6] / date / "fits"
            day.mkdir(parents=True)
            (day / f"{date}-001.fit").touch()
        self.catalogs = self.inputs / "catalogs/S/2017"
        self.catalogs.mkdir(parents=True)
        names = [f"EPH_S{i}_201705.DAT" for i in (1, 2, 8, 9)]
        names += ["Q_EPH_S1_201705.DAT", "EPH_S9_201706.DAT",
                  "GAIA3_S_201705.DAT", "GAIA3_S_201706.DAT"]
        for name in names:
            (self.catalogs / name).touch()
        self.root = tk.Tk()
        self.root.withdraw()
        self.addCleanup(self.root.destroy)
        self.panel = inputs_panel.build_widget(self.root, self.repo, lambda: None,
                                               self.inputs, self.outputs)
        self.panel.var_target.set("S")
        self.panel._on_target()
        self.panel.var_epoch.set("2017")
        self.panel._on_epoch()
        self.panel.var_sub.set("201705")
        self.panel._on_sub()

    def names(self):
        return [Path(path).name for path in self.panel.get_selection()["eph_files"]]

    def test_dialog_multi_selection_reaches_numbered_config_and_target_count(self):
        self.panel.btn_eph.invoke()
        dialog = self.panel._eph_dialog
        selected = ["EPH_S1_201705.DAT", "EPH_S2_201705.DAT", "EPH_S9_201705.DAT"]
        dialog._set_checked(selected)
        dialog._apply()
        self.assertFalse(dialog.winfo_exists())
        self.assertEqual(self.names(), selected)
        selection = self.panel.get_selection()
        self.assertEqual(selection["obj_total"], 3)
        self.assertEqual(self.panel.selection_errors("match"), [])
        self.assertIn("已选 3 份", self.panel.var_eph_summary.get())
        cfg = write_cfg(Path(self.tmp.name) / "multiple.cfg", {
            "3obj_total": str(selection["obj_total"]), "3modeltype": "6",
        }, selection["fitspaths"], selection["eph_files"], selection["gaia_catfile"])
        config = load_config(str(cfg), steps=["match"])
        self.assertEqual(config.match.obj_total, 3)
        self.assertEqual(config.match.eph_files, selection["eph_files"])
        self.assertIn("3obj_ephfile3=", cfg.read_text())

    def test_cancel_preserves_choice_and_auto_restores_all_targets_once(self):
        selected = ["EPH_S1_201705.DAT", "EPH_S8_201705.DAT"]
        self.panel.set_eph_names(selected)
        self.panel.btn_eph.invoke()
        dialog = self.panel._eph_dialog
        dialog._select_month()
        self.assertEqual(sum(var.get() for var in dialog.variables.values()), 4)
        dialog.destroy()  # 取消时不提交对话框中的修改。
        self.assertEqual(self.names(), selected)
        self.panel.btn_auto_eph.invoke()
        self.assertEqual(set(self.names()), {"Q_EPH_S1_201705.DAT", "EPH_S2_201705.DAT",
                                           "EPH_S8_201705.DAT", "EPH_S9_201705.DAT"})
        self.assertEqual(self.panel.get_selection()["obj_total"], 4)

    def test_same_month_day_and_output_switch_keep_manual_subset(self):
        selected = ["EPH_S1_201705.DAT", "EPH_S8_201705.DAT"]
        self.panel.set_eph_names(selected)
        for subdir in ("201705/20170511", "201705/20170512", "201705"):
            self.panel.var_sub.set(subdir)
            self.panel._on_sub()
            self.assertEqual(self.names(), selected)
        self.panel.set_roots(self.inputs, self.outputs / "new output")
        self.assertEqual(self.names(), selected)
        self.panel.var_sub.set("201706")
        self.panel._on_sub()
        self.assertEqual(self.names(), ["EPH_S9_201706.DAT"])

    def test_invalid_multi_selection_keeps_previous_valid_choice(self):
        selected = ["EPH_S1_201705.DAT", "EPH_S8_201705.DAT"]
        self.panel.set_eph_names(selected)
        for invalid, message in (([], "没有选中目标历表"),
                (["EPH_S9_201706.DAT"], "与观测月"),
                (["EPH_S1_201705.DAT", "Q_EPH_S1_201705.DAT"], "多份历表"),
                (["EPH_S99_201705.DAT"], "不在当前数据目录")):
            with self.subTest(invalid=invalid), self.assertRaisesRegex(ValueError, message):
                self.panel.set_eph_names(invalid)
            self.assertEqual(self.names(), selected)
            self.assertEqual(self.panel.get_selection()["obj_total"], 2)


if __name__ == "__main__":
    unittest.main()
