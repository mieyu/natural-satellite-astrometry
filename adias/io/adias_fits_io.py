# 功能：FITS 文件读写工具（读取图像数据、写出处理结果）。
# 使用：from adias.io.fits_io import read_fits, write_fits

import numpy as np
from astropy.io import fits
import warnings
from astropy.utils.exceptions import AstropyWarning

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