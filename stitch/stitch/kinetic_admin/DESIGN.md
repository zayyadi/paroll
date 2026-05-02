```markdown
# Design System Specification: The Architectural Pulse

## 1. Overview & Creative North Star
### Creative North Star: "The Editorial Command"
This design system rejects the "SaaS-in-a-box" aesthetic. Instead of a rigid, claustrophobic grid of boxes and borders, we embrace the feel of a high-end business journal. The goal is to transform complex HR data into a legible, authoritative narrative.

We achieve this through **Intentional Asymmetry** and **Tonal Depth**. By utilizing wide margins, dramatic typographic scales, and layered surfaces, we move away from "software" and toward "experience." This system treats information as a curated exhibition—spacious, premium, and inherently trustworthy.

---

## 2. Colors & Surface Philosophy
The palette is rooted in deep, intellectual teals and blues (`primary: #004355`), balanced by a sophisticated neutral foundation.

### The "No-Line" Rule
**Strict Mandate:** Traditional 1px solid borders (`#CCCCCC` or similar) are prohibited for sectioning. 
Structure must be defined through:
*   **Background Shifts:** Use `surface-container-low` for sidebars sitting against a `surface` main stage.
*   **Tonal Transitions:** Define a dashboard widget by placing a `surface-container-lowest` card on a `surface-container` background.

### Surface Hierarchy & Nesting
Treat the UI as physical layers of fine paper. 
*   **Base:** `surface` (#f9f9fa) – The desk.
*   **Sectioning:** `surface-container-low` (#f3f4f4) – Large layout blocks.
*   **Actionable Cards:** `surface-container-lowest` (#ffffff) – The primary focus area.
*   **High-Priority Overlays:** `surface-container-highest` (#e2e2e3) – For subtle emphasis or inactive states.

### The Glass & Gradient Rule
To inject "soul" into the HRMS, use Glassmorphism for floating elements (e.g., User Profile popovers). 
*   **Implementation:** Use a semi-transparent `surface` color (80% opacity) with a `backdrop-blur` of 12px.
*   **Signature Gradients:** For primary Action Buttons or high-level Analytics Heroes, use a linear gradient from `primary` (#004355) to `primary_container` (#005c73) at a 135° angle.

---

## 3. Typography: The Editorial Voice
We utilize two distinct families to balance authority with utility.

*   **Display & Headlines (Manrope):** This is our "Editorial" voice. Use `display-lg` and `headline-md` with tight letter-spacing (-0.02em) to create a sense of executive presence.
*   **Body & Labels (Inter):** Our "Utility" voice. Inter is chosen for its exceptional legibility in dense data environments like payroll tables and employee directories.

**Contrast as Hierarchy:**
Use `on_surface` (#1a1c1d) for primary text and `on_surface_variant` (#40484c) for metadata. The high contrast between `Manrope` headlines and `Inter` body text provides a clear mental map for the user.

---

## 4. Elevation & Depth
In this system, "Elevation" is a feeling, not a drop-shadow effect.

### The Layering Principle
Avoid the "floating shadow" look. Instead, achieve lift by stacking surface tiers. A `surface-container-lowest` card (Pure White) placed on a `surface-dim` (#d9dadb) background creates a natural, crisp "pop" without a single shadow pixel.

### Ambient Shadows
When a component must float (Modals, Tooltips):
*   **Shadow Color:** Use a tinted version of `on_surface` (10% opacity) rather than grey.
*   **Blur:** Use a minimum of `24px` blur with a `y-offset` of `8px` to simulate soft, natural overhead lighting.

### The "Ghost Border" Fallback
If accessibility requires a container boundary, use the **Ghost Border**: 
*   `outline_variant` (#bfc8cc) at **15% opacity**. It should be felt, not seen.

---

## 5. Components: Refined Primitives

### Buttons
*   **Primary:** Gradient of `primary` to `primary_container`. `Rounded-md` (0.75rem). No border.
*   **Secondary:** `surface_container_high` background with `on_secondary_container` text.
*   **Tertiary:** Transparent background, `primary` text, no border. Only a subtle `surface_container_low` background on hover.

### Cards & Data Lists
*   **Prohibition:** No horizontal divider lines.
*   **Separation:** Use `spacing-6` (2rem) of vertical white space or alternating backgrounds (`surface` to `surface_container_low`).
*   **Table Header:** Use `label-md` in all-caps with `letter-spacing: 0.05em` for a professional, "Report" feel.

### Input Fields
*   **Style:** Minimalist. No bottom line or full box. Use `surface_container_low` as a subtle background fill with `rounded-sm` (0.25rem).
*   **Focus State:** A 2px "Ghost Border" using `surface_tint` at 40% opacity.

### The "Pulse" Dashboard Widget
*   A custom component for HR metrics. It uses a `surface-container-lowest` card with a `tertiary_fixed` (#ffdcc2) accent bar on the left edge (4px wide) to denote "Live" or "Active" data.

---

## 6. Do’s and Don’ts

### Do
*   **Do** use `spacing-10` and `spacing-12` for layout margins to create breathing room.
*   **Do** use `rounded-lg` (1rem) for large dashboard cards to soften the professional tone.
*   **Do** use `tertiary` (#5f3201) sparingly for high-value alerts or "New Feature" callouts.

### Don't
*   **Don't** use pure black (#000000) for text; always use `on_surface`.
*   **Don't** use "Card-in-Card" layouts without shifting the surface tier (e.g., an inner card must be a different `surface-container` level than its parent).
*   **Don't** use 1px dividers to separate list items; let the white space do the work.

---

## 7. Role-Based Visual Cues
*   **Admin/HR View:** High-density layouts using `body-sm` and `label-md` to prioritize data-over-pixels.
*   **Employee View:** Low-density, "Lifestyle" layouts using `display-sm` and `body-lg` to prioritize clarity and ease of use. Use more `surface-container-lowest` (white) to feel light and approachable.```