"""03match 阶段编排：组合 GAIA/历表读取、检测星读取、底片常数算法、目标写出。

算法层在 adias.domain.matching（find_obj_base_angle / find_obj_base_prepar）。
本模块负责：
  - 逐日重读 GAIA
  - 逐图读头 + 检测星
  - 同图像跨目标的 base_angle / prepar 状态切换
  - 把目标观测结果通过 ObjectObservation 适配器写出
  - 把过程错误收敛到 StepResult.warnings / failed_items / output_files
"""

import glob
import os

from adias.adapters.catalog_adapter import read_gaia_catalog, read_target_ephemeris
from adias.adapters.object_out_adapter import (
    close_object_output_files,
    open_object_output_files,
    sort_object_outputs,
    write_object_observation,
)
from adias.adapters.region_adapter import read_detection_region, write_reference_region
from adias.application.pipeline import StepResult
from adias.domain.astrometry import extract_field_stars, print_par
from adias.domain.matching import find_obj_base_angle, find_obj_base_prepar
from adias.domain.models import ObjectObservation, PlateConstants
from adias.errors import DataFormatError, ProcessingError
from adias.io.fits_io import read_fits_header
from adias.paths import (
    OUT_DIR,
    REF_DIR,
    ensure_dir,
    list_fits,
    ref_path,
    reg_path,
    stage_dirs,
)
from adias.utils.math_utils import interpolate


def run_match(config, fitspath_list):
    """对每个观测目录的每张原始 .fit 执行匹配归算。

    关键行为（与 Fortran 一致）：
      - GAIA 星表每日重读
      - flag_pre 每幅图重置：每张图的第 1 个目标走 base_angle，后续目标走 prepar
      - base_angle 返回 nostar=1 时，本图剩余目标全部跳过
      - prepar 写 ref.reg 时沿用本图最近一次 base_angle 的参考星数据
      - 写 object_X.out 时 sig0 始终用 base_angle 的值（prepar 不覆盖）
    """
    step_result = StepResult("match")
    for idx, fitspath in enumerate(fitspath_list, 1):
        print(f"\n{'#' * 10} 本观测时段，第{idx:02d}日：fits文件夹：{fitspath}")

        # 逐日重读 GAIA 星表
        try:
            gaia = read_gaia_catalog(
                config["gaiacatpath"], config["min_mag"], config["max_mag"]
            )
        except DataFormatError as exc:
            print(f"    GAIA 星表解析失败：{exc}")
            step_result.warnings.append(f"match: {exc}")
            step_result.failed_items.append(fitspath)
            continue
        if gaia.is_empty():
            print("    GAIA 星表本日无可用条目，跳过")
            step_result.warnings.append(f"match: GAIA 无可用条目 {fitspath}")
            step_result.failed_items.append(fitspath)
            continue
        print(f"======读取本日配置文件及星表结束，共 {gaia.count} 颗。")

        fits_files = list_fits(fitspath)
        if not fits_files:
            print(f"    本日图像不足，跳过：{fitspath}")
            step_result.warnings.append(f"match: 无 .fit {fitspath}")
            continue
        n_total = len(fits_files)
        print(f"======本日观测图像数量共计：{n_total} 幅")

        # 产物目录就位
        stages = stage_dirs(fitspath)
        ensure_dir(stages[REF_DIR])
        out_directory = ensure_dir(stages[OUT_DIR])

        # 批量打开 object_N.out
        object_out_files = open_object_output_files(
            out_directory, config["obj_total"]
        )

        # 逐幅图像
        for n_fits, fitsfile in enumerate(fits_files, 1):
            print(f"\n======当前图像：{n_fits:3d}/{n_total} - {os.path.basename(fitsfile)}")

            try:
                hdr = read_fits_header(fitsfile, config["tele_label"])
            except ProcessingError as exc:
                print(f"    {exc}")
                step_result.warnings.append(f"match: {exc}")
                step_result.failed_items.append(fitsfile)
                continue

            obj_T = (
                hdr["day"]
                + (hdr["hh"] * 3600 + hdr["mm"] * 60 + hdr["ss"] + config["delta_t"])
                / 86400.0
            )
            calpm_epoch = hdr["year"] + ((hdr["month"] - 1) * 30 + hdr["day"]) / 365.0

            # 一次性读检测星表，供本图全部目标共用
            regfile = reg_path(fitspath, os.path.basename(fitsfile))
            det_x, det_y, det_flux, det_snr = read_detection_region(regfile)

            # 每幅图重置：底片常数沿用状态 + 上次 base_angle 的完整结果
            plate = PlateConstants.empty()
            last_base_result = None

            skip_image = False
            for obj in range(1, config["obj_total"] + 1):
                print(f"\n*****当前处理目标为：{obj}/{config['obj_total']}")

                try:
                    eph = read_target_ephemeris(config["ephpath"][obj - 1])
                except DataFormatError as exc:
                    print(f"    历表解析失败：{exc}")
                    step_result.warnings.append(f"match: {exc}")
                    step_result.failed_items.append(config["ephpath"][obj - 1])
                    continue
                print(f"    读取该目标IMCCE历表位置数：{eph.count}")
                obj_ephra = interpolate(eph.t, eph.ra, eph.count, obj_T)
                obj_ephde = interpolate(eph.t, eph.de, eph.count, obj_T)

                n_field, gf_ra, gf_de, gf_mag = extract_field_stars(
                    gaia.ra, gaia.de, gaia.pm_ra, gaia.pm_de, gaia.mag,
                    gaia.count, obj_ephra, obj_ephde, config["fsize"], calpm_epoch,
                )
                print(f"    用于匹配的恒星数量：{n_field}")

                if not plate.valid:
                    print("    ----自动寻星检测确定底片常数")
                    result = find_obj_base_angle(
                        det_x, det_y, det_flux, det_snr,
                        os.path.basename(fitsfile),
                        config["field_angle"], config["pscale"], config["fl"],
                        config["limit_match"], obj_ephra, obj_ephde,
                        gf_ra, gf_de, gf_mag, n_field, config["modeltype"],
                    )

                    if result.nostar == 1:
                        skip_image = True
                        break

                    if result.nopre < 1:
                        print(
                            f"    目标星x/y/obsra/obsde位置："
                            f"{result.obj_x:10.3f}{result.obj_y:10.3f}"
                            f"{result.obj_obsra:10.3f}{result.obj_obsde:10.3f}"
                        )
                        print(f"    成功匹配星数：{result.n_match1}")
                        print_par(result.par1, config["modeltype"])
                        print(f"    底片模型归算sigma：{result.sig0:7.3f}")

                    # 精度达标则保存底片常数给后续目标使用
                    if 0.0001 < result.sig0 < 0.06 and result.n_match1 > 10:
                        plate = PlateConstants.from_match(result)

                    last_base_result = result
                else:
                    print("    ----使用pre_par归算(sig<0.06 & n_match>10)")
                    result = find_obj_base_prepar(
                        det_x, det_y, det_flux, det_snr,
                        plate, config["pscale"], config["fl"], config["modeltype"],
                        config["limit_match"], obj_ephra, obj_ephde,
                    )

                    if result.nopre < 1:
                        print(
                            f"    目标星x/y/obsra/obsde位置："
                            f"{result.obj_x:10.3f}{result.obj_y:10.3f}"
                            f"{result.obj_obsra:10.3f}{result.obj_obsde:10.3f}"
                        )
                        print("    其余参数同前")

                # 写 ref.reg：prepar 模式沿用本图最近一次 base_angle 的参考星
                ref_data = last_base_result if plate.valid else result
                if ref_data is not None and ref_data.n_match1 > 0:
                    write_reference_region(
                        ref_path(fitspath, os.path.basename(fitsfile), obj), ref_data
                    )

                # 写 object_N.out：sig0 始终用 base_angle 的值
                if plate.valid:
                    sig_for_write = (
                        last_base_result.sig0 if last_base_result is not None else 0.0
                    )
                else:
                    sig_for_write = result.sig0
                if 0.0001 < abs(sig_for_write) < 1.0:
                    observation = ObjectObservation(
                        year=hdr["year"],
                        month=hdr["month"],
                        day_fraction=obj_T,
                        obs_ra=result.obj_obsra,
                        obs_de=result.obj_obsde,
                        eph_ra=obj_ephra,
                        eph_de=obj_ephde,
                        sigma=sig_for_write,
                        fits_file=fitsfile,
                    )
                    write_object_observation(
                        object_out_files[obj],
                        observation,
                        hdr["hh"], hdr["mm"], hdr["ss"], hdr["exptime"],
                        config["field_angle"],
                    )
                    print(f"    写入out文件的结果，文件名：object_{obj}")

                print("=====当前图像处理完毕，处理下一个目标=====")

            if skip_image:
                print("======本图检测星不足，跳过，处理下一幅图像======")
                step_result.warnings.append(f"match: 检测星不足 {fitsfile}")
                step_result.failed_items.append(fitsfile)
                continue
            print("======本幅图像处理完毕，处理下一幅图像======")

        # 关闭 + 按观测时刻排序
        close_object_output_files(object_out_files)
        sort_object_outputs(out_directory, config["obj_total"])

        step_result.output_files.extend(
            sorted(glob.glob(os.path.join(out_directory, "object_*.out")))
        )
        step_result.output_files.extend(
            sorted(glob.glob(os.path.join(stages[REF_DIR], "*.ref.reg")))
        )

        print(f"\n   本日匹配共归算天然卫星目标个数 {config['obj_total']}")
        print("=================================================================")

    print(f"\n   本时段观测任务匹配结束，共匹配天数：{len(fitspath_list)}")
    print("=================================================================")
    return step_result
