---
namespace: categories
category: F
tags: [newcomers, immigrants, settlement]
last_reviewed: 2026-05-01
---

F covers recent immigrants and refugees settling in Canada. The appropriate match is a Tier 3 (Basic) computer or a Mobile item. Newcomers typically need internet access for settlement services, language learning, banking, immigration paperwork, and family communication abroad — none of which exceed T3 capability.

## Who qualifies

- Permanent residents who arrived within the past 24 months.
- Refugee claimants and government-assisted refugees.
- International students whose primary use case is settlement (their education use case may also qualify for A3 — the splitter handles this).

## Typical use cases

- Immigration and settlement portals (IRCC, provincial settlement services).
- Language learning (Duolingo, LINC programs).
- Banking, ServiceCanada / ServiceOntario equivalents.
- Video and voice calls with family overseas (WhatsApp, Skype, Telegram).
- Children's homework support when the household has school-aged kids.

## Tier rationale

T3 covers the workload. Mobile is often preferable for video calling and translation use cases. The splitter handles multi-category applicants (e.g., newcomer also job-searching → [F, C]); typically the C arm scores higher because of the employment priority bump, so the engine returns the C match.

## Edge cases

- Newcomer families with school-aged children: the parent's application is F, but the child may also need a device for school (A1 or A2). Treat each member's request as a separate applicant unless LGT staff confirm a single allocation.
- Newcomers enrolled in employment-bridging programs may qualify as both F and C; the engine picks the stronger match.
