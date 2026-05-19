---
name: Academic Excellence
colors:
  surface: '#f8f9ff'
  surface-dim: '#cbdbf5'
  surface-bright: '#f8f9ff'
  surface-container-lowest: '#ffffff'
  surface-container-low: '#eff4ff'
  surface-container: '#e5eeff'
  surface-container-high: '#dce9ff'
  surface-container-highest: '#d3e4fe'
  on-surface: '#0b1c30'
  on-surface-variant: '#434653'
  inverse-surface: '#213145'
  inverse-on-surface: '#eaf1ff'
  outline: '#747685'
  outline-variant: '#c4c6d6'
  surface-tint: '#2a56c7'
  primary: '#002b80'
  on-primary: '#ffffff'
  primary-container: '#003fb1'
  on-primary-container: '#a1b6ff'
  inverse-primary: '#b5c4ff'
  secondary: '#006d3d'
  on-secondary: '#ffffff'
  secondary-container: '#97f3b5'
  on-secondary-container: '#057240'
  tertiary: '#4b2d00'
  on-tertiary: '#ffffff'
  tertiary-container: '#694100'
  on-tertiary-container: '#ffa61a'
  error: '#ba1a1a'
  on-error: '#ffffff'
  error-container: '#ffdad6'
  on-error-container: '#93000a'
  primary-fixed: '#dbe1ff'
  primary-fixed-dim: '#b5c4ff'
  on-primary-fixed: '#00174c'
  on-primary-fixed-variant: '#003dab'
  secondary-fixed: '#9af6b8'
  secondary-fixed-dim: '#7ed99e'
  on-secondary-fixed: '#00210f'
  on-secondary-fixed-variant: '#00522d'
  tertiary-fixed: '#ffddb8'
  tertiary-fixed-dim: '#ffb95f'
  on-tertiary-fixed: '#2a1700'
  on-tertiary-fixed-variant: '#653e00'
  background: '#f8f9ff'
  on-background: '#0b1c30'
  surface-variant: '#d3e4fe'
typography:
  headline-xl:
    fontFamily: Inter
    fontSize: 40px
    fontWeight: '700'
    lineHeight: 48px
    letterSpacing: -0.02em
  headline-lg:
    fontFamily: Inter
    fontSize: 32px
    fontWeight: '700'
    lineHeight: 40px
    letterSpacing: -0.02em
  headline-lg-mobile:
    fontFamily: Inter
    fontSize: 24px
    fontWeight: '700'
    lineHeight: 32px
  headline-md:
    fontFamily: Inter
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 32px
  body-lg:
    fontFamily: Inter
    fontSize: 18px
    fontWeight: '400'
    lineHeight: 28px
  body-md:
    fontFamily: Inter
    fontSize: 16px
    fontWeight: '400'
    lineHeight: 24px
  label-md:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: '500'
    lineHeight: 20px
    letterSpacing: 0.01em
  label-sm:
    fontFamily: Inter
    fontSize: 12px
    fontWeight: '600'
    lineHeight: 16px
rounded:
  sm: 0.25rem
  DEFAULT: 0.5rem
  md: 0.75rem
  lg: 1rem
  xl: 1.5rem
  full: 9999px
spacing:
  base: 8px
  xs: 4px
  sm: 12px
  md: 24px
  lg: 40px
  xl: 64px
  gutter: 24px
  margin: 32px
---

## Brand & Style
The design system is rooted in the concepts of authority, clarity, and academic progression. It balances the rigor of institutional education with a modern, approachable digital experience. The aesthetic follows a **Corporate/Modern** direction infused with **Soft UI** elements to reduce cognitive load and create a welcoming environment for both students and educators. 

The visual narrative is built on high-legibility typography, generous white space, and a refined use of depth through soft, ambient shadows. It aims to evoke a sense of reliability and focus, ensuring that the interface never distracts from the educational content.

## Colors
This design system utilizes a structured palette designed for academic hierarchy. 

*   **Primary Blue (#003FB1):** The institutional core. Used for primary actions, navigation headers, and brand signifiers.
*   **Academic Green (#2D8A56):** Used for secondary accents, highlighting progress, and positive reinforcements.
*   **Functional Palette:** 
    *   **Success:** A vibrant emerald to denote completion.
    *   **Error:** A high-visibility red for alerts and validation failures.
    *   **Process:** An amber/orange hue to indicate pending states or "in-progress" coursework.
    *   **Neutral:** A versatile range of cool grays for borders, secondary text, and background layers.

## Typography
Inter is the exclusive typeface for this design system, chosen for its exceptional legibility in dense academic contexts. 

Headlines use a tighter letter-spacing and heavier weights to establish a clear hierarchy. Body text is optimized for long-form reading with generous line heights (1.5x) to ensure focus. Labels and small metadata use medium to semi-bold weights to maintain visibility at smaller scales. On mobile devices, headline sizes scale down to prevent excessive line-breaking while maintaining the same weight ratios.

## Layout & Spacing
The design system employs a **12-column fluid grid** for desktop and a **4-column grid** for mobile. 

The spacing rhythm is based on an 8px scale, ensuring consistency across all components. Layouts should prioritize large margins and gutters (24px - 32px) to prevent the "cluttered" feel common in legacy educational software. Elements are grouped using logical nesting: 8px for internal component spacing (e.g., icon to text) and 24px+ for section spacing.

## Elevation & Depth
Depth is created through **Ambient Shadows** and **Tonal Layers**. This "Soft UI" approach avoids harsh black shadows in favor of tinted, diffused blurs.

*   **Surface Level 0:** The main canvas, using a very light neutral gray (#F8FAFC).
*   **Surface Level 1 (Cards):** Pure white background with a 16px blur shadow at 4% opacity, tinted with the Primary Blue.
*   **Surface Level 2 (Modals/Popovers):** Pure white background with a 32px blur shadow at 8% opacity.

The goal is to make cards appear to "float" gently above the canvas, guiding the user's eye to the interactive content without creating high-contrast visual noise.

## Shapes
The shape language is consistently **Rounded**. 

The base radius is 0.5rem (8px), applied to buttons, input fields, and small UI elements. For larger containers such as lesson cards or dashboard widgets, use `rounded-lg` (16px) or `rounded-xl` (24px) to emphasize the soft, approachable nature of the platform. This curvature offsets the professional blue color palette, making the experience feel more modern and less institutional.

## Components

### Buttons & Inputs
Buttons should have a 0.5rem corner radius. The Primary button uses the Deep Institutional Blue with white text. Inputs should feature a subtle 1px border in a light neutral gray, which transitions to a 2px Primary Blue border on focus, accompanied by a soft blue outer glow.

### Soft UI Cards
Cards are the primary container for content. They must always feature a white background, rounded corners (16px), and the defined ambient shadow. Internal padding should be at least 24px.

### Breadcrumbs
Breadcrumbs use the `label-md` typography. Use the Primary Blue for the current page and Neutral Gray for parent links. Use a chevron-right icon as a separator. Breadcrumbs should be placed at the very top of the content area, below the main navigation.

### Empty States
Empty states should be centered both vertically and horizontally. They must include:
1.  **Illustration:** A stylized, low-contrast academic illustration using the secondary green and neutral grays.
2.  **Title:** `headline-md` weight.
3.  **Description:** `body-md` in Neutral Gray.
4.  **CTA:** A primary button to guide the user toward the first step (e.g., "Add your first course").

### Iconography
Icons must be consistent in stroke weight (2px) and style (Rounded Linear). Academic icons (books, caps, lightbulbs) should be used to provide visual cues for different content types.