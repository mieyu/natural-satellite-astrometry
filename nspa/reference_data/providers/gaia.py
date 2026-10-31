"""ESA Gaia DR3 TAP: complete VOTable response with nulls preserved in raw data."""

import math
from urllib.parse import urlencode
import xml.etree.ElementTree as ET

from .transport import fetch
from ..formats import write_gaia
from ..models import ReferenceError, check_cancel
from ..planning import separation
from ..validation import validate_gaia_file

URL = 'https://gea.esac.esa.int/tap-server/tap/sync'
FIELDS = ('source_id', 'ra', 'dec', 'pmra', 'pmdec', 'phot_g_mean_mag')


def query_for(cone):
    ra, dec, radius = cone
    return ("SELECT source_id,ra,dec,pmra,pmdec,phot_g_mean_mag FROM gaiadr3.gaia_source "
            "WHERE 1=CONTAINS(POINT('ICRS',ra,dec),"
            f"CIRCLE('ICRS',{ra:.10f},{dec:.10f},{radius:.10f}))")


def parse_response(raw):
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise ReferenceError('Gaia 服务未返回有效 VOTable。') from exc
    statuses = [item for item in root.iter() if item.tag.split('}')[-1] == 'INFO'
                and item.get('name', '').upper() == 'QUERY_STATUS']
    if not statuses or any(item.get('value', '').upper() != 'OK' for item in statuses):
        detail = '; '.join((item.get('value', '') + ' ' + (item.text or ''))[:400] for item in statuses)
        raise ReferenceError('Gaia 查询失败或结果被截断，不能使用不完整星表：' + detail)
    tables = [e for e in root.iter() if e.tag.split('}')[-1] == 'TABLE']
    if len(tables) != 1:
        raise ReferenceError('Gaia 返回的表数量与请求不符。')
    table = tables[0]
    columns = [e for e in table if e.tag.split('}')[-1] == 'FIELD']
    names = [e.get('name', '').lower() for e in columns]
    if set(names) != set(FIELDS) or len(names) != len(FIELDS):
        raise ReferenceError('Gaia 返回字段不符。')
    units = {e.get('name', '').lower(): e.get('unit', '').lower().replace(' ', '') for e in columns}
    if units['ra'] not in ('deg', 'degree') or units['dec'] not in ('deg', 'degree'):
        raise ReferenceError('Gaia 赤经赤纬单位不是度。')
    if any(units[key] not in ('mas.yr-1', 'mas/yr', 'masyr-1', 'mas.yr**-1', 'mas.yr^-1') for key in ('pmra', 'pmdec')):
        raise ReferenceError('Gaia 自行单位不符。')
    data = next((e for e in table.iter() if e.tag.split('}')[-1] == 'TABLEDATA'), None)
    if data is None:
        raise ReferenceError('Gaia 未返回请求的 TABLEDATA 文本格式。')
    stars, missing, seen, total = [], 0, set(), 0
    for row in data:
        cells = [(e.text or '').strip() for e in row]
        if len(cells) != len(names):
            raise ReferenceError('Gaia 数据行列数不完整。')
        values = dict(zip(names, cells))
        try:
            sid = int(values['source_id'])
            if sid <= 0 or sid in seen:
                raise ValueError('duplicate or invalid source identifier')
            seen.add(sid)
            parsed = [float(values[key]) if values[key] else None for key in FIELDS[1:]]
        except ValueError as exc:
            raise ReferenceError('Gaia 数据行含无效数字或重复来源标识。') from exc
        total += 1
        if any(v is None or not math.isfinite(v) for v in parsed):
            missing += 1
            continue
        if not (0 <= parsed[0] < 360 and -90 <= parsed[1] <= 90):
            raise ReferenceError('Gaia 坐标超出度数范围。')
        stars.append((sid, tuple(values[key] for key in FIELDS[1:])))
    if not stars:
        raise ReferenceError('该天区没有五字段齐全的 Gaia DR3 参考星。')
    stars.sort(key=lambda row: row[0])
    return stars, {'total_rows': total, 'usable_rows': len(stars), 'missing_required_fields': missing,
                   'reference_epoch': 2016.0, 'catalogue': 'Gaia DR3', 'frame': 'ICRS',
                   'pmra_convention': 'mu_alpha*cos(dec)', 'missing_value_policy': 'exclude without zero filling; preserve raw response'}


def build(folder, cone, month, request, progress, cancel=None):
    check_cancel(cancel)
    query = query_for(cone)
    form = {'REQUEST': 'doQuery', 'LANG': 'ADQL', 'FORMAT': 'votable_plain',
            'MAXREC': '100000', 'QUERY': query}
    progress(f'查询 Gaia DR3：中心 {cone[0]:.5f}°, {cone[1]:+.5f}°，半径 {cone[2] * 60:.1f}′')
    raw, _charset = fetch(URL + '?' + urlencode(form), mode=request.network_mode, cancel=cancel)
    (folder / 'raw.vot').write_bytes(raw)
    stars, metadata = parse_response(raw)
    if any(separation(cone[0], cone[1], float(values[0]), float(values[1])) > cone[2] + 1e-7
           for _sid, values in stars):
        raise ReferenceError('Gaia 返回记录不在请求天区内，拒绝使用。')
    check_cancel(cancel)
    name = f'GAIA3_FIELD_{month}.DAT'
    write_gaia(folder / name, stars)
    validate_gaia_file(folder / name, stars)
    metadata.update({'url': URL, 'query': query, 'request': form, 'cone_degrees': list(cone)})
    progress(f'Gaia 已准备 {len(stars)} 颗参考星；{metadata["missing_required_fields"]} 条缺失字段保留在原始响应中')
    return name, metadata
