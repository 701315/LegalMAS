#!/usr/bin/env bash

FRONTEND_DIR="/srv/steloom-dev/frontend"
SRC_DIR="$FRONTEND_DIR/src"
C="$SRC_DIR/components"
P="$SRC_DIR/pages"

if [ ! -d "$SRC_DIR" ]; then
  echo "ERROR: not found: $SRC_DIR"
  exit 2
fi

HARD_FAIL=0

sep() { echo "----------------------------------------------"; }
header() { echo ""; echo "=== $1 ==="; sep; }

gx() {
  grep -rnE --include="*.tsx" --exclude-dir=marketing "$1" "$C" "$P" 2>/dev/null || true
}

gt() {
  grep -rnE --include="*.tsx" --include="*.ts" --exclude-dir=marketing "$1" "$C" "$P" 2>/dev/null || true
}

check_hard() {
  local title="$1"
  local result="$2"
  header "HARD | $title"
  if [ -n "$result" ]; then
    echo "$result"
    HARD_FAIL=1
  else
    echo "OK"
  fi
}

check_review() {
  local title="$1"
  local result="$2"
  header "REVIEW | $title"
  if [ -n "$result" ]; then
    echo "$result"
  else
    echo "OK"
  fi
}

echo "=============================================="
echo " Design System Audit v3"
echo " $SRC_DIR"
echo "=============================================="

check_hard "Raw Tailwind status colors" \
  "$(gx 'bg-(red|rose|yellow|amber|green|emerald|sky|indigo|violet)-[0-9]|text-(red|rose|yellow|amber|green|emerald|sky|indigo|violet)-[0-9]|border-(red|rose|yellow|amber|green|emerald|sky|indigo|violet)-[0-9]')"

check_hard "dark: classes" \
  "$(gx 'dark:')"

check_hard "Hex literals" \
  "$(gt '#[0-9a-fA-F]{6}')"

check_hard "var() fallbacks" \
  "$(gt 'var\(--[^,)]+,[^)]+\)')"

# Точный паттерн: только --danger, --bg-hover, --bg-muted, --accent) или --accent,
# НЕ --accent-primary, --accent-hover, --accent-muted, --accent-subtle
check_hard "Non-canonical bare tokens: --danger / --bg-hover / --bg-muted / --accent (exact)" \
  "$(gt 'var\(--(danger|bg-hover|bg-muted)\b' | grep -v 'accent-'; gt 'var\(--accent[,)"\x27 ]' 2>/dev/null || true)"

check_hard "Token: --bg-elevated without -soft" \
  "$(gt 'var\(--bg-elevated\b' | grep -v 'bg-elevated-soft' || true)"

check_hard "Token: --color-primary" \
  "$(gt 'var\(--color-primary\b')"

check_hard "Non-canonical subtle tokens (success-subtle, error-subtle, warning-subtle)" \
  "$(gt 'color-(success|warning|error)-subtle')"

check_hard "color-mix() with base status tokens" \
  "$(gt 'color-mix.*var\(--color-(success|warning|error)\)')"

check_review "Base status color used as text/bg class" \
  "$(gx '(text|bg|border)-\[var\(--color-(success|warning|error)\)\]')"

header "focus-visible pattern check"
FFILES=$(grep -rl --include="*.tsx" --exclude-dir=marketing 'focus-visible:' "$C" "$P" 2>/dev/null || true)
if [ -z "$FFILES" ]; then
  echo "OK — no focus-visible usages"
else
  FISSUES=""
  while IFS= read -r f; do
    [ -z "$f" ] && continue
    MISSING=""
    grep -qF 'focus-visible:outline-none' "$f"                           || MISSING="$MISSING outline-none"
    grep -qF 'focus-visible:ring-2' "$f"                                 || MISSING="$MISSING ring-2"
    grep -qF 'focus-visible:ring-[var(--accent-primary)]/35' "$f"        || MISSING="$MISSING accent-ring"
    grep -qF 'focus-visible:ring-offset-2' "$f"                          || MISSING="$MISSING ring-offset-2"
    grep -qE 'focus-visible:ring-offset-\[var\(--bg-(card|base|elevated-soft)\)\]' "$f" || MISSING="$MISSING ring-offset-bg"
    if [ -n "$MISSING" ]; then
      FISSUES="$FISSUES\n  $f  missing:$MISSING"
    fi
  done <<< "$FFILES"
  if [ -n "$FISSUES" ]; then
    printf "%b\n" "$FISSUES"
  else
    echo "OK"
  fi
fi

echo ""
echo "=============================================="
if [ "$HARD_FAIL" -eq 1 ]; then
  echo " RESULT: FAIL — hard violations found"
else
  echo " RESULT: PASS — no hard violations"
fi
echo "=============================================="

exit $HARD_FAIL
