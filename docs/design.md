# Design implementation

The interface follows the supplied Figma screen designs: welcome, onboarding, interests, home, task catalogue, careers, opportunity details, points, events, profile, history quiz and rewards. The shift game remains intentionally unavailable while its screens are being designed.

The application uses React with TypeScript and plain CSS. Mobile frames have a 390 px maximum width and 20 px gutters, leaving a 350 px content area. On smaller screens the interface adapts to the viewport. Common typography uses Inter with system fallbacks: caption 11/15, label 13/18, body 15/21, title 18/24, heading 24/30 and display 32/38. The primary palette is red `#D50032`, burgundy `#AB2328`, paper `#FFF8F2`, blush `#FCE8EE`, line `#E9CDD4`, ink `#17171C` and muted `#626262`.

`src/styles.css` owns the application tokens, layout, shared controls, focus states, mobile navigation and reduced-motion behavior. `src/components/Art.tsx` reuses the exact local welcome artwork. The mascot source is a transparent four-pose raster, rendered at 432 × 144 px and clipped to one 108 × 144 px pose. The welcome history uses the three original vector assets at their intrinsic sizes. Game artwork is stored separately in `public/assets/games/`.

The design detail screen for a reward contains no reward-product illustration. No replacement product image is invented. Progress is dynamic so the percentage reflects the current account rather than the fixed value shown in the design.

## Extraction and verification

High-fidelity design context was translated into project CSS and reusable React components. Image assets were downloaded to local files; runtime components do not depend on temporary design-host asset URLs. Source context and reference screenshots are local working files excluded from publication.

Figwright was also attempted as requested. Its MCP stdio server started successfully and the desktop plugin was already installed. Both the current MCP release and an MCP version matching the installed desktop plugin were checked. A persistent relay listened on the configured local port, and the plugin was restarted. However, the plugin stayed in its reconnecting state, reporting no server; the server reported zero connected plugin sessions. No Figwright read or export succeeded. This is a transport connection limitation, and the implementation does not claim a successful Figwright extraction. The design document was not edited.
