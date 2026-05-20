---
namespace: policies
tags: [policy, multi-category, splitter]
last_reviewed: 2026-05-01
---

When an applicant qualifies for more than one category, the engine splits the applicant into one application per category, runs the full scoring pipeline on each independently, and keeps only the application whose top match scored highest. The discarded applications are recorded so reviewers can audit the choice — they are not forwarded to allocation.

## Why this approach

LGT distributes one device per applicant in the MVP. The applicant's needs may span multiple categories (e.g., a newcomer also job-searching), but allocating two devices would double the per-applicant cost and starve other applicants. Running the scoring across categories and keeping the best lets the engine choose the path that produces the most-fitting device, not just the most-eligible category.

## What the applicant sees

Allocation correspondence should say: "Based on your intake, we considered your need as both [Category X] and [Category Y]. The strongest match given today's inventory came from the [Category X] lens, so we are sending you [device]." The transparency helps applicants who are unsure how to describe themselves.

## When this rule should not apply

If LGT staff identify two non-overlapping needs that genuinely require two devices (e.g., a parent + a child), the recommended pattern is to treat them as separate applicants. The 7-question intake's `who_needs_it` captures who the primary user is.
