"""Precision-preserving adapters for the existing fixed-header DAT readers."""

from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
import re

from .models import EphemerisRow, ReferenceError


def parse_ephemeris(text):
    rows = []
    for line in text.splitlines():
        if not re.match(r'^\s*\d{4}\s+\d{1,2}\s+\d{1,2}\s+', line):
            continue
        parts = line.split()
        try:
            if len(parts) < 8:
                raise ValueError('missing coordinate columns')
            time = datetime(*map(int, parts[:5])) + timedelta(seconds=float(parts[5]))
            ra, dec = Decimal(parts[6]), Decimal(parts[7])
            if not (ra.is_finite() and dec.is_finite() and 0 <= ra < 24 and -90 <= dec <= 90):
                raise ValueError('coordinates are not decimal hours/degrees')
        except (ValueError, InvalidOperation, OverflowError) as exc:
            raise ReferenceError(f"历表数据行格式无效：{line[:160]}") from exc
        rows.append(EphemerisRow(time, parts[6], parts[7]))
    if not rows or any(a.time >= b.time for a, b in zip(rows, rows[1:])):
        raise ReferenceError('历表为空或时刻存在重复/逆序。')
    return rows


def write_ephemeris(path, rows, header):
    lines = ['# NSPA prepared ephemeris; raw response and request in manifest.json',
             '# ' + header.get('planet', ''), '# ' + header.get('satellite', ''),
             '# Observatory: ' + header.get('observatory', ''), '# Timescale: UTC',
             '# ICRF, J2000, astrometric; RA hours, Dec degrees',
             '# No visibility cut; full requested time coverage',
             '# Numeric precision retained from source response',
             '# Ten header lines for nspa.io.catalog_io.read_ephemeris',
             '# year month day hour minute seconds RA(hours) Dec(degrees)']
    lines += [f"{r.time:%Y %m %d %H %M} {r.time.second + r.time.microsecond / 1e6:.6f} {r.ra_hours} {r.dec_degrees}"
              for r in rows]
    Path(path).write_text('\n'.join(lines) + '\n', encoding='utf-8')


def write_gaia(path, stars):
    header = ['# Gaia DR3 ICRS, reference epoch 2016.0; no premature proper-motion propagation',
              '# RA/Dec degrees; pmRA=mu_alpha*cos(dec), pmDE mas/year; G magnitude',
              '# Missing required fields excluded; raw values and counts retained in cache',
              '# Source identifier prefix is exactly 39 columns']
    header += ['# Prepared reference data'] * (60 - len(header))
    lines = [f"{str(sid):<39}" + ' '.join(str(v) for v in values) for sid, values in stars]
    Path(path).write_text('\n'.join(header + lines + ['#END']) + '\n', encoding='utf-8')
