"""Immutable artifacts: request hashes, checked manifests, atomic publication."""

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import tempfile

from .models import ReferenceError, check_cancel

FORMAT_VERSION = 1


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def request_key(request):
    raw = json.dumps({"format_version": FORMAT_VERSION, **request}, sort_keys=True,
                     ensure_ascii=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def _load(folder, request):
    try:
        manifest = json.loads((folder / 'manifest.json').read_text(encoding='utf-8'))
        if manifest['request'] != request or manifest['format_version'] != FORMAT_VERSION:
            raise ValueError('request/version mismatch')
        for name, expected in manifest['files'].items():
            path = (folder / name).resolve()
            if not path.is_relative_to(folder.resolve()) or sha256(path) != expected:
                raise ValueError('artifact checksum mismatch')
        artifact = folder / manifest['artifact']
        if manifest['artifact'] not in manifest['files']:
            raise ValueError('untracked artifact')
        return artifact, manifest
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise ReferenceError(f"下载缓存校验失败，未覆盖该目录：{folder}。请选择新的缓存目录后重试。") from exc


def obtain(root, kind, request, build, progress, cancel=None):
    parent = Path(root) / kind
    check_cancel(cancel)
    folder = parent / request_key(request)
    if folder.exists():
        artifact, manifest = _load(folder, request)
        progress(f"复用已校验缓存：{artifact.name}")
        return artifact, folder / 'manifest.json', manifest
    parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix='.preparing-', dir=parent))
    try:
        artifact_name, metadata = build(temporary)
        check_cancel(cancel)
        if not (temporary / artifact_name).is_file():
            raise ReferenceError('准备过程未生成预期文件。')
        manifest = {'format_version': FORMAT_VERSION, 'request': request,
                    'created_at': datetime.now(timezone.utc).isoformat(),
                    'artifact': artifact_name, 'metadata': metadata,
                    'files': {str(p.relative_to(temporary)): sha256(p)
                              for p in temporary.rglob('*') if p.is_file()}}
        (temporary / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        try:
            temporary.rename(folder)
        except OSError:
            if not folder.exists():
                raise
            # A concurrent preparation may have completed the same request.
            _load(folder, request)
        artifact, manifest = _load(folder, request)
        return artifact, folder / 'manifest.json', manifest
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
