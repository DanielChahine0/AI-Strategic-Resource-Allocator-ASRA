---
namespace: software
tier: matrix
tags: [software, fit-gate]
last_reviewed: 2026-05-01
---

The software capability matrix maps named software/tools to the minimum tier they require to run usefully. The fit gate in `rules.py` consults a Python copy of this table; the LLM uses retrieved chunks from this document to justify recommendations. Update the table here AND the constant in `rules.DEFAULT_SOFTWARE_MIN_TIER` together — they are intentionally redundant for resilience.

## Tier 3 (Basic) — runs cleanly

- Microsoft 365 web, Office 365, Google Workspace, Google Docs, Word, Excel, PowerPoint.
- Zoom, Microsoft Teams, Google Meet, Skype, WhatsApp web.
- Chrome, Firefox, Edge, Safari for general browsing.
- Patient portals (MyChart equivalents), CRA, ServiceCanada, banking sites.
- Duolingo, Khan Academy, Coursera, edX (web players).

## Tier 2 (Standard) — minimum

- Photoshop, Illustrator, Audition, Figma (desktop), Affinity Photo.
- VS Code with extensions, IntelliJ IDEA Community, PyCharm Community.
- MATLAB, RStudio, Jupyter notebooks on small datasets.
- Tableau Public, AutoCAD LT.
- Microsoft 365 desktop apps (heavy use), large Excel workbooks.
- Logic Pro, GarageBand (light projects).

## Tier 1 (High Power) — required

- Premiere Pro, After Effects, Final Cut, DaVinci Resolve.
- Android Studio (with emulator), Xcode + iOS Simulator.
- Docker Desktop, VirtualBox, VMware Workstation/Fusion.
- Unity, Unreal Engine.
- PyTorch / TensorFlow with GPU training; sustained heavy compilation.

## Notes on matching

- "VS Code" alone is T2. "VS Code + Docker + a database" is T1 because Docker is the limiting factor.
- "Photoshop" alone is T2. "Photoshop + Premiere" is T1 because Premiere is the limiting factor.
- "Zoom" alone is T3. "Zoom + dozens of tabs + a video editor" is T1 because the video editor is the limiting factor.
- The fit gate is conservative: it returns False whenever ANY software in the applicant's list exceeds the device tier's capability.
