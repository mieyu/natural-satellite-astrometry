"""只读检查日期选择，不读取图像内容、不运行流水线。"""

import tkinter as tk
import unittest
from pathlib import Path
from unittest.mock import patch

from ui import inputs_panel


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


if __name__ == "__main__":
    unittest.main()
