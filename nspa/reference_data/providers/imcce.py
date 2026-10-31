"""Official MULTI-SAT form client; trust returned models, not HTML labels."""

from datetime import timedelta
from html.parser import HTMLParser
import json
from pathlib import Path
import re
from urllib.parse import urlencode

from .transport import fetch
from ..formats import parse_ephemeris, write_ephemeris
from ..models import PreparationCancelled, ReferenceError, check_cancel
from ..validation import validate_coverage, validate_ephemeris_file

URL = 'https://www.sai.msu.ru/neb/nss/cgi-bin/nss-eph3.cgi'
TARGETS = json.loads((Path(__file__).parents[1] / 'targets.json').read_text(encoding='utf-8'))


class ModelMismatch(ReferenceError):
    pass


class PreParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.active, self.done = [], False, False

    def handle_starttag(self, tag, attrs):
        if tag == 'pre' and not self.done:
            self.active = True

    def handle_endtag(self, tag):
        if tag == 'pre' and self.active:
            self.active, self.done = False, True

    def handle_data(self, data):
        if self.active:
            self.parts.append(data)


def model_name(text):
    match = re.search(r'^\s*Satellite:[^\n]*', text, re.M)
    if not match or '(' not in match[0]:
        return ''
    return match[0].split('(', 1)[1].rsplit(')', 1)[0].strip()


def _same_model(actual, expected):
    return re.sub(r'\s+', '', actual).casefold() == re.sub(r'\s+', '', expected).casefold()


def _model_policy(target):
    system = TARGETS[target]['system']
    match = re.fullmatch(r'([MSJUNP])(\d+)', target)
    number = int(match[2]) if match else -1
    if system == 'U' and 1 <= number <= 5:
        return ('0', '2', '1'), r'Lainey.*2015'
    if system == 'S' and (1 <= number <= 8 or number in (12, 13, 14, 34)):
        return ('4', '0', '3', '1', '2'), r'Lainey.*2015'
    if system == 'J' and 1 <= number <= 4:
        return ('2', '0', '3', '1'), r'Lainey'
    if system == 'M' and number in (1, 2):
        return ('3', '0', '2', '1'), r'Lainey.*2015'
    if system == 'N' and number in (1, 2):
        return ('2', '0', '1', '3'), r'Emelyanov.*2015'
    if system == 'P':
        return ('2', '0', '1'), r'Beauvalet'
    # These targets use a fixed numerical theory rather than the main-moon
    # selector. A supplied local-model hint still pins their exact version.
    return ('0',), None


def parse_response(raw, charset, target, observatory, expected_model=None, pattern=None):
    parser = PreParser()
    parser.feed(raw.decode(charset))
    text = ''.join(parser.parts).lstrip('\r\n')
    header = text.splitlines()[:10]
    prefix = '\n'.join(header)
    target_name = TARGETS[target]['name']
    satellite_line = next((line.strip() for line in header if 'Satellite:' in line), '')
    expected_label = target if re.fullmatch(r'[MSJUNP]\d+', target) else target_name
    normalize = lambda s: re.sub(r'[^a-z0-9]', '', s.lower())
    identity_ok = (re.search(r'Satellite:\s*' + re.escape(expected_label) + r'(?!\d)', satellite_line) is not None
                   if re.fullmatch(r'[MSJUNP]\d+', target)
                   else normalize(target_name) in normalize(satellite_line))
    planet = {'M': 'Mars', 'J': 'Jupiter', 'S': 'Saturn', 'U': 'Uranus',
              'N': 'Neptune', 'P': 'Pluto'}[TARGETS[target]['system']]
    if not identity_ok or not re.search(r'Planet:\s*' + planet + r'\s*\(DE441\)', prefix):
        raise ReferenceError(f'上游返回的目标或行星理论不符：{satellite_line or prefix[:240]}')
    if (not re.search(r'Observatory N:\s*' + re.escape(observatory) + r'\s*-', prefix)
            or 'Timescale: UTC' not in prefix or 'ICRF' not in prefix
            or 'J2000' not in prefix or 'Coordinates astrometric' not in prefix):
        raise ReferenceError('上游返回的测站、时间尺度或坐标参考系不符。')
    if not re.search(r'alpha\s*\(h\)', prefix, re.I):
        raise ReferenceError('上游未返回所需的十进制赤经时数格式。')
    actual_model = model_name(text)
    if not actual_model:
        raise ReferenceError('上游未说明实际卫星理论，不能自动使用。')
    if expected_model and not _same_model(actual_model, expected_model):
        raise ModelMismatch(f'需要卫星理论 {expected_model}，上游实际返回 {actual_model}')
    if not expected_model and pattern and not re.search(pattern, actual_model, re.I):
        raise ModelMismatch(f'需要推荐卫星理论 {pattern}，上游实际返回 {actual_model}')
    rows = parse_ephemeris(text)
    metadata = {'planet': next(line.strip() for line in header if 'Planet:' in line),
                'satellite': satellite_line, 'model': actual_model, 'observatory': observatory,
                'frame': 'ICRF/J2000 astrometric', 'timescale': 'UTC'}
    return rows, metadata


def build(folder, target, plan, request, progress, cancel=None, expected_model=None):
    if target not in TARGETS:
        raise ReferenceError(f'未知的官方目标编号：{target}')
    if not re.fullmatch(r'\d{3}|[A-Za-z]\d{2}', request.observatory):
        raise ReferenceError('请明确填写三位 IAU 观测站代码，例如 286 或 500。')
    base = {'langue': '30', 'satellite': TARGETS[target]['satellite'], 'relative': '-1',
            'nde': '6', 'observatory': request.observatory, 'epoch': 'ICRF', 'tscale': 'UTC',
            'initform': '1', 'steptype': '1', 'timestep': str(request.step_seconds / 3600),
            'outputtype': '1000', 'vangle': '0'}
    # Deliberately omit visible: every selected exposure must be covered.
    candidates, pattern = _model_policy(target)
    calls, errors = [], []

    def query(form, label, chosen_model=None, chosen_pattern=None):
        check_cancel(cancel)
        progress(f'{target}：{label}')
        raw, charset = fetch(URL, urlencode(form).encode(), mode=request.network_mode, cancel=cancel,
                             headers={'Content-Type': 'application/x-www-form-urlencoded'})
        name = f'raw-{len(calls):03d}.html'
        (folder / name).write_bytes(raw)
        calls.append({'url': URL, 'form': form, 'charset': charset, 'raw': name})
        return parse_response(raw, charset, target, request.observatory, chosen_model, chosen_pattern)

    for code in candidates:
        form = {**base, 'plnvar': code, 'initmom': plan.start.strftime('%Y %m %d %H %M %S'), 'ntimes': '1'}
        try:
            _probe, metadata = query(form, '核验实际模型', expected_model, pattern)
            break
        except PreparationCancelled:
            raise
        except ModelMismatch as exc:
            errors.append(str(exc))
    else:
        raise ReferenceError('无法取得所需的卫星理论；未改用其他模型。' + '\n'.join(errors))
    base['plnvar'] = code
    all_rows = []
    total = int((plan.stop - plan.start).total_seconds() // request.step_seconds) + 1
    for offset in range(0, total, 5000):
        count = min(5000, total - offset)
        start = plan.start + timedelta(seconds=offset * request.step_seconds)
        form = {**base, 'initmom': start.strftime('%Y %m %d %H %M %S'), 'ntimes': str(count)}
        rows, current = query(form, f'下载 {offset + 1}～{offset + count}/{total} 个历表点', metadata['model'])
        expected = [start + timedelta(seconds=i * request.step_seconds) for i in range(count)]
        if len(rows) != count or any(abs((r.time - t).total_seconds()) > .011 for r, t in zip(rows, expected)):
            raise ReferenceError(f'{target} 返回的历表点数或时刻不完整。')
        all_rows.extend(rows)
    if all_rows[-1].time < plan.stop:
        form = {**base, 'initmom': plan.stop.strftime('%Y %m %d %H %M %S'), 'ntimes': '1'}
        rows, _meta = query(form, '下载月末覆盖点', metadata['model'])
        if len(rows) != 1 or abs((rows[0].time - plan.stop).total_seconds()) > .011:
            raise ReferenceError('上游未返回月末覆盖点。')
        all_rows.extend(rows)
    if any(r.time.strftime('%Y%m') != plan.month for r in all_rows):
        raise ReferenceError('历表跨越 UTC 月份，当前读取器不能安全使用。')
    validate_coverage(all_rows, plan, request.step_seconds)
    name = f'EPH_{re.sub(r"[^A-Za-z0-9_]+", "_", target)}_{plan.month}.DAT'
    write_ephemeris(folder / name, all_rows, metadata)
    validate_ephemeris_file(folder / name, all_rows)
    metadata.update({'requests': calls, 'rows': len(all_rows), 'failed_model_probes': errors,
                     'start': all_rows[0].time.isoformat(), 'stop': all_rows[-1].time.isoformat(),
                     'visibility_filter': False})
    return name, metadata
