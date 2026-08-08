#!/usr/bin/env bash
set -euo pipefail

FRONTEND_DIR=/srv/steloom-dev/frontend
cd "$FRONTEND_DIR" || exit 1

SRC=./src
EXT="--include=*.css --include=*.scss --include=*.ts --include=*.tsx --include=*.js --include=*.jsx"
EXCL="--exclude-dir=node_modules --exclude-dir=dist --exclude-dir=build --exclude-dir=.next --exclude-dir=coverage --exclude-dir=.turbo --exclude-dir=storybook-static --exclude-dir=.git"
APP_EXCL="$EXCL --exclude-dir=marketing"

OUT=./audit-output
rm -rf "$OUT"
mkdir -p "$OUT"

# g     = весь src (включая marketing)
# g_app = только app-слой (без marketing)
# gc    = весь src, только совпадения без номера строки (для частот)
# gc_app = app-слой, только совпадения без номера строки (для частот)

g()      { grep -rn  $EXT $EXCL     "$@" "$SRC"; }
gc()     { grep -roh $EXT $EXCL     "$@" "$SRC"; }
g_app()  { grep -rn  $EXT $APP_EXCL "$@" "$SRC"; }
gc_app() { grep -roh $EXT $APP_EXCL "$@" "$SRC"; }

# ══════════════════════════════════════════
echo "0. СТРУКТУРА ПРОЕКТА"
# ══════════════════════════════════════════

find "$SRC" -type d \( -name node_modules -o -name dist -o -name build \) -prune \
  -o -type f -print \
  | grep -E '\.(css|scss|tsx?|jsx?)$' \
  > "$OUT/00_all_files.txt"

find "$SRC" -type f \( -name "*.css" -o -name "*.scss" -o -name "*.module.css" \) \
  > "$OUT/00_style_files.txt"

# Ищем shell/layout компоненты через grep по пути (без -iregex, он портативнее)
find "$SRC" -type f \
  | grep -Ei '/[^/]*(layout|shell|sidebar|topbar|navbar|nav|header|dashboard|drawer|panel|workspace|appshell|main)\.(ts|tsx|js|jsx)$' \
  > "$OUT/00_shell_components.txt" || true

# Дерево директорий app-слоя (без marketing)
find "$SRC" -type d \
  | grep -v marketing \
  | grep -v node_modules \
  | sort \
  > "$OUT/00_app_directory_tree.txt"

# Счётчик файлов по типу
echo "=== Файлов .tsx ===" > "$OUT/00_file_counts.txt"
find "$SRC" -name "*.tsx" | grep -v marketing | wc -l >> "$OUT/00_file_counts.txt"
echo "=== Файлов .ts ===" >> "$OUT/00_file_counts.txt"
find "$SRC" -name "*.ts" | grep -v marketing | wc -l >> "$OUT/00_file_counts.txt"
echo "=== Файлов .css/.scss ===" >> "$OUT/00_file_counts.txt"
find "$SRC" \( -name "*.css" -o -name "*.scss" \) | grep -v marketing | wc -l >> "$OUT/00_file_counts.txt"


# ══════════════════════════════════════════
echo "1. ТИПОГРАФИКА"
# ══════════════════════════════════════════

# Serif в app-слое (должно быть 0)
g_app -e "Instrument Serif" -e "font-serif" -e "font-display" \
  > "$OUT/01_serif_in_app.txt" || true

# Все serif включая marketing (для справки)
g -e "Instrument Serif" -e "font-serif" -e "font-display" \
  > "$OUT/01_serif_all.txt" || true

g_app -e "font-family" \
  > "$OUT/01_font_family.txt" || true

# Крупный текст только в app (marketing исключён)
g_app -E "text-(2xl|3xl|4xl|5xl|6xl|7xl)" \
  > "$OUT/01_large_text_app.txt" || true

g_app -E "font-size:\s*[0-9]" \
  > "$OUT/01_hardcoded_font_size.txt" || true

g_app -E "line-height:\s*[0-9]" \
  > "$OUT/01_hardcoded_line_height.txt" || true

# Частота font-weight (только app)
{
  gc_app -E "font-weight:\s*[0-9]+" 2>/dev/null || true
  gc_app -E "font-(thin|extralight|light|normal|medium|semibold|bold|extrabold|black)\b" 2>/dev/null || true
} | sort | uniq -c | sort -rn \
  > "$OUT/01_font_weight_distribution.txt"

# Arbitrary font-size в Tailwind (text-[Npx] / text-[Nrem])
g_app -E "text-\[[0-9]" \
  > "$OUT/01_tailwind_arbitrary_fontsize.txt" || true


# ══════════════════════════════════════════
echo "2. ЦВЕТА / ТОКЕНЫ"
# ══════════════════════════════════════════

# Хардкод hex в app (без index.css — он source of truth)
g_app -E "#[0-9a-fA-F]{3,8}\b" \
  --exclude=index.css \
  > "$OUT/02_hardcoded_hex_app.txt" || true

# Хардкод rgb/rgba в app
g_app -E "rgba?\([0-9]" \
  --exclude=index.css \
  > "$OUT/02_hardcoded_rgb_app.txt" || true

# Частота использования CSS-переменных в app
gc_app -E "var\(--[a-zA-Z0-9-]+\)" 2>/dev/null \
  | sort | uniq -c | sort -rn \
  > "$OUT/02_css_var_usage_frequency.txt"

# Все токены определённые в index.css (оба слоя — @theme и :root)
grep -nE "^\s*--[a-zA-Z0-9-]+:\s*" "$SRC/index.css" \
  > "$OUT/02_all_tokens_in_index_css.txt" 2>/dev/null || true

# Только цветовые токены с hex-значениями (дубли между слоями)
grep -nE "^\s*--(color|bg|text|border|accent|app)-[a-zA-Z0-9-]+:\s*#" "$SRC/index.css" \
  > "$OUT/02_duplicate_color_tokens.txt" 2>/dev/null || true

# Tailwind arbitrary цвета в app
g_app -E "(bg|text|border|ring|fill|stroke)-\[#[0-9a-fA-F]{3,8}\]" \
  > "$OUT/02_tailwind_arbitrary_colors_app.txt" || true

# var() с фолбэком (проблема несовпадающих fallback)
g_app -E "var\(--[a-zA-Z0-9-]+,[^)]+\)" \
  > "$OUT/02_var_with_fallback.txt" || true

# Сырые Tailwind статусные классы (rose/red/green/yellow/amber/emerald)
g_app -E "(bg|text|border)-(rose|red|green|yellow|amber|emerald|orange)-[0-9]+" \
  > "$OUT/02_raw_tailwind_status_colors.txt" || true

# Частота сырых статусных классов
gc_app -E "(bg|text|border)-(rose|red|green|yellow|amber|emerald|orange)-[0-9]+" 2>/dev/null \
  | sort | uniq -c | sort -rn \
  > "$OUT/02_raw_status_color_frequency.txt"

# Чужие rgb-литералы (точные значения из аудита)
g_app -E "rgb\(161,\s*53,\s*68\)|rgb\(120,\s*35,\s*46\)|rgb\(67,\s*122,\s*34\)|rgb\(47,\s*93,\s*24\)|rgb\(150,\s*66,\s*25\)|rgb\(122,\s*59,\s*27\)|rgba\(1,\s*105,\s*111" \
  > "$OUT/02_foreign_rgb_literals.txt" || true

# Градиенты (только app)
g_app -e "linear-gradient" -e "radial-gradient" -e "conic-gradient" \
  > "$OUT/02_gradients_app.txt" || true

# Dark mode следы
g_app -e "prefers-color-scheme" -e "data-theme" -e "dark:" \
  > "$OUT/02_dark_mode_traces.txt" || true


# ══════════════════════════════════════════
echo "3. SPACING / РАЗМЕРЫ"
# ══════════════════════════════════════════

g_app -E "(padding|margin|gap):\s*[0-9]+px" \
  > "$OUT/03_hardcoded_px_spacing.txt" || true

g_app -E "\b(p|m|gap|space)(x|y|t|b|l|r)?-\[[0-9]" \
  > "$OUT/03_tailwind_arbitrary_spacing.txt" || true

gc_app -E "\b(p|m|gap)(x|y|t|b|l|r)?-[0-9]+\b" 2>/dev/null \
  | sort | uniq -c | sort -rn \
  > "$OUT/03_spacing_class_frequency.txt"


# ══════════════════════════════════════════
echo "4. RADIUS / SHADOW / BORDER"
# ══════════════════════════════════════════

g_app -E "border-radius:\s*[0-9]" \
  > "$OUT/04_hardcoded_radius.txt" || true

gc_app -E "rounded(-[a-z0-9]+)?" 2>/dev/null \
  | sort | uniq -c | sort -rn \
  > "$OUT/04_rounded_class_frequency.txt"

g_app -e "box-shadow" \
  > "$OUT/04_box_shadow_usage.txt" || true

g_app -E "border-(left|inline-start):\s*[0-9]+px solid" \
  > "$OUT/04_colored_left_border_pattern.txt" || true

g_app -E "border-l-(2|3|4)\b" \
  >> "$OUT/04_colored_left_border_pattern.txt" || true


# ══════════════════════════════════════════
echo "5. КОМПОНЕНТНЫЕ ПАТТЕРНЫ"
# ══════════════════════════════════════════

# Active / selected состояния
g_app -e "aria-current" -e "aria-selected" -e "data-active" -e "data-selected" \
  > "$OUT/05_active_state_aria.txt" || true

# Ручные бейджи (паттерн: rounded-full + px + text-[10-11px])
g_app -E "rounded-full.{0,60}px-[0-9]" \
  > "$OUT/05_adhoc_badge_pattern.txt" || true

# Все файлы с ad-hoc badge паттерном
grep -rl $EXT $APP_EXCL \
  -e "rounded-full" \
  "$SRC" \
  | xargs -r grep -l "px-[12]\b" 2>/dev/null \
  > "$OUT/05_badge_candidate_files.txt" || true

# Использование готовых badge-компонентов из ui/
g_app -e "ClassificationBadge" -e "QcStatusBadge" -e "SeverityBadge" \
  > "$OUT/05_ui_badge_usage.txt" || true

# Кнопки — использование компонента vs нативный button
g_app -E "import.*Button.*from" \
  > "$OUT/05_button_import.txt" || true

g_app -E "<button\b" \
  > "$OUT/05_native_button_usage.txt" || true

g_app -E "<Button\b" \
  > "$OUT/05_ui_button_usage.txt" || true

# cva / clsx / cn паттерны
g_app -e "cva(" -e "clsx(" -e "cn(" \
  > "$OUT/05_class_composition.txt" || true


# ══════════════════════════════════════════
echo "6. SCROLL-МОДЕЛЬ"
# ══════════════════════════════════════════

g_app -e "overflow-y" -e "overflow-x" -e "overflow:" -e "overscroll-behavior" \
  > "$OUT/06_scroll_model.txt" || true

# sticky и fixed раздельно (избегаем ошибку с -E и -e вместе)
g_app -E "position:\s*(sticky|fixed)" \
  > "$OUT/06_sticky_fixed_usage.txt" || true

g_app -E "\bsticky\b|\bfixed\b" \
  >> "$OUT/06_sticky_fixed_usage.txt" || true

# AppShell специфично
grep -n "overflow\|scroll\|h-screen\|h-full\|min-h-0\|flex-1" \
  "$SRC/components/layout/AppShell.tsx" \
  > "$OUT/06_appshell_scroll_detail.txt" 2>/dev/null || true

# Двойной скролл риск: страницы с h-full + overflow-y-auto
g_app -E "h-full.{0,80}overflow-y-auto|overflow-y-auto.{0,80}h-full" \
  > "$OUT/06_double_scroll_risk.txt" || true


# ══════════════════════════════════════════
echo "7. ДОСТУПНОСТЬ"
# ══════════════════════════════════════════

# Изображения без alt
grep -rl $EXT $APP_EXCL -e "<img" "$SRC" \
  | xargs -r grep -L "alt=" 2>/dev/null \
  > "$OUT/07_images_missing_alt.txt" || true

# Подозрительные кликабельные div (построчно, не по файлу)
g_app -E "<div[^>]*onClick" \
  > "$OUT/07_clickable_divs_lines.txt" || true

# Из них те, где нет role= на той же строке
grep -v 'role=' "$OUT/07_clickable_divs_lines.txt" \
  > "$OUT/07_clickable_divs_no_role.txt" 2>/dev/null || true

# Все focus состояния
g_app -e "focus-visible" -e ":focus" \
  > "$OUT/07_focus_states.txt" || true

# Интерактивные элементы без focus-visible (подозреваемые файлы)
grep -rl $EXT $APP_EXCL -e "onClick" "$SRC" \
  | xargs -r grep -L "focus-visible" 2>/dev/null \
  > "$OUT/07_onclick_without_focus_visible.txt" || true

# aria-label покрытие
g_app -e "aria-label" \
  > "$OUT/07_aria_label_usage.txt" || true

# tabIndex явное использование
g_app -e "tabIndex" -e "tabindex" \
  > "$OUT/07_tabindex_usage.txt" || true


# ══════════════════════════════════════════
echo "8. LOGIN PAGE (отдельно — нет токенов)"
# ══════════════════════════════════════════

if [ -f "$SRC/pages/LoginPage.tsx" ]; then
  grep -nE "#[0-9a-fA-F]{3,8}|rgba?\([0-9]" \
    "$SRC/pages/LoginPage.tsx" \
    > "$OUT/08_loginpage_hardcoded_colors.txt" 2>/dev/null || true

  grep -n "var(--" \
    "$SRC/pages/LoginPage.tsx" \
    > "$OUT/08_loginpage_css_vars.txt" 2>/dev/null || true
fi


# ══════════════════════════════════════════
echo "9. ДУБЛИРОВАНИЕ ТОКЕНОВ (index.css)"
# ══════════════════════════════════════════

# Все переменные определённые более одного раза в index.css
grep -oE "--[a-zA-Z0-9-]+:" "$SRC/index.css" \
  | sort | uniq -c | sort -rn \
  | awk '$1 > 1' \
  > "$OUT/09_duplicate_var_definitions.txt" 2>/dev/null || true

# Переменные определённые в :root и использующиеся в app
grep -E "^\s*--" "$SRC/index.css" \
  | grep -v "@theme" \
  > "$OUT/09_root_layer_tokens.txt" 2>/dev/null || true


# ══════════════════════════════════════════
echo "ГЕНЕРАЦИЯ SUMMARY"
# ══════════════════════════════════════════

SUMMARY="$OUT/_SUMMARY.txt"
> "$SUMMARY"

for f in "$OUT"/*.txt; do
  [ "$(basename "$f")" = "_SUMMARY.txt" ] && continue
  lines=$(wc -l < "$f")
  {
    echo ""
    echo "════ $(basename "$f")  (строк: $lines) ════"
    if [ "$lines" -eq 0 ]; then
      echo "(пусто)"
    else
      head -60 "$f"
      [ "$lines" -gt 60 ] && echo "... (обрезано, показаны первые 60 из $lines)"
    fi
  } >> "$SUMMARY"
done

echo ""
echo "════════════════════════════════════"
echo "ГОТОВО"
echo "Файлов в audit-output: $(ls "$OUT"/*.txt | wc -l)"
echo "Строк в _SUMMARY.txt:  $(wc -l < "$SUMMARY")"
echo "Размер _SUMMARY.txt:   $(du -h "$SUMMARY" | cut -f1)"
echo "════════════════════════════════════"
echo ""
echo "Запусти:"
echo "  cat $FRONTEND_DIR/audit-output/_SUMMARY.txt"


