#!/usr/bin/env bash
# ════════════════════════════════════════════════════════════════════════
# FRONTEND VISUAL AUDIT v2 — steloom-dev/frontend
# Исправлено: сканируем только ./src (реальный код), не весь репозиторий.
# В конце генерируется _SUMMARY.txt — присылай мне ТОЛЬКО его.
# ════════════════════════════════════════════════════════════════════════

FRONTEND_DIR=/srv/steloom-dev/frontend
cd "$FRONTEND_DIR" || exit 1

SRC=./src
EXT="--include=*.css --include=*.scss --include=*.ts --include=*.tsx --include=*.js --include=*.jsx"
EXCL="--exclude-dir=node_modules --exclude-dir=dist --exclude-dir=build --exclude-dir=.next --exclude-dir=coverage --exclude-dir=.turbo --exclude-dir=storybook-static --exclude-dir=.git"
OUT=./audit-output
rm -rf "$OUT"
mkdir -p "$OUT"

g() { grep -rn $EXT $EXCL "$@" "$SRC"; }
gc() { grep -rohn $EXT $EXCL "$@" "$SRC"; }

echo "══════════════════════════════════════════"
echo "0. СТРУКТУРА ПРОЕКТА (в пределах ./src)"
echo "══════════════════════════════════════════"

find "$SRC" -type d \( -name node_modules -o -name dist -o -name build \) -prune -o -type f -print \
  | grep -E '\.(css|scss|tsx?|jsx?)$' > "$OUT/00_all_files.txt"

find "$SRC" -type f \( -name "*.css" -o -name "*.scss" -o -name "*.module.css" \) > "$OUT/00_style_files.txt"

# Расширенный список ключевых слов для shell/layout компонентов
find "$SRC" -type f -iregex '.*\(layout\|shell\|sidebar\|topbar\|navbar\|nav\|header\|dashboard\|drawer\|panel\|workspace\|appshell\|main\)\.\(tsx\?\|jsx\?\)' > "$OUT/00_shell_components.txt"


echo "══════════════════════════════════════════"
echo "1. ТИПОГРАФИКА"
echo "══════════════════════════════════════════"

g -e "Instrument Serif" -e "font-serif" -e "font-display" > "$OUT/01_serif_usage.txt"
g -e "font-family" > "$OUT/01_font_family.txt"
g -E "text-(2xl|3xl|4xl|5xl|6xl|7xl)" > "$OUT/01_large_text_classes.txt"
g -E "font-size:\s*[0-9]" > "$OUT/01_hardcoded_font_size.txt"
g -E "line-height:\s*[0-9]" > "$OUT/01_hardcoded_line_height.txt"

gc -E "font-weight:\s*[0-9]+" | sort | uniq -c | sort -rn > "$OUT/01_font_weight_distribution.txt"
gc -E "font-(thin|extralight|light|normal|medium|semibold|bold|extrabold|black)\b" | sort | uniq -c | sort -rn >> "$OUT/01_font_weight_distribution.txt"


echo "══════════════════════════════════════════"
echo "2. ЦВЕТА / ТОКЕНЫ"
echo "══════════════════════════════════════════"

g -E "#[0-9a-fA-F]{3,8}\b" --exclude=index.css > "$OUT/02_hardcoded_hex.txt"
g -E "rgba?\([0-9]" --exclude=index.css > "$OUT/02_hardcoded_rgb.txt"
gc -E "var\(--[a-zA-Z0-9-]+\)" | sort | uniq -c | sort -rn > "$OUT/02_css_var_usage_frequency.txt"
grep -nE "^\s*--(color|bg|text|border|accent|app)-[a-zA-Z0-9-]+:\s*#" "$SRC/index.css" > "$OUT/02_duplicate_color_tokens.txt" 2>/dev/null
g -E "(bg|text|border)-\[#[0-9a-fA-F]{3,8}\]" > "$OUT/02_tailwind_arbitrary_colors.txt"
g -e "linear-gradient" -e "radial-gradient" -e "conic-gradient" > "$OUT/02_gradients.txt"
g -e "prefers-color-scheme" -e "data-theme" -e "dark:" > "$OUT/02_dark_mode_traces.txt"


echo "══════════════════════════════════════════"
echo "3. SPACING / РАЗМЕРЫ"
echo "══════════════════════════════════════════"

g -E "(padding|margin|gap):\s*[0-9]+px" > "$OUT/03_hardcoded_px_spacing.txt"
g -E "\b(p|m|gap|space)(x|y|t|b|l|r)?-\[[0-9]" > "$OUT/03_tailwind_arbitrary_spacing.txt"
gc -oE "\b(p|m|gap)(x|y|t|b|l|r)?-[0-9]+\b" | sort | uniq -c | sort -rn > "$OUT/03_spacing_class_frequency.txt"


echo "══════════════════════════════════════════"
echo "4. RADIUS / SHADOW / BORDER"
echo "══════════════════════════════════════════"

g -E "border-radius:\s*[0-9]" > "$OUT/04_hardcoded_radius.txt"
gc -oE "rounded(-[a-z0-9]+)?" | sort | uniq -c | sort -rn > "$OUT/04_rounded_class_frequency.txt"
g -e "box-shadow" > "$OUT/04_box_shadow_usage.txt"
g -E "border-(left|inline-start):\s*[0-9]+px solid" > "$OUT/04_colored_left_border_pattern.txt"
g -E "border-l-(2|3|4)\b" >> "$OUT/04_colored_left_border_pattern.txt"


echo "══════════════════════════════════════════"
echo "5. КОМПОНЕНТНЫЕ ПАТТЕРНЫ"
echo "══════════════════════════════════════════"

g -e "active" -e "selected" -e "is-active" -e "aria-current" > "$OUT/05_active_state_usage.txt"
g -e "rounded-full" | grep -i "bg-" > "$OUT/05_icon_in_circle_pattern.txt"
grep -rl $EXT $EXCL -e "badge" -e "chip" -e "pill" "$SRC" > "$OUT/05_badge_chip_files.txt"
grep -rl $EXT $EXCL -ie "button\|btn" "$SRC" > "$OUT/05_button_related_files.txt"

# Более широкий поиск вариантов кнопок: className, styled(), cva(), clsx
gc -oE "(className|class)=\{?\`?[^}]*\b(btn|button)[a-zA-Z-]*" | sort | uniq -c | sort -rn > "$OUT/05_btn_class_variants.txt"
g -e "styled(button)" -e "styled.button" -e "cva(" >> "$OUT/05_btn_class_variants.txt"


echo "══════════════════════════════════════════"
echo "6. SCROLL-МОДЕЛЬ"
echo "══════════════════════════════════════════"

g -e "overflow-y" -e "overflow-x" -e "overflow:" -e "overscroll-behavior" > "$OUT/06_scroll_model.txt"
g -E "position:\s*(sticky|fixed)" -e "sticky " -e "fixed " > "$OUT/06_sticky_fixed_usage.txt"


echo "══════════════════════════════════════════"
echo "7. ДОСТУПНОСТЬ (быстрая проверка)"
echo "══════════════════════════════════════════"

grep -rl $EXT $EXCL -e "<img" "$SRC" | xargs grep -L "alt=" 2>/dev/null > "$OUT/07_images_missing_alt.txt"
grep -rl $EXT $EXCL -e "onClick" "$SRC" | xargs grep -L "aria-label\|role=\"button\"\|<button\|<Button" 2>/dev/null > "$OUT/07_clickable_divs_suspect.txt"
g -e "focus-visible" -e ":focus" > "$OUT/07_focus_states.txt"


echo "══════════════════════════════════════════"
echo "ГЕНЕРАЦИЯ SUMMARY (единственный файл для отправки)"
echo "══════════════════════════════════════════"

SUMMARY="$OUT/_SUMMARY.txt"
> "$SUMMARY"
for f in "$OUT"/*.txt; do
  [ "$(basename "$f")" = "_SUMMARY.txt" ] && continue
  lines=$(wc -l < "$f")
  {
    echo ""
    echo "════ $(basename "$f")  (всего строк: $lines) ════"
    if [ "$lines" -eq 0 ]; then
      echo "(пусто)"
    else
      head -40 "$f"
      [ "$lines" -gt 40 ] && echo "... (обрезано, показаны первые 40 из $lines)"
    fi
  } >> "$SUMMARY"
done

echo ""
echo "ГОТОВО."
echo "Пришли мне ТОЛЬКО этот файл: $OUT/_SUMMARY.txt"
wc -l "$SUMMARY"

