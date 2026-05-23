"""GAIA 星表与历表适配器。"""

from adias.domain.models import Ephemeris, GaiaCatalog
from adias.io.catalog_io import read_catalog, read_ephemeris


def read_gaia_catalog(catfile, min_mag, max_mag):
    """读 GAIA 星表，返回 GaiaCatalog（封装 ndarray，hot-path 仍走 numpy）。"""
    n, ra, de, pm_ra, pm_de, mag = read_catalog(catfile, min_mag, max_mag)
    if n == 0 or ra is None:
        return GaiaCatalog.empty()
    return GaiaCatalog(count=n, ra=ra, de=de, pm_ra=pm_ra, pm_de=pm_de, mag=mag)


def read_target_ephemeris(ephfile):
    """读单目标 IMCCE 历表，返回 Ephemeris。"""
    n, t, ra, de = read_ephemeris(ephfile)
    if n == 0 or t is None:
        return Ephemeris.empty()
    return Ephemeris(count=n, t=t, ra=ra, de=de)
