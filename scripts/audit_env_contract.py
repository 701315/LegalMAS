#!/usr/bin/env python3
"""
Audit dev/demo .env contract.

Проверяет, что параметры конфигурации между dev и demo контурами
соответствуют заданной политике:
- одни параметры ДОЛЖНЫ совпадать (алгоритмы, пороги, модели);
- другие параметры ДОЛЖНЫ различаться (порты, БД, URLs);
- третьи пока не классифицированы и выводятся для ручной проверки.

Использование:
    /srv/steloom-dev/scripts/audit_env_contract.py
    /srv/steloom-dev/scripts/audit_env_contract.py --strict-uncategorized
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


# ─────────────────────────────────────────────────────────────────────────────
# POLICY: backend parameters that MUST have identical values in dev and demo
# ─────────────────────────────────────────────────────────────────────────────

BACKEND_MUST_MATCH_EXACT = {
    "CHECK_RUNNER_MODE",
    "DISABLE_DOWNSTREAM_TASKS",
    "EMBEDDINGS_MODEL",
    "CLASSIFIER_EMBEDDINGS_MODEL",
    "RUNNER_EMBEDDINGS_MODEL",
    "LLM_EXTRACTION_MAX_TOKENS",
    "LLM_CONTEXT_LIMIT",
    "LLM_SAFETY_MARGIN_TOKENS",
    "LLM_MIN_OUTPUT_TOKENS",
    "LLM_TIMEOUT_SECONDS",
    "LLM_PROVIDER",
    "LLM_OLLAMA_MODEL",
    "EMBEDDING_CACHE_ENABLED",
    "EMBEDDING_CACHE_TTL_SECONDS",
    "EMBEDDING_CACHE_MAX_ITEMS",
    "DOCX_CONVERTER_TIMEOUT_SECONDS",
    "SEMANTIC_ENRICHMENT_MAX_INFLIGHT_LLM_CALLS",
}

BACKEND_MUST_MATCH_PREFIXES = (
    "CLASSIFICATION_",
    "CLASSIFIER_",
    "SEMANTIC_",
    "STRUCTURE_",
    "PII_",
    "RUNNER_",
    "CIRCUIT_",
)

# ─────────────────────────────────────────────────────────────────────────────
# POLICY: backend parameters that SHOULD have different values per contour
# ─────────────────────────────────────────────────────────────────────────────

BACKEND_SHOULD_DIFFER_EXACT = {
    "ENVIRONMENT",
    "DATABASE_URL",
    "REDIS_URL",
    "MINIO_ENDPOINT",
    "MINIO_PUBLIC_ENDPOINT",
    "MINIO_BUCKET",
    "DOCX_CONVERTER_URL",
    "CORS_ALLOW_ORIGINS",
    "PROMPTS_DIR",
    "CLASSIFICATION_REGISTRY_PATH",
    "LLM_EXTRACTION_JSON_GRAMMAR_PATH",
    "OTEL_SERVICE_NAME",
    "PII_ENCRYPTION_KEY",
    "JWT_SECRET_KEY",
}

BACKEND_SHOULD_DIFFER_PREFIXES = (
    "PLAYBOOK_",
)

# ─────────────────────────────────────────────────────────────────────────────
# POLICY: keys where both-empty is acceptable (not an error)
# ─────────────────────────────────────────────────────────────────────────────

BACKEND_ALLOW_BOTH_EMPTY = {
    "PLAYBOOK_DEFAULT_PATH",
}

# ─────────────────────────────────────────────────────────────────────────────
# POLICY: keys where path differs only by contour prefix — this is expected
# ─────────────────────────────────────────────────────────────────────────────

BACKEND_CONTOUR_PATH_KEYS = {
    "CLASSIFICATION_REGISTRY_PATH",
    "LLM_EXTRACTION_JSON_GRAMMAR_PATH",
    "PROMPTS_DIR",
}

DEV_CONTOUR_PREFIX = "/srv/steloom-dev"
DEMO_CONTOUR_PREFIX = "/srv/steloom-demo"

# ─────────────────────────────────────────────────────────────────────────────
# POLICY: parameters that SHOULD match but are allowed to differ between
# contours if explicitly documented (e.g. LLM_OLLAMA_BASE_URL when demo
# uses a different GPU server). Listed here so they don't show as
# "uncategorized" but also don't trigger false-positive errors.
# ─────────────────────────────────────────────────────────────────────────────

BACKEND_SHOULD_MATCH_BUT_CONTOUR_SPECIFIC = {
    "LLM_OLLAMA_BASE_URL",
    "LOCAL_LLM_ENDPOINT",
}

# ─────────────────────────────────────────────────────────────────────────────
# POLICY: keys that are inherently contour-specific and should not trigger
# any warnings even if identical or different
# ─────────────────────────────────────────────────────────────────────────────

BACKEND_KNOWN_CONTOUR_SPECIFIC = {
    "LOG_LEVEL",
    "LOG_FORMAT",
    "LOG_TO_STDOUT",
    "LOG_TO_FILE",
    "MINIO_ACCESS_KEY",
    "MINIO_SECRET_KEY",
    "MINIO_SECURE",
    "CORS_ALLOW_CREDENTIALS",
    "CORS_ALLOW_METHODS",
    "CORS_ALLOW_HEADERS",
    "JWT_ALGORITHM",
    "JWT_ACCESS_TOKEN_EXPIRE_MINUTES",
    "OTEL_ENABLED",
    "OTEL_EXPORTER_OTLP_ENDPOINT",
    "OTEL_TRACES_SAMPLER",
    "OTEL_TRACES_SAMPLER_ARG",
    "OTEL_NOISY_TASKS",
}

# ─────────────────────────────────────────────────────────────────────────────
# POLICY: frontend env
# ─────────────────────────────────────────────────────────────────────────────

FRONTEND_SHOULD_DIFFER_EXACT = {
    "VITE_API_URL",
    "VITE_API_DOCS_URL",
}

# ─────────────────────────────────────────────────────────────────────────────
# Secret detection
# ─────────────────────────────────────────────────────────────────────────────

SECRET_HINTS = (
    "SECRET",
    "TOKEN",
    "PASSWORD",
    "ENCRYPTION_KEY",
    "ACCESS_KEY",
    "PRIVATE_KEY",
    "API_KEY",
)


def parse_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    result: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = normalize_env_value(value.strip())
        result[key] = value
    return result


def normalize_env_value(value: str) -> str:
    if not value:
        return ""
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    value = re.sub(r"\s+#.*$", "", value).rstrip()
    return value


def is_contour_path_equivalent(key: str, dev_val: str, demo_val: str) -> bool:
    if key not in BACKEND_CONTOUR_PATH_KEYS:
        return False
    dev_normalized = dev_val.replace(DEV_CONTOUR_PREFIX, "__CONTOUR__")
    demo_normalized = demo_val.replace(DEMO_CONTOUR_PREFIX, "__CONTOUR__")
    return dev_normalized == demo_normalized


def classify_backend_key(key: str) -> str:
    if key in BACKEND_ALLOW_BOTH_EMPTY:
        return "allow_both_empty"
    if key in BACKEND_KNOWN_CONTOUR_SPECIFIC:
        return "contour_specific"
    if key in BACKEND_SHOULD_MATCH_BUT_CONTOUR_SPECIFIC:
        return "soft_match"
    if key in BACKEND_MUST_MATCH_EXACT:
        return "must_match"
    if any(key.startswith(p) for p in BACKEND_MUST_MATCH_PREFIXES):
        if key in BACKEND_SHOULD_DIFFER_EXACT:
            return "should_differ"
        if key in BACKEND_CONTOUR_PATH_KEYS:
            return "contour_path"
        return "must_match"
    if key in BACKEND_SHOULD_DIFFER_EXACT:
        return "should_differ"
    if any(key.startswith(p) for p in BACKEND_SHOULD_DIFFER_PREFIXES):
        return "should_differ"
    return "uncategorized"


def classify_frontend_key(key: str) -> str:
    if key in FRONTEND_SHOULD_DIFFER_EXACT:
        return "should_differ"
    return "uncategorized"


def is_secret_key(key: str) -> bool:
    return any(hint in key.upper() for hint in SECRET_HINTS)


def render_value(key: str, value: str) -> str:
    if is_secret_key(key):
        return "***MASKED***"
    if len(value) > 200:
        return value[:200] + "...<truncated>"
    return value


def compare_group(
    *,
    title: str,
    dev_values: dict[str, str],
    demo_values: dict[str, str],
    classifier,
) -> tuple[int, int]:
    print()
    print("=" * 80)
    print(title)
    print("=" * 80)

    all_keys = sorted(set(dev_values) | set(demo_values))

    errors = 0

    must_match_ok: list[str] = []
    must_match_bad: list[str] = []
    should_differ_ok: list[str] = []
    should_differ_bad: list[str] = []
    contour_path_ok: list[str] = []
    contour_specific_ok: list[str] = []
    soft_match_ok: list[str] = []
    soft_match_warn: list[str] = []
    allow_empty_ok: list[str] = []
    uncategorized: list[str] = []

    for key in all_keys:
        category = classifier(key)
        dev_present = key in dev_values
        demo_present = key in demo_values
        dev_val = dev_values.get(key, "")
        demo_val = demo_values.get(key, "")

        if category == "allow_both_empty":
            if dev_val == "" and demo_val == "":
                allow_empty_ok.append(f"{key}: both empty (allowed)")
            elif dev_val != demo_val:
                should_differ_ok.append(
                    f"{key}: DEV={render_value(key, dev_val)} | DEMO={render_value(key, demo_val)}"
                )
            else:
                should_differ_ok.append(f"{key}: identical non-empty (acceptable)")
            continue

        if category == "contour_path":
            if is_contour_path_equivalent(key, dev_val, demo_val):
                contour_path_ok.append(
                    f"{key}: paths differ only by contour prefix (OK)"
                )
            else:
                must_match_bad.append(
                    f"{key}: DEV={render_value(key, dev_val)} | DEMO={render_value(key, demo_val)}"
                )
                errors += 1
            continue

        if category == "contour_specific":
            contour_specific_ok.append(key)
            continue

        if category == "soft_match":
            if dev_val == demo_val:
                soft_match_ok.append(key)
            else:
                soft_match_warn.append(
                    f"{key}: DEV={render_value(key, dev_val)} | DEMO={render_value(key, demo_val)} (review manually)"
                )
            continue

        if category == "must_match":
            if not dev_present or not demo_present:
                must_match_bad.append(
                    f"{key}: missing in {'dev' if not dev_present else 'demo'}"
                )
                errors += 1
            elif dev_val != demo_val:
                if is_contour_path_equivalent(key, dev_val, demo_val):
                    contour_path_ok.append(
                        f"{key}: paths differ only by contour prefix (OK)"
                    )
                else:
                    must_match_bad.append(
                        f"{key}: DEV={render_value(key, dev_val)} | DEMO={render_value(key, demo_val)}"
                    )
                    errors += 1
            else:
                must_match_ok.append(key)

        elif category == "should_differ":
            if not dev_present or not demo_present:
                should_differ_bad.append(
                    f"{key}: missing in {'dev' if not dev_present else 'demo'}"
                )
                errors += 1
            elif dev_val == demo_val:
                should_differ_bad.append(
                    f"{key}: values are unexpectedly identical ({render_value(key, dev_val)})"
                )
                errors += 1
            else:
                should_differ_ok.append(
                    f"{key}: DEV={render_value(key, dev_val)} | DEMO={render_value(key, demo_val)}"
                )

        else:
            uncategorized.append(key)

    # ── Print results ──
    def _section(label: str, items: list[str], prefix: str = "  + ") -> None:
        print()
        print(f"[{label}]:")
        if items:
            for item in items:
                print(f"{prefix}{item}")
        else:
            print("  (none)")

    _section("MUST MATCH — OK", must_match_ok)
    _section("MUST MATCH — ERRORS", must_match_bad, prefix="  ! ")
    _section("CONTOUR PATHS — OK", contour_path_ok)
    _section("SHOULD DIFFER — OK", should_differ_ok)
    _section("SHOULD DIFFER — ERRORS", should_differ_bad, prefix="  ! ")
    _section("ALLOW BOTH EMPTY — OK", allow_empty_ok)
    _section("CONTOUR-SPECIFIC — OK (skipped)", contour_specific_ok)
    _section("SOFT MATCH — OK", soft_match_ok)
    _section("SOFT MATCH — WARNINGS (review manually)", soft_match_warn, prefix="  ~ ")
    _section("UNCATEGORIZED KEYS", uncategorized, prefix="  ? ")

    print()
    print(f"Summary for {title}: errors={errors}, uncategorized={len(uncategorized)}")

    return errors, len(uncategorized)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audit dev/demo .env contract."
    )
    parser.add_argument(
        "--dev-backend", default="/srv/steloom-dev/.env",
    )
    parser.add_argument(
        "--demo-backend", default="/srv/steloom-demo/.env",
    )
    parser.add_argument(
        "--dev-frontend", default="/srv/steloom-dev/frontend/.env.development",
    )
    parser.add_argument(
        "--demo-frontend", default="/srv/steloom-demo/frontend/.env.production",
    )
    parser.add_argument(
        "--strict-uncategorized", action="store_true",
        help="Return non-zero exit code if uncategorized keys exist.",
    )
    args = parser.parse_args()

    total_errors = 0
    total_uncategorized = 0

    dev_be = parse_env_file(Path(args.dev_backend))
    demo_be = parse_env_file(Path(args.demo_backend))

    e, u = compare_group(
        title="BACKEND .env CONTRACT",
        dev_values=dev_be,
        demo_values=demo_be,
        classifier=classify_backend_key,
    )
    total_errors += e
    total_uncategorized += u

    dev_fe = Path(args.dev_frontend)
    demo_fe = Path(args.demo_frontend)

    if dev_fe.exists() and demo_fe.exists():
        e, u = compare_group(
            title="FRONTEND ENV CONTRACT",
            dev_values=parse_env_file(dev_fe),
            demo_values=parse_env_file(demo_fe),
            classifier=classify_frontend_key,
        )
        total_errors += e
        total_uncategorized += u
    else:
        print()
        print("=" * 80)
        print("FRONTEND ENV CONTRACT — SKIPPED")
        print("=" * 80)
        print(f"  dev : {dev_fe} {'exists' if dev_fe.exists() else 'MISSING'}")
        print(f"  demo: {demo_fe} {'exists' if demo_fe.exists() else 'MISSING'}")

    print()
    print("=" * 80)
    print("FINAL RESULT")
    print("=" * 80)
    print(f"contract_errors={total_errors}")
    print(f"uncategorized_keys={total_uncategorized}")

    if total_errors > 0:
        print("\nACTION REQUIRED: fix errors listed above.")
        return 1
    if args.strict_uncategorized and total_uncategorized > 0:
        print("\nWARNING: uncategorized keys exist. Review and classify them.")
        return 2

    print("\nAll checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
