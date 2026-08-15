# Design System: PayNest — Editorial Command

> Source of truth for prompting new screens. Tokens are defined in
> `static/css/editorial-system.css` (canonical `--pn-*` variables) and the
> Tailwind CDN config in `templates/base_new.html` (color/font/radius/shadow
> scales). Consume tokens, never invent hex values.

## 1. Visual Theme & Atmosphere

**Calm, confident, data-first professional.** PayNest reads like a financial
editorial brand — deep teal anchors, warm neutral canvas, and generous white
space. The interface is *quiet but decisive*: almost everything rests on a
near-white canvas (#f9f9fa) washed with two soft radial glows — a pale teal
veil top-left and a faint warm peach top-right — so pages feel lit rather than
flat. Density is moderate-to-low: whitespace is generous, cards breathe, and
only payroll figures carry visual weight (via tabular numerals and Manrope
headlines). Nothing shouts; hierarchy is achieved through ink weight, teal
accents, and pill-shaped micro-labels rather than saturated color blocks.
Status is always encoded in soft tinted chips with dark text — never neon.

## 2. Color Palette & Roles

All roles below follow the 60-30-10 rule: ~60% canvas/surfaces, ~30% ink and
teal accents, ~10% status and CTA highlights.

### Canvas & Surfaces (60%)
- **Porcelain Canvas** (#f9f9fa) — page background; also the `surface` token.
- **Cloud White** (#ffffff) — `surface-container-lowest`; card and panel fills.
- **Mist** (#f3f4f4) — `surface-container-low`; table header bands, muted wells.
- **Fog** (#edeeef) — `surface-container`; secondary wells, `surface-card-muted`.
- **Ash** (#e2e2e3) — `surface-container-highest`; subtle separators and hover bases.
- **Dusk** (#d9dadb) — `surface-dim`; placeholders and disabled wells.

### Brand & Ink (30%)
- **Deep Teal** (#005c73) — `primary-600`; the brand's core — primary buttons,
  links, active nav, `primary-container`.
- **Teal Ink** (#004355) — `primary-800` / `--pn-primary-strong`; section titles
  and emphasized headings.
- **Midnight Teal** (#18667e) — `primary-500`; hover states and focus rings.
- **Ink** (#1a1c1d) — `secondary-900` / `--pn-text`; body text and `on-surface`.
- **Slate Smoke** (#536167) — `secondary-600` / `--pn-muted`; secondary text,
  captions, table micro-headers.
- **Pewter** (#70787d) — `secondary-500` / `outline`; borders and icons.
- **Abyss Teal** (#014355) — `tertiary`; eyebrow labels and deep accent text.

### Status & Highlights (10%)
- **Moss Green** (#1f7b48) — `success-600`; confirmed/paid/remitted states,
  filled with soft **Pale Sage** (#daf4e4) and deep **Forest Text** (#174f31).
- **Ember Orange** (#c2410c) — `warning-600`; due-soon states, soft fill
  **Apricot Wash** (#ffedd5), deep text **Burnt Sienna** (#7c2d12).
- **Crimson** (#ba1a1a) — `danger-600`; overdue/error/delete, soft fill
  **Rose Wash** (#ffdad6), deep text **Wine** (#740006).
- **Teal Tint** (#e7f6fa) — `primary-soft` / `info` fills with **Teal Ink**
  (#004355) text for informational badges and alerts.

## 3. Typography Rules

Two families, strictly separated by job:

- **Manrope (700/800)** — *headline voice.* Display and section titles, card
  titles, hero headlines, stat-block numbers. Tight letter-spacing (-0.01 to
  -0.02em), balanced wrapping (`text-wrap: balance`).
- **Inter (400/500/600)** — *body voice.* All body copy, labels, tables, nav.

Type scale (from `tailwind.config` in `base_new.html`):

| Token | Size/Line | Weight | Tracking | Use |
| --- | --- | --- | --- | --- |
| `display-lg` | 48/52px | 800 | -0.02em | Marketing hero headlines |
| `headline-lg` | 32/40px | 700 | -0.01em | Page titles |
| `headline-md` | 24/32px | 700 | 0 | Card/section titles |
| `title-lg` | 20/28px | 600 | 0 | Sub-section titles |
| `body-lg` | 16/24px | 400 | 0 | Lead paragraphs |
| `body-md` | 14/20px | 400 | 0 | Default body |
| `label-md` | 12/16px | 600 | +0.05em | Uppercase micro-labels |
| `data-tabular` | 14/20px | 500 | 0 | Payroll figures (`tabular-nums`) |

Numbers and money always render with `font-variant-numeric: tabular-nums` so
columns align. Micro-labels are uppercase, letterspaced, and weight 600-800.

## 4. Component Stylings

- **Buttons:** Gently rounded (0.8125rem). Primary and success variants are
  filled **Deep Teal** (#005c73) / **Moss Green** (#1f7b48) with white text and
  *no* resting shadow; hover deepens the fill slightly. Secondary/outline
  variants are white with a thin border. Danger is filled **Crimson**
  (#ba1a1a). Disabled states drop to 58% opacity with `not-allowed` cursor.
- **Cards / Containers:** White (**Cloud White**), softly rounded (1.125rem
  standard, 1.5rem for `surface-card`, 1rem for `bento-card`, 1.75rem for the
  page hero). Flat at rest; on hover they lift with whisper-soft diffused
  shadows (`0 16px 36px rgba(26,28,29,.06)`) and a faint teal border tint.
  Never hard-edged, never glowing.
- **Inputs / Forms:** Matching 0.8125rem radius, flat white background with a
  hairline border; focus draws a 3px soft teal ring
  (`rgba(24,102,126,.13)`) plus the global teal focus outline.
- **Badges & Chips:** Pill-shaped (999px radius). Always soft tinted fills with
  deep readable text — never solid saturated chips: success = **Pale Sage** /
  **Forest Text**, warning = **Apricot Wash** / **Burnt Sienna**, danger =
  **Rose Wash** / **Wine**, info = **Teal Tint** / **Teal Ink**.
- **Alerts:** Borderless, same tinted-fill language as badges, control-radius.
- **Tables:** `table-shell` — a 1.25rem-rounded bordered container; header rows
  on **Mist** with uppercase 0.12em letterspaced 800-weight micro-labels in
  **Slate Smoke**; hairline row separators; hover tints rows with pale teal
  (`rgba(231,246,250,.55)`).
- **Hero / Page header:** `page-hero` — a deep-teal diagonal gradient
  (Teal Ink → Deep Teal → pale teal) with white text and a primary-tinted
  shadow (`0 20px 42px rgba(0,67,85,.15)`).
- **Section eyebrow:** a tiny uppercase pill (peach tint
  `rgba(255,220,194,.58)`, **Abyss Teal** text, 0.22em tracking) above section
  titles.
- **Icons:** Lucide, 1:1 stroke icons at consistent sizes; color follows text
  color (muted icons in **Pewter**, active in **Deep Teal**).

## 5. Layout Principles

- **Whitespace is a tool.** Cards pad at 1.5rem (1.25rem on mobile); sections
  stack with generous vertical rhythm. Nothing crowds.
- **Progressive section pattern:** eyebrow pill → Manrope 800 title
  (`clamp(1.5rem, 2vw, 2rem)`) → muted subtitle (line-height 1.65). Used
  identically across marketing pages and in-app dashboards.
- **Grid alignment:** 12-column feel via Tailwind's `sm 480 / md 768 / lg 976 /
  xl 1440` breakpoints. Dashboards arrange status/metric panels as a bento grid
  of equal-height cards; content columns are max-width-constrained and
  centered on the canvas.
- **Mobile (<768px):** sidebar collapses, cards stack full-width, controls go
  full-width, tables scroll inside `table-shell`. Buttons never overflow.
- **Layering:** the `page-shell` sits above the canvas's radial washes with a
  soft white-to-transparent overlay; content rides at `z-index: 1`. Elevation
  is expressed through shadow, not color.
- **Motion:** restrained — `fade-in` (0.35s) for page content, `slide-up`
  (0.3s) for notifications, 0.3s hover transitions. Fully disabled under
  `prefers-reduced-motion`.
- **Accessibility baked in:** 3px teal `focus-visible` outline with 3px offset
  on every interactive element, skip-link, WCAG-AA text contrast, and a print
  stylesheet that strips chrome and flattens backgrounds.
