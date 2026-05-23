"""03match 阶段编排：组合 GAIA/历表读取、检测星读取、底片常数算法、目标写出。

本模块负责：
  - 逐日重读 GAIA
  - 逐图读头 + 检测星
  - 同图像跨目标的 base_angle / prepar 状态切换
  - 把目标观测结果按列宽规范写出
  - 把过程错误收敛到 StepResult.warnings / failed_items / output_files

匹配算法本身在 domain 层。
"""

import os
from pathlib import Path

from adias.application.log import get_logger
from adias.application.pipeline import StepResult
from adias.domain.astrometry import extract_field_stars, print_par
from adias.domain.matching import find_obj_base_angle, find_obj_base_prepar
from adias.domain.models import (
    Ephemeris,
    GaiaCatalog,
    MatchResult,
    ObjectObservation,
    PlateConstants,
)
from adias.errors import DataFormatError, ProcessingError
from adias.io.catalog_io import read_catalog, read_ephemeris
from adias.io.fits_io import read_fits_header
from adias.io.text_io import (
    read_reg_file,
    sort_output_file,
    write_object_result,
    write_ref_file,
)
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

_log = get_logger("match")


def _load_gaia(path, min_mag, max_mag) -> GaiaCatalog:
    n, ra, de, pr, pd, mag = read_catalog(path, min_mag, max_mag)
    if n == 0:
        return GaiaCatalog.empty()
    return GaiaCatalog(count=n, ra=ra, de=de, pm_ra=pr, pm_de=pd, mag=mag)


def _load_ephemeris(path) -> Ephemeris:
    n, t, ra, de = read_ephemeris(path)
    if n == 0:
        return Ephemeris.empty()
    return Ephemeris(count=n, t=t, ra=ra, de=de)


def _open_object_outputs(out_directory, obj_total):
    return {
        obj: open(out_directory / f"object_{obj}.out", "w", encoding="utf-8")
        for obj in range(1, obj_total + 1)
    }


def _close_object_outputs(files):
    for f in files.values():
        f.close()


def _sort_object_outputs(out_directory, obj_total):
    for obj in range(1, obj_total + 1):
        sort_output_file(str(out_directory / f"object_{obj}.out"))


def run_match(config, fitspath_list):
    """对每个观测目录的每张原始 .fit 执行匹配归算。

    关键行为：
      - GAIA 星表每日重读
      - flag_pre 每幅图重置：每张图的第 1 个目标走 base_angle，后续目标走 prepar
      - base_angle 返回 nostar=1 时，本图剩余目标全部跳过
      - prepar 写 ref.reg 时沿用本图最近一次 base_angle 的参考星数据
      - 写 object_X.out 时 sig0 始终用 base_angle 的值（prepar 不覆盖）
    """
    match = config.match
    step_result = StepResult("match")
    for idx, fitspath in enumerate(fitspath_list, 1):
        fitspath = Path(fitspath)
        _log.info(f"\n{'#' * 10} 本观测时段，第{idx:02d}日：fits文件夹：{fitspath}")

        try:
            gaia = _load_gaia(match.gaia_catfile, match.min_mag, match.max_mag)
        except DataFormatError as exc:
            _log.info(f"    GAIA 星表解析失败：{exc}")
            step_result.warnings.append(f"match: {exc}")
            step_result.failed_items.append(str(fitspath))
            continue
        if gaia.is_empty():
            _log.info("    GAIA 星表本日无可用条目，跳过")
            step_result.warnings.append(f"match: GAIA 无可用条目 {fitspath}")
            step_result.failed_items.append(str(fitspath))
            continue
        _log.info(f"======读取本日配置文件及星表结束，共 {gaia.count} 颗。")

        fits_files = list_fits(fitspath)
        if not fits_files:
            _log.info(f"    本日图像不足，跳过：{fitspath}")
            step_result.warnings.append(f"match: 无 .fit {fitspath}")
            continue
        n_total = len(fits_files)
        _log.info(f"======本日观测图像数量共计：{n_total} 幅")

        stages = stage_dirs(fitspath)
        ensure_dir(stages[REF_DIR])
        out_directory = ensure_dir(stages[OUT_DIR])

        object_out_files = _open_object_outputs(out_directory, match.obj_total)

        for n_fits, fitsfile in enumerate(fits_files, 1):
            _log.info(f"\n======当前图像：{n_fits:3d}/{n_total} - {fitsfile.name}")

            try:
                hdr = read_fits_header(str(fitsfile), match.tele_label)
            except ProcessingError as exc:
                _log.info(f"    {exc}")
                step_result.warnings.append(f"match: {exc}")
                step_result.failed_items.append(str(fitsfile))
                continue

            obj_T = (
                hdr["day"]
                + (hdr["hh"] * 3600 + hdr["mm"] * 60 + hdr["ss"] + match.delta_t)
                / 86400.0
            )
            calpm_epoch = hdr["year"] + ((hdr["month"] - 1) * 30 + hdr["day"]) / 365.0

            # 一次性读检测星表，供本图全部目标共用
            regfile = reg_path(fitspath, fitsfile.name)
            det_x, det_y, det_flux, det_snr = read_reg_file(str(regfile))

            # 每幅图重置：底片常数沿用状态 + 上次 base_angle 的完整结果
            plate = PlateConstants.empty()
            last_base_result: MatchResult | None = None

            skip_image = False
            for obj in range(1, match.obj_total + 1):
                _log.info(f"\n*****当前处理目标为：{obj}/{match.obj_total}")

                try:
                    eph = _load_ephemeris(match.eph_files[obj - 1])
                except DataFormatError as exc:
                    _log.info(f"    历表解析失败：{exc}")
                    step_result.warnings.append(f"match: {exc}")
                    step_result.failed_items.append(str(match.eph_files[obj - 1]))
                    continue
                _log.info(f"    读取该目标IMCCE历表位置数：{eph.count}")
                obj_ephra = interpolate(eph.t, eph.ra, eph.count, obj_T)
                obj_ephde = interpolate(eph.t, eph.de, eph.count, obj_T)

                n_field, gf_ra, gf_de, gf_mag = extract_field_stars(
                    gaia.ra, gaia.de, gaia.pm_ra, gaia.pm_de, gaia.mag,
                    gaia.count, obj_ephra, obj_ephde, match.field_size, calpm_epoch,
                )
                _log.info(f"    用于匹配的恒星数量：{n_field}")

                if not plate.valid:
                    _log.info("    ----自动寻星检测确定底片常数")
                    result = find_obj_base_angle(
                        det_x, det_y, det_flux, det_snr,
                        fitsfile.name,
                        match.plate_angle, match.pixel_scale, match.focal_length,
                        match.match_limit, obj_ephra, obj_ephde,
                        gf_ra, gf_de, gf_mag, n_field, match.model_type,
                    )

                    if result.nostar == 1:
                        skip_image = True
                        break

                    if result.nopre < 1:
                        _log.info(
                            f"    目标星x/y/obsra/obsde位置："
                            f"{result.obj_x:10.3f}{result.obj_y:10.3f}"
                            f"{result.obj_obsra:10.3f}{result.obj_obsde:10.3f}"
                        )
                        _log.info(f"    成功匹配星数：{result.n_match1}")
                        print_par(result.par1, match.model_type)
                        _log.info(f"    底片模型归算sigma：{result.sig0:7.3f}")

                    # 精度达标则保存底片常数给后续目标使用
                    if 0.0001 < result.sig0 < 0.06 and result.n_match1 > 10:
                        plate = PlateConstants.from_match(result)

                    last_base_result = result
                else:
                    _log.info("    ----使用pre_par归算(sig<0.06 & n_match>10)")
                    result = find_obj_base_prepar(
                        det_x, det_y, det_flux, det_snr,
                        plate, match.pixel_scale, match.focal_length, match.model_type,
                        match.match_limit, obj_ephra, obj_ephde,
                    )

                    if result.nopre < 1:
                        _log.info(
                            f"    目标星x/y/obsra/obsde位置："
                            f"{result.obj_x:10.3f}{result.obj_y:10.3f}"
                            f"{result.obj_obsra:10.3f}{result.obj_obsde:10.3f}"
                        )
                        _log.info("    其余参数同前")

                # 写 ref.reg：prepar 模式沿用本图最近一次 base_angle 的参考星
                ref_data = last_base_result if plate.valid else result
                if ref_data is not None and ref_data.n_match1 > 0:
                    write_ref_file(
                        str(ref_path(fitspath, fitsfile.name, obj)), ref_data
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
                        fits_file=str(fitsfile),
                    )
                    write_object_result(
                        object_out_files[obj],
                        observation,
                        hdr["hh"], hdr["mm"], hdr["ss"], hdr["exptime"],
                        match.plate_angle,
                    )
                    _log.info(f"    写入out文件的结果，文件名：object_{obj}")

                _log.info("=====当前图像处理完毕，处理下一个目标=====")

            if skip_image:
                _log.info("======本图检测星不足，跳过，处理下一幅图像======")
                step_result.warnings.append(f"match: 检测星不足 {fitsfile}")
                step_result.failed_items.append(str(fitsfile))
                continue
            _log.info("======本幅图像处理完毕，处理下一幅图像======")

        _close_object_outputs(object_out_files)
        _sort_object_outputs(out_directory, match.obj_total)

        step_result.output_files.extend(
            str(p) for p in sorted(out_directory.glob("object_*.out"))
        )
        step_result.output_files.extend(
            str(p) for p in sorted(stages[REF_DIR].glob("*.ref.reg"))
        )

        _log.info(f"\n   本日匹配共归算天然卫星目标个数 {match.obj_total}")
        _log.info("=================================================================")

    _log.info(f"\n   本时段观测任务匹配结束，共匹配天数：{len(fitspath_list)}")
    _log.info("=================================================================")
    return step_result
