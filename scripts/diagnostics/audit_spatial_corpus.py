"""Dev-only аудит реальных PDF для SpatialMarkerRecovery.

Запуск на сервере:
  PYTHONPATH=src:. python scripts/diagnostics/audit_spatial_corpus.py
  PYTHONPATH=src:. python scripts/diagnostics/audit_spatial_corpus.py --audit SHA_PREFIX

Без --audit выполняется только инвентаризация. Диагностика не меняет PDF,
БД или артефакты приложения. Приватные отчёты записываются в /tmp.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import re
from pathlib import Path

import fitz

ROOT = Path('/srv/steloom-dev/docs')
OUT = Path('/tmp/steloom_b75_spatial_audit')
_SAFE_MARKER = re.compile(r'[0-9IVXLCDMivxlcdm.()§\-\s]{1,24}\Z')


def _sha_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _marker(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if _SAFE_MARKER.fullmatch(text):
        return text
    return 'sha256:' + hashlib.sha256(text.encode('utf-8')).hexdigest()[:16]


def _atom(atom: object) -> dict:
    meta = getattr(atom, 'metadata', None) or {}
    text = str(getattr(atom, 'text', '') or '')
    return {
        'element_id': getattr(atom, 'element_id', None),
        'page': getattr(atom, 'page', None),
        'bbox': getattr(atom, 'bbox', None),
        'label': getattr(atom, 'label', None),
        'marker': _marker(getattr(atom, 'marker', None)),
        'marker_source': meta.get('marker_source'),
        'recovery_confidence': meta.get('recovery_confidence'),
        'recovery_y_delta': meta.get('recovery_y_delta'),
        'text_sha256': hashlib.sha256(text.encode('utf-8')).hexdigest()[:16],
    }


def _write_private(path: Path, data: dict) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    fd = os.open(path, flags, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2)


def _inventory(path: Path) -> dict:
    sha = _sha_file(path)
    with fitz.open(path) as doc:
        pages = len(doc)
        no_text = sum(not page.get_text('text').strip() for page in doc)
    return {
        'sha256': sha,
        'sha_prefix': sha[:12],
        'pages': pages,
        'pages_without_text_layer': no_text,
        'size_bytes': path.stat().st_size,
    }


def _audit(path: Path, item: dict) -> dict:
    from services.document_layout.docling_extractor import DoclingExtractor
    from services.document_layout.spatial_marker_recovery import (
        SpatialMarkerRecovery,
        SpatialMatcher,
    )

    state: dict = {'proposed_matches': [], 'orphan_markers_count': None}
    original_recover = SpatialMarkerRecovery.recover.__func__
    original_match = SpatialMatcher.match

    def traced_match(self, atoms, orphan_markers, document_id):
        state['orphan_markers_count'] = len(orphan_markers)
        proposed = original_match(self, atoms, orphan_markers, document_id)
        state['proposed_matches'] = [
            {
                'atom_id': match.atom.element_id,
                'atom_page': match.atom.page,
                'atom_bbox': match.atom.bbox,
                'marker': _marker(match.marker.text),
                'marker_bbox': match.marker.bbox,
                'y_delta': float(match.y_delta),
                'x_gap': float(match.x_gap),
                'confidence': float(match.confidence),
                'column_match': bool(match.column_match),
            }
            for match in proposed
        ]
        return proposed

    def traced_recover(cls, atoms, pdf_bytes, document_id):
        before = {atom.element_id: _atom(atom) for atom in atoms}
        result = original_recover(cls, atoms, pdf_bytes, document_id)
        after = {atom.element_id: _atom(atom) for atom in result[0]}
        changes = [
            {'before': before[atom_id], 'after': record}
            for atom_id, record in after.items()
            if atom_id in before and (
                before[atom_id]['marker'] != record['marker']
                or before[atom_id]['text_sha256'] != record['text_sha256']
            )
        ]
        state['pre_atoms'] = len(before)
        state['pre_marked'] = sum(value['marker'] is not None for value in before.values())
        state['post_atoms'] = len(after)
        state['newly_spatial_recovered'] = changes
        return result

    try:
        SpatialMatcher.match = traced_match
        SpatialMarkerRecovery.recover = classmethod(traced_recover)
        pdf_bytes = path.read_bytes()
        extractor = DoclingExtractor()
        extractor.extract(pdf_bytes, 'audit-' + item['sha_prefix'], item['sha256'])
    finally:
        SpatialMatcher.match = original_match
        SpatialMarkerRecovery.recover = classmethod(original_recover)

    return {
        'sha256': item['sha256'],
        'pages': item['pages'],
        'matcher_input_orphan_count': state['orphan_markers_count'],
        'matcher_proposed_pairs': state['proposed_matches'],
        'pre_atoms': state.get('pre_atoms'),
        'pre_marked': state.get('pre_marked'),
        'post_atoms': state.get('post_atoms'),
        'newly_spatial_recovered': state.get('newly_spatial_recovered', []),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--audit', metavar='SHA_PREFIX', help='Обработать один PDF по SHA-префиксу из инвентаризации')
    args = parser.parse_args()
    if not ROOT.is_dir():
        parser.error(f'Нет каталога: {ROOT}')

    paths = sorted(path for path in ROOT.rglob('*') if path.is_file() and path.suffix.lower() == '.pdf')
    inventory = []
    for path in paths:
        try:
            item = _inventory(path)
            inventory.append((path, item))
            print(
                f"{item['sha_prefix']} pages={item['pages']} "
                f"no_text={item['pages_without_text_layer']} "
                f"bytes={item['size_bytes']}"
            )
        except Exception as exc:
            print(f'INVENTORY_ERROR {type(exc).__name__} (путь не выводится)')
    print(f'PDF files: {len(inventory)}; unique SHA: {len({item["sha256"] for _, item in inventory})}')

    if not args.audit:
        return
    selected = [(path, item) for path, item in inventory if item['sha256'].startswith(args.audit.lower())]
    unique = {item['sha256'] for _, item in selected}
    if len(unique) != 1:
        parser.error('SHA-префикс должен однозначно указывать на один PDF')
    path, item = selected[0]
    OUT.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(OUT, 0o700)
    report = _audit(path, item)
    output = OUT / f"pairs_{item['sha_prefix']}.json"
    _write_private(output, report)
    print(
        f"AUDITED {item['sha_prefix']} "
        f"proposed={len(report['matcher_proposed_pairs'])} "
        f"changed={len(report['newly_spatial_recovered'])} "
        f"report={output}"
    )


if __name__ == '__main__':
    main()

    