import tempfile
import unittest
from pathlib import Path

from ui import inputs_panel, params_panel


class UiConfigFileTests(unittest.TestCase):
    def test_list_config_files_excludes_generated_ui_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg_dir = root / "inputs" / "configs"
            cfg_dir.mkdir(parents=True)
            (cfg_dir / "nspa2024.cfg").write_text("", encoding="utf-8")
            (cfg_dir / "nspa202011.cfg").write_text("", encoding="utf-8")
            (cfg_dir / "_ui_run.cfg").write_text("", encoding="utf-8")

            self.assertEqual(
                params_panel.list_config_files(root),
                ["nspa202011.cfg", "nspa2024.cfg"],
            )

    def test_load_cfg_form_values_skips_path_owned_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = Path(tmp) / "sample.cfg"
            cfg.write_text(
                "\n".join(
                    [
                        "1fitspath=inputs/images/S9/2024/202411",
                        "1superflag=3",
                        "2snr_threshold=1.25",
                        "3tele_label=km100B",
                        "3obj_total=5",
                        "3obj_ephfile1=inputs/catalogs/U/2020/EPH_U1_202011.DAT",
                        "3gaia_catfile1=inputs/catalogs/U/2020/GAIA3_US_202011.DAT",
                        "4specified-output=outputs/results/U/2020",
                    ]
                ),
                encoding="utf-8",
            )

            values = params_panel.load_cfg_form_values(cfg)

            self.assertEqual(values["1superflag"], "3")
            self.assertEqual(values["2snr_threshold"], "1.25")
            self.assertEqual(values["3tele_label"], "km100B")
            self.assertNotIn("3obj_total", values)
            self.assertNotIn("4specified-output", values)


class UiCatalogSelectionTests(unittest.TestCase):
    def test_default_eph_selection_returns_matching_month_names(self):
        eph_files = [
            "inputs/catalogs/S9/2024/EPH_S9_202411.DAT",
            "inputs/catalogs/S9/2024/EPH_S9_202412.DAT",
            "inputs/catalogs/S9/2024/EPH_S8_202412.DAT",
        ]

        selected_names = inputs_panel.default_eph_names(eph_files, "202412")

        self.assertEqual(
            selected_names,
            ["EPH_S8_202412.DAT", "EPH_S9_202412.DAT"],
        )

    def test_resolve_eph_names_maps_visible_names_to_paths(self):
        eph_files = [
            "inputs/catalogs/U/2020/EPH_U1_202011.DAT",
            "inputs/catalogs/U/2020/EPH_U2_202011.DAT",
        ]

        selected = inputs_panel.resolve_eph_names(eph_files, ["EPH_U2_202011.DAT"])

        self.assertEqual(selected, ["inputs/catalogs/U/2020/EPH_U2_202011.DAT"])

    def test_gaia_display_uses_file_names_but_resolves_to_path(self):
        gaia_files = [
            "/repo/inputs/catalogs/S9/2024/GAIA3_S9_202410.DAT",
            "/repo/inputs/catalogs/S9/2024/GAIA3_S9_202412.DAT",
        ]

        self.assertEqual(
            inputs_panel.gaia_file_names(gaia_files),
            ["GAIA3_S9_202410.DAT", "GAIA3_S9_202412.DAT"],
        )
        self.assertEqual(
            inputs_panel.resolve_gaia_name(gaia_files, "GAIA3_S9_202412.DAT"),
            "/repo/inputs/catalogs/S9/2024/GAIA3_S9_202412.DAT",
        )


if __name__ == "__main__":
    unittest.main()
