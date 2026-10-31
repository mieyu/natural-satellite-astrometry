"""Read original input files without rewriting or normalizing them in place."""

from pathlib import Path
import re

from ..formats import parse_ephemeris
from ..models import ReferenceError
from ..validation import validate_coverage, validate_gaia_file


def target_code(path):
    match = re.fullmatch(r'(?:Q_)?EPH_(.+)_\d{6}\.DAT', Path(path).name, re.I)
    if not match:
        raise ReferenceError(f'无法识别历表目标：{Path(path).name}')
    return match[1]


def load_ephemeris(path):
    try:
        text = Path(path).read_text(encoding='utf-8-sig')
    except (OSError, UnicodeError) as exc:
        raise ReferenceError(f'无法读取本地历表：{path}') from exc
    return text, parse_ephemeris(text)


def ephemerides(paths, plan=None):
    codes, rows = set(), []
    if not paths:
        raise ReferenceError('请选择至少一份本地目标历表。')
    for path in paths:
        code = target_code(path)
        if code in codes:
            raise ReferenceError(f'同一目标只能选择一份历表：{code}')
        codes.add(code)
        text, selected = load_ephemeris(path)
        if plan is not None:
            if ('Timescale: UTC' not in text[:2000] or 'ICRF' not in text[:2000]
                    or 'astrometric' not in text[:2000].lower()):
                raise ReferenceError(f'无法确认本地历表的 UTC/ICRF 信息：{path}')
            identity = re.search(r'Satellite:\s*([MSJUNP]\d+)(?!\d)', text[:2000])
            if identity and re.fullmatch(r'[MSJUNP]\d+', code, re.I) and identity[1].upper() != code.upper():
                raise ReferenceError(f'本地历表文件名与返回头中的目标不符：{path}')
            if any(r.time.strftime('%Y%m') != plan.month for r in selected):
                raise ReferenceError(f'本地历表与观测月不符：{path}')
            validate_coverage(selected, plan)
            selected = [r for r in selected if plan.start <= r.time <= plan.stop]
        rows.extend(selected)
    return rows


def gaia(path):
    if path is None or not Path(path).is_file():
        raise ReferenceError('请选择有效的本地 Gaia 星表。')
    validate_gaia_file(path)
    return Path(path)
