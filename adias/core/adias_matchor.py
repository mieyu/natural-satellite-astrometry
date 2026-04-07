# 功能：03match 星象匹配与天体归算批处理逻辑。
# 使用：from adias.core.adias_matcher import run_match

import os
import numpy as np

from adias.io.adias_fits_io   import read_fits_header
from adias.io.adias_text_io   import (read_fits_list, read_reg_file,
                                      write_ref_file, write_object_result,
                                      sort_output_file)
from adias.io.adias_catalog_io      import read_catalog, read_ephemeris
from adias.utils.adias_math_utils import (
    Q, cal_rl, interpolate, extract_field_stars,
    rade2ky, rade2xieta, xy2rade, xieta2xy,
    sol_par, print_par)

MAX_SIZE = 900000


# ─────────────────────────────────────────────
# 核心匹配函数（私有）
# ─────────────────────────────────────────────

def _find_obj_base_angle(fitsfile, field_angle, pscale, fl, limit_match,
                         obj_ephra, obj_ephde,
                         gaia_ra, gaia_de, gaia_mag, n_gaia, modeltype):
    """
    基于初始底片旋转角自动搜索目标并解算底片常数。
    对应原版 find_obj_base_angle 方法。
    """
    _empty = dict(nostar=0, nopre=0, obj_x=0.0, obj_y=0.0,
                  obj_flux=0.0, snr=0.0, obj_obsra=0.0, obj_obsde=0.0,
                  n_match1=0, sig0=0.0, par1=np.zeros(30),
                  x_center=0.0, y_center=0.0,
                  ra_center=0.0, de_center=0.0,
                  ref_x=np.zeros(MAX_SIZE), ref_y=np.zeros(MAX_SIZE),
                  ref_ra=np.zeros(MAX_SIZE), ref_de=np.zeros(MAX_SIZE),
                  ref_mag=np.zeros(MAX_SIZE))

    # 初始底片旋转矩阵（6 参数线性模型）
    ca, sa = np.cos(field_angle * Q), np.sin(field_angle * Q)
    par_init = np.zeros(30)
    par_init[0], par_init[1] =  ca, sa
    par_init[3], par_init[4] = -sa, ca

    regfile = fitsfile + '.reg'
    det_x, det_y, det_flux, det_snr = read_reg_file(regfile)
    n_det = len(det_x)
    if n_det < 3:
        print(f'    检测星少于 3 颗，跳过：{os.path.basename(fitsfile)}')
        _empty['nostar'] = 1
        return _empty

    # 粗匹配：以每颗检测星为假定中心逐一尝试
    best = dict(n=0, sig=999.0)
    rx0 = np.zeros(MAX_SIZE); ry0 = np.zeros(MAX_SIZE)
    rra0 = np.zeros(MAX_SIZE); rde0 = np.zeros(MAX_SIZE)
    rmag0 = np.zeros(MAX_SIZE)

    for j in range(n_det):
        ox, oy = det_x[j], det_y[j]
        rx, ry, rra, rde, rmag, rfl = [], [], [], [], [], []
        for k in range(n_det):
            if det_x[k] <= 0 or det_y[k] <= 0:
                continue
            xn = (det_x[k] - ox) * pscale / fl
            yn = (det_y[k] - oy) * pscale / fl
            ra_k, de_k = xy2rade(par_init[:6], 6, xn, yn,
                                  obj_ephra * Q, obj_ephde * Q)
            for n in range(n_gaia):
                rl = cal_rl(ra_k, de_k, gaia_ra[n] * Q, gaia_de[n] * Q)
                if rl / Q * 3600 <= limit_match:
                    rx.append(xn); ry.append(yn)
                    rra.append(gaia_ra[n]); rde.append(gaia_de[n])
                    rmag.append(gaia_mag[n]); rfl.append(det_flux[k])
                    break
        if len(rx) < 3:
            continue
        try:
            par1, sig0, _ = sol_par(np.array(rx), np.array(ry),
                                    np.array(rra), np.array(rde),
                                    len(rx), obj_ephra, obj_ephde, modeltype)
            sig0_arcsec = sig0 / Q * 3600.0
            nm = len(rx)
            if 0.001 < sig0_arcsec < 0.5:
                if nm > best['n'] or (nm == best['n'] and sig0_arcsec < best['sig']):
                    best.update(n=nm, sig=sig0_arcsec, j=j, par=par1.copy(),
                                rx=rx[:], ry=ry[:], rra=rra[:], rde=rde[:],
                                rmag=rmag[:], ox=ox, oy=oy)
        except Exception:
            continue

    if best['n'] < 3:
        print('    粗匹配失败：未找到足够参考星')
        _empty['nopre'] = 1
        return _empty

    # 精化中心
    ox, oy = best['ox'], best['oy']
    rx0[:best['n']] = [v * fl / pscale + ox for v in best['rx']]
    ry0[:best['n']] = [v * fl / pscale + oy for v in best['ry']]
    for i in range(best['n']):
        rra0[i] = best['rra'][i]; rde0[i] = best['rde'][i]
        rmag0[i] = best['rmag'][i]
    n_m = best['n']

    x_cen = np.mean(rx0[:n_m])
    y_cen = np.mean(ry0[:n_m])
    rxn = (rx0[:n_m] - x_cen) * pscale / fl
    ryn = (ry0[:n_m] - y_cen) * pscale / fl

    par1, sig0, _ = sol_par(rxn, ryn, rra0[:n_m], rde0[:n_m],
                             n_m, obj_ephra, obj_ephde, modeltype)
    xn = (x_cen - ox) * pscale / fl
    yn = (y_cen - oy) * pscale / fl
    ra_cen, de_cen = xy2rade(par1[:modeltype], modeltype, xn, yn,
                              obj_ephra * Q, obj_ephde * Q)
    print(f'    参考星中心 x/y/ra/de：{x_cen:11.3f}{y_cen:11.3f}'
          f'{ra_cen/Q:11.3f}{de_cen/Q:11.3f}')

    # 以新中心重解
    rxn = (rx0[:n_m] - x_cen) * pscale / fl
    ryn = (ry0[:n_m] - y_cen) * pscale / fl
    par1, sig0, _ = sol_par(rxn, ryn, rra0[:n_m], rde0[:n_m],
                             n_m, ra_cen / Q, de_cen / Q, modeltype)
    sig1 = sig0 / Q * 3600.0

    # 以新底片常数重新匹配全部检测星
    rx_new, ry_new, rra_new, rde_new, rmag_new = [], [], [], [], []
    for k in range(n_det):
        if det_x[k] <= 0 or det_y[k] <= 0:
            continue
        xn = (det_x[k] - x_cen) * pscale / fl
        yn = (det_y[k] - y_cen) * pscale / fl
        ra_k, de_k = xy2rade(par1[:modeltype], modeltype, xn, yn, ra_cen, de_cen)
        for n in range(n_gaia):
            rl = cal_rl(ra_k, de_k, gaia_ra[n] * Q, gaia_de[n] * Q)
            if rl / Q * 3600 <= limit_match:
                rx_new.append(xn); ry_new.append(yn)
                rra_new.append(gaia_ra[n]); rde_new.append(gaia_de[n])
                rmag_new.append(gaia_mag[n])
                break

    n_m = len(rx_new)
    if n_m < 3:
        _empty['nopre'] = 1
        return _empty

    par1, sig0, _ = sol_par(np.array(rx_new), np.array(ry_new),
                             np.array(rra_new), np.array(rde_new),
                             n_m, ra_cen / Q, de_cen / Q, modeltype)
    sig1 = sig0 / Q * 3600.0

    # 预报目标位置
    xi, eta = rade2xieta(obj_ephra * Q, obj_ephde * Q, ra_cen, de_cen)
    pre_x, pre_y = xieta2xy(xi, eta, par1[:6])
    pre_x = pre_x * fl / pscale + x_cen
    pre_y = pre_y * fl / pscale + y_cen
    print(f'    预报 x/y：{pre_x:11.5f}{pre_y:11.5f}  '
          f'历表 ra/de：{obj_ephra:11.5f}{obj_ephde:11.5f}')

    # 在 reg 中选最近的检测星作为目标
    from adias.io.adias_text_io import read_reg_file as _read_reg
    _, _, _, _ = det_x, det_y, det_flux, det_snr   # 已读取
    dis0, selectflag = 20.0, 0
    obj_x_obs = obj_y_obs = obj_flux_obs = snr_obs = 0.0
    for i in range(n_det):
        dis = np.hypot(det_x[i] - pre_x, det_y[i] - pre_y)
        if dis <= 3.0 and dis < dis0:
            dis0 = dis
            obj_x_obs, obj_y_obs = det_x[i], det_y[i]
            obj_flux_obs, snr_obs = det_flux[i], det_snr[i]
            selectflag = 1

    if not selectflag:
        print('    未找到与预报位置相近的目标星')
        _empty['nopre'] = 1
        return _empty

    xn = (obj_x_obs - x_cen) * pscale / fl
    yn = (obj_y_obs - y_cen) * pscale / fl
    obj_obsra, obj_obsde = xy2rade(par1[:modeltype], modeltype, xn, yn, ra_cen, de_cen)

    result = _empty.copy()
    result.update(obj_x=obj_x_obs, obj_y=obj_y_obs,
                  obj_flux=obj_flux_obs, snr=snr_obs,
                  obj_obsra=obj_obsra / Q, obj_obsde=obj_obsde / Q,
                  n_match1=n_m, sig0=sig1, par1=par1,
                  x_center=x_cen, y_center=y_cen,
                  ra_center=ra_cen, de_center=de_cen)
    for i in range(n_m):
        result['ref_x'][i]  = rx_new[i] * fl / pscale + x_cen
        result['ref_y'][i]  = ry_new[i] * fl / pscale + y_cen
        result['ref_ra'][i] = rra_new[i]
        result['ref_de'][i] = rde_new[i]
        result['ref_mag'][i]= rmag_new[i]
    return result


def _find_obj_base_prepar(fitsfile, par1, pscale, fl, modeltype,
                          x_cen, y_cen, ra_cen, de_cen, limit_match,
                          obj_ephra, obj_ephde,
                          gaia_ra, gaia_de, gaia_mag, n_gaia):
    """
    利用前一幅图像的底片常数直接寻星归算。
    对应原版 find_obj_base_prepar 方法。
    """
    result = dict(nopre=1, obj_x=0.0, obj_y=0.0, obj_flux=0.0, snr=0.0,
                  obj_obsra=0.0, obj_obsde=0.0, sig0=0.0, n_match1=0,
                  par1=par1.copy(), x_center=x_cen, y_center=y_cen,
                  ra_center=ra_cen, de_center=de_cen,
                  ref_x=np.zeros(MAX_SIZE), ref_y=np.zeros(MAX_SIZE),
                  ref_ra=np.zeros(MAX_SIZE), ref_de=np.zeros(MAX_SIZE),
                  ref_mag=np.zeros(MAX_SIZE))

    det_x, det_y, det_flux, det_snr = read_reg_file(fitsfile + '.reg')
    n_det = len(det_x)

    rx, ry, rra, rde, rmag = [], [], [], [], []
    for k in range(n_det):
        if det_x[k] <= 0 or det_y[k] <= 0:
            continue
        xn = (det_x[k] - x_cen) * pscale / fl
        yn = (det_y[k] - y_cen) * pscale / fl
        ra_k, de_k = xy2rade(par1[:modeltype], modeltype, xn, yn, ra_cen, de_cen)
        for n in range(n_gaia):
            rl = cal_rl(ra_k, de_k, gaia_ra[n] * Q, gaia_de[n] * Q)
            if rl / Q * 3600 <= limit_match:
                rx.append(det_x[k]); ry.append(det_y[k])
                rra.append(gaia_ra[n]); rde.append(gaia_de[n])
                rmag.append(gaia_mag[n])
                break

    n_m = len(rx)
    result['n_match1'] = n_m
    for i in range(n_m):
        result['ref_x'][i] = rx[i]; result['ref_y'][i] = ry[i]
        result['ref_ra'][i] = rra[i]; result['ref_de'][i] = rde[i]
        result['ref_mag'][i] = rmag[i]

    if n_m >= 3:
        rxn = (np.array(rx) - x_cen) * pscale / fl
        ryn = (np.array(ry) - y_cen) * pscale / fl
        _, sig0, _ = sol_par(rxn, ryn, np.array(rra), np.array(rde),
                              n_m, ra_cen / Q, de_cen / Q, modeltype)
        result['sig0'] = sig0 / Q * 3600.0

    # 寻找目标星
    rl0 = limit_match
    for k in range(n_det):
        if det_x[k] <= 0 or det_y[k] <= 0:
            continue
        xn = (det_x[k] - x_cen) * pscale / fl
        yn = (det_y[k] - y_cen) * pscale / fl
        ra_k, de_k = xy2rade(par1[:modeltype], modeltype, xn, yn, ra_cen, de_cen)
        rl = cal_rl(ra_k, de_k, obj_ephra * Q, obj_ephde * Q) / Q * 3600
        if rl <= limit_match and rl < rl0:
            rl0 = rl
            result.update(obj_x=det_x[k], obj_y=det_y[k],
                          obj_flux=det_flux[k], snr=det_snr[k],
                          obj_obsra=ra_k / Q, obj_obsde=de_k / Q,
                          nopre=0)

    if result['nopre']:
        print('    pre_par 模式：未找到目标星')
    return result


# ─────────────────────────────────────────────
# 对外接口
# ─────────────────────────────────────────────

def run_match(config, fitspath_list):
    """
    对 fitspath_list 中每个观测目录执行星象匹配与天体位置归算。

    Parameters
    ----------
    config        : dict，parse_config() 返回的参数字典
    fitspath_list : list[str]
    """
    # 读取 GAIA 星表（全程共用）
    n_gaia, gaia_ra, gaia_de, gaia_pr, gaia_pd, gaia_mag = read_catalog(
        config['gaiacatpath'], config['min_mag'], config['max_mag'])
    print(f'读取 GAIA 星表完成，共 {n_gaia} 颗。')

    for idx, fitspath in enumerate(fitspath_list, 1):
        print(f'\n{"#"*10} 第 {idx:02d} 日：{fitspath}')

        fits_files = read_fits_list(fitspath)
        if not fits_files:
            continue
        n_total = len(fits_files)
        print(f'本日图像总数：{n_total}')

        # 为每个目标开启输出文件
        fh = {}
        for obj in range(1, config['obj_total'] + 1):
            fh[obj] = open(os.path.join(fitspath, f'object_{obj}.out'), 'w')

        flag_pre = 0
        pre_par = np.zeros(30)
        pre_x_cen = pre_y_cen = pre_ra_cen = pre_de_cen = 0.0

        for n_fits, fitsfile_path in enumerate(fits_files, 1):
            fitsfile = fitsfile_path.strip()
            print(f'\n  {n_fits:3d}/{n_total} - {os.path.basename(fitsfile)}')

            hdr = read_fits_header(fitsfile, config['tele_label'])
            if hdr is None:
                continue

            obj_T      = hdr['day'] + (hdr['hh']*3600 + hdr['mm']*60 + hdr['ss'] +
                                       config['delta_t']) / 86400.0
            calpm_epoch = hdr['year'] + ((hdr['month']-1)*30 + hdr['day']) / 365.0

            for obj in range(1, config['obj_total'] + 1):
                print(f'\n  * 目标 {obj}/{config["obj_total"]}')

                # 读取历表并插值
                n_eph, eph_T, eph_ra, eph_de = read_ephemeris(config['ephpath'][obj-1])
                print(f'    历表行数：{n_eph}')
                obj_ephra = interpolate(eph_T, eph_ra, n_eph, obj_T)
                obj_ephde = interpolate(eph_T, eph_de, n_eph, obj_T)

                # 截取视场内参考星
                n_field, gf_ra, gf_de, gf_mag = extract_field_stars(
                    gaia_ra, gaia_de, gaia_pr, gaia_pd, gaia_mag, n_gaia,
                    obj_ephra, obj_ephde, config['fsize'], calpm_epoch)
                print(f'    视场内参考星：{n_field} 颗')

                # 匹配与归算
                if flag_pre < 1:
                    print('    模式：自动搜索底片常数')
                    result = _find_obj_base_angle(
                        fitsfile, config['field_angle'],
                        config['pscale'], config['fl'], config['limit_match'],
                        obj_ephra, obj_ephde,
                        gf_ra, gf_de, gf_mag, n_field, config['modeltype'])

                    if result['nostar'] == 1:
                        continue
                    if result['nopre'] < 1:
                        print(f'    目标 x/y/ra/de：{result["obj_x"]:10.3f}'
                              f'{result["obj_y"]:10.3f}'
                              f'{result["obj_obsra"]:10.3f}{result["obj_obsde"]:10.3f}')
                        print(f'    匹配星数：{result["n_match1"]}')
                        print_par(result['par1'], config['modeltype'])
                        print(f'    sig0：{result["sig0"]:7.3f} arcsec')

                    if 0.0001 < result['sig0'] < 0.06 and result['n_match1'] > 10:
                        flag_pre = 1
                        pre_par    = result['par1'].copy()
                        pre_x_cen  = result['x_center']
                        pre_y_cen  = result['y_center']
                        pre_ra_cen = result['ra_center']
                        pre_de_cen = result['de_center']
                else:
                    print('    模式：使用 pre_par')
                    result = _find_obj_base_prepar(
                        fitsfile, pre_par,
                        config['pscale'], config['fl'], config['modeltype'],
                        pre_x_cen, pre_y_cen, pre_ra_cen, pre_de_cen,
                        config['limit_match'], obj_ephra, obj_ephde,
                        gf_ra, gf_de, gf_mag, n_field)
                    if result['nopre'] < 1:
                        print(f'    目标 x/y/ra/de：{result["obj_x"]:10.3f}'
                              f'{result["obj_y"]:10.3f}'
                              f'{result["obj_obsra"]:10.3f}{result["obj_obsde"]:10.3f}')
                        print(f'    匹配星数：{result["n_match1"]}  '
                              f'sig0：{result["sig0"]:7.3f}')

                # 写出参考星文件
                if result.get('n_match1', 0) > 0:
                    write_ref_file(f'{fitsfile}{obj}.ref.reg', result)

                # 写出目标观测结果
                if 0.0001 < abs(result.get('sig0', 0)) < 1.0:
                    write_object_result(
                        fh[obj], hdr['year'], hdr['month'], obj_T,
                        result['obj_obsra'], result['obj_obsde'],
                        obj_ephra, obj_ephde, result['sig0'],
                        hdr['hh'], hdr['mm'], hdr['ss'],
                        hdr['exptime'], fitsfile, config['field_angle'])

        # 关闭文件并排序
        for f in fh.values():
            f.close()
        for obj in range(1, config['obj_total'] + 1):
            sort_output_file(os.path.join(fitspath, f'object_{obj}.out'))

        print(f'\n  本日归算目标数：{config["obj_total"]}')

    print(f'\n{"="*50}\n03match 完成，共处理 {len(fitspath_list)} 天。')