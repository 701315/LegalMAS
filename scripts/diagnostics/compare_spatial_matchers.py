"""Dev-only сравнение master и текущего SpatialMatcher на ОДНИХ атомах и PDF.

Перед запуском сохранить исходный модуль через git show в /tmp, см. инструкцию.
Отчёт не включает текст атомов и имена PDF. Не публиковать сырой лог Docling.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import sys
from pathlib import Path

from services.document_layout.docling_extractor import DoclingExtractor
from services.document_layout.spatial_marker_recovery import SpatialMatcher

DOCS = Path('/srv/steloom-dev/docs')
OUT = Path('/tmp/steloom_b75_spatial_audit')
BASELINE = OUT / 'spatial_marker_recovery_baseline.py'
SAFE_MARKER = re.compile(r'[0-9IVXLCDMivxlcdm.()§\-\s]{1,24}\Z')


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_marker(value: str) -> str:
    text = str(value).strip()
    if SAFE_MARKER.fullmatch(text):
        return text
    return 'sha256:' + hashlib.sha256(text.encode('utf-8')).hexdigest()[:16]


def _load_baseline(path: Path):
    spec = importlib.util.spec_from_file_location(
        'services.document_layout._b75_spatial_baseline', path
    )
    if spec is None or spec.loader is None:
        raise RuntimeError('Baseline module cannot be loaded')
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _pair(match) -> dict:
    atom = match.atom
    marker = match.marker
    return {
        'atom_id': atom.element_id,
        'page': atom.page,
        'atom_bbox': atom.bbox,
        'marker': _safe_marker(marker.text),
        'marker_bbox': marker.bbox,
        'y_delta': float(match.y_delta),
        'physical_x_gap': float(atom.bbox[0] - marker.bbox[2]),
        'score': float(match.confidence),
    }


def _write_private(path: Path, data: dict) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--sha', required=True, help='SHA-префикс из inventory')
    args = parser.parse_args()
    if not BASELINE.is_file():
        parser.error('Нет исходного модуля из git show')

    choices = [
        (path, _hash_file(path))
        for path in DOCS.rglob('*')
        if path.is_file() and path.suffix.lower() == '.pdf'
    ]
    choices = [(path, sha) for path, sha in choices if sha.startswith(args.sha.lower())]
    if len({sha for _, sha in choices}) != 1:
        parser.error('SHA-префикс должен однозначно указывать на один PDF')
    path, sha = choices[0]
    baseline_module = _load_baseline(BASELINE)
    old_matcher_type = baseline_module.SpatialMatcher
    original_match = SpatialMatcher.match
    state: dict = {'invoked': False, 'before_unmarked': None, 'marker_candidates': None,
                   'baseline_pairs': [], 'current_pairs': []}

    def compare_match(self, atoms, orphan_markers, document_id):
        state['invoked'] = True
        state['before_unmarked'] = sum(not atom.marker and bool(atom.text.strip()) for atom in atoms)
        state['marker_candidates'] = len(orphan_markers)
        baseline_pairs = old_matcher_type(self.fingerprint).match(atoms, orphan_markers, document_id)
        current_pairs = original_match(self, atoms, orphan_markers, document_id)
        state['baseline_pairs'] = [_pair(match) for match in baseline_pairs]
        state['current_pairs'] = [_pair(match) for match in current_pairs]
        return current_pairs

    try:
        SpatialMatcher.match = compare_match
        extractor = DoclingExtractor()
        extractor.extract(path.read_bytes(), 'audit-' + sha[:12], sha)
    finally:
        SpatialMatcher.match = original_match

    OUT.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(OUT, 0o700)
    output = OUT / ('compare_' + sha[:12] + '.json')
    _write_private(output, {'sha256': sha, **state})
    print(
        f"COMPARE sha={sha[:12]} invoked={state['invoked']} "
        f"unmarked={state['before_unmarked']} candidates={state['marker_candidates']} "
        f"old={len(state['baseline_pairs'])} new={len(state['current_pairs'])} "
        f"report={output}"
    )


if __name__ == '__main__':
    main()
