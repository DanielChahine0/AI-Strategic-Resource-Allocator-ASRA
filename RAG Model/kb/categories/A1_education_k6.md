---
namespace: categories
category: A1
tags: [education, children, elementary]
last_reviewed: 2026-05-01
---

A1 covers children from Kindergarten through Grade 6. The appropriate computer is a Tier 3 (Basic) device because the workload is dominated by lightweight, web-based learning: reading-and-writing platforms (Raz-Kids, Epic), math drill sites (Prodigy, Khan Academy Kids), Google Classroom, video calls with classmates and teachers, and short educational videos. None of these workloads benefit from a faster CPU or dedicated graphics.

## Who qualifies

- A school-aged child in K through Grade 6.
- A parent or guardian applying on the child's behalf is the typical pattern; the `who_needs_it` field should reflect this.
- Households where the child does not have any device of their own (`device_situation: none`) are highest priority within A1.

## Typical use cases

- Asynchronous classwork pushed through Google Classroom or Seesaw.
- Live class video calls (Zoom, Google Meet) — these are the most demanding workload, but every T3 device in the LGT inventory handles a single Zoom call cleanly.
- Light typing, slide creation, and reading.
- Educational games delivered via the browser.

## Tier rationale

T3 is the right answer for almost every A1 case. T2 is wasted hardware here — the additional CPU power and storage will sit idle, and that machine is better matched to a post-secondary student or a healthcare worker who genuinely needs it. T1 is never appropriate.

## Edge cases

- A child enrolled in a specialty arts program who lists Photoshop or video editing in their software needs: do NOT bump the recommendation to T2 without LGT staff review. K-6 design education in Canadian curricula is overwhelmingly done in the browser (Canva, Adobe Express). Confirm with the parent rather than over-allocating.
- Households sharing a single device among multiple children: still T3, but flag for staff review if `shared_user_count >= 3` — additional peripherals (a second monitor, an external keyboard) may help and can be bundled separately.
