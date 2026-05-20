---
namespace: policies
tags: [policy, scoring, weights]
last_reviewed: 2026-05-01
---

The MVP scoring composite uses weights `priority=0.35, timing=0.25, condition=0.20, efficiency=0.20`. The Fit score is a hard gate — never a weighted contribution. The composite is what the engine sorts on; the gate decides which devices are eligible to be sorted.

## Why priority leads

Priority is the strongest signal in the intake because it captures both urgency and current access. An applicant with no device and a critical-this-week urgency genuinely cannot wait; the weights should let that signal dominate even when other dimensions are comparable.

## Why timing matters next

Timing is the engine's check against handing someone a device that won't arrive in time. A T2 in great condition that's only available 60 days from now is worse than a T3 in decent condition available next week for an applicant whose urgency is "critical".

## Why condition and efficiency tie at 0.20

Condition reflects how usable the device will be over a meaningful lifespan; efficiency reflects whether the inventory is being used wisely (not over-allocating a T1 to a T3-fit applicant). These are values about good stewardship rather than urgency — they should not dominate the ranking, but they are not negligible either.

## What is NOT encoded

- No fixed category multipliers — A1 is not weighted above F, B is not weighted above D, etc. This is intentional and one of the open design questions for LGT stakeholders.
- No first-come-first-serve mechanism is encoded into the composite; submission time is the tiebreak.
- No waitlist-age boost. The MVP doesn't persist applicant state.

These are listed in the README's Open Design Questions section so LGT can decide before launch.
