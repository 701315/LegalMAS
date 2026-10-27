"""Pre-render mermaid blocks to PNG via local mmdc (mermaid-cli v12+).

Requires: mmdc in PATH. Auto-detects chrome-headless-shell from puppeteer
cache if mmdc's bundled version is missing. --no-sandbox required for
Ubuntu 24.04 AppArmor (unprivileged userns disabled). Fully offline.

Usage: python3 render_mermaid.py input.md outdir > output.md
"""
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile


def _find_chrome() -> str | None:
    env = os.environ.get("PUPPETEER_EXECUTABLE_PATH")
    if env and pathlib.Path(env).exists():
        return env

    cache = pathlib.Path.home() / ".cache" / "puppeteer"
    if cache.exists():
        for pattern in (
            "chrome-headless-shell/*/chrome-headless-shell-linux64/chrome-headless-shell",
            "chrome/*/chrome-linux64/chrome",
        ):
            matches = sorted(cache.glob(pattern))
            if matches:
                return str(matches[-1])
    return None


def _make_config(chrome: str) -> str:
    cfg = pathlib.Path(tempfile.gettempdir()) / "puppeteer-config.json"
    cfg.write_text(
        '{"executablePath": "' + chrome + '", '
        '"args": ["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]}',
        encoding="utf-8",
    )
    return str(cfg)


def render_block(code: str, out: str, cfg: str) -> bool:
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".mmd", delete=False, encoding="utf-8"
    ) as f:
        f.write(code)
        mmd_path = f.name
    try:
        cmd = [
            "mmdc", "-i", mmd_path, "-o", out,
            "-b", "white", "-e", "png", "-s", "2",
            "-p", cfg,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        if result.returncode != 0:
            print(f"# mmdc FAIL {out}: {result.stderr.strip()[:300]}", file=sys.stderr)
            return False
        size = pathlib.Path(out).stat().st_size
        print(f"# OK {out} ({size} bytes)", file=sys.stderr)
        return True
    finally:
        pathlib.Path(mmd_path).unlink(missing_ok=True)


def main(src: str, outdir: str) -> None:
    if not shutil.which("mmdc"):
        print("# FATAL: mmdc not in PATH", file=sys.stderr)
        sys.exit(1)

    chrome = _find_chrome()
    if not chrome:
        print("# FATAL: no chrome/chrome-headless-shell in puppeteer cache", file=sys.stderr)
        print("# Run: npx puppeteer browsers install chrome-headless-shell", file=sys.stderr)
        sys.exit(1)
    cfg = _make_config(chrome)
    print(f"# chrome: {chrome}", file=sys.stderr)

    content = pathlib.Path(src).read_text(encoding="utf-8")

    # Strip leading H1 (+ blank lines) — pandoc renders --metadata title
    # as a title block at the top; keeping the H1 produces a duplicate.
    lines = content.split("\n")
    i = 0
    while i < len(lines) and (lines[i].startswith("# ") or lines[i].strip() == ""):
        i += 1
    content = "\n".join(lines[i:])

    pattern = re.compile(r"^~~~mermaid\n(.*?)\n~~~$", re.MULTILINE | re.DOTALL)
    counter = [0]

    def repl(m):
        code = m.group(1).strip()
        i = counter[0]
        counter[0] += 1
        out = f"{outdir}/diagram_{i}.png"
        ok = render_block(code, out, cfg)
        if ok:
            return f"![]({out})"
        return m.group(0)

    result = pattern.sub(repl, content)
    sys.stdout.write(result)
    print(f"# rendered {counter[0]} diagram(s)", file=sys.stderr)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
