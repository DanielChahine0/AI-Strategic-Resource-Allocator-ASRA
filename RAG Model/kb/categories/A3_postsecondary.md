---
namespace: categories
category: A3
tags: [education, post-secondary, university, college]
last_reviewed: 2026-05-01
---

A3 covers post-secondary students (university, college, vocational). The tier is RAG-decided: arts, science, and business sub-tracks default to Tier 2 (Standard), and software engineering defaults to Tier 2 unless the applicant lists workloads that genuinely require Tier 1 — virtual machines, ML frameworks, Docker Desktop, or mobile emulators (Android Studio, iOS Simulator).

## Sub-track guidance

- **arts**: T2. Photoshop, Illustrator, Figma, and Audition all run cleanly on T2. Premiere Pro and After Effects warrant T1 only if the program/portfolio explicitly requires them.
- **science**: T2. Python, R, MATLAB, RStudio, and Jupyter are T2-compatible workloads. Bump to T1 only if PyTorch/TensorFlow training is part of the coursework (not just inference).
- **software_engineering**: T2 by default. Bump to T1 ONLY if `software_needed` includes any of: VMs (VirtualBox, VMware), Docker Desktop, Android Studio, Xcode/iOS Simulator, Unity, Unreal, or local ML training (PyTorch, TensorFlow with GPU).
- **business**: T2. Microsoft 365, Tableau, and statistical packages run cleanly. T3 is acceptable if no T2 is available but is not preferred.

## When to require Tier 1

Tier 1 is scarce. Justifying it requires a specific, named workload in the applicant's intake that cannot run on T2. "I might learn Docker someday" is not justification. "My second-year course requires us to deploy services in Docker locally" is.

## Edge cases

- Applicants who only list browser-based programs and online classes: T3 may suffice. Confirm with the applicant before assigning a T3 to an A3 — they often have software they didn't think to mention.
- Returning adult learners in college trades programs (drafting, CAD): AutoCAD is borderline T1, but the trades-college curriculum typically uses lab machines for AutoCAD work; T2 covers the rest of the coursework.
- Applicants in nursing or healthcare-adjacent post-secondary programs may also qualify as B; the splitter handles this and chooses the strongest match.
