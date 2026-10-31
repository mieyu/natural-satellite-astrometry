"""Read exposure midpoints using exactly the pipeline's FITS header rules."""

from datetime import datetime, timedelta
import math

from nspa.io.fits_io import read_fits_header
from nspa.paths import expand_fitspath, list_fits
from .models import ObservationPlan, ReferenceError, check_cancel


def plan_observations(request, progress=lambda _s: None, cancel=None):
    files = sorted({p.resolve() for day in expand_fitspath(request.fitspaths) for p in list_fits(day)})
    if not files:
        raise ReferenceError("所选目录没有原始 FITS 图像。")
    if request.step_seconds <= 0 or request.step_seconds > 3600:
        raise ReferenceError("历表步长应为 1～3600 秒。")
    if not math.isfinite(request.delta_t) or not 0 <= request.padding_seconds <= 3600:
        raise ReferenceError("时间改正或历表余量无效。")
    moments = []
    progress(f"读取 {len(files)} 张图像的曝光中点 UTC 时间…")
    for index, path in enumerate(files):
        check_cancel(cancel)
        try:
            header = read_fits_header(str(path), request.tele_label)
            # Normalize day 0/32 emitted by legacy ss156 timezone arithmetic.
            time = datetime(header['year'], header['month'], 1) + timedelta(
                days=header['day'] - 1, hours=header['hh'], minutes=header['mm'],
                seconds=header['ss'] + request.delta_t)
            if (time.year, time.month) != (header['year'], header['month']):
                raise ValueError('曝光中点/时间改正跨月，当前算法按月内日数插值，不能自动混用月份')
        except Exception as exc:
            raise ReferenceError(f"无法确定观测时刻：{path.name}：{exc}") from exc
        moments.append(time)
        if (index + 1) % 100 == 0:
            progress(f"已读取 {index + 1}/{len(files)} 张图像时间")
    moments = tuple(sorted(set(moments)))
    if len({(t.year, t.month) for t in moments}) != 1:
        raise ReferenceError("自动准备暂按单个 UTC 观测月执行；请按月选择图像。")
    first = moments[0].replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    next_month = (first.replace(day=28) + timedelta(days=4)).replace(day=1)
    start = max(first, (moments[0] - timedelta(seconds=request.padding_seconds)).replace(second=0, microsecond=0))
    stop = min(next_month - timedelta(seconds=1),
               (moments[-1] + timedelta(seconds=request.padding_seconds + 60)).replace(second=0, microsecond=0))
    if stop < moments[-1]:
        raise ReferenceError("图像位于 UTC 月末最后一秒内，当前单月历表无法完整覆盖，请拆分该边界图像。")
    if (stop - start).total_seconds() < 3 * request.step_seconds:
        stop = min(next_month - timedelta(seconds=1), start + timedelta(seconds=3 * request.step_seconds))
        start = max(first, stop - timedelta(seconds=3 * request.step_seconds))
    return ObservationPlan(moments, start, stop, first.strftime('%Y%m'), len(files))


def separation(ra1, dec1, ra2, dec2):
    a, b = math.radians(dec1), math.radians(dec2)
    d = math.radians(((ra2 - ra1 + 180) % 360) - 180)
    h = math.sin((b - a) / 2) ** 2 + math.cos(a) * math.cos(b) * math.sin(d / 2) ** 2
    return math.degrees(2 * math.asin(min(1.0, math.sqrt(max(0.0, h)))))


def plan_cone(rows, request):
    half, margin = request.field_half_arcmin, request.sky_margin_arcmin
    if not all(math.isfinite(x) and x >= 0 for x in (half, margin)) or half <= 0:
        raise ReferenceError("参考星半宽必须大于零，天区余量必须为非负数。")
    points = [(float(r.ra_hours) * 15, float(r.dec_degrees)) for r in rows]
    if not points:
        raise ReferenceError("没有可用于确定 Gaia 天区的历表位置。")
    x = y = z = 0.0
    for ra, dec in points:
        a, b = math.radians(ra), math.radians(dec)
        x += math.cos(b) * math.cos(a); y += math.cos(b) * math.sin(a); z += math.sin(b)
    if math.hypot(x, y) + abs(z) < 1e-9:
        raise ReferenceError("所选目标分布过广，请按天区拆分任务。")
    ra = math.degrees(math.atan2(y, x)) % 360
    if ra >= 360:
        ra = 0.0
    dec = math.degrees(math.atan2(z, math.hypot(x, y)))
    border = (math.sqrt(2) * half + margin) / 60
    radius = max(separation(ra, dec, a, b) for a, b in points) + border
    cone = request.gaia_cone or (ra, dec, max(0.5, radius))
    a, b, r = cone
    if not all(math.isfinite(v) for v in cone) or not (0 <= a < 360 and -90 <= b <= 90 and 0 < r <= 5):
        raise ReferenceError("Gaia 查询范围无效或超过 5°；请按更小天区拆分任务。")
    if any(separation(a, b, p, q) + border > r + 1e-8 for p, q in points):
        raise ReferenceError("指定 Gaia 天区未覆盖所有目标轨迹及参考星搜索范围。")
    return (round(cone[0], 10) % 360, round(cone[1], 10), round(cone[2], 10))
