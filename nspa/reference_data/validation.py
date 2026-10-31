"""Validation at the handoff to the unchanged scientific pipeline."""

from bisect import bisect_left
import math

from nspa.io.catalog_io import read_catalog, read_ephemeris
from .models import ReferenceError


def validate_coverage(rows, plan, max_gap=None):
    if len(rows) < 4:
        raise ReferenceError('历表至少需要 4 个有效时刻供插值使用。')
    times = [r.time for r in rows]
    for moment in plan.moments:
        if moment < times[0] or moment > times[-1]:
            raise ReferenceError(f'历表未覆盖图像曝光中点：{moment} UTC')
        if max_gap is not None:
            index = bisect_left(times, moment)
            if index and index < len(times) and (times[index] - times[index - 1]).total_seconds() > max_gap + .02:
                raise ReferenceError(f'历表在观测时刻附近存在缺口：{moment} UTC')


def validate_ephemeris_file(path, rows):
    n, times, ras, decs = read_ephemeris(str(path))
    if n != len(rows):
        raise ReferenceError('历表兼容文件回读丢失数据行。')
    for i, row in enumerate(rows):
        t = row.time
        expected = t.day + (t.hour * 3600 + t.minute * 60 + t.second + t.microsecond / 1e6) / 86400
        if abs(times[i] - expected) > 1e-10 or ras[i] != float(row.ra_hours) * 15 or decs[i] != float(row.dec_degrees):
            raise ReferenceError('历表回读时刻、赤经单位或赤纬不一致。')


def validate_gaia_file(path, expected=None):
    data = read_catalog(str(path), -100, 100)
    if not data[0] or any(not math.isfinite(float(v)) for column in data[1:] for v in column):
        raise ReferenceError('Gaia 星表没有完整有效的五字段记录。')
    if expected is not None:
        if data[0] != len(expected):
            raise ReferenceError('Gaia 兼容文件回读丢失数据行。')
        for i, (_sid, values) in enumerate(expected):
            if any(float(data[j + 1][i]) != float(values[j]) for j in range(5)):
                raise ReferenceError('Gaia 五字段回读数值不一致。')
    return data[0]
