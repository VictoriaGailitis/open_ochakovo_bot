# Design implementation

The interface follows the supplied Figma screen designs: welcome, onboarding, interests, home, task catalogue, careers, opportunity details, points, events, profile, history quiz and rewards. The shift game remains intentionally unavailable while its screens are being designed.

The application uses React with TypeScript and plain CSS. Mobile frames have a 390 px maximum width and 20 px gutters, leaving a 350 px content area. On smaller screens the interface adapts to the viewport. Common typography uses locally bundled Inter Variable with system fallbacks: caption 11/15, label 13/18, body 15/21, title 18/24, heading 24/30 and display 32/38. The primary palette is red `#D50032`, burgundy `#AB2328`, paper `#FFF8F2`, blush `#FCE8EE`, line `#E9CDD4`, ink `#17171C` and muted `#626262`.

`src/styles.css` owns the application tokens, layout, shared controls, focus states, mobile navigation and reduced-motion behavior. `src/components/Art.tsx` reuses the exact local welcome artwork. The mascot source is a transparent four-pose raster, rendered at 432 × 144 px and clipped to one 108 × 144 px pose. The welcome history uses the three original vector assets at their intrinsic sizes. Game artwork is stored separately in `public/assets/games/`.

The design detail screen for a reward contains no reward-product illustration. No replacement product image is invented. Progress is dynamic so the percentage reflects the current account rather than the fixed value shown in the design.

## Extraction and verification

High-fidelity design context was translated into project CSS and reusable React components. Image assets were downloaded to local files; runtime components do not depend on temporary design-host asset URLs. Source context and reference screenshots are local working files excluded from publication.

Figwright was used successfully through its local MCP relay connected to the installed Figma Desktop plugin. A successful end-to-end ping confirmed one connected plugin session. Its `get_design_context` read confirmed the home frame is 390 × 844 px with vertical auto-layout, 20 px padding and 16 px spacing. `save_screenshots` exported the home and welcome frames as PNG files. These reference images and the full read/export responses are retained only in the local, ignored design working directory. The document was not edited.

The installed desktop plugin required a matching MCP version and a persistent local server before its reconnecting state resolved. The completed read and export confirm the transport now works; no user action is required to connect it.
