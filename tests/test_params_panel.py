"""仅检查参数界面和配置转换，不启动处理流水线。"""

import tkinter as tk
import unittest
from pathlib import Path

from ui.cfg_writer import build_cfg_text
from ui.params_panel import build_widget, load_cfg_form_values


class ParamsPanelTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.panel = build_widget(self.root)

    def tearDown(self):
        self.root.destroy()

    def test_template_round_trip_and_choice_serialization(self):
        template = Path(__file__).resolve().parents[1] / "inputs/configs/nspa202011.cfg"
        values = load_cfg_form_values(template)
        self.panel.load_values(values)
        actual = self.panel.get_scalars()
        for key, value in values.items():
            if key in actual:  # 报告前缀等字段不在参数面板中。
                self.assertEqual(actual[key], value, key)
        self.assertEqual(self.panel.validate(), [])
        self.panel.entries["1superflag"].set("中值滤波")
        self.panel.entries["4del_flag"].set("保留中间文件")
        text = build_cfg_text(self.panel.get_scalars(), [], [], "")
        self.assertIn("1superflag=1\n", text)
        self.assertIn("4del_flag=0\n", text)
        self.assertNotIn("中值滤波", text)

    def test_modes_disable_without_losing_values(self):
        self.panel.set_value("1med_length", "55")
        self.panel.set_value("1superflag", "3")
        self.assertEqual(str(self.panel.widgets["1med_length"]["state"]), "disabled")
        self.assertEqual(str(self.panel.widgets["1bssr_gauss_size"]["state"]), "normal")
        self.panel.set_value("1superflag", "1")
        self.assertEqual(str(self.panel.widgets["1med_length"]["state"]), "normal")
        self.assertEqual(self.panel.get_scalars()["1med_length"], "55")
        self.panel.set_value("4std_limit", "2.6")
        self.assertEqual(str(self.panel.widgets["4mean_limit"]["state"]), "disabled")
        self.panel.set_value("4std_limit", "0")
        self.assertEqual(str(self.panel.widgets["4mean_limit"]["state"]), "normal")
        self.assertEqual(str(self.panel.widgets["4eps"]["state"]), "disabled")
        self.assertEqual(str(self.panel.widgets["1biasflag"]["state"]), "readonly")

    def test_custom_numbers_and_unknown_template_option(self):
        self.panel.set_value("2detect_workers", "7")
        self.panel.set_value("2pos_method", "4")
        self.assertEqual(self.panel.get_scalars()["2detect_workers"], "7")
        self.assertEqual(self.panel.get_scalars()["2pos_method"], "4")
        self.panel.set_value("1superflag", "99")
        self.assertEqual(self.panel.get_scalars()["1superflag"], "99")
        self.assertTrue(any("1superflag" in error for error in self.panel.validate()))
        self.panel.set_value("3tele_label", "KM100B")
        self.assertEqual(self.panel.get_scalars()["3tele_label"], "km100B")


if __name__ == "__main__":
    unittest.main()
