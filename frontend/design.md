# Design System: Anthropic-style for Steloom

## 1. Color Palette

### Backgrounds
- `--bg-base`: #FAF8F5 (warm cream — основной фон)
- `--bg-surface`: #F3F0EB (slightly darker cream — секции)
- `--bg-card`: #FFFFFF (белые карточки)
- `--bg-elevated`: #FFFFFF (модалки, dropdowns)
- `--bg-dark`: #1A1917 (dark sections, footer)

### Text
- `--text-primary`: #1A1917 (warm black)
- `--text-secondary`: #78756F (warm gray)
- `--text-muted`: #A8A29E (stone-400 equivalent)
- `--text-inverse`: #FAF8F5 (on dark bg)

### Accent / Brand
- `--accent`: #C86B52 (warm terracotta — primary CTA, links)
- `--accent-hover`: #B55D46 (darker terracotta)
- `--accent-muted`: rgba(200, 107, 82, 0.10)
- `--accent-subtle`: #F5EBE7 (very light terracotta bg)

### Borders
- `--border`: #E8E4DD (warm light border)
- `--border-strong`: #D6D0C7
- `--border-subtle`: #F0ECE6

### Semantic (keep from original)
- success: #059669
- warning: #D97706
- danger: #DC2626

## 2. Typography

### Font Stack
- Display (headlines): 'Tiempos Head', 'Reckless Neue', Georgia, serif
  - Fallback: use 'Instrument Serif' (already loaded) or switch to 'Playfair Display'
- Body (UI): 'Inter', system-ui, sans-serif (already loaded ✓)

### Scale
- Hero H1: clamp(3rem, 5.5vw, 5rem) / line-height 1.05 / tracking -0.03em
- Section H2: clamp(2.25rem, 4vw, 3.5rem) / line-height 1.08 / tracking -0.02em
- H3: 1.75rem / line-height 1.2 / tracking -0.01em
- Body: 1rem / line-height 1.7
- Small/UI: 0.875rem / line-height 1.5
- Eyebrow: 0.75rem / uppercase / tracking 0.14em / weight 500

### Weights
- Regular: 400 (body)
- Medium: 500 (UI, eyebrows)
- Semibold: 600 (card titles)
- Light: 300 (hero display — optional)

## 3. Spacing & Layout

### Container
- max-width: 1200px (slightly narrower than current 1280px — more editorial)
- padding-x: 1.5rem (mobile), 2rem (tablet), 3rem (desktop)

### Section Spacing
- Section padding-y: 6rem (desktop), 4rem (mobile)
- Gap between elements: 1.5rem — 3rem

### Grid
- 12-column grid with gap-6 to gap-8
- Asymmetric splits: 5/7, 4/8, 7/5 (keep current pattern)

## 4. Radius & Shadows

### Border Radius
- `--radius-sm`: 6px (small UI elements)
- `--radius-md`: 12px (inputs, small cards)
- `--radius-lg`: 16px (main cards)
- `--radius-xl`: 24px (large panels)
- `--radius-pill`: 9999px (buttons, badges)

### Shadows (very subtle — Anthropic uses almost no shadows)
- `--shadow-sm`: 0 1px 2px rgba(26, 25, 23, 0.04)
- `--shadow-md`: 0 4px 12px rgba(26, 25, 23, 0.06)
- `--shadow-lg`: 0 8px 24px rgba(26, 25, 23, 0.08)

## 5. Component Patterns

### Buttons
- Primary: bg-accent, text-white, rounded-pill, px-6 py-3, font-medium
- Secondary: bg-transparent, border border-border, text-primary, rounded-pill
- Ghost: no bg, no border, text-accent, underline on hover
- Hover: subtle bg darken (no shadow)

### Cards
- bg-card, border border-border, rounded-xl (16px)
- padding: 2rem (32px)
- NO shadows (Anthropic style — flat, border-defined)
- Hover: border-color darken slightly

### Badges / Eyebrows
- bg-accent-subtle, text-accent, rounded-pill, px-3 py-1
- font-size: 0.75rem, font-weight: 500, tracking: 0.05em

### Navigation
- Clean, minimal, no background blur on scroll (or very subtle)
- Logo left, nav center/right, CTA right
- Active state: text-primary with subtle underline

### Hero
- Large serif headline, generous line-height
- Subtitle in sans-serif, text-secondary
- CTA below with spacing
- Minimal decoration (no heavy gradients)

## 6. Motion
- Transitions: 200ms ease-out (fast, not bouncy)
- Fade-in on scroll: subtle translateY(8px) + opacity
- No heavy animations — editorial calm

## 7. Key Differences from Current Steloom
- ❌ Remove: heavy grain overlay, glass-panel effects, dark hero with video bg
- ❌ Change: rounded-[28px]/[32px] → rounded-xl (16px) — less "pillowy"
- ❌ Change: bg-[#ece5d8] cards → white cards with borders — cleaner
- ❌ Change: dark green accent → warm terracotta
- ✅ Keep: serif headlines (Instrument Serif works well)
- ✅ Keep: editorial layout structure
- ✅ Keep: asymmetric grids
- ✅ Add: more whitespace, calmer palette


