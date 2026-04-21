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
    本函数采用“迭代逼近与星图模式识别”算法，用于在未知望远镜精确指向和光路畸变的情况下，
    将提取的未知星点与 GAIA 理论星表进行强行对齐并锁定目标天体。主要分为四个阶段：
    1. 粗略试探（暴力粗匹配）：以每颗检测星为假定中心，套用初始旋转角将其他星投影至天球，
       与 GAIA 星表进行交叉匹配。寻找并记录匹配星数最多、拟合残差最小的最佳“锚点”。
    2. 中心精化（第一次迭代）：根据粗匹配筛选出的参考星，计算这批星的实际几何质心，
       以此质心作为新的坐标系原点，重新解算更精确的初版底片常数。
    3. 全图再匹配（第二次迭代）：利用精化后的底片常数，对全图所有检测星进行再次交叉匹配，
       收罗之前因误差过大而遗漏的参考星，并最终拟合出包含高阶畸变修正的底片常数（par1）。
    4. 预报与抓取（目标提取）：根据最终的底片常数反向推演目标天体在照片上的理论像素坐标，
       在极小容差（3个像素）内抓取真实的对应星象，并归算出该目标极高精度的实测赤经/赤纬。

    Parameters
    ----------
    fitsfile    : str，FITS 图像文件路径（函数内部会自动追加 '.reg' 读取星表）
    field_angle : float，相机的初始视场旋转角（度）
    pscale      : float，像素比例尺 (Pixel Scale)
    fl          : float，望远镜系统等效焦距 (Focal Length)
    limit_match : float，星点交叉匹配的容差阈值（角秒）
    obj_ephra   : float，目标天体在曝光瞬间的历表理论赤经（度）
    obj_ephde   : float，目标天体在曝光瞬间的历表理论赤纬（度）
    gaia_ra     : np.ndarray，视场内 GAIA 参考星的赤经数组
    gaia_de     : np.ndarray，视场内 GAIA 参考星的赤纬数组
    gaia_mag    : np.ndarray，视场内 GAIA 参考星的星等数组
    n_gaia      : int，视场内 GAIA 参考星的总数
    modeltype   : int，底片常数多项式模型的参数个数（如 6 代表 6 参数线性模型）

    Returns
    -------
    result : dict
        包含盲搜匹配结果的字典，核心键值包括：
        - nostar, nopre : int，错误/失败标记（1为失败，0为正常）
        - obj_x, obj_y : float，目标天体在图像上的实测像素坐标
        - obj_flux, snr : float，目标天体的实测流量和信噪比
        - obj_obsra, obj_obsde : float，目标天体最终归算出的实测赤经/赤纬（度）
        - n_match1 : int，最终参与解算的参考星数量
        - sig0 : float，模型拟合残差（角秒）
        - par1 : np.ndarray，解算出的底片常数数组 (容量 30)
        - x_center, y_center, ra_center, de_center : float，参考几何中心坐标
        - ref_* : np.ndarray，匹配成功的参考星坐标及星等数组
    """
    # 1. 初始化空结果字典，防止匹配失败时报错
    _empty = dict(nostar=0, nopre=0, obj_x=0.0, obj_y=0.0,
                  obj_flux=0.0, snr=0.0, obj_obsra=0.0, obj_obsde=0.0,
                  n_match1=0, sig0=0.0, par1=np.zeros(30),
                  x_center=0.0, y_center=0.0,
                  ra_center=0.0, de_center=0.0,
                  ref_x=np.zeros(MAX_SIZE), ref_y=np.zeros(MAX_SIZE),
                  ref_ra=np.zeros(MAX_SIZE), ref_de=np.zeros(MAX_SIZE),
                  ref_mag=np.zeros(MAX_SIZE))

    # 2. 构建初始的 6 参数线性底片模型（仅包含平移和已知的近似旋转角）
    # ca, sa 为旋转矩阵的 cos 和 sin 值 (Q为角度转弧度系数)
    ca, sa = np.cos(field_angle * Q), np.sin(field_angle * Q)
    par_init = np.zeros(30)
    par_init[0], par_init[1] =  ca, sa
    par_init[3], par_init[4] = -sa, ca

    # 3. 读取图像测光检测结果（X, Y, 流量, 信噪比）
    regfile = fitsfile + '.reg'
    det_x, det_y, det_flux, det_snr = read_reg_file(regfile)
    n_det = len(det_x)
    
    # 若提取到的星极少（比如被云遮挡），直接放弃
    if n_det < 3:
        print(f'    检测星少于 3 颗，跳过：{os.path.basename(fitsfile)}')
        _empty['nostar'] = 1
        return _empty

    # ================= 阶段一：暴力粗匹配 =================
    best = dict(n=0, sig=999.0) # 记录最佳拟合状态
    rx0 = np.zeros(MAX_SIZE); ry0 = np.zeros(MAX_SIZE)
    rra0 = np.zeros(MAX_SIZE); rde0 = np.zeros(MAX_SIZE)
    rmag0 = np.zeros(MAX_SIZE)

    # 遍历每一颗检测星 j
    for j in range(n_det):
        ox, oy = det_x[j], det_y[j]
        rx, ry, rra, rde, rmag, rfl = [], [], [], [], [], []
        
        # 将其他星 k 相对于 j 的位置投影到天球上
        for k in range(n_det):
            if det_x[k] <= 0 or det_y[k] <= 0:
                continue
            
            # 将像素坐标转为标准坐标系 (Standard Coordinates: xn, yn)
            xn = (det_x[k] - ox) * pscale / fl
            yn = (det_y[k] - oy) * pscale / fl
            
            # 利用初始旋转矩阵，将标准坐标粗略推算为 RA/Dec
            ra_k, de_k = xy2rade(par_init[:6], 6, xn, yn,
                                  obj_ephra * Q, obj_ephde * Q)
            
            # 在 GAIA 参考星表中寻找距离最近的星 (交叉匹配)
            for n in range(n_gaia):
                rl = cal_rl(ra_k, de_k, gaia_ra[n] * Q, gaia_de[n] * Q) # 计算球面角距离
                if rl / Q * 3600 <= limit_match: # 如果距离小于容差限度（角秒）
                    rx.append(xn); ry.append(yn)
                    rra.append(gaia_ra[n]); rde.append(gaia_de[n])
                    rmag.append(gaia_mag[n]); rfl.append(det_flux[k])
                    break # 找到匹配就跳出内层寻找
                    
        # 匹配星数太少，无法拟合（至少需要3颗星解算6参数）
        if len(rx) < 3:
            continue
            
        # 尝试求解底片常数，评价匹配质量
        try:
            par1, sig0, _ = sol_par(np.array(rx), np.array(ry),
                                    np.array(rra), np.array(rde),
                                    len(rx), obj_ephra, obj_ephde, modeltype)
            sig0_arcsec = sig0 / Q * 3600.0
            nm = len(rx)
            
            # 筛选条件：残差在合理范围内（0.001 ~ 0.5角秒）
            # 如果匹配星数更多，或者星数一样但残差更小，则更新“最佳匹配”
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

    # ================= 阶段二：精化参考中心 =================
    ox, oy = best['ox'], best['oy']
    
    # 将标准坐标还原为像素坐标
    rx0[:best['n']] = [v * fl / pscale + ox for v in best['rx']]
    ry0[:best['n']] = [v * fl / pscale + oy for v in best['ry']]
    for i in range(best['n']):
        rra0[i] = best['rra'][i]; rde0[i] = best['rde'][i]
        rmag0[i] = best['rmag'][i]
    n_m = best['n']

    # 计算这批成功匹配的星的几何质心，作为新的参考中心
    x_cen = np.mean(rx0[:n_m])
    y_cen = np.mean(ry0[:n_m])
    
    # 基于新的几何中心，重新计算标准坐标并重新解算初版底片常数
    rxn = (rx0[:n_m] - x_cen) * pscale / fl
    ryn = (ry0[:n_m] - y_cen) * pscale / fl
    par1, sig0, _ = sol_par(rxn, ryn, rra0[:n_m], rde0[:n_m],
                             n_m, obj_ephra, obj_ephde, modeltype)
                             
    # 计算新几何中心在天球上对应的 RA/Dec
    xn = (x_cen - ox) * pscale / fl
    yn = (y_cen - oy) * pscale / fl
    ra_cen, de_cen = xy2rade(par1[:modeltype], modeltype, xn, yn,
                              obj_ephra * Q, obj_ephde * Q)
    print(f'    参考星中心 x/y/ra/de：{x_cen:11.3f}{y_cen:11.3f}'
          f'{ra_cen/Q:11.3f}{de_cen/Q:11.3f}')

    # 以新的中心重解一次模型，确保坐标系锚定
    rxn = (rx0[:n_m] - x_cen) * pscale / fl
    ryn = (ry0[:n_m] - y_cen) * pscale / fl
    par1, sig0, _ = sol_par(rxn, ryn, rra0[:n_m], rde0[:n_m],
                             n_m, ra_cen / Q, de_cen / Q, modeltype)
    sig1 = sig0 / Q * 3600.0

    # ================= 阶段三：全图再匹配 (收罗遗漏星) =================
    rx_new, ry_new, rra_new, rde_new, rmag_new = [], [], [], [], []
    # 拿着精化后的底片常数，把图片里所有的检测星再去和 GAIA 比对一次
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

    # 用所有匹配成功的星，计算出最终的底片常数 par1
    par1, sig0, _ = sol_par(np.array(rx_new), np.array(ry_new),
                             np.array(rra_new), np.array(rde_new),
                             n_m, ra_cen / Q, de_cen / Q, modeltype)
    sig1 = sig0 / Q * 3600.0

    # ================= 阶段四：预报并抓取目标天体 =================
    # 1. 预报：将历表理论位置反演为照片上的像素坐标
    xi, eta = rade2xieta(obj_ephra * Q, obj_ephde * Q, ra_cen, de_cen)
    pre_x, pre_y = xieta2xy(xi, eta, par1[:6])
    pre_x = pre_x * fl / pscale + x_cen
    pre_y = pre_y * fl / pscale + y_cen
    print(f'    预报 x/y：{pre_x:11.5f}{pre_y:11.5f}  '
          f'历表 ra/de：{obj_ephra:11.5f}{obj_ephde:11.5f}')

    # 2. 抓取：在距离预报位置 3 个像素的范围内，寻找真实的检测星
    dis0, selectflag = 20.0, 0
    obj_x_obs = obj_y_obs = obj_flux_obs = snr_obs = 0.0
    for i in range(n_det):
        dis = np.hypot(det_x[i] - pre_x, det_y[i] - pre_y) # 计算距离
        if dis <= 3.0 and dis < dis0: # 在3像素容差内，取最近的那颗
            dis0 = dis
            obj_x_obs, obj_y_obs = det_x[i], det_y[i]
            obj_flux_obs, snr_obs = det_flux[i], det_snr[i]
            selectflag = 1

    if not selectflag:
        print('    未找到与预报位置相近的目标星')
        _empty['nopre'] = 1
        return _empty

    # 3. 定位：将抓取到的目标实际像素坐标，通过底片模型转换为极其精准的真实 RA/Dec
    xn = (obj_x_obs - x_cen) * pscale / fl
    yn = (obj_y_obs - y_cen) * pscale / fl
    obj_obsra, obj_obsde = xy2rade(par1[:modeltype], modeltype, xn, yn, ra_cen, de_cen)

    # ================= 阶段五：整理结果并返回 =================
    result = _empty.copy()
    # 写入目标的观测数据
    result.update(obj_x=obj_x_obs, obj_y=obj_y_obs,
                  obj_flux=obj_flux_obs, snr=snr_obs,
                  obj_obsra=obj_obsra / Q, obj_obsde=obj_obsde / Q,
                  n_match1=n_m, sig0=sig1, par1=par1,
                  x_center=x_cen, y_center=y_cen,
                  ra_center=ra_cen, de_center=de_cen)
                  
    # 写入所有匹配上的参考星数据（供后续生成 .reg 审查文件用）
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
        object_out_files = {}
        for obj in range(1, config['obj_total'] + 1):
            object_out_files[obj] = open(os.path.join(fitspath, f'object_{obj}.out'), 'w')

        flag_pre = 0
        pre_par = np.zeros(30)
        pre_x_cen = pre_y_cen = pre_ra_cen = pre_de_cen = 0.0

        for n_fits, fitsfile_path in enumerate(fits_files, 1):
            fitsfile = fitsfile_path.strip()
            print(f'\n  {n_fits:3d}/{n_total} - {os.path.basename(fitsfile)}')

            hdr = read_fits_header(fitsfile, config['tele_label'])
            if hdr is None:
                continue

            obj_T = hdr['day'] + (hdr['hh']*3600 + hdr['mm']*60 + hdr['ss'] + config['delta_t']) / 86400.0
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
                        object_out_files[obj], hdr['year'], hdr['month'], obj_T,
                        result['obj_obsra'], result['obj_obsde'],
                        obj_ephra, obj_ephde, result['sig0'],
                        hdr['hh'], hdr['mm'], hdr['ss'],
                        hdr['exptime'], fitsfile, config['field_angle'])

        # 关闭文件并排序
        for f in object_out_files.values():
            f.close()
        for obj in range(1, config['obj_total'] + 1):
            sort_output_file(os.path.join(fitspath, f'object_{obj}.out'))

        print(f'\n  本日归算目标数：{config["obj_total"]}')

    print(f'\n{"="*50}\n03match 完成，共处理 {len(fitspath_list)} 天。')