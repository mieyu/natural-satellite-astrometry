"""功能：FITS 文件读写工具（读取图像数据、写出处理结果）。
使用：from adias.io.fits_io import read_fits, write_fits
"""

import numpy as np
from astropy.io import fits
import warnings
from astropy.utils.exceptions import AstropyWarning

from adias.errors import ProcessingError

warnings.filterwarnings('ignore', category=AstropyWarning)

def read_fits(fitsfile):
    """
    读取 FITS 文件，返回图像数据（float64）和头信息。

    Parameters
    ----------
    fitsfile : str

    Returns
    -------
    data   : np.ndarray，float64
    header : astropy.io.fits.Header
    """
    with fits.open(fitsfile, ignore_missing_end=True) as hdul:
        data   = hdul[0].data.astype(np.float64)
        header = hdul[0].header.copy()
    return data, header


def write_fits(fitsfile, data, header):
    """
    将处理后的图像写出为 FITS 文件（float32 节省空间）。

    Parameters
    ----------
    fitsfile : str
    data     : np.ndarray
    header   : astropy.io.fits.Header
    """
    fits.writeto(fitsfile, data.astype(np.float32), header, overwrite=True)

def read_fits_header(fitsfile, tele_label):
    """
    解析 FITS 头，返回曝光中点 UTC 时间及基本参数。
    支持望远镜标签：ss156 / ss156_2014 / km100 / lj240 / km100B。

    Parameters
    ----------
    fitsfile   : str
    tele_label : str，望远镜标签

    Returns
    -------
    dict，包含：naxis1, naxis2, bscale, bzero, gain, exptime,
               year, month, day, hh, mm, ss
    解析失败时抛 ProcessingError（单图错误，调用方应捕获后跳过此图）。
    """
    try:
        with fits.open(fitsfile) as hdul:
            h = hdul[0].header
            naxis1  = h.get('NAXIS1',  0)
            naxis2  = h.get('NAXIS2',  0)
            bscale  = h.get('BSCALE',  1.0)
            bzero   = h.get('BZERO',   0.0)
            gain    = h.get('GAIN',    1.0)
            exptime = h.get('EXPTIME', 0.0)

            # 按望远镜标签选择时间关键字
            key = 'DATE-STA' if tele_label == 'ss156_2014' else 'DATE-OBS'
            date_str = h.get(key, '')
            if not date_str:
                raise ProcessingError(f"{fitsfile} 中未找到时间关键字 {key}")
            if tele_label not in ('ss156', 'ss156_2014', 'km100', 'lj240', 'km100B'):
                raise ProcessingError(f"未知望远镜标签：{tele_label}")

            p = date_str.replace('T', ' ').replace('-', ' ').replace(':', ' ').split()
            year, month, day = int(p[0]), int(p[1]), int(p[2])
            hh,   mm,    ss  = int(p[3]), int(p[4]), float(p[5])

            # 修正到曝光中点
            ss += 0.5 * exptime
            while ss >= 60:
                mm += 1; ss -= 60
                if mm >= 60:
                    hh += 1; mm -= 60
                    if hh >= 24:
                        day += 1; hh -= 24

            # 北京时 -> UTC（仅 ss156 系列）
            if tele_label in ('ss156', 'ss156_2014'):
                if hh < 8:
                    day -= 1; hh += 24
                hh -= 8

            return dict(naxis1=naxis1, naxis2=naxis2, bscale=bscale, bzero=bzero,
                        gain=gain, exptime=exptime,
                        year=year, month=month, day=day, hh=hh, mm=mm, ss=ss)
    except ProcessingError:
        raise
    except Exception as e:
        raise ProcessingError(f"读取 FITS 头错误：{fitsfile}: {e}") from e