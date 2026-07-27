#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import json
import re
import sys
import warnings
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib  # type: ignore


warnings.filterwarnings("ignore", category=SyntaxWarning)

EXCLUDE_DIRS = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    "node_modules",
    "dist",
    "build",
    ".next",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".cache",
    "artifacts",
    "output",
    "logs",
    ".idea",
}

LOCAL_JS_PREFIXES = ("./", "../", "/", "@/", "~/")

NODE_BUILTINS = {
    "assert",
    "buffer",
    "child_process",
    "cluster",
    "console",
    "constants",
    "crypto",
    "dgram",
    "diagnostics_channel",
    "dns",
    "domain",
    "events",
    "fs",
    "http",
    "http2",
    "https",
    "inspector",
    "module",
    "net",
    "os",
    "path",
    "perf_hooks",
    "process",
    "punycode",
    "querystring",
    "readline",
    "repl",
    "stream",
    "string_decoder",
    "timers",
    "tls",
    "trace_events",
    "tty",
    "url",
    "util",
    "v8",
    "vm",
    "worker_threads",
    "zlib",
}


def normalize_package_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower().strip()


PY_PACKAGE_IMPORTS = {
    normalize_package_name("Pillow"): {"PIL"},
    normalize_package_name("python-dotenv"): {"dotenv"},
    normalize_package_name("PyYAML"): {"yaml"},
    normalize_package_name("python-docx"): {"docx"},
    normalize_package_name("PyJWT"): {"jwt"},
    normalize_package_name("python-Levenshtein"): {"Levenshtein"},
    normalize_package_name("pydantic-settings"): {"pydantic_settings"},
    normalize_package_name("sentence-transformers"): {"sentence_transformers"},
    normalize_package_name("rank-bm25"): {"rank_bm25"},
    normalize_package_name("prometheus-client"): {"prometheus_client"},
    normalize_package_name("prometheus-fastapi-instrumentator"): {
        "prometheus_fastapi_instrumentator"
    },
    normalize_package_name("python-multipart"): {"multipart"},
    normalize_package_name("llama-cpp-python"): {"llama_cpp"},
    normalize_package_name("fpdf2"): {"fpdf"},
    normalize_package_name("opentelemetry-api"): {"opentelemetry"},
    normalize_package_name("opentelemetry-sdk"): {"opentelemetry"},
    normalize_package_name("opentelemetry-semantic-conventions"): {"opentelemetry"},
    normalize_package_name("opentelemetry-exporter-otlp-proto-http"): {
        "opentelemetry.exporter.otlp.proto.http"
    },
    normalize_package_name("opentelemetry-instrumentation-fastapi"): {
        "opentelemetry.instrumentation.fastapi"
    },
    normalize_package_name("opentelemetry-instrumentation-sqlalchemy"): {
        "opentelemetry.instrumentation.sqlalchemy"
    },
    normalize_package_name("opentelemetry-instrumentation-httpx"): {
        "opentelemetry.instrumentation.httpx"
    },
    normalize_package_name("opentelemetry-instrumentation-celery"): {
        "opentelemetry.instrumentation.celery"
    },
}

PY_IMPORT_SUGGESTIONS = {
    "PIL": "Pillow",
    "dotenv": "python-dotenv",
    "yaml": "PyYAML",
    "docx": "python-docx",
    "jwt": "PyJWT",
    "Levenshtein": "python-Levenshtein",
    "pydantic_settings": "pydantic-settings",
    "sentence_transformers": "sentence-transformers",
    "rank_bm25": "rank-bm25",
    "prometheus_client": "prometheus-client",
    "prometheus_fastapi_instrumentator": "prometheus-fastapi-instrumentator",
    "multipart": "python-multipart",
    "llama_cpp": "llama-cpp-python",
    "fpdf": "fpdf2",
}

PY_CLI_TO_PACKAGE = {
    "uvicorn": "uvicorn",
    "celery": "celery",
    "alembic": "alembic",
    "pytest": "pytest",
    "ruff": "ruff",
    "mypy": "mypy",
    "pip_audit": "pip-audit",
    "pip-audit": "pip-audit",
}

JS_SCRIPT_TOOL_TO_PACKAGE = {
    "vite": "vite",
    "eslint": "eslint",
    "tsc": "typescript",
}

KNOWN_BINARIES = {
    "tesseract": "tesseract-ocr",
    "pdftocairo": "poppler-utils",
    "pdftoppm": "poppler-utils",
    "soffice": "libreoffice",
    "libreoffice": "libreoffice",
    "curl": "curl",
}

IMPLICIT_OR_INTENTIONAL_PACKAGES = {
    normalize_package_name("python-multipart"): "FastAPI file uploads often need this indirectly.",
    normalize_package_name("setuptools"): "Intentional build/runtime compatibility cap.",
}

JS_IMPORT_RE = re.compile(
    r"""(?:import\s+(?:[^'"]+?\s+from\s+)?|export\s+[^'"]+?\s+from\s+|require\(|import\()\s*['"]([^'"]+)['"]""",
    re.MULTILINE,
)


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def write_text(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def is_excluded(path: Path, root: Path) -> bool:
    try:
        rel_path = path.relative_to(root)
    except ValueError:
        rel_path = path
    return any(part in EXCLUDE_DIRS for part in rel_path.parts)


def iter_files(root: Path):
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if is_excluded(path, root):
            continue
        yield path


def rel(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except Exception:
        return str(path)


def extract_requirement_name(spec: str) -> str | None:
    s = spec.strip()
    if not s:
        return None
    if s.startswith(("-r ", "--requirement ")):
        return None
    if s.startswith(("--extra-index-url", "--index-url", "--find-links", "-f")):
        return None
    if "#egg=" in s:
        return s.split("#egg=", 1)[1].strip()
    if " @ " in s:
        return s.split(" @ ", 1)[0].strip()
    m = re.match(r"([A-Za-z0-9_.-]+)", s)
    if not m:
        return None
    return m.group(1)


def is_exactly_pinned(spec: str) -> bool:
    s = spec.strip()
    if not s or s.startswith("-"):
        return True
    return ("==" in s) or (" @ " in s)


def parse_requirements_file(
    path: Path,
    visited: set[Path],
    declared: dict[str, list[dict]],
    unpinned: list[dict],
) -> None:
    if not path.exists():
        return

    path = path.resolve()
    if path in visited:
        return
    visited.add(path)

    for lineno, raw_line in enumerate(read_text(path).splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        no_comment = line if "#egg=" in line else line.split("#", 1)[0].strip()
        if not no_comment:
            continue

        if no_comment.startswith(("-r ", "--requirement ")):
            include = no_comment.split(maxsplit=1)[1].strip()
            parse_requirements_file(path.parent / include, visited, declared, unpinned)
            continue

        name = extract_requirement_name(no_comment)
        if not name:
            continue

        pkg = normalize_package_name(name)
        declared[pkg].append(
            {
                "file": str(path),
                "line": lineno,
                "raw": no_comment,
            }
        )
        if not is_exactly_pinned(no_comment):
            unpinned.append(
                {
                    "package": name,
                    "file": str(path),
                    "line": lineno,
                    "raw": no_comment,
                }
            )


def parse_pyproject_dependencies(path: Path) -> tuple[set[str], set[str]]:
    runtime: set[str] = set()
    dev: set[str] = set()

    if not path.exists():
        return runtime, dev

    try:
        data = tomllib.loads(read_text(path))
    except Exception:
        return runtime, dev

    project = data.get("project", {}) or {}

    for dep in project.get("dependencies", []) or []:
        name = extract_requirement_name(dep)
        if name:
            runtime.add(normalize_package_name(name))

    for _group, deps in (project.get("optional-dependencies", {}) or {}).items():
        for dep in deps or []:
            name = extract_requirement_name(dep)
            if name:
                dev.add(normalize_package_name(name))

    return runtime, dev


def valid_python_dir(path: Path) -> bool:
    if not path.is_dir() or not path.name.isidentifier():
        return False
    if (path / "__init__.py").exists():
        return True
    try:
        next(path.rglob("*.py"))
        return True
    except StopIteration:
        return False


def collect_local_python_modules(root: Path) -> set[str]:
    names: set[str] = set()

    for base in [root, root / "src"]:
        if not base.exists():
            continue
        for child in base.iterdir():
            if child.name.startswith(".") or child.name in EXCLUDE_DIRS:
                continue
            if child.is_file() and child.suffix == ".py" and child.stem.isidentifier():
                names.add(child.stem)
            elif valid_python_dir(child):
                names.add(child.name)

    names.update({"tests", "src"})
    return names


def classify_python_scope(path: Path, root: Path) -> str:
    r = path.relative_to(root)
    head = r.parts[0] if r.parts else ""
    if head in {"src", "office-converter", "alembic"}:
        return "runtime"
    if head == "tests":
        return "dev"
    if head == "scripts":
        return "ops"
    return "other"


def collect_python_imports(root: Path, local_modules: set[str]) -> tuple[dict[str, list[dict]], list[dict]]:
    stdlib = set(getattr(sys, "stdlib_module_names", set()))
    stdlib.update({"__future__"})

    imports: dict[str, list[dict]] = defaultdict(list)
    parse_errors: list[dict] = []

    for path in iter_files(root):
        if path.suffix != ".py":
            continue

        source = read_text(path)
        try:
            tree = ast.parse(source, filename=str(path))
        except SyntaxError as exc:
            parse_errors.append(
                {
                    "file": rel(path, root),
                    "error": str(exc),
                }
            )
            continue

        scope = classify_python_scope(path, root)
        file_rel = rel(path, root)

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    full = alias.name
                    top = full.split(".")[0]
                    if top in stdlib or top in local_modules:
                        continue
                    imports[full].append(
                        {
                            "file": file_rel,
                            "scope": scope,
                            "line": getattr(node, "lineno", None),
                        }
                    )

            elif isinstance(node, ast.ImportFrom):
                if node.level and not node.module:
                    continue
                if not node.module:
                    continue
                full = node.module
                top = full.split(".")[0]
                if top in stdlib or top in local_modules:
                    continue
                imports[full].append(
                    {
                        "file": file_rel,
                        "scope": scope,
                        "line": getattr(node, "lineno", None),
                    }
                )

    return imports, parse_errors


def package_import_roots(pkg: str) -> set[str]:
    if pkg in PY_PACKAGE_IMPORTS:
        return PY_PACKAGE_IMPORTS[pkg]
    return {pkg.replace("-", "_")}


def python_package_matches_import(pkg: str, import_name: str) -> bool:
    top = import_name.split(".")[0]
    for root_name in package_import_roots(pkg):
        if "." in root_name:
            if import_name == root_name or import_name.startswith(root_name + "."):
                return True
        else:
            if top == root_name or top.lower() == root_name.lower():
                return True
    return False


def gather_python_cli_usage(root: Path) -> tuple[set[str], dict[str, list[str]]]:
    used: set[str] = set()
    refs: dict[str, list[str]] = defaultdict(list)

    for path in iter_files(root):
        r = rel(path, root)
        name = path.name
        parts = Path(r).parts

        target = False
        if name == "Makefile" or name.startswith("Dockerfile") or path.suffix == ".sh":
            target = True
        elif (
            len(parts) >= 3
            and parts[0] == ".github"
            and parts[1] == "workflows"
            and path.suffix in {".yml", ".yaml"}
        ):
            target = True

        if not target:
            continue

        text = read_text(path)
        for cli, pkg_name in PY_CLI_TO_PACKAGE.items():
            if re.search(rf"(?<![A-Za-z0-9_-]){re.escape(cli)}(?![A-Za-z0-9_-])", text):
                pkg = normalize_package_name(pkg_name)
                used.add(pkg)
                refs[pkg].append(r)

    return used, refs


def npm_package_name(spec: str) -> str | None:
    spec = spec.strip()
    if not spec:
        return None

    if spec.startswith(LOCAL_JS_PREFIXES):
        return None

    if spec.startswith("node:"):
        return None

    if spec in NODE_BUILTINS:
        return None

    if spec.startswith("@"):
        parts = spec.split("/")
        if len(parts) >= 2:
            return "/".join(parts[:2])
        return spec

    return spec.split("/", 1)[0]


def classify_js_scope(path: Path, root: Path) -> str:
    r = path.relative_to(root)
    if len(r.parts) >= 2 and r.parts[0] == "frontend" and r.parts[1] == "src":
        return "frontend_runtime"
    if len(r.parts) >= 1 and r.parts[0] == "frontend":
        return "frontend_dev"
    return "root_js"


def collect_js_imports(root: Path) -> dict[str, list[dict]]:
    imports: dict[str, list[dict]] = defaultdict(list)

    for path in iter_files(root):
        if path.suffix not in {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"}:
            continue

        text = read_text(path)
        scope = classify_js_scope(path, root)
        file_rel = rel(path, root)

        for match in JS_IMPORT_RE.finditer(text):
            spec = match.group(1).strip()
            pkg = npm_package_name(spec)
            if not pkg:
                continue
            imports[pkg].append({"file": file_rel, "scope": scope})

    return imports


def read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(read_text(path))
    except Exception:
        return {}


def scan_js_script_tools(scripts: dict[str, str]) -> set[str]:
    used: set[str] = set()
    for cmd in scripts.values():
        for tool, pkg in JS_SCRIPT_TOOL_TO_PACKAGE.items():
            if re.search(rf"(?<![A-Za-z0-9_-]){re.escape(tool)}(?![A-Za-z0-9_-])", cmd):
                used.add(pkg)
    return used


def shell_logical_lines(text: str) -> list[str]:
    result: list[str] = []
    buf = ""
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if buf:
            buf += " " + line
        else:
            buf = line
        if line.endswith("\\"):
            buf = buf[:-1].strip()
            continue
        result.append(buf)
        buf = ""
    if buf:
        result.append(buf)
    return result


def extract_os_packages_from_dockerfile(text: str) -> set[str]:
    packages: set[str] = set()

    for cmd in shell_logical_lines(text):
        for segment in re.split(r"\s&&\s|;", cmd):
            segment = segment.strip()
            if not segment:
                continue

            tokens = segment.split()
            if "install" in tokens:
                idx = tokens.index("install") + 1
            elif "add" in tokens:
                idx = tokens.index("add") + 1
            else:
                continue

            for tok in tokens[idx:]:
                tok = tok.strip().rstrip("\\")
                if not tok:
                    continue
                if tok.startswith("-"):
                    continue
                if tok in {"apt-get", "apt", "apk", "yum", "dnf"}:
                    continue
                if tok in {"&&", ";", "rm"}:
                    break
                if re.match(r"^[A-Za-z0-9.+:_-]+$", tok):
                    packages.add(tok)

    return packages


def collect_dockerfiles(root: Path) -> dict[str, dict]:
    result: dict[str, dict] = {}
    for path in iter_files(root):
        if path.name == "Dockerfile" or path.name.startswith("Dockerfile"):
            text = read_text(path)
            result[rel(path, root)] = {
                "os_packages": sorted(extract_os_packages_from_dockerfile(text)),
                "has_entrypoint_or_cmd": bool(
                    re.search(r"^\s*(CMD|ENTRYPOINT)\b", text, flags=re.MULTILINE)
                ),
            }
    return result


def parse_compose_services(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}

    services: dict[str, dict] = {}
    in_services = False
    current_service: str | None = None
    current_block: str | None = None

    for raw in read_text(path).splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue

        if re.match(r"^services:\s*$", raw):
            in_services = True
            current_service = None
            current_block = None
            continue

        if in_services and re.match(r"^[A-Za-z0-9_.-]+:\s*$", raw) and not raw.startswith("  "):
            in_services = False
            current_service = None
            current_block = None
            continue

        if not in_services:
            continue

        m_service = re.match(r"^  ([A-Za-z0-9_.-]+):\s*$", raw)
        if m_service:
            current_service = m_service.group(1)
            services[current_service] = {}
            current_block = None
            continue

        if not current_service:
            continue

        m_key = re.match(r"^\s{4}([A-Za-z0-9_.-]+):\s*(.*)$", raw)
        if m_key:
            key, value = m_key.groups()
            if key in {"build", "environment", "healthcheck"} and value == "":
                services[current_service][key] = {}
                current_block = key
            else:
                services[current_service][key] = value
                current_block = None
            continue

        m_sub = re.match(r"^\s{6}([A-Za-z0-9_.-]+):\s*(.*)$", raw)
        if m_sub and current_block:
            k, v = m_sub.groups()
            block = services[current_service].setdefault(current_block, {})
            if isinstance(block, dict):
                block[k] = v

    return services


def parse_env_file(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if not path.exists():
        return env
    for raw in read_text(path).splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        env[key.strip()] = value.strip()
    return env


def infer_external_services(env: dict[str, str], compose_services: dict[str, dict]) -> list[str]:
    found: set[str] = set(compose_services.keys())

    if "DATABASE_URL" in env:
        found.add("postgres")
    if "REDIS_URL" in env:
        found.add("redis")
    if any(k.startswith("MINIO_") for k in env):
        found.add("minio/s3")
    if "DOCX_CONVERTER_URL" in env:
        found.add("office-converter")
    if "LOCAL_LLM_ENDPOINT" in env or env.get("LLM_PROVIDER") in {"ollama", "vllm"}:
        found.add("local-llm")
    if (
        env.get("OPENAI_API_KEY", "")
        or env.get("ANTHROPIC_API_KEY", "")
        or env.get("LLM_CLOUD_API_KEY", "")
    ):
        found.add("cloud-llm")
    if any(k.startswith("OTEL_") for k in env):
        found.add("opentelemetry")

    return sorted(found)


def collect_binary_references(root: Path) -> dict[str, list[str]]:
    refs: dict[str, list[str]] = defaultdict(list)

    for path in iter_files(root):
        r = rel(path, root)
        if not (
            path.suffix in {".py", ".sh", ".yml", ".yaml", ".toml", ".ini"}
            or path.name == "Makefile"
            or path.name.startswith("Dockerfile")
        ):
            continue

        text = read_text(path)
        for binary in KNOWN_BINARIES:
            if re.search(rf"(?<![A-Za-z0-9_-]){re.escape(binary)}(?![A-Za-z0-9_-])", text):
                refs[binary].append(r)

    return {k: sorted(set(v)) for k, v in refs.items()}


def unique_files(occurrences: list[dict], limit: int = 8) -> list[str]:
    files = sorted({o["file"] for o in occurrences})
    return files[:limit]


def unique_dicts(items: list[dict]) -> list[dict]:
    seen: set[str] = set()
    result: list[dict] = []
    for item in items:
        key = json.dumps(item, sort_keys=True, ensure_ascii=False)
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def compose_service_looks_like_app(name: str, meta: dict) -> bool:
    if name.lower() in {"app", "api", "backend", "web"}:
        return True

    build_value = meta.get("build")

    if isinstance(build_value, dict):
        return build_value.get("context") in {".", "./"}

    if isinstance(build_value, str):
        return build_value in {".", "./"}

    return False


def main() -> int:
    parser = argparse.ArgumentParser(description="LegalMAS dependency audit")
    parser.add_argument(
        "--project-root",
        default=str(Path(__file__).resolve().parents[1]),
        help="Project root path",
    )
    parser.add_argument(
        "--json-out",
        default=None,
        help="Path to JSON report (default: <root>/dependency_audit_report.json)",
    )
    parser.add_argument(
        "--txt-out",
        default=None,
        help="Path to text report (default: <root>/dependency_audit_report.txt)",
    )
    args = parser.parse_args()

    root = Path(args.project_root).resolve()
    json_out = Path(args.json_out) if args.json_out else root / "dependency_audit_report.json"
    txt_out = Path(args.txt_out) if args.txt_out else root / "dependency_audit_report.txt"

    declared_runtime: dict[str, list[dict]] = defaultdict(list)
    declared_dev: dict[str, list[dict]] = defaultdict(list)
    python_unpinned: list[dict] = []

    visited_runtime: set[Path] = set()
    visited_dev: set[Path] = set()

    req_runtime_files = [
        root / "requirements.txt",
        root / "requirements-base.txt",
    ]
    req_dev_files = [
        root / "requirements-dev.txt",
    ]

    for rf in req_runtime_files:
        parse_requirements_file(rf, visited_runtime, declared_runtime, python_unpinned)

    for rf in req_dev_files:
        parse_requirements_file(rf, visited_dev, declared_dev, python_unpinned)

    pyproject_runtime, pyproject_dev = parse_pyproject_dependencies(root / "pyproject.toml")
    for pkg in pyproject_runtime:
        declared_runtime[pkg].append(
            {"file": str(root / "pyproject.toml"), "line": None, "raw": "pyproject"}
        )
    for pkg in pyproject_dev:
        declared_dev[pkg].append(
            {"file": str(root / "pyproject.toml"), "line": None, "raw": "pyproject"}
        )

    runtime_pkgs = set(declared_runtime.keys())
    dev_pkgs = set(declared_dev.keys())
    all_python_pkgs = runtime_pkgs | dev_pkgs

    local_python_modules = collect_local_python_modules(root)
    python_imports, python_parse_errors = collect_python_imports(root, local_python_modules)
    python_cli_used, python_cli_refs = gather_python_cli_usage(root)

    used_python_packages: dict[str, list[dict]] = defaultdict(list)
    missing_python_imports: list[dict] = []

    for import_name, occurrences in sorted(python_imports.items()):
        matches = [pkg for pkg in all_python_pkgs if python_package_matches_import(pkg, import_name)]
        if matches:
            for pkg in matches:
                used_python_packages[pkg].extend(occurrences)
        else:
            top = import_name.split(".")[0]
            missing_python_imports.append(
                {
                    "import": import_name,
                    "suggested_package": PY_IMPORT_SUGGESTIONS.get(top),
                    "files": unique_files(occurrences),
                    "scopes": sorted({o["scope"] for o in occurrences}),
                }
            )

    missing_python_imports = unique_dicts(missing_python_imports)

    declared_without_direct_usage: list[dict] = []
    for pkg in sorted(all_python_pkgs):
        if pkg in used_python_packages or pkg in python_cli_used:
            continue
        declared_without_direct_usage.append(
            {
                "package": pkg,
                "declared_scopes": sorted(
                    ["runtime"] * (pkg in runtime_pkgs) + ["dev"] * (pkg in dev_pkgs)
                ),
                "reason": IMPLICIT_OR_INTENTIONAL_PACKAGES.get(
                    pkg, "No direct import/CLI usage detected; may still be intentional or transitive."
                ),
            }
        )

    js_imports = collect_js_imports(root)

    root_pkg_json = read_json(root / "package.json")
    frontend_pkg_json = read_json(root / "frontend" / "package.json")

    root_deps = set((root_pkg_json.get("dependencies") or {}).keys())
    root_dev_deps = set((root_pkg_json.get("devDependencies") or {}).keys())

    frontend_deps = set((frontend_pkg_json.get("dependencies") or {}).keys())
    frontend_dev_deps = set((frontend_pkg_json.get("devDependencies") or {}).keys())
    frontend_all = frontend_deps | frontend_dev_deps

    frontend_scripts_used = scan_js_script_tools(frontend_pkg_json.get("scripts", {}) or {})
    root_scripts_used = scan_js_script_tools(root_pkg_json.get("scripts", {}) or {})

    frontend_runtime_imports = {
        pkg for pkg, occs in js_imports.items() if any(o["scope"] == "frontend_runtime" for o in occs)
    }
    frontend_dev_imports = {
        pkg for pkg, occs in js_imports.items() if any(o["scope"] == "frontend_dev" for o in occs)
    }
    root_js_imports = {
        pkg for pkg, occs in js_imports.items() if any(o["scope"] == "root_js" for o in occs)
    }

    frontend_missing = sorted(
        pkg for pkg in frontend_runtime_imports | frontend_dev_imports if pkg not in frontend_all
    )
    frontend_runtime_in_dev = sorted(
        pkg for pkg in frontend_runtime_imports if pkg in frontend_dev_deps and pkg not in frontend_deps
    )
    frontend_types_in_runtime = sorted(pkg for pkg in frontend_deps if pkg.startswith("@types/"))

    frontend_declared_without_usage = sorted(
        pkg
        for pkg in frontend_all
        if pkg not in frontend_runtime_imports
        and pkg not in frontend_dev_imports
        and pkg not in frontend_scripts_used
    )

    root_manifest_warnings: list[str] = []
    if root_deps or root_dev_deps:
        if not root_js_imports and not root_scripts_used:
            root_manifest_warnings.append(
                "Root package.json exists, but no root-level JS/TS imports or npm script tool usage were found. It is likely redundant."
            )
        elif all(pkg not in root_js_imports for pkg in (root_deps | root_dev_deps)):
            root_manifest_warnings.append(
                "Root package.json dependencies do not appear to be used outside frontend/. Verify whether root npm manifest is needed."
            )

    dockerfiles = collect_dockerfiles(root)
    installed_os_packages: set[str] = set()
    for meta in dockerfiles.values():
        installed_os_packages.update(meta["os_packages"])

    compose_path = root / "docker-compose.yml"
    compose_services = parse_compose_services(compose_path)
    env_example = parse_env_file(root / ".env.example")
    external_services = infer_external_services(env_example, compose_services)

    binary_refs = collect_binary_references(root)
    required_os_packages = sorted({KNOWN_BINARIES[b] for b in binary_refs if b in KNOWN_BINARIES})
    missing_os_packages = sorted(pkg for pkg in required_os_packages if pkg not in installed_os_packages)

    compose_has_app_service = any(
        compose_service_looks_like_app(name, meta)
        for name, meta in compose_services.items()
    )
    compose_has_worker_service = any("worker" in name.lower() for name in compose_services)

    deployment_warnings: list[str] = []
    if "Dockerfile" in dockerfiles and not dockerfiles["Dockerfile"]["has_entrypoint_or_cmd"]:
        deployment_warnings.append("Main Dockerfile has no CMD/ENTRYPOINT.")
    if compose_services and not compose_has_app_service:
        deployment_warnings.append(
            "docker-compose.yml contains infrastructure services only; no main backend/app service detected."
        )
    if compose_services and not compose_has_worker_service:
        deployment_warnings.append("docker-compose.yml has no Celery worker service.")
    if compose_services and "postgres" not in compose_services and "DATABASE_URL" in env_example:
        deployment_warnings.append(
            "DATABASE_URL exists in .env.example, but postgres service not found in docker-compose.yml."
        )
    if env_example.get("LLM_LOCAL_MODEL_PATH", "").startswith("/home/"):
        deployment_warnings.append(
            "LLM_LOCAL_MODEL_PATH in .env.example is a local absolute path and should be made server-safe."
        )

    recommendations: list[str] = []
    if frontend_runtime_in_dev:
        recommendations.append(
            "Move frontend runtime packages from devDependencies to dependencies: "
            + ", ".join(frontend_runtime_in_dev)
        )
    if frontend_types_in_runtime:
        recommendations.append(
            "Move type-only packages from dependencies to devDependencies: "
            + ", ".join(frontend_types_in_runtime)
        )
    if root_manifest_warnings:
        recommendations.append(
            "Review or remove root package.json if frontend/package.json is the real app manifest."
        )
    if missing_python_imports:
        recommendations.append("Add missing Python packages for imports not covered by requirements/pyproject.")
    if frontend_missing:
        recommendations.append("Add missing frontend packages to frontend/package.json.")
    if missing_os_packages:
        recommendations.append(
            "Install missing OS packages in Dockerfiles or server image: " + ", ".join(missing_os_packages)
        )
    if python_unpinned:
        recommendations.append("Pin non-exact Python dependencies for reproducible deploys.")
    if deployment_warnings:
        recommendations.append("Add app/worker startup definitions to Dockerfile/docker-compose before server deploy.")

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "project_root": str(root),
        "python": {
            "runtime_declared_count": len(runtime_pkgs),
            "dev_declared_count": len(dev_pkgs),
            "missing_imports": missing_python_imports,
            "declared_without_direct_usage": declared_without_direct_usage,
            "unpinned_requirements": unique_dicts(python_unpinned),
            "parse_errors": python_parse_errors,
            "cli_usage": {k: sorted(set(v)) for k, v in python_cli_refs.items()},
        },
        "frontend": {
            "root_package_json_present": bool(root_pkg_json),
            "frontend_package_json_present": bool(frontend_pkg_json),
            "missing_packages": frontend_missing,
            "runtime_packages_declared_as_devDependencies": frontend_runtime_in_dev,
            "type_packages_declared_as_dependencies": frontend_types_in_runtime,
            "declared_without_observed_usage": frontend_declared_without_usage,
            "root_manifest_warnings": root_manifest_warnings,
            "root_runtime_imports": sorted(root_js_imports),
            "frontend_runtime_imports": sorted(frontend_runtime_imports),
        },
        "system": {
            "binaries_referenced": binary_refs,
            "required_os_packages_from_binaries": required_os_packages,
            "installed_os_packages_found_in_dockerfiles": sorted(installed_os_packages),
            "missing_os_packages_in_dockerfiles": missing_os_packages,
            "dockerfiles": dockerfiles,
        },
        "deployment": {
            "compose_services": compose_services,
            "external_services_inferred": external_services,
            "warnings": deployment_warnings,
        },
        "recommendations": recommendations,
    }

    text_lines: list[str] = []
    text_lines.append("LegalMAS dependency audit")
    text_lines.append(f"Generated: {report['generated_at']}")
    text_lines.append(f"Project root: {report['project_root']}")
    text_lines.append("")

    text_lines.append("== Summary ==")
    text_lines.append(f"Python runtime packages declared: {report['python']['runtime_declared_count']}")
    text_lines.append(f"Python dev packages declared: {report['python']['dev_declared_count']}")
    text_lines.append(f"Missing Python imports: {len(report['python']['missing_imports'])}")
    text_lines.append(f"Frontend missing packages: {len(report['frontend']['missing_packages'])}")
    text_lines.append(
        "Frontend runtime packages in devDependencies: "
        + str(len(report['frontend']['runtime_packages_declared_as_devDependencies']))
    )
    text_lines.append(f"Deployment warnings: {len(report['deployment']['warnings'])}")
    text_lines.append("")

    text_lines.append("== Python missing imports ==")
    if report["python"]["missing_imports"]:
        for item in report["python"]["missing_imports"]:
            suggestion = f" -> suggested package: {item['suggested_package']}" if item["suggested_package"] else ""
            text_lines.append(
                f"- {item['import']}{suggestion}; scopes={','.join(item['scopes'])}; files={', '.join(item['files'])}"
            )
    else:
        text_lines.append("- none")
    text_lines.append("")

    text_lines.append("== Python declared without direct usage ==")
    if report["python"]["declared_without_direct_usage"]:
        for item in report["python"]["declared_without_direct_usage"]:
            text_lines.append(
                f"- {item['package']} [{','.join(item['declared_scopes'])}] : {item['reason']}"
            )
    else:
        text_lines.append("- none")
    text_lines.append("")

    text_lines.append("== Python unpinned requirements ==")
    if report["python"]["unpinned_requirements"]:
        for item in report["python"]["unpinned_requirements"]:
            text_lines.append(f"- {item['package']}: {item['raw']} ({item['file']}:{item['line']})")
    else:
        text_lines.append("- none")
    text_lines.append("")

    text_lines.append("== Frontend issues ==")
    if report["frontend"]["missing_packages"]:
        text_lines.append("- Missing packages: " + ", ".join(report["frontend"]["missing_packages"]))
    else:
        text_lines.append("- Missing packages: none")

    if report["frontend"]["runtime_packages_declared_as_devDependencies"]:
        text_lines.append(
            "- Runtime packages incorrectly in devDependencies: "
            + ", ".join(report["frontend"]["runtime_packages_declared_as_devDependencies"])
        )
    else:
        text_lines.append("- Runtime packages incorrectly in devDependencies: none")

    if report["frontend"]["type_packages_declared_as_dependencies"]:
        text_lines.append(
            "- Type packages incorrectly in dependencies: "
            + ", ".join(report["frontend"]["type_packages_declared_as_dependencies"])
        )
    else:
        text_lines.append("- Type packages incorrectly in dependencies: none")

    if report["frontend"]["root_manifest_warnings"]:
        for warning_text in report["frontend"]["root_manifest_warnings"]:
            text_lines.append(f"- Root manifest warning: {warning_text}")
    else:
        text_lines.append("- Root manifest warning: none")
    text_lines.append("")

    text_lines.append("== System / OS dependencies ==")
    text_lines.append(
        "- Referenced binaries: "
        + (", ".join(sorted(report["system"]["binaries_referenced"].keys())) or "none")
    )
    text_lines.append(
        "- OS packages found in Dockerfiles: "
        + (", ".join(report["system"]["installed_os_packages_found_in_dockerfiles"]) or "none")
    )
    text_lines.append(
        "- Missing OS packages from binary usage: "
        + (", ".join(report["system"]["missing_os_packages_in_dockerfiles"]) or "none")
    )
    text_lines.append("")

    text_lines.append("== Deployment ==")
    text_lines.append(
        "- Compose services: "
        + (", ".join(sorted(report["deployment"]["compose_services"].keys())) or "none")
    )
    text_lines.append(
        "- External services inferred: "
        + (", ".join(report["deployment"]["external_services_inferred"]) or "none")
    )
    if report["deployment"]["warnings"]:
        for warning_text in report["deployment"]["warnings"]:
            text_lines.append(f"- Warning: {warning_text}")
    else:
        text_lines.append("- Warning: none")
    text_lines.append("")

    text_lines.append("== Recommendations ==")
    if report["recommendations"]:
        for rec in report["recommendations"]:
            text_lines.append(f"- {rec}")
    else:
        text_lines.append("- none")

    write_text(json_out, json.dumps(report, ensure_ascii=False, indent=2))
    write_text(txt_out, "\n".join(text_lines))

    print(f"[OK] JSON report: {json_out}")
    print(f"[OK] Text report: {txt_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
