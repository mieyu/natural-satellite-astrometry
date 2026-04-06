# 功能：文本文件 IO 工具（fits.lst、fitspath.in 的读写）。
# 使用：from adias.io.text_io import read_fitspath, read_fits_list, write_fits_list

import os
import glob


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