# Frontend design system

## Purpose

The SSK interface is designed for frequent administrative work with sensitive social-services records. It favors compact information density, obvious working context, predictable actions, and high contrast over decorative presentation.

The frontend remains server-rendered Django. The only client script manages the responsive navigation drawer, synchronizes the compact top-bar title, closes menus with Escape, and asks for confirmation before selected destructive actions.

## Color tokens

All interface colors are defined as custom properties in `static/css/app.css`.

| Token group | Purpose |
|---|---|
| Brand yellow | Active navigation, focus, selected text, and limited emphasis |
| Near-black and charcoal | Sidebar, primary actions, headings, and strong hierarchy |
| White and warm off-white | Content surfaces and the application canvas |
| Neutral gray | Borders, secondary copy, metadata, and inactive controls |
| Green | Successful, completed, and active states |
| Orange | Draft, pending, no-show, and warning states |
| Red | Failed, cancelled, inactive, and destructive states |

Yellow is never used as body text on white and never communicates a status by itself. Semantic status badges include visible text and a colored dot.

## Typography and spacing

The system font stack supports English and Georgian without loading third-party assets. Page headings use a compact fluid scale. Labels, table headings, and metadata use smaller sizes with stronger weights to retain hierarchy in dense screens.

Spacing follows quarter-rem increments. Components use three restrained radius tokens and two subtle shadow tokens. Shadows are limited to the user menu, mobile drawer, and authentication panel.

## Application shell

- Desktop uses a persistent near-black sidebar with text and icons.
- The current section has a yellow edge and `aria-current="page"`.
- The top bar keeps the page title, active center, role, language, and sign-out controls visible.
- At 1024 pixels and below, the sidebar becomes a keyboard-operable drawer with an overlay, Escape handling, and focus restoration.
- Manager-only destinations are omitted for other roles as a usability aid. Server authorization remains authoritative.

## Components

### Buttons

- Primary: near-black for the main save or create action.
- Secondary: yellow for high-priority supporting actions and filter submission.
- Quiet: white with a neutral border for navigation and cancellation.
- Danger: white with red text and border. Record deletion also uses a dedicated confirmation page.

### Tables

Tables use sticky headers, compact rows, strong first-column hierarchy, explicit status text, and focusable horizontal-scroll regions. The page itself never overflows at narrow widths.

### Forms

Forms use persistent labels, visible required markers, grouped sections, inline errors, linked validation summaries, helpful descriptions only where needed, and sticky save/cancel actions on long screens. Relationship fields and validation remain backed by authorized server-side querysets.

### Empty and error states

Empty states explain why content is missing and provide an available next action. Permission, not-found, server-error, reset-link, and destructive confirmation states share the same visual hierarchy and accessible heading structure.

### Beneficiary timeline

The beneficiary detail page presents authorized case activity as a semantic ordered list. Every entry has a visible date, textual type label, linked title, optional status text, and explicit record or download action. Type colors support scanning but never replace the type label. The desktop date rail collapses to a single-column layout on narrow screens. Pagination remains server-rendered and preserves existing query parameters. The empty timeline uses a live status region with a heading and explanatory text.

## Accessibility rules

- Keep one `h1` per page and do not skip heading levels.
- Use semantic controls instead of clickable generic elements.
- Keep labels visible and associate help and error text with stable IDs.
- Preserve the skip link and visible yellow focus outline.
- Include text in every status and navigation item.
- Keep interactive targets at least 2.5rem high where practical.
- Test the drawer, menus, tables, and forms with keyboard input.
- Check English and Georgian at 320, 768, 1024, and 1440 pixels.

## Maintenance

Reuse existing tokens and component classes before adding variants. New status values require a visible label and an appropriate semantic modifier. New pages should extend `templates/base.html`, use the standard page header, and place dense data in a focusable `.table-wrap` region.
