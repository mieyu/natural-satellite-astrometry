"""04comoc：对 03match 的 object_N.out 逐日逐目标做野值剔除与统计汇总。
读 fits_out/object_N.out，写 fits_out/final_*；跨日 .dat / *_all_*.out 汇总在 cfg
的 4specified-output 目录下。
"""

import glob
import os

from adias.adapters.object_out_adapter import (
    read_object_residuals,
    write_comoc_lines,
    write_oc_stats,
)
from adias.application.pipeline import StepResult
from adias.domain.models import OCStats
from adias.paths import clean_proc_files, ensure_dir, list_fits, out_dir
from adias.utils.math_utils import initial_stats, sigma_clip_oc


def run_comoc(config, fitspath_list):
    """对每个观测目录的每个目标逐日执行 O-C 野值剔除与统计汇总。"""
    result = StepResult("comoc")
    outdir = config["newoutfile0"]
    obj_total = config["obj_total"]
    oc_limit = config["oc_limit"]
    mean_limit = config["mean_limit"]
    eps = config["eps"]
    del_flag = config["del_flag"]

    os.makedirs(outdir, exist_ok=True)

    for obj in range(1, obj_total + 1):
        obj_label = str(obj)
        oc_summary_path = os.path.join(outdir, f"00oc_{obj_label}.out")
        # 月度汇总 .dat：以首个观测目录 basename 命名
        month_out_path = os.path.join(
            outdir, os.path.basename(fitspath_list[0]) + obj_label + ".dat"
        )

        with (
            open(oc_summary_path, "a", encoding="utf-8") as f_oc_summary,
            open(month_out_path, "a", encoding="utf-8") as f_month,
        ):
            for n_day, fitspath in enumerate(fitspath_list, 1):
                print()
                print(f"{n_day:3d}-本日fits文件：{fitspath}")

                if del_flag == 1:
                    clean_proc_files(fitspath)

                # 日期串：取首个原始 .fit basename 的前 8 位
                fit_files = list_fits(fitspath)
                date_str = (
                    os.path.basename(fit_files[0])[:8] if fit_files else "output"
                )

                fits_out = ensure_dir(out_dir(fitspath))
                objout_path = os.path.join(fits_out, f"object_{obj_label}.out")
                final_obj = os.path.join(fits_out, f"final_object_{obj_label}.out")
                final_oc = os.path.join(fits_out, f"final_oc_{obj_label}.out")
                day_out = os.path.join(outdir, date_str + obj_label + ".out")
                obsdata_out = os.path.join(
                    outdir, date_str + f"_obsdata_{obj_label}.out"
                )
                all_out = os.path.join(outdir, date_str + f"_all_{obj_label}.out")

                if not os.path.exists(objout_path):
                    print(f"警告：文件不存在 {objout_path}")
                    result.warnings.append(f"comoc: 缺失 {objout_path}")
                    result.failed_items.append(objout_path)
                    continue

                raw_lines, res_ra, res_de = read_object_residuals(objout_path)
                n_raw = len(raw_lines)

                # all_out 保留原始 147 列
                with open(all_out, "w", encoding="utf-8") as f_all:
                    for line in raw_lines:
                        f_all.write((line[:147] if len(line) >= 147 else line) + "\n")

                raw_mean_ra, raw_mean_de, raw_std_ra, raw_std_de = initial_stats(
                    res_ra, res_de
                )

                kept_lines, _new_ra, _new_de, mean_ra, mean_de, std_ra, std_de, iloop = (
                    sigma_clip_oc(res_ra, res_de, raw_lines, oc_limit, mean_limit, eps)
                )
                n_new = len(kept_lines)

                # 剔除后样本数 < 2 时，均值/标准差置无效值 999.999
                if n_new < 2:
                    mean_ra = mean_de = std_ra = std_de = 999.999

                # 原始为空或剔除后为空时，统计全置 0（覆盖 999.999）
                if n_raw < 1:
                    raw_mean_ra = raw_mean_de = raw_std_ra = raw_std_de = 0.0
                    n_new = 0
                    mean_ra = mean_de = std_ra = std_de = 0.0
                elif n_new < 1:
                    n_new = 0
                    mean_ra = mean_de = std_ra = std_de = 0.0

                stats = OCStats(
                    raw_count=n_raw,
                    raw_mean_ra=raw_mean_ra,
                    raw_mean_de=raw_mean_de,
                    raw_std_ra=raw_std_ra,
                    raw_std_de=raw_std_de,
                    kept_count=n_new,
                    mean_ra=mean_ra,
                    mean_de=mean_de,
                    std_ra=std_ra,
                    std_de=std_de,
                    iterations=iloop,
                )

                print("================04Comoc-Program execution summary==================")
                print("=================res数据统计结果=================")
                print(f"  原始数据数量n_obj：{stats.raw_count:4d}")
                print(
                    f"  原始数据均值ra,de：{stats.raw_mean_ra:12.4f}{stats.raw_mean_de:12.4f}"
                )
                print(
                    f"  原始数据方差ra,de：{stats.raw_std_ra:12.4f}{stats.raw_std_de:12.4f}"
                )
                if oc_limit > 0.0:
                    print(f"*********剔除野值标准(oc_limit)：{oc_limit:5.2f}  *********")
                else:
                    print(f"*********剔除野值标准(mean_limit)：{mean_limit:5.2f}  *********")
                print(f"  剔除野值后数据数量n_new：{stats.kept_count:4d}")
                print(
                    f"  剔除野值后数据均值ra,de：{stats.mean_ra:12.4f}{stats.mean_de:12.4f}"
                )
                print(
                    f"  剔除野值后数据方差ra,de：{stats.std_ra:12.4f}{stats.std_de:12.4f}"
                )
                print(f"  剔除野值迭代次数：{stats.iterations:2d}")
                print(f"  残差文件输出:{oc_summary_path}")

                write_oc_stats(final_oc, stats, oc_limit, mean_limit)

                # 仅当剔除后精度足够（std < 0.3″）才输出当日数据
                if stats.std_ra < 0.3 and stats.std_de < 0.3 and stats.kept_count > 1:
                    with (
                        open(day_out, "w", encoding="utf-8") as f_out,
                        open(final_obj, "w", encoding="utf-8") as f_final,
                        open(obsdata_out, "w", encoding="utf-8") as f_obsdata,
                    ):
                        write_comoc_lines(
                            f_out, f_final, f_obsdata, f_month, kept_lines
                        )

                    f_oc_summary.write(
                        f"{date_str} & {stats.raw_count:4d} & "
                        f"{stats.raw_mean_ra:9.3f} & {stats.raw_mean_de:9.3f} & "
                        f"{stats.raw_std_ra:9.3f} & {stats.raw_std_de:9.3f} & "
                        f"{stats.kept_count:4d} & "
                        f"{stats.mean_ra:9.3f} & {stats.mean_de:9.3f} & "
                        f"{stats.std_ra:9.3f} & {stats.std_de:9.3f}\n"
                    )
                else:
                    print("删除该日期数据：============")
                    print(
                        f"{date_str}{stats.raw_count:4d}"
                        f"{stats.raw_mean_ra:9.4f}{stats.raw_mean_de:9.4f}"
                        f"{stats.raw_std_ra:9.4f}{stats.raw_std_de:9.4f}"
                        f"{stats.kept_count:4d}"
                        f"{stats.mean_ra:9.4f}{stats.mean_de:9.4f}"
                        f"{stats.std_ra:9.4f}{stats.std_de:9.4f}"
                    )
                    print("================")
                    result.warnings.append(
                        f"comoc: 精度不达标剔除 {date_str} obj={obj_label}"
                    )

                result.output_files.append(final_oc)
                result.output_files.append(all_out)
                if os.path.exists(final_obj):
                    result.output_files.append(final_obj)
                if os.path.exists(day_out):
                    result.output_files.append(day_out)
                if os.path.exists(obsdata_out):
                    result.output_files.append(obsdata_out)

        result.output_files.append(month_out_path)
        result.output_files.append(oc_summary_path)

        print(f"   本日匹配共归算天然卫星目标个数{obj:3d}")
        print("=================================================================")

    print(f"数据统计归算结束，共处理数据天数：{len(fitspath_list):3d}")
    print("=================================================================")
    print("=====================ADIAS END======================")
    return result
