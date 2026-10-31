"""Unified preparation entry point for local inputs and downloaded references."""

from datetime import datetime, timezone
import json
from pathlib import Path
from uuid import uuid4

from .cache import obtain, sha256
from .formats import parse_ephemeris
from .models import PreparedReferences, ReferenceError, check_cancel
from .planning import plan_cone, plan_observations
from .providers import gaia, imcce, local
from .validation import validate_coverage


def prepare_references(request, progress=lambda _s: None, cancel=None):
    """Return final file paths; never rewrite any existing input/config file."""
    if request.eph_source not in {'inputs', 'download'} or request.gaia_source not in {'inputs', 'download'}:
        raise ReferenceError('星表/历表来源必须为 inputs 或 download。')
    check_cancel(cancel)
    if request.gaia_source == 'inputs':
        gaia_path = local.gaia(request.local_gaia_file)
    if request.eph_source == request.gaia_source == 'inputs':
        local.ephemerides(request.local_eph_files)
        progress('本地星表、历表检查完成。')
        return PreparedReferences(tuple(Path(p) for p in request.local_eph_files), gaia_path, None)

    plan = plan_observations(request, progress, cancel)
    progress(f'观测月 {plan.month}，UTC {plan.moments[0]} ～ {plan.moments[-1]}')
    manifests, eph_paths, all_rows = [], [], []
    if request.eph_source == 'inputs':
        all_rows = local.ephemerides(request.local_eph_files, plan)
        eph_paths = [Path(p) for p in request.local_eph_files]
    else:
        if not request.targets or len(set(request.targets)) != len(request.targets):
            raise ReferenceError('请选择至少一个目标，同一目标不能重复。')
        if any(code not in imcce.TARGETS for code in request.targets):
            raise ReferenceError('所选目标不在已收录的官方编号表中。')
        hints = {}
        for path in request.local_eph_files:
            try:
                text, _rows = local.load_ephemeris(path)
                if _rows[0].time.strftime('%Y%m') == plan.month:
                    hints[local.target_code(path)] = imcce.model_name(text)
            except ReferenceError:
                continue  # Optional hints are not a substitute for a download.
        for target in request.targets:
            check_cancel(cancel)
            key = {'provider': 'IMCCE-SAI', 'target': target,
                   'satellite': imcce.TARGETS[target]['satellite'],
                   'start': plan.start.isoformat(), 'stop': plan.stop.isoformat(),
                   'step_seconds': request.step_seconds, 'observatory': request.observatory,
                   'planet_model': 'DE441', 'satellite_model_hint': hints.get(target, ''),
                   'frame': 'ICRF/J2000 astrometric', 'timescale': 'UTC', 'visibility_filter': False}
            path, manifest, metadata = obtain(request.cache_root, 'ephemeris', key,
                lambda folder, code=target: imcce.build(folder, code, plan, request, progress, cancel, hints.get(code)),
                progress, cancel)
            rows = parse_ephemeris(path.read_text(encoding='utf-8'))
            validate_coverage(rows, plan, request.step_seconds)
            all_rows.extend(rows)
            eph_paths.append(path)
            manifests.append(str(manifest))
            progress(f'{target} 已准备：{len(rows)} 点，{metadata["metadata"]["model"]}')

    cone = None
    if request.gaia_source == 'download':
        cone = plan_cone(all_rows, request)
        key = {'provider': 'ESA Gaia Archive', 'catalogue': 'gaiadr3.gaia_source',
               'query': gaia.query_for(cone), 'reference_epoch': 2016.0,
               'format': 'votable_plain', 'maxrec': 100000, 'month_label': plan.month}
        gaia_path, manifest, _metadata = obtain(request.cache_root, 'gaia', key,
            lambda folder: gaia.build(folder, cone, plan.month, request, progress, cancel), progress, cancel)
        manifests.append(str(manifest))
    check_cancel(cancel)
    folder = Path(request.cache_root) / 'jobs'
    folder.mkdir(parents=True, exist_ok=True)
    manifest_path = folder / (uuid4().hex + '.json')
    manifest = {'prepared_at': datetime.now(timezone.utc).isoformat(),
                'sources': {'ephemeris': request.eph_source, 'gaia': request.gaia_source},
                'observations': {'files': plan.files, 'utc_start': plan.moments[0].isoformat(),
                                 'utc_stop': plan.moments[-1].isoformat(), 'month': plan.month},
                'gaia_cone_degrees': cone, 'artifact_manifests': manifests,
                'eph_files': [str(p) for p in eph_paths], 'gaia_catfile': str(gaia_path),
                'obj_total': len(eph_paths),
                'local_inputs': {str(p): sha256(p) for p in
                    ([*eph_paths] if request.eph_source == 'inputs' else []) +
                    ([gaia_path] if request.gaia_source == 'inputs' else [])}}
    with manifest_path.open('x', encoding='utf-8') as stream:
        json.dump(manifest, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    progress(f'参考数据就绪：{len(eph_paths)} 份历表、1 份 Gaia 星表。')
    return PreparedReferences(tuple(eph_paths), gaia_path, manifest_path)
