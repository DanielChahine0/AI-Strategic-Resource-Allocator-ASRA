# Application Intake Form

Fields marked `*` are required. All others are optional.

## Scoring / Matching Weights

Each field below is annotated with a **`[weight: N]`** tag describing how much it
contributes to the allocation decision. Weights are points on a **100-point
priority score** (higher score means higher need means higher allocation priority).

Tag meanings:

- **`[weight: N]`**, contributes N points to the need/priority score.
- **`[weight: 0, excluded]`**, contact / personal identity. **Never used for
  matching** (privacy plus no bearing on need).
- **`[weight: 0, gate]`**, required process step or operational flag, pass/fail
  only, not scored.
- **`[fit-only]`**, used to match the *right device/config*, not to rank priority.

Total priority points available, **100**.

| Category | Points |
|---|---|
| Financial need (income, proof, situation) | 50 |
| Purpose & impact (needs, challenges, software) | 26 |
| Household need (family size, children, region) | 13 |
| Equity & demographics (identity groups) | 6 |
| Support/verification & comfort | 5 |
| Contact, gates, operational | 0 |

---

## Step 1: Contact Information

**Full Name** `*` your full legal name, `[weight: 0, excluded]`

**Email Address** `*` we'll use this to contact you about your application, `[weight: 0, excluded]`

**Phone Number** `*` with or without formatting (e.g. `416 555 1234` or `4165551234`), `[weight: 0, excluded]`

## Step 2: Computer Application

**Requested Computer(s)** `*` select all that apply, `[fit-only]` (matches device type to availability. "whichever first" eases matching)

Refurbished computer (Ubuntu OS)
Refurbished desktop computer (Ubuntu OS)
Whichever becomes available first
Refurbished Windows 11 computer (prices vary)

**Main need(s) for a computer** `*` select all that apply, `[weight: 10]` (Education / Employment / Health / Community Services rank highest impact. Entertainment lowest)

Education (school assignments, online classes, adult learning, certifications, training)
Employment / Job Seeking (job search, applications, resumes, virtual interviews, workplace training)
Health (telehealth, counseling/therapy, medical information, health portals)
Accessing Community Services (benefits, housing, immigration support, government forms, community programs)
Social Communication (email, video calls, messaging family/friends, community groups)
Entertainment (videos, streaming, music, games)
Other (please specify)

**Requested Mobile Device(s)** optional, `[fit-only]` (inventory matching only)

Cell Phone (low supply)
Tablet (low supply)

**Other fields**

**Rogers Internet Connect Package?** optional, Yes / No, `[weight: 1]` (Yes signals connectivity gap, slightly higher need)

**Technology Comfort Level** `*` 1 (Beginner) to 5 (Expert), `[weight: 2]` (lower comfort flags for support/training, not a penalty. mild equity factor)

**What challenges do you currently face by not owning a computer, and how will this computer help?** `*` free text, up to 2000 characters, `[weight: 12]` (qualitative need/impact, scored by AI against severity and concreteness)

**Software you plan to use** `*` select all that apply, `[weight: 4]` (`[fit-only]` for OS choice. accessibility software adds need points)

Office software (Word, spreadsheets, presentations: MS Office, LibreOffice, Google Docs)
Video meeting software (Zoom, Teams, Google Meet, Skype)
Programming/coding tools (Python, Java, C++, VS Code, GitHub, Jupyter)
Graphic design or creative software (Canva, Photoshop, GIMP, video editing)
Accessibility software (screen readers, text to speech, screen magnifier)
School/learning platforms (Moodle, Blackboard, Google Classroom)
Job search tools (résumé builders, LinkedIn)
CD or DVD ROM (videos or software)
Not sure / I would need help installing software
Other (please specify)

**Currently receiving support from a community organization, case worker, or service provider?** optional, Yes / No, `[weight: 3]` (third-party referral corroborates genuine need)

If yes: Referring Organization, Staff Email, Staff Name & Position, `[weight: 0, excluded]` (staff contact info. org name feeds the +3 above as verification, not extra points)

**How did you hear about us?** `*`, `[weight: 0, gate]` (analytics/outreach only)

Friend
School / Organization
Website
Social Media (Facebook, X, Instagram)
Newsletter
Event
Radio / Newspaper
Other

## Step 3: Household Information

**Postal Code** `*` Canadian (`M5V 3L9`) or US (`12345`) format, `[weight: 2]` (service-area eligibility plus regional prioritization. not the identity, just the region)

**Number of Family Members** `*` total household including yourself, `[weight: 6]` (more people sharing one resource means higher need)

**Children Ages** ages of children 25 and under, comma separated (e.g. `5, 7, 10`), `[weight: 5]` (school-age children, education impact multiplier)

**Languages Spoken** `*` all languages spoken in your household, `[weight: 0, excluded]` (used only for service delivery/language support, not ranking)

## Step 4: Financial Information & Status

**Annual Household Income** `*` total before taxes, numbers only (e.g. `45000`), `[weight: 20]` (largest single driver, scored against household size / low-income cutoffs)

**Current situation** `*` select all that apply, `[weight: 14]` (each barrier adds need. disability / no income / shelter / unemployed / single parent weighted highest)

Single parent family
New Canadian / Refugee
Low income
Elementary / High School Student
International Student
Post secondary / Graduate Student
Senior
Family member with a disability
Unemployed
Living in transitional / emergency housing or shelter
Indigenous (First Nations, Métis, Inuit)
Other Minority Group
No Income

**Identity groups** optional, select all that apply, `[weight: 6]` (equity prioritization for historically underserved groups)

Indigenous (First Nations, Métis, Inuit)
Newcomer to Canada / refugee
Person with a disability
Member of a racialized or minority group
Prefer not to say
Other (please specify)

**Proof of Income** select all that apply, `[weight: 10]` (documented assistance verifies and strengthens need. presence of any program corroborates the income field)

Ontario Works (OW)
Ontario Disability Support Program (ODSP)
Canada Pension Plan Disability (CPPD)
Ontario Student Assistance Program (OSAP)
Employment Insurance
Supporting Letter from School / Organization
Refugee Letter from IRCC
Notice of Assessment from latest year
Second Career Agreement or equivalent
Referred by an Affiliate Partner

## Step 5: Additional Information & Waiver

**Need shipping / delivery?** Yes / No, `[weight: 0, gate]` (logistics/cost flag, not priority)

**Anything else you'd like us to know?** optional, free text, `[weight: 0]` (read for context/edge cases. can override via manual review, not auto-scored)

**Refurbished Computer Waiver Agreement** applicant must read and check: `[weight: 0, gate]` (hard requirement. unchecked means ineligible)

"I Agree to Waiver Terms" (click **View Waiver Agreement** to read)
"I have read and agree to the waiver terms above" `*`
Waiver covers: Acknowledgment, Warranty, Assumption of Risk, Release of Liability, Indemnification, Security and Data, Return and Disposal, Restriction on Resale, Education and Training Requirements.

**Submit Application**

---

## Weight Summary (priority score, 100 pts)

| Field | Weight |
|---|---|
| Annual Household Income | 20 |
| Current situation | 14 |
| Challenges faced (free text) | 12 |
| Proof of Income | 10 |
| Main need(s) for a computer | 10 |
| Number of Family Members | 6 |
| Identity groups | 6 |
| Children Ages | 5 |
| Software you plan to use | 4 |
| Currently receiving support (referral) | 3 |
| Postal Code (region) | 2 |
| Technology Comfort Level | 2 |
| Rogers Internet Package | 1 |
| **Total** | **100** |

**Excluded from matching (weight 0):** Full Name, Email, Phone, Staff contact
info, Languages Spoken, all personal/contact data.

**Gates / operational (weight 0):** Waiver agreement (required to be eligible),
Shipping flag, How did you hear, Requested device & mobile selections
(device-fit only), "Anything else" (manual-review context).
