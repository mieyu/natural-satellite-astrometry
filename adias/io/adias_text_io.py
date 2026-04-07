# 功能：文本文件 IO 工具（fits.lst、fitspath.in 的读写）。
# 使用：from adias.io.text_io import read_fitspath, read_fits_list, write_fits_list

import os
import glob
import numpy as np


def read_fitspath(fitspath_file='fitspath.in'):
    """
    读取 fitspath.in，返回观测目录路径列表。

    Parameters
    ----------
    fitspath_file : str，路径列表文件，默认 'fitspath.in'

    Returns
    -------
    list[str]

    Raises
    ------
    FileNotFoundError
    """
    if not os.path.exists(fitspath_file):
        raise FileNotFoundError(f"路径文件 '{fitspath_file}' 未找到。")
    with open(fitspath_file, 'r') as f:
        return [line.strip() for line in f if line.strip()]


def read_fits_list(fitspath):
    """
    读取指定目录下的 fits.lst，返回其中记录的文件路径列表。

    Parameters
    ----------
    fitspath : str，观测数据目录

    Returns
    -------
    list[str]，fits.lst 中每行路径；文件不存在时返回空列表
    """
    lst_path = os.path.join(fitspath, 'fits.lst')
    if not os.path.exists(lst_path):
        print(f"警告：未找到 '{lst_path}'")
        return []
    with open(lst_path, 'r') as f:
        return [line.strip() for line in f if line.strip()]


def write_fits_list(fitspath):
    """
    扫描目录下所有原始 .fit 文件（排除 *_n.fit），
    生成 fits.lst 并写入该目录。

    Parameters
    ----------
    fitspath : str，观测数据目录

    Returns
    -------
    list[str]，写入 fits.lst 的文件路径列表（已排序）
    """
    all_fits = sorted(glob.glob(os.path.join(fitspath, '*.fit')))
    science_files = [f for f in all_fits if not f.endswith('_n.fit')]

    lst_path = os.path.join(fitspath, 'fits.lst')
    with open(lst_path, 'w') as f:
        for fp in science_files:
            f.write(f"{fp}\n")

    print(f"已生成 fits.lst --> {lst_path}（共 {len(science_files)} 个）")
    return science_files


def clean_old_files(fitspath):
    """
    删除目录下旧的 *_n.fit 结果文件和 *.lst 列表文件，
    确保每次运行从干净状态开始。

    Parameters
    ----------
    fitspath : str，观测数据目录
    """
    patterns = [
        os.path.join(fitspath, '*_n.fit*'),
        os.path.join(fitspath, '*.lst'),
    ]
    removed = 0
    for pat in patterns:
        for f in glob.glob(pat):
            os.remove(f)
            removed += 1
    if removed:
        print(f"已清理旧文件 {removed} 个 <- {fitspath}")

def write_reg_file(reg_path, stars, bkgd, bkgdsigma, snr_threshold):
    """
    将星象检测结果写出为 DS9 region 格式的 .reg 文件。

    Parameters
    ----------
    reg_path      : str，输出文件路径（形如 xxx.fit.reg）
    stars         : list[dict]，detect_stars_xzj 返回的星表
    bkgd          : float，背景均值
    bkgdsigma     : float，背景 sigma
    snr_threshold : float，SNR 阈值，低于此值的星不写出

    Returns
    -------
    int，实际写出的星数
    """
    n_out = 0
    with open(reg_path, 'w') as f:
        f.write('global color=green font="helvetica 10 normal" '
                'select=1 highlite=1 edit=1 move=1 delete=1 include=1 fixed=0 source\n')
        f.write('physical\n')
        for s in stars:
            if s['snr'] > snr_threshold and s['star_pix'] > 5:
                f.write(
                    f"ellipse {s['starx']:11.3f}{s['stary']:11.3f}"
                    f"{10.0:6.1f}{10.0:6.1f}   #  "
                    f"{s['sumi']:21.4f}{s['snr']:10.2f}"
                    f"{s['star_id']:5d}{s['star_pix']:5d}{s['overflag']:5d}"
                    f"{bkgd:15.3f}{bkgdsigma:15.3f}\n"
                )
                n_out += 1
    return n_out

def read_reg_file(regfile):
    """
    读取 02detect 生成的 .reg 文件，返回检测星的像面坐标、流量和 SNR。

    Returns
    -------
    det_x, det_y, det_flux, snr : np.ndarray x4
    """
    det_x, det_y, det_flux, snr = [], [], [], []
    try:
        with open(regfile, 'r') as f:
            lines = f.readlines()
        for line in lines[2:]:
            line = line.strip()
            if not line or 'ellipse' not in line.lower():
                continue
            try:
                parts = line.split()
                x, y = float(parts[1]), float(parts[2])
                hi = line.find('#')
                if hi != -1:
                    ap = line[hi+1:].split()
                    if len(ap) >= 2:
                        det_x.append(x)
                        det_y.append(y)
                        det_flux.append(float(ap[0]))
                        snr.append(float(ap[1]))
            except (ValueError, IndexError):
                continue
    except Exception as e:
        print(f"读取 reg 文件错误：{regfile}，{e}")
    return np.array(det_x), np.array(det_y), np.array(det_flux), np.array(snr)


def write_ref_file(filename, result):
    """
    写出参考星 DS9 region 文件（*.ref.reg）。

    Parameters
    ----------
    filename : str
    result   : dict，matcher 返回的结果字典
    """
    n = result.get('n_match1', 0)
    if n == 0:
        return
    try:
        with open(filename, 'w') as f:
            f.write('global color=red font="helvetica 10 normal" '
                    'select=1 highlite=1 edit=1 move=1 delete=1 include=1 fixed=0 source\n')
            f.write('physical\n')
            for i in range(n):
                f.write(f'ellipse{result["ref_x"][i]:11.3f}{result["ref_y"][i]:11.3f}'
                        f'{15.0:6.1f}{15.0:6.1f}  #  '
                        f'{result["ref_ra"][i]:15.8f}{result["ref_de"][i]:8.3f}'
                        f'{result["ref_mag"][i]:20.10f}\n')
    except Exception as e:
        print(f"写入参考星文件错误：{e}")


def write_object_result(fh, year, month, obj_T, obj_obsra, obj_obsde,
                        obj_ephra, obj_ephde, sig0,
                        hh, mm, ss, exptime, objfitsfile, field_angle):
    """
    向已打开的 object_X.out 文件追加一行观测结果。

    Parameters
    ----------
    fh          : file handle（已打开）
    year, month : int
    obj_T       : float，观测时刻（day + 时间分数）
    obj_obsra/de: float，观测赤经赤纬（度）
    obj_ephra/de: float，历表赤经赤纬（度）
    sig0        : float，归算 sigma（角秒）
    hh,mm,ss    : int,int,float，曝光开始时刻
    exptime     : float，曝光时间（s）
    objfitsfile : str，图像文件名
    field_angle : float，底片旋转角（度）
    """
    from adias.utils.adias_math_utils import am2hms
    Q = np.pi / 180.0
    obj_resra = (obj_obsra - obj_ephra) * 3600.0 * np.cos(obj_ephde * Q)
    obj_resde = (obj_obsde - obj_ephde) * 3600.0
    if abs(obj_resra) >= 10 or abs(obj_resde) >= 10:
        return
    i1, i2, ff, cc, j1, j2, fff = am2hms(obj_obsra * 60.0, obj_obsde * 60.0)
    line = (f'{year:6d} {month:02d}{obj_T:10.6f}'
            f'{i1:3d}{i2:3d}{ff:8.4f} {cc}{j1:02d}{j2:3d}{fff:7.3f}'
            f'{obj_obsra:12.7f}{obj_obsde:12.7f}'
            f'{obj_ephra:12.7f}{obj_ephde:12.7f}'
            f'{obj_resra:10.4f}{obj_resde:10.4f}{sig0:10.4f}'
            f'{hh:3d}{mm:3d}{ss:6.2f}{exptime:9.2f} {objfitsfile}{field_angle:7.2f}\n')
    fh.write(line)
    print(f'    写入残差 ra/de：{obj_resra:10.4f} / {obj_resde:10.4f}')


def sort_output_file(filename):
    """
    按第 2 列（观测时刻）对 object_X.out 文件排序。
    """
    try:
        with open(filename, 'r') as f:
            lines = [l.strip() for l in f if l.strip()]
        times = []
        for l in lines:
            parts = l.split()
            times.append(float(parts[1]) if len(parts) > 1 else 0.0)
        idx = np.argsort(times)
        with open(filename, 'w') as f:
            for i in idx:
                f.write(lines[i] + '\n')
    except Exception:
        pass