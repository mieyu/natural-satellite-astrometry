# 功能：星表与历表文件读取（GAIA 星表、IMCCE 历表）。
# 使用：from adias.io.catalog_io import read_catalog, read_ephemeris
#
# 错误约定：
#   - 文件无法打开或全文解析失败：raise DataFormatError，由调用方决定跳过策略
#   - 单行解析失败：保持静默跳过（与历史行为一致）

import numpy as np

from adias.errors import DataFormatError


def read_catalog(catfile, min_mag, max_mag):
    """
    读取 GAIA 星表文件。
    格式：跳过前 60 行，之后每行从第 39 列起读取：
    RA(deg)  DE(deg)  pmRA(mas/yr)  pmDE(mas/yr)  Gmag

    Parameters
    ----------
    catfile  : str，星表文件路径
    min_mag  : float，星等下限
    max_mag  : float，星等上限

    Returns
    -------
    n_gaia   : int
    gaia_ra  : np.ndarray，赤经（度）
    gaia_de  : np.ndarray，赤纬（度）
    gaia_pr  : np.ndarray，RA 方向自行（mas/yr）
    gaia_pd  : np.ndarray，DE 方向自行（mas/yr）
    gaia_mag : np.ndarray，G 星等
    """
    ra, de, pr, pd, mag = [], [], [], [], []
    try:
        with open(catfile, 'r') as f:
            lines = f.readlines()
    except OSError as e:
        raise DataFormatError(f"无法打开 GAIA 星表 {catfile}: {e}") from e

    for line in lines[60:]:
        if line[:4] in ('    ', '#END'):
            break
        if len(line) < 39:
            continue
        try:
            parts = line[39:].split()
            if len(parts) >= 5:
                m = float(parts[4])
                if min_mag <= m <= max_mag:
                    ra.append(float(parts[0]))
                    de.append(float(parts[1]))
                    pr.append(float(parts[2]))
                    pd.append(float(parts[3]))
                    mag.append(m)
        except (ValueError, IndexError):
            continue

    n = len(ra)
    return n, np.array(ra), np.array(de), np.array(pr), np.array(pd), np.array(mag)

def read_ephemeris(ephfile):
    """
    读取 IMCCE 历表文件。
    格式：跳过前 10 行，之后每行：
    year month day hh mm ss  RA(h)  DE(deg)  ...

    Parameters
    ----------
    ephfile : str，历表文件路径

    Returns
    -------
    n_eph   : int
    eph_T   : np.ndarray，儒略日内时间（day + 时间分数）
    eph_ra  : np.ndarray，赤经（度，已从时角换算）
    eph_de  : np.ndarray，赤纬（度）
    """
    T, ra_list, de_list = [], [], []
    try:
        with open(ephfile, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except OSError as e:
        raise DataFormatError(f"无法打开历表 {ephfile}: {e}") from e

    print(f"历表文件总行数: {len(lines)}")
    skipped = parsed = 0
    for i, line in enumerate(lines[10:], start=10):
        s = line.strip()
        if not s or s.startswith('---'):
            skipped += 1
            continue
        try:
            p = s.split()
            if len(p) >= 8:
                day = int(p[2])
                hh, mm, ss = int(p[3]), int(p[4]), float(p[5])
                T.append(day + (hh * 3600.0 + mm * 60.0 + ss) / 86400.0)
                ra_list.append(float(p[6]) * 15.0)   # 时角 -> 度
                de_list.append(float(p[7]))
                parsed += 1
            else:
                skipped += 1
        except (ValueError, IndexError) as e:
            print(f"第 {i+1} 行解析失败：{s}，错误：{e}")
            skipped += 1
    print(f"跳过行数：{skipped}，成功解析行数：{parsed}")

    if parsed == 0:
        raise DataFormatError(f"历表 {ephfile} 无可解析行（共 {len(lines)} 行）")

    n = len(T)
    return n, np.array(T), np.array(ra_list), np.array(de_list)