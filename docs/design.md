# Design implementation

The interface follows the supplied Figma screen designs: welcome, onboarding, interests, home, task catalogue, careers, opportunity details, points, events, profile, history quiz and rewards. The shift investigation is included: overview, individual metric histories, line scheme, event journal and details, checks, pinned observations, explanation and team review.

The application uses React with TypeScript and plain CSS. Mobile frames have a 390 px maximum width and 20 px gutters, leaving a 350 px content area. On smaller screens the interface adapts to the viewport. Common typography uses locally bundled Inter Variable with system fallbacks: caption 11/15, label 13/18, body 15/21, title 18/24, heading 24/30 and display 32/38. The primary palette is red `#D50032`, burgundy `#AB2328`, paper `#FFF8F2`, blush `#FCE8EE`, line `#E9CDD4`, ink `#17171C` and muted `#626262`.

`src/styles.css` owns the application tokens, layout, shared controls, focus states, mobile navigation and reduced-motion behavior. `src/components/Art.tsx` reuses the exact local welcome artwork. The mascot source is a transparent four-pose raster, rendered at 432 × 144 px and clipped to one 108 × 144 px pose. The welcome history uses the three original vector assets at their intrinsic sizes. Game artwork is stored separately in `public/assets/games/`.

The design detail screen for a reward contains no reward-product illustration. No replacement product image is invented. Progress is dynamic so the percentage reflects the current account rather than the fixed value shown in the design.

## Extraction and verification

High-fidelity design context was translated into project CSS and reusable React components. Image assets were downloaded to local files; runtime components do not depend on temporary design-host asset URLs. Source context and reference screenshots are local working files excluded from publication.

Figwright was used successfully through its local MCP relay connected to the installed Figma Desktop plugin. A successful end-to-end ping confirmed one connected plugin session. Its `get_design_context` read confirmed the home frame is 390 × 844 px with vertical auto-layout, 20 px padding and 16 px spacing. `save_screenshots` exported the home and welcome frames as PNG files. These reference images and the full read/export responses are retained only in the local, ignored design working directory. The document was not edited.

The installed desktop plugin required a matching MCP version and a persistent local server before its reconnecting state resolved. The completed read and export confirm the transport now works; no user action is required to connect it.

## Shift investigation

The updated investigation screens were extracted through Figwright as full design context and PNG references, including all twelve metric details, the line scheme, checks, event details, evidence list, explanation form and team review. The usable observation example contains three selected facts; a hidden duplicate frame is excluded from implementation. All raw context, screenshots and export responses remain in the ignored local design directory.

The investigation follows the same 390 px frame and 20 px gutters. Its content uses 12 px vertical spacing; the overview has three 111⅓ px columns with 8 px gaps and 78 px cards. Metric detail charts occupy 350 × 176 px and the scheme occupies 350 × 270 px. Both bind their displayed measurements to scenario data. The scheme connector is exported unchanged as a local SVG; typography, controls, cards and data visualization labels remain accessible application content.

## Registration age restriction

A dedicated registration screen uses the existing typography and colors, a blush circular backdrop, a restrained 18+ badge and a sad variation of the opener mascot. It explains the age condition and offers a date-correction action without registering a profile. The illustration is a local transparent PNG generated from the existing mascot using the built-in image-generation tool; it is not a new extracted design frame. See `docs/age-gate.md` for the text, source asset and prompt.

## Event activities and scanner

The event detail includes activity cards with title, description, current reward and completion state. Completed cards display their historical awarded points and Moscow completion time. The scanner is available from Events and from event details. It uses the app palette and accessible native controls, with an explicit camera action, local image selection, a manual-code fallback and separate successful/repeated result states. No new design extraction was needed for these application components.
