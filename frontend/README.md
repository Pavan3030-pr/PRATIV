# SIGNALPOST (PRATIV) — Frontend

The interface for an enterprise agentic company intelligence platform: official Brreg registry
verification, source-backed evidence, and vector semantic lineage auditing in one workspace.

## Local development

```bash
npm ci
npm run dev
```

Vite proxies `/api`, `/oauth2`, and `/login/oauth2` to the backend and `/agent` to FastAPI. Set
`VITE_BACKEND_PROXY_TARGET` to use a different local backend. For a separately hosted frontend, set
`VITE_API_BASE_URL` to the public Spring Boot origin at build time. OAuth login requires
Google/GitHub client credentials and JWT/CORS configuration in the backend; see the root README
deployment guide. Preview identities shown while the API is offline are illustrative only.

```bash
npm run lint    # oxlint
npm run build   # tsc -b && vite build
```

Google and GitHub OAuth authenticate through Spring Security; the API client attaches a short-lived
JWT bearer token. Revenue and net profit remain withheld unless matching metric-level evidence
exists in the backend.

## Structure

```
src/
  App.tsx                  route selection: landing → auth → workspace
  index.css                design tokens (Tailwind v4 @theme), base layer, motion
  components/
    ui/                    Button, Card, Badge, Field/Input, Reveal primitives
    Brand.tsx              SIGNALPOST wordmark
    landing/               SiteHeader, Hero, TrustStrip, Narrative, FeatureGrid,
                           HowItWorks, Architecture, FinalCta, SiteFooter, LandingPage
    auth/                  AuthScreen + OAuth provider icons
    workspace/             WorkspacePage (state), Sidebar, OverviewView, RecordsView,
                           EvidenceView, LineageDrawer, LineageDetail
  context/, lib/, types.ts AuthContext, API client, and shared types — unchanged contracts
```

## Visual system

Editorial minimalism with a high-contrast, restrained palette:

- **Type** — Inter throughout. Large headlines use `clamp()` scales, `font-semibold`, and tight
  negative tracking (`-0.03em` to `-0.04em`); body copy sits at 15–17px with generous leading;
  labels are 11px uppercase with `0.16em` tracking. Identifier-style data (organization numbers,
  hashes, timestamps) uses the mono stack with tabular numerals.
- **Colour** — near-black ink (`#0A0A0A`) on paper white, cool neutrals for surfaces
  (`#FAFAFA` canvas, `#F4F4F5` sunken, `#ECECEE` hairlines). One accent, deep indigo (`#4338CA`),
  reserved for active navigation, links, kickers, and focus. Green/amber/red appear only to
  communicate state. Two dark bands (Architecture, footer) provide rhythm.
- **Surfaces** — flat cards with 1px hairline borders and a whisper shadow; elevation appears only
  on hover (`shadow-lift`) and on the drawer. Radii: 14px cards, 8px controls, pill buttons for
  marketing CTAs.
- **Spacing** — sections use 80/112px vertical padding on a shared `page-shell` (1180px max),
  so vertical rhythm stays consistent from hero to footer.
- **Icons** — Lucide line icons at 13–19px, tinted neutral or accent. Brand marks (Google,
  GitHub) are inline SVG.
- **Motion** — `Reveal` fades sections up 16px on intersection with staggered delays; the hero
  animates on load; the drawer slides in over 320ms. Everything collapses under
  `prefers-reduced-motion`.
- **Accessibility** — visible indigo focus rings, `aria-current` navigation, labelled sortable
  table headers, focus restore on drawer close, `role="alert"`/`role="status"` live regions, and
  keyboard-operable table rows.