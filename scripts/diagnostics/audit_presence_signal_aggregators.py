#!/usr/bin/env python3
"""
Аудит presence_signal-агрегаторов в playbooks/global_checks/**/*.yaml.

Проверки:
  1. CRITICAL — в блоке "- "present" — ..." (Шаг 0) негативные значения
     (no / none / absent / not_*) используются как триггеры статуса present.
  2. WARNING — отсутствует safeguard-фраза в <context_rules>, но ТОЛЬКО
     если step0_found=True (в check'ах без формального present/missing шага
     safeguard не требуется).
  3. WARNING — в <edge_cases> блок «Нет релевантных фрагментов» использует
     unclear для полей с натуральным отрицательным значением. Игнорируется
     для полей-оценок (_consistent / _quality / _assessment /
     _completeness / _clarity / _status), у которых unclear корректен.

Использование:
    cd /srv/steloom-dev
    source .venv/bin/activate
    export PYTHONPATH=src:.

    python scripts/diagnostics/audit_presence_signal_aggregators.py
    python scripts/diagnostics/audit_presence_signal_aggregators.py --json
    python scripts/diagnostics/audit_presence_signal_aggregators.py --output /tmp/audit.md
    python scripts/diagnostics/audit_presence_signal_aggregators.py --verbose
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML не установлен. source .venv/bin/activate", file=sys.stderr)
    sys.exit(2)


ROOT = Path("playbooks/global_checks")

NEGATIVE_VALUES_EN = {
    "no", "none", "absent", "not_applicable", "not_addressed",
    "not_mentioned", "not_required", "not_specified", "never", "false",
    "n/a",
}
NEGATIVE_VALUES_RU = {
    "не применимо", "не предусмотрено", "не установлен", "не установлено",
    "не выявлено", "не указано", "не определено", "не удалось определить",
    "нет",
}

RF3_MARKERS = ("RF3", "прямой цитатой", "с прямой цитатой")
SAFEGUARD_PHRASE = 'Не использовать "unclear" при полном отсутствии'

# Поля-оценки: у них "unclear" в missing-edge-case корректен.
EVALUATIVE_FIELD_SUFFIXES = (
    "_consistent", "_quality", "_assessment", "_completeness",
    "_clarity", "_status",
)

STEP0_RE = re.compile(
    r"Шаг\s+0\s*—[^\n]*\n(.*?)(?=\n\s*Шаг\s+\d+\s*—|</\w+>)",
    re.DOTALL,
)

PRESENT_BULLET_RE = re.compile(r'-\s*"present"\s*—', re.IGNORECASE)
MISSING_BULLET_RE = re.compile(r'-\s*"missing"\s*—', re.IGNORECASE)
UNCLEAR_BULLET_RE = re.compile(r'-\s*"unclear"\s*—', re.IGNORECASE)

VAL_BRACE_RE = re.compile(r"[∈=]\s*\{([^}]+)\}")
VAL_EQ_RE = re.compile(r'=\s*"([^"]+)"')
VAL_BRACKET_RE = re.compile(r"\[([^\]]+)\]")

BULLET_RE = re.compile(r"^\s*[\*\-+]\s")


@dataclass
class AggregatorHit:
    line_no_in_step: int
    line_text: str
    offending_values: list[str]
    is_rf3: bool


@dataclass
class CheckReport:
    file: str
    check_id: str | None = None
    presence_signal_field: str | None = None
    present_values: list[str] = field(default_factory=list)
    missing_values: list[str] = field(default_factory=list)
    unclear_values: list[str] = field(default_factory=list)

    step0_found: bool = False
    step0_has_present_bullet: bool = False
    step0_negative_triggers: list[AggregatorHit] = field(default_factory=list)

    has_safeguard_in_context_rules: bool = False

    edge_case_missing_block_found: bool = False
    edge_case_wrong_unclear: list[str] = field(default_factory=list)

    @property
    def severity(self) -> str:
        if self.step0_negative_triggers:
            return "CRITICAL"
        if self.edge_case_wrong_unclear:
            return "WARNING"
        # Safeguard WARNING — только если есть формальный present-блок.
        if self.step0_has_present_bullet and not self.has_safeguard_in_context_rules:
            return "WARNING"
        return "OK"


def iter_yaml_files(root: Path) -> list[Path]:
    if not root.exists():
        print(f"ERROR: путь не существует: {root}", file=sys.stderr)
        return []
    return sorted(root.rglob("*.yaml"))


def load_yaml(path: Path) -> dict[str, Any] | None:
    try:
        with path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return data if isinstance(data, dict) else None
    except Exception as exc:
        print(f"WARN: не удалось распарсить {path}: {exc}", file=sys.stderr)
        return None


def extract_step0(prompt: str) -> str | None:
    m = STEP0_RE.search(prompt)
    return m.group(1) if m else None


def _split_and_strip(blob: str) -> list[str]:
    parts = re.split(r"[,\s]+", blob)
    return [p.strip().strip('"\'').strip() for p in parts if p.strip()]


def extract_values_from_line(line: str) -> list[str]:
    values: list[str] = []
    for m in VAL_BRACE_RE.finditer(line):
        values.extend(_split_and_strip(m.group(1)))
    for m in VAL_BRACKET_RE.finditer(line):
        values.extend(_split_and_strip(m.group(1)))
    for m in VAL_EQ_RE.finditer(line):
        values.append(m.group(1).strip().strip('"\''))
    return [v for v in values if v]


def is_negative(value: str) -> bool:
    v = value.strip().lower()
    return v in NEGATIVE_VALUES_EN or v in NEGATIVE_VALUES_RU


def line_is_rf3(line: str, lookahead: list[str]) -> bool:
    haystack = (line + " " + " ".join(lookahead)).lower()
    return any(marker.lower() in haystack for marker in RF3_MARKERS)


def is_evaluative_field(name: str) -> bool:
    return any(name.endswith(suffix) for suffix in EVALUATIVE_FIELD_SUFFIXES)


def analyze_step0(step0: str) -> list[AggregatorHit]:
    lines = step0.splitlines()

    present_start: int | None = None
    present_end: int | None = None

    for i, line in enumerate(lines):
        if present_start is None and PRESENT_BULLET_RE.search(line):
            present_start = i
            continue
        if present_start is not None and present_end is None:
            if MISSING_BULLET_RE.search(line) or UNCLEAR_BULLET_RE.search(line):
                present_end = i
                break

    if present_start is None:
        return []
    if present_end is None:
        present_end = len(lines)

    hits: list[AggregatorHit] = []
    present_block = lines[present_start:present_end]

    for rel_i, line in enumerate(present_block):
        if not BULLET_RE.match(line):
            continue
        values = extract_values_from_line(line)
        if not values:
            continue
        negatives = [v for v in values if is_negative(v)]
        if not negatives:
            continue
        lookahead = present_block[rel_i + 1:rel_i + 3]
        rf3 = line_is_rf3(line, lookahead)
        hits.append(AggregatorHit(
            line_no_in_step=present_start + rel_i + 1,
            line_text=line.rstrip(),
            offending_values=negatives,
            is_rf3=rf3,
        ))
    return hits


def has_safeguard(prompt: str) -> bool:
    return SAFEGUARD_PHRASE in prompt


MISSING_BLOCK_HEAD_RE = re.compile(
    r"-\s*Нет релевантных фрагментов[^\n]*\n((?:\s+\*[^\n]*\n)+)",
    re.IGNORECASE,
)
EDGE_FIELD_RE = re.compile(r'\*\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*"([^"]+)"')


def analyze_edge_cases(
    prompt: str,
    fields_allowed: dict[str, set[str]],
) -> tuple[bool, list[str]]:
    m = MISSING_BLOCK_HEAD_RE.search(prompt)
    if not m:
        return False, []

    block = m.group(1)
    wrong: list[str] = []
    for fm in EDGE_FIELD_RE.finditer(block):
        name, value = fm.group(1), fm.group(2).strip()
        if is_evaluative_field(name):
            continue  # поля-оценки: unclear корректен
        allowed = fields_allowed.get(name)
        if not allowed:
            continue
        if value != "unclear":
            continue
        if any(is_negative(a) for a in allowed):
            wrong.append(name)
    return True, wrong


def analyze_check(path: Path, data: dict[str, Any]) -> CheckReport:
    rep = CheckReport(file=str(path))
    rep.check_id = data.get("id")

    extraction = data.get("extraction") or {}
    ps = extraction.get("presence_signal") or {}
    rep.presence_signal_field = ps.get("field")
    rep.present_values = list(ps.get("present_values") or [])
    rep.missing_values = list(ps.get("missing_values") or [])
    rep.unclear_values = list(ps.get("unclear_values") or [])

    prompt = extraction.get("llm_prompt_extraction") or ""

    step0 = extract_step0(prompt)
    if step0:
        rep.step0_found = True
        rep.step0_has_present_bullet = bool(PRESENT_BULLET_RE.search(step0))
        hits = analyze_step0(step0)
        rep.step0_negative_triggers = [h for h in hits if not h.is_rf3]

    rep.has_safeguard_in_context_rules = has_safeguard(prompt)

    fields = extraction.get("fields") or []
    fields_allowed: dict[str, set[str]] = {}
    for f in fields:
        if not isinstance(f, dict):
            continue
        name = f.get("name")
        allowed = f.get("allowed_values")
        if name and isinstance(allowed, list):
            fields_allowed[name] = {str(v) for v in allowed}

    found_block, wrong = analyze_edge_cases(prompt, fields_allowed)
    rep.edge_case_missing_block_found = found_block
    rep.edge_case_wrong_unclear = wrong

    return rep


def render_markdown(reports: list[CheckReport]) -> str:
    lines: list[str] = []
    lines.append("# Аудит presence_signal агрегаторов")
    lines.append("")
    lines.append(f"Проверено checks: **{len(reports)}**")
    counts = {"CRITICAL": 0, "WARNING": 0, "OK": 0}
    for r in reports:
        counts[r.severity] += 1
    lines.append(
        f"CRITICAL: **{counts['CRITICAL']}** · "
        f"WARNING: **{counts['WARNING']}** · "
        f"OK: **{counts['OK']}**"
    )
    lines.append("")

    lines.append("## Сводка")
    lines.append("")
    lines.append("| Severity | Check | File | Step 0 (present-block neg) | Safeguard | Edge-case unclear |")
    lines.append("|---|---|---|---|---|---|")
    order = {"CRITICAL": 0, "WARNING": 1, "OK": 2}
    for r in sorted(reports, key=lambda x: (order[x.severity], str(x.file))):
        step0_cell = (
            "—" if not r.step0_found
            else (f"**{len(r.step0_negative_triggers)}**" if r.step0_negative_triggers else "ok")
        )
        if not r.step0_has_present_bullet:
            safe_cell = "n/a"
        elif r.has_safeguard_in_context_rules:
            safe_cell = "✓"
        else:
            safe_cell = "**missing**"
        edge_cell = (
            "—" if not r.edge_case_missing_block_found
            else ("**" + ", ".join(r.edge_case_wrong_unclear) + "**" if r.edge_case_wrong_unclear else "ok")
        )
        lines.append(
            f"| {r.severity} | `{r.check_id or '—'}` | `{r.file}` | {step0_cell} | {safe_cell} | {edge_cell} |"
        )
    lines.append("")

    crit = [r for r in reports if r.severity == "CRITICAL"]
    if crit:
        lines.append("## CRITICAL — present-блок использует негативные значения как триггеры")
        lines.append("")
        for r in crit:
            lines.append(f"### `{r.check_id}`")
            lines.append(f"Файл: `{r.file}`")
            lines.append("")
            lines.append("| Строка | Вхождение | Offending |")
            lines.append("|---|---|---|")
            for h in r.step0_negative_triggers:
                snippet = h.line_text.strip()
                if len(snippet) > 100:
                    snippet = snippet[:97] + "…"
                snippet = snippet.replace("|", "\\|")
                lines.append(f"| {h.line_no_in_step} | `{snippet}` | {', '.join(h.offending_values)} |")
            lines.append("")

    warn = [r for r in reports if r.severity == "WARNING"]
    if warn:
        lines.append("## WARNING")
        lines.append("")
        for r in warn:
            lines.append(f"### `{r.check_id}`")
            lines.append(f"Файл: `{r.file}`")
            if r.step0_found and not r.has_safeguard_in_context_rules:
                lines.append(f"- Нет safeguard-фразы в `<context_rules>`: `{SAFEGUARD_PHRASE}`")
            if r.edge_case_wrong_unclear:
                lines.append(
                    f"- В `<edge_cases>` блок «Нет релевантных фрагментов» использует `unclear` "
                    f"для полей с натуральным отрицательным значением: "
                    f"{', '.join('`'+f+'`' for f in r.edge_case_wrong_unclear)}"
                )
            lines.append("")

    ok = [r for r in reports if r.severity == "OK"]
    if ok:
        lines.append("## OK")
        lines.append("")
        for r in ok:
            lines.append(f"- `{r.check_id}` — `{r.file}`")
        lines.append("")

    return "\n".join(lines)


def render_json(reports: list[CheckReport]) -> str:
    payload = []
    for r in reports:
        d = asdict(r)
        d["severity"] = r.severity
        payload.append(d)
    return json.dumps(payload, ensure_ascii=False, indent=2)


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--root", default=str(ROOT))
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--output", type=Path)
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    root = Path(args.root)
    files = iter_yaml_files(root)
    if not files:
        print(f"Не найдено YAML-файлов в {root}", file=sys.stderr)
        return 1

    if args.verbose:
        print(f"Найдено {len(files)} YAML-файлов", file=sys.stderr)

    reports: list[CheckReport] = []
    for i, path in enumerate(files, 1):
        data = load_yaml(path)
        if data is None:
            continue
        extraction = data.get("extraction") or {}
        if "presence_signal" not in extraction:
            if args.verbose:
                print(f"[{i}/{len(files)}] skip (no presence_signal): {path}", file=sys.stderr)
            continue
        rep = analyze_check(path, data)
        reports.append(rep)
        if args.verbose:
            print(f"[{i}/{len(files)}] {rep.severity:8} {rep.check_id}", file=sys.stderr)

    if not reports:
        print("Не найдено checks с presence_signal", file=sys.stderr)
        return 1

    output = render_json(reports) if args.json else render_markdown(reports)

    if args.output:
        args.output.write_text(output, encoding="utf-8")
        print(f"Отчёт сохранён: {args.output}", file=sys.stderr)
    else:
        print(output)

    has_critical = any(r.severity == "CRITICAL" for r in reports)
    return 1 if has_critical else 0


if __name__ == "__main__":
    sys.exit(main())