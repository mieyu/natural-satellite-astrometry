"""FITS 文件读写工具：图像数据与头部读取、处理结果落地。

错误约定：
  - 读取异常统一抛 ProcessingError，调用方应捕获后跳过单图，不中断流水线。
"""

import warnings

import numpy as np
from astropy.io import fits
from astropy.utils.exceptions import AstropyWarning

from adias.errors import ProcessingError

warnings.filterwarnings('ignore', category=AstropyWarning)


def read_fits(fitsfile):
    """读取 FITS 文件，返回 (data: np.ndarray[float64], header)。"""
    with fits.open(fitsfile, ignore_missing_end=True) as hdul:
        data = hdul[0].data.astype(np.float64)
        header = hdul[0].header.copy()
    return data, header


def write_fits(fitsfile, data, header, dtype="float32"):
    """将处理结果写出为 FITS。

    dtype="float32"（默认）：存 float32，适用于结果本就是浮点的模式
        （同态滤波 / Retinex）。
    dtype="uint16"：按原图的无符号 16 位整型写出，并对越界值取模回绕
        （mod 65536）。这是中值滤波超级背景模式的正确写法：原始观测图为
        BITPIX=16 / BZERO=32768 的无符号整型，密集饱和区在“扣中值背景”后
        会产生大负值；若存成 float32 会把这些负值原样保留，破坏饱和亮星，
        与历史 Fortran 结果产生 65536 量级的灾难性差异。复刻无符号整型的
        回绕行为可保证与 Fortran 一致。
    """
    if dtype == "uint16":
        arr = (np.rint(data).astype(np.int64) % 65536).astype(np.uint16)
        hdr = header.copy()
        # 去掉旧标度，让 astropy 按 uint16 自动写 BITPIX=16 / BZERO=32768
        for k in ("BSCALE", "BZERO", "BITPIX"):
            if k in hdr:
                del hdr[k]
        fits.writeto(fitsfile, arr, hdr, overwrite=True)
    else:
        fits.writeto(fitsfile, data.astype(np.float32), header, overwrite=True)


def read_fits_header(fitsfile, tele_label):
    """解析 FITS 头，返回曝光中点 UTC 时间及基本参数 dict。

    支持 tele_label：ss156 / ss156_2014 / km100 / lj240 / km100B。
    解析失败时抛 ProcessingError（单图错误，调用方应捕获后跳过此图）。
    """
    try:
        with fits.open(fitsfile) as hdul:
            h = hdul[0].header
            naxis1 = h.get('NAXIS1', 0)
            naxis2 = h.get('NAXIS2', 0)
            bscale = h.get('BSCALE', 1.0)
            bzero = h.get('BZERO', 0.0)
            gain = h.get('GAIN', 1.0)
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
            hh, mm, ss = int(p[3]), int(p[4]), float(p[5])

            # 修正到曝光中点
            ss += 0.5 * exptime
            while ss >= 60:
                mm += 1
                ss -= 60
                if mm >= 60:
                    hh += 1
                    mm -= 60
                    if hh >= 24:
                        day += 1
                        hh -= 24

            # 北京时 -> UTC（仅 ss156 系列）
            if tele_label in ('ss156', 'ss156_2014'):
                if hh < 8:
                    day -= 1
                    hh += 24
                hh -= 8

            return dict(naxis1=naxis1, naxis2=naxis2, bscale=bscale, bzero=bzero,
                        gain=gain, exptime=exptime,
                        year=year, month=month, day=day, hh=hh, mm=mm, ss=ss)
    except ProcessingError:
        raise
    except Exception as e:
        raise ProcessingError(f"读取 FITS 头错误：{fitsfile}: {e}") from e
