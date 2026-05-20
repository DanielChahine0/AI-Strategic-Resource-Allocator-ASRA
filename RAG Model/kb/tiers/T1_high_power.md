---
namespace: tiers
tier: T1
tags: [high-power, professional, creative, engineering]
last_reviewed: 2026-05-01
---

Tier 1 (High Power) is a workstation-class machine reserved for heavy creative, engineering, and compute workloads that genuinely exceed Tier 2. T1 is scarce in the LGT inventory and should be matched conservatively — over-allocating a T1 to a workload that runs on T2 starves the applicant who actually needs it.

## Representative specs

- 6+ core CPU (Intel i7/i9, AMD Ryzen 7/9, Apple M-series Pro or higher).
- 16 GB RAM minimum, 32 GB preferred.
- 512 GB SSD or larger.
- Dedicated GPU for any video editing, 3D, ML, or game-development workload.

## Workloads that justify T1

- **Video editing**: Premiere Pro, Final Cut, DaVinci Resolve, After Effects.
- **3D and game dev**: Unity, Unreal Engine, Blender for sustained renders.
- **Mobile development**: Android Studio with emulator, Xcode with iOS Simulator.
- **Local virtualization**: Docker Desktop with active containers, VirtualBox/VMware running guest OSes.
- **ML training**: PyTorch / TensorFlow with GPU; not inference-only.
- **Sustained heavy compilation**: large C++ codebases, monorepo builds.

## Workloads that do NOT justify T1

- Office documents, slides, spreadsheets.
- Web browsing, video calls, streaming.
- VS Code with extensions for typical web or scripting work — Tier 2 covers this cleanly.
- Photoshop, Illustrator, Figma — Tier 2 covers this cleanly.
- MATLAB, R, Python data analysis on small/medium datasets — Tier 2 covers this cleanly.
