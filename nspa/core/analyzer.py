"""04comoc：对 03match 的 object_N.out 逐日逐目标做野值剔除与统计汇总。

读 fits_out/object_N.out，写 fits_out/final_*；跨日 .dat / *_all_*.out 汇总在
cfg 的 4specified-output 目录下。
"""

from pathlib import Path

from nspa.application.log import get_logger
from nspa.application.pipeline import StepResult
from nspa.domain.models import OCStats
from nspa.io.text_io import (
    read_object_out,
    write_comoc_lines,
    write_oc_stat,
)
from nspa.paths import clean_proc_files, ensure_dir, list_fits, out_dir
from nspa.utils.math_utils import initial_stats, sigma_clip_oc

_log = get_logger("comoc")


def run_comoc(config, fitspath_list):
    """对每个观测目录的每个目标逐日执行 O-C 野值剔除与统计汇总。"""
    comoc = config.comoc
    obj_total = config.match.obj_total
    result = StepResult("comoc")
    outdir = Path(comoc.output_dir)
    outdir.mkdir(parents=True, exist_ok=True)

    oc_limit = comoc.std_limit
    mean_limit = comoc.mean_limit
    eps = comoc.eps
    del_flag = comoc.del_flag

    for obj in range(1, obj_total + 1):
        obj_label = str(obj)
        oc_summary_path = outdir / f"00oc_{obj_label}.out"
        # 月度汇总 .dat：以首个观测目录 basename 命名
        first_obs = Path(fitspath_list[0])
        month_out_path = outdir / f"{first_obs.name}{obj_label}.dat"

        with (
            open(oc_summary_path, "a", encoding="utf-8") as f_oc_summary,
            open(month_out_path, "a", encoding="utf-8") as f_month,
        ):
            for n_day, fitspath in enumerate(fitspath_list, 1):
                fitspath = Path(fitspath)
                _log.info("")
                _log.info(f"{n_day:3d}-本日fits文件：{fitspath}")

                if del_flag == 1:
                    clean_proc_files(fitspath)

                # 日期串：取首个原始 .fit basename 的前 8 位
                fit_files = list_fits(fitspath)
                date_str = fit_files[0].name[:8] if fit_files else "output"

                fits_out = ensure_dir(out_dir(fitspath))
                objout_path = fits_out / f"object_{obj_label}.out"
                final_obj = fits_out / f"final_object_{obj_label}.out"
                final_oc = fits_out / f"final_oc_{obj_label}.out"
                day_out = outdir / f"{date_str}{obj_label}.out"
                obsdata_out = outdir / f"{date_str}_obsdata_{obj_label}.out"
                all_out = outdir / f"{date_str}_all_{obj_label}.out"

                if not objout_path.exists():
                    _log.info(f"警告：文件不存在 {objout_path}")
                    result.warnings.append(f"comoc: 缺失 {objout_path}")
                    result.failed_items.append(str(objout_path))
                    continue

                raw_lines, res_ra, res_de = read_object_out(str(objout_path))
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

                _log.info("================04Comoc-Program execution summary==================")
                _log.info("=================res数据统计结果=================")
                _log.info(f"  原始数据数量n_obj：{stats.raw_count:4d}")
                _log.info(f"  原始数据均值ra,de：{stats.raw_mean_ra:12.4f}{stats.raw_mean_de:12.4f}")
                _log.info(f"  原始数据方差ra,de：{stats.raw_std_ra:12.4f}{stats.raw_std_de:12.4f}")
                if oc_limit > 0.0:
                    _log.info(f"*********剔除野值标准(oc_limit)：{oc_limit:5.2f}  *********")
                else:
                    _log.info(f"*********剔除野值标准(mean_limit)：{mean_limit:5.2f}  *********")
                _log.info(f"  剔除野值后数据数量n_new：{stats.kept_count:4d}")
                _log.info(f"  剔除野值后数据均值ra,de：{stats.mean_ra:12.4f}{stats.mean_de:12.4f}")
                _log.info(f"  剔除野值后数据方差ra,de：{stats.std_ra:12.4f}{stats.std_de:12.4f}")
                _log.info(f"  剔除野值迭代次数：{stats.iterations:2d}")
                _log.info(f"  残差文件输出:{oc_summary_path}")

                write_oc_stat(str(final_oc), stats, oc_limit, mean_limit)

                # 仅当剔除后精度足够（std < 0.3″）才输出当日数据
                if stats.std_ra < 0.3 and stats.std_de < 0.3 and stats.kept_count > 1:
                    with (
                        open(day_out, "w", encoding="utf-8") as f_out,
                        open(final_obj, "w", encoding="utf-8") as f_final,
                        open(obsdata_out, "w", encoding="utf-8") as f_obsdata,
                    ):
                        write_comoc_lines(f_out, f_final, f_obsdata, f_month, kept_lines)

                    f_oc_summary.write(
                        f"{date_str} & {stats.raw_count:4d} & "
                        f"{stats.raw_mean_ra:9.3f} & {stats.raw_mean_de:9.3f} & "
                        f"{stats.raw_std_ra:9.3f} & {stats.raw_std_de:9.3f} & "
                        f"{stats.kept_count:4d} & "
                        f"{stats.mean_ra:9.3f} & {stats.mean_de:9.3f} & "
                        f"{stats.std_ra:9.3f} & {stats.std_de:9.3f}\n"
                    )
                else:
                    _log.info("删除该日期数据：============")
                    _log.info(
                        f"{date_str}{stats.raw_count:4d}"
                        f"{stats.raw_mean_ra:9.4f}{stats.raw_mean_de:9.4f}"
                        f"{stats.raw_std_ra:9.4f}{stats.raw_std_de:9.4f}"
                        f"{stats.kept_count:4d}"
                        f"{stats.mean_ra:9.4f}{stats.mean_de:9.4f}"
                        f"{stats.std_ra:9.4f}{stats.std_de:9.4f}"
                    )
                    _log.info("================")
                    result.warnings.append(
                        f"comoc: 精度不达标剔除 {date_str} obj={obj_label}"
                    )

                result.output_files.append(str(final_oc))
                result.output_files.append(str(all_out))
                if final_obj.exists():
                    result.output_files.append(str(final_obj))
                if day_out.exists():
                    result.output_files.append(str(day_out))
                if obsdata_out.exists():
                    result.output_files.append(str(obsdata_out))

        result.output_files.append(str(month_out_path))
        result.output_files.append(str(oc_summary_path))

        _log.info(f"   本日匹配共归算天然卫星目标个数{obj:3d}")
        _log.info("=================================================================")

    _log.info(f"数据统计归算结束，共处理数据天数：{len(fitspath_list):3d}")
    _log.info("=================================================================")
    _log.info("=====================NSPA END======================")
    return result
