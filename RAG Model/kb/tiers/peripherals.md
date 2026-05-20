---
namespace: tiers
tier: OTHER
tags: [peripherals, accessories, bundling]
last_reviewed: 2026-05-01
---

Peripherals — keyboards, mice, monitors, headphones, microphones, cables, chargers, USB hubs — are tracked in inventory as item types `input`, `display`, `audio`, `connectivity`. Mobile items (phones, tablets, Chromebooks) are item type `mobile` and have their own role.

## Bundling policy (MVP)

The MVP engine does not auto-bundle peripherals with a primary computer match. The fit gate explicitly rejects peripherals as standalone matches because no applicant in the 7-question intake asks for a mouse on its own. Bundling decisions are deferred to LGT staff after the engine returns a primary device.

When LGT staff bundle, the typical patterns are:
- A monitor for an applicant in software engineering, design, or healthcare clinical roles where dual-screen workflow is essential.
- A keyboard and mouse for any laptop being used as a desk-bound primary device.
- A headphone/microphone for any applicant with regular video calls (every category).

## Mobile

Mobile is a first-class item type. Categories D (seniors) and F (newcomers) may be matched to a Mobile as their primary device when the use case is video calling and reading rather than typing-heavy work.
