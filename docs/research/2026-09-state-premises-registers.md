# State veterinary premises registers — research spike (2026-09-15)

**Ruling D-C58 (John, 2026-09-14), verbatim:** "a research spike on state premises registers
(approach C), with no screen and no ingestion until the Foundation clears a registry row — yes, low
priority."

**Research only.** No code, no ingestion, no screen, no registry row inserted, no change to the
competition figure. Nothing below has been fetched into the repository: this document holds field
**names**, counts, URLs and legal terms, and not one licensee record — the same rule that blocked
the 2017 Google Places export under D15.

---

## Read this first — the five-state sweep was superseded, not completed

This spike was commissioned as a five-state sweep (TX, CA, FL, NY, CO). Part-way through, an
existing dataset built in a separate stack was put in front of the programme:
`retire-forward-all-facility-data-2026-09-15.xls`, 28 MB, **12,941 published facility registrations
across nine states**, with field-level provenance — every address, licence status and type carrying
its own `source_url`, `checked_at` and `note`; each snapshot carrying a `source_url` and a file
digest; raw and normalised licence status kept apart; and a `State audit` sheet carrying
`legal_regime`, `legal_evidence_url`, `address_type`, `premises_verified`, `approval_required` and
`request_status` for all 51 jurisdictions.

**Four of the five states were already answered there**, so the sweep was stopped and the remaining
effort was pointed at the three things that file could not settle:

1. **Colorado** — the one state of the five genuinely unreviewed, with a board request drafted and
   unsent.
2. **Independent verification of the two "no state facility register" verdicts, Texas and New
   York** — the most consequential claim in the file, because Texas is where this product's demo
   listings live.
3. **California's `legal_regime: UNCERTAIN` against Florida's `YES`** — California is the largest
   single block at 4,744 rows and its reuse terms were unresolved.

This document is that narrowed work. Where a fact comes from the existing dataset rather than from
a fetch made here, it says so. **This document did not re-derive the file's row counts and does not
restate them as its own findings**, with one exception noted under Florida, where a pass completed
before the sweep was stopped and independently reproduced two of the file's fields.

---

## The table

One row per state. Every URL is the primary source — the board's or department's own page, never a
search result and never a third-party mirror.

| State | Premises register? | Primary source | Public, no agreement/fee? | Bulk? | Coordinates? | Rough count | Legal verdict |
|---|---|---|---|---|---|---|---|
| **TX** | **NOT YET — but enacted.** No register operating; facility registration is **in force in law since 1 Sep 2026**, records from 2027 | [SB 2155 enrolled](https://capitol.texas.gov/tlodocs/89R/billtext/html/SB02155F.htm) · [board announcement](https://veterinary.texas.gov/announcements/tbvme-now-has-the-authority-to-register-and-regulate-veterinary-facilities/) | n/a (no records yet) | **NO** | n/a | **0 today**; all facilities must register by **1 Sep 2027** | **unclear** — no terms written yet |
| **NY** | **NO** — state licenses individuals only | [op.nysed.gov Article 135](https://www.op.nysed.gov/title8/education-law/article-135) · [Subpart 62](https://www.op.nysed.gov/professions/veterinarian/laws-rules-regulations/subpart-62) | individual lookup yes | **PARTIAL** — request-gated bulk files exist | **NO** | **0 facilities**; **5,765** NY-addressed veterinarians (1 Jan 2026) | **conditional** (for the individual register that does exist) |
| **CA** | **YES** — "Veterinary Premises", B&P §4853 | [dca.ca.gov/consumers/public_info](https://www.dca.ca.gov/consumers/public_info/index.shtml) | **YES** | **YES** — free monthly file, no account | **NO** — and it is a *mailing* address (16.7% out-of-state) | **3,905** active (4,744 disclosable) | **conditional** — DCA grants copying "for non-commercial use only" |
| **FL** | **YES** — premises permits, §474.215 F.S. | [myfloridalicense.com veterinary public records](https://www2.myfloridalicense.com/veterinary-medicine/public-records/) | **YES** | **YES** — free weekly CSV | **NO** — addresses only, and *mailing* | **3,127** establishments | **reuse allowed** |
| **CO** | **NO** — no agency registers a veterinary facility; PACFA **exempts** vet hospitals | [C.R.S. §35-80-103(2)(a)](https://leg.colorado.gov/) · [DORA licensee data](https://data.colorado.gov/Business/Professional-and-Occupational-Licenses-for-Colorad/7s5z-vewr) | **YES** (for the individual data) | **YES** — but of *people*, not premises | **NO** — city/state/mailing ZIP only | **0 facilities**; **6,259** active veterinarians | **reuse allowed** (public domain, one attribution string) |

**Reading the verdict column.** A verdict is about *whatever register that state actually has*. For
TX, NY and CO there is no premises register, so the verdict describes the individual-licensee data
that does exist — and "reuse allowed" for Colorado emphatically does **not** mean a facility list may
be reused, because no facility list exists. Only CA and FL have verdicts about premises data.

---

## Texas — the verification changed the answer

**This is the consequential row, and the second pass overturned the first.** The existing dataset
records Texas as "NO STATE FACILITY REGISTER — review complete, authority confirmed", and the first
pass here reached the same conclusion from the board's own licensing pages. **Both are out of date.**

**Texas enacted veterinary facility registration in 2025, and the subchapter took effect on
1 September 2026 — fourteen days before this spike was written.** The first pass missed it because
it read the board's *current* licence types and *current* rulebook, both of which still describe the
pre-2025 world. Only a pass that went to the statute found it.

**The statute.** SB 2155, 89th Legislature Regular Session, signed 20 June 2025, adds **Occupations
Code Chapter 801, Subchapter M — Veterinary Medical Facilities, §§801.601–801.604**. §801.601(a),
verbatim from the enrolled text:

> "Veterinary medicine, including veterinary medicine practiced remotely by electronic means, shall
> be practiced only in or from a veterinary medical facility that is registered with the board or
> that is exempted by rule from the registration requirement."

A "veterinary medical facility" is defined as "a location, including a building, portion of a
building, or vehicle, in which the practice of veterinary medicine normally takes place or is
provided." §801.602 requires the applicant entity to supply its owners, partners and operators
(including any management services organization), the names and licence numbers of all
board-regulated persons at the facility, and a designated **medical director** — which is the
veterinarian-in-charge field no other state in this set publishes in bulk.

**The timetable, from the bill's own closing sections and the board's own announcement:**

| Milestone | Date | Status at 2026-09-15 |
|---|---|---|
| Subchapter M takes effect (SECTION 42(b)) | **1 Sep 2026** | **in force** |
| Stakeholder meetings and proposed rules | Fall 2026 | not yet done |
| Board adopts rules (SECTION 40) | by **1 Mar 2027** | pending |
| Registration portal opens | Summer 2027 | pending |
| All facilities must be registered (SECTION 41) | by **1 Sep 2027** | pending |

The board's own words: "With the passage of SB2155 in the 89th Regular Session, TBVME now has the
authority to register and regulate veterinary facilities" — and the registration requirement "does
not go into effect until September 1, 2027."

**So the honest reading is not "no" and not "yes" but "not yet".** Texas today has **zero**
registered facilities and no portal, so nothing can be ingested and the existing dataset's count of
0 is correct as an operational fact. But the premise underneath it — that Texas does not register
veterinary premises — stopped being true a fortnight ago, and **Texas is on course to have an
authoritative facility register, with a medical director per facility, by September 2027.** Given
that the demo listings are Texas-heavy, that is the single most decision-relevant fact in this
document.

### What Texas licenses today

The board issues exactly three licences, all to **people** — Doctor of Veterinary Medicine (DVM),
Licensed Veterinary Technician (LVT), Licensed Equine Dental Provider (EDP) — confirmed from the
board's own licensing page and read again out of the live licensing system's own `Profession`
picklist. Its rulebook is still the pre-2025 four chapters (571 Licensing, 573 Rules of Professional
Conduct, 575 Practice and Procedure, 577 General Administration), with no facility chapter yet
written. §801.3541 states the pre-2025 position plainly: "The premises on which a veterinary
practice is located may be owned by a person or other legal entity that does not hold a license to
practice veterinary medicine issued under this chapter."

**What Texas actually licenses.** The Texas Board of Veterinary Medical Examiners (TBVME) issues
exactly three licences, all of them to **people**: Doctor of Veterinary Medicine (DVM), Licensed
Veterinary Technician (LVT), Licensed Equine Dental Provider (EDP)
([veterinary.texas.gov/licensing](https://veterinary.texas.gov/licensing/)). TDLR's own page for the
board says the same in its own words — it "regulates veterinarians, licensed veterinary technicians
and equine dental providers" ([tdlr.texas.gov/TBVME](https://www.tdlr.texas.gov/TBVME/)). **There is
no facility, premises, clinic or hospital licence.** Licensing an individual veterinarian is not
registering a premises, and Texas does only the former.

**The structural proof.** The board's entire rulebook is four chapters, listed on its own Laws &
Rules page ([veterinary.texas.gov/laws-and-rules](https://veterinary.texas.gov/laws-and-rules/)):
**571 Licensing · 573 Rules of Professional Conduct · 575 Practice and Procedure · 577 General
Administration and Duties**. There is no premises chapter to hold a facility regime, and no facility
registration appears in the three licence types the board issues.

**The TDLR attachment does not change it.** TBVME was administratively attached to TDLR on
**1 September 2023** for four years, to **31 August 2027**, with day-to-day licensing staying at
TBVME. That attachment did **not** put veterinary licences into TDLR's bulk data: the Texas Open
Data Portal's `TDLR - All Licenses` dataset (`data.texas.gov/d/7358-krk7`) carries **87 distinct
licence types and none of them is veterinary** (queried directly through the Socrata API). Nor is
there any veterinary dataset on the portal at all — `q=license` returns 205 datasets, `q=veterinary`
returns **zero**. (`DataSet-01-All Licenses` is the Texas *Medical* Board — human physicians.)

**What does exist, and why neither is a register of veterinary premises:**

- **Temporary Limited-Service Clinic notifications**, board rule **§573.71** — a veterinarian must
  notify the board at least 48 hours before holding one. It is a **per-event notification**, not a
  standing premises register, and the resulting set is not published.
- **Texas DSHS Radiation Control X-ray certificates of registration** — a different regime under a
  different agency, covering only those facilities that hold a radiation machine. Searchable at
  `vo.ras.dshs.state.tx.us/datamart` (a cookie-gated portal whose own footer reads "Last Updated Mar
  27, 2013"). It is a machine registry that veterinary clinics appear in, not a veterinary register.

**Legal verdict: unclear, and moot.** There is no premises register to have a verdict about. For the
individual-licensee lookup that does exist, the verdict is **unclear**: `veterinary.texas.gov`
publishes **no terms-of-use page at all** (`/site-policies/` and `/policies/` both 404), so there is
nothing to read. The surrounding law is permissive but silent on redistribution — Tex. Occ. Code
**§801.207** makes a board record "a public record … available for public inspection", and Gov't
Code **§552.222** forbids the agency from asking why a requester wants information. Neither says
anything about republishing a scraped lookup.

**Count of facilities: 0.** Not "unknown" — there is no register, so there is nothing to count. This
matches the existing dataset's Texas row exactly (0 rows, review complete, authority confirmed).

---

## New York — NO state facility register (independently verified here)

**What New York actually licenses.** Individuals, and only individuals. **Education Law Article
135** — the veterinary practice act — has 19 sections and not one of them licenses, registers,
permits or inspects a premises; **8 NYCRR Subpart 62** (the Commissioner's Regulations, §§62.1–62.8)
is education, examination, endorsement, scope and CE, with no facility standards and no inspection
regime. Established by exhaustion, and cross-checked against NYS Open Legislation's copy of the
same statute.

**The two near-misses, both closed:**

- **§6706 (corporate practice)** restricts **who may own** a veterinary practice — "No business
  corporation, other than a professional service corporation … shall hereafter be organized for the
  practice of veterinary medicine". It creates no facility licence and no premises register, and it
  presumes the licensed thing is the individual, not the building.
- **NYSED's own definition of a "veterinary facility"** exists, at Professional Practice Guideline
  1.17 — "any fixed or mobile establishment, veterinary hospital, animal hospital, clinic or
  premises where veterinary medicine is practiced" — but the same page states that "Practice
  guidelines do not carry the force of law or regulation." It is a vocabulary definition attached to
  no register. **It must not be read as licensure.**

The closest adjacent thing is the **Certificate of Authority** for a veterinary professional service
corporation, with a public "Verification of Professional Service Entities" search. That is a
**business-entity** register, not a premises one: one PC can operate several hospitals, and a sole
practitioner need form no entity at all.

**No other NY agency fills the gap.** The Department of Agriculture & Markets licences dairy, food,
nurseries, pet dealers, shelters and rescues — veterinary practices are not among them. Controlled
substances (DOH Bureau of Narcotic Enforcement / DEA) is a drug-handling authorisation, not a
premises licence.

**Legal verdict: conditional** — and this is a verdict about the **individual** register, the only
one that exists. The first pass called it *prohibited*; the second pass corrected it to
*conditional*, because NYSED operates an explicit permission channel in both directions (see below).
Absent written permission the default is still prohibited. NYSED's verification terms
([op.nysed.gov/services/verifications/terms-and-conditions-of-use](https://www.op.nysed.gov/services/verifications/terms-and-conditions-of-use))
bar three separate things this product would need to do — **verified word for word against the raw
page by both passes**:

> "The State Education Department does not authorize the modification, republishing or distribution
> of this license information for **any commercial purpose**."

> "The State Education Department does not authorize the **aggregating** of individual information
> provided on these pages for anything other than licensing verification."

> "The State Education Department reserves the right to **block access to any IP address** that
> appears to be performing data harvesting through the use of robots or other automated programs
> making rapid-sequence queries."

The site-wide Terms of Use are stricter still, and are **incorporated by reference** by the sentence
"you signify that you agree to these terms of use, and all other applicable terms of use for the
online systems provided by the State Education Department". Read **live** by the second pass at
[nysed.gov/terms-of-use](https://www.nysed.gov/terms-of-use) (the first pass's TLS failure was a
tooling artefact, not a site problem): copying is permitted "for personal, private and educational
purposes, **except that reproducing materials for profit or any commercial use is strictly forbidden
without express prior written permission**", with requests to `legal@nysed.gov`.

**That permission channel is why the verdict is conditional rather than prohibited** — and it is
real, not theoretical. NYSED's verification search carries a **Downloads tab** offering bulk
verification files: "to request bulk verification files of currently registered NYS licensees,
please submit a Bulk Verifications Request Form … which are updated weekly", with an API "in
development". The request form's profession picker carries 80 options and **both "Veterinarian" and
"Veterinary Technician" are among them**. The form screens "Purpose of the Request", "Frequency of
searches" and "Number of anticipated records retrieved", so a commercial-marketplace purpose would
very likely be refused — but a bulk route exists, and the first pass was wrong to say it did not.

**FOIL is a weaker barrier than the first pass claimed.** **Public Officers Law §89(2)(b)(iii)**
does make it an unwarranted invasion of personal privacy to release "lists of names and addresses
**if such lists would be used for solicitation or fund-raising purposes**" — but the exemption is
conditional on that use, counting facilities is not solicitation, it protects natural persons rather
than veterinary PCs, and §89(2)(c)(iv) cuts the other way for records relating to real property.

**And the data would not work even if the terms allowed it.** NYSED states the address on record "is
not necessarily the licensee's practice address", and the verification pages say city and state are
provided "as an aid in identifying the individual". A register that cannot place a practice cannot
count practices near a point. (Field-level granularity of the result column labelled `Address` is
**UNKNOWN** — the backing API returns 403 to programmatic clients and neither pass attempted to
defeat it, the terms expressly reserving the right to block automated querying.)

**Two things the second pass found that are worth keeping.** First, **NYSED does register premises
— for pharmacies**, under Education Law Art. 137 §6808 ("no establishment shall operate as a
pharmacy unless that establishment is registered"), with a dedicated "Pharmacy Establishment" search
mode. Same agency, same Title 8: the veterinary absence is a deliberate structural choice, not an
oversight. Second, NYSED publishes **per-county counts of registered veterinarians** across all 62
counties — a free, aggregate, geographic denominator that never touches an individual record, and
the most reusable artefact in New York for any density measure.

**Other NY agencies do register veterinary premises — but not usefully.** New York State DOH under
10 NYCRR Part 16 registers radiation installations per site, with **§16.54 titled "Veterinary
radiographic and fluoroscopic installations"** and a certificate that "shall expire upon … a change
in location"; New York City DOHMH does the same under Health Code Art. 175 (**§175.51 "Veterinary
radiography, dental and fluoroscopy"**). So a NY veterinary hospital with an X-ray machine is on a
government register keyed to its street location. It is still not usable: it registers *imaging
equipment*, not practices (a practice with no imaging is absent); it is **not published** anywhere,
so FOIL is the only route; and it is split between two custodians with different formats. NYC Health
Code Art. 161 (animal permits) **expressly exempts** "a veterinary hospital or other veterinary or
medical facility".

**Count of facilities: 0.** As of 1 January 2026 there are **5,765 NY-addressed** registered
veterinarians (8,314 worldwide on NY's register, including 2,379 with other US addresses and 170
non-US) and 5,761 NY-addressed veterinary technicians (6,546 worldwide) — **individuals, not
facilities**. The first pass reported the worldwide totals as New York's; the second pass caught it,
and the correction matters because 8,314 overstates the NY population by 44%.

---

## California — the UNCERTAIN resolves, and a worse problem appears behind it

California is **structurally the strongest source of the five** and **legally the most stuck**. It is
the largest single block of records, so the answer here decides most of the value of the whole idea.

**The register is real and first-class.** "Veterinary Premises" is a licence type in its own right —
agency code 460, licence type code **4604**, licence numbers prefixed `HSP` — under the California
Veterinary Medical Board within the Department of Consumer Affairs.

**The bulk route is genuinely open.** DCA publishes a **free monthly file per agency** from its
Public Information page, and the folder returned **HTTP 200 to a plain unauthenticated request** —
no login, no click-through agreement, no fee, no registration. DCA's own words on cadence: "Data is
refreshed automatically at the beginning of each month." The Veterinary Medical Board's folder was
last updated **2026-09-01**. The California Public Records Act is explicitly *not* this route — the
page says "This is NOT the site for Public Records Act (PRA) Requests" — and it does not need to be.

**Fields — names only, and the bulk file and the lookup differ, which matters.** The published
department-wide "Public Information Record Layout" carries 20: Agency Code · Agency Name · License
Type Code · License Type Name · License Number · Individual or Organization Indicator ·
Organization/Last Name · First Name · Middle Name · Suffix · Address Line 1 · Address Line 2 · City ·
County · State · Zip · Country · Original Issue Date · Expiration Date · License Status. The
**per-record lookup page carries more** — Previous Names, Public Record Actions (discipline), Public
Documents, and a **"Premises to Managing Licensee" relationship**, which is the
veterinarian-in-charge. **The managing licensee, the enforcement flags and the previous names exist
only on the lookup page and not in the bulk layout**, so getting them for all premises means
per-record retrieval.

**Coordinates: none.** Addresses only — verified by grepping a rendered premises profile for
`latitude`, `longitude`, `lat`, `lng`, `geocode` and `coordinates`, with zero hits. The page's "Map"
control is a Google Maps *search* URL built by concatenating the address, not a coordinate link.
Geocoding ~4.7k addresses is the floor cost.

**Counts, both primary and reconciling.** **4,744** disclosable records, from DCA's own counts file
dated 2026-09-01 — which per the record layout spans Current, Delinquent and Inactive. **3,905**
*active* premises, verbatim from the Senate Committee on Business, Professions and Economic
Development background paper of 25 August 2025: "In Fiscal Year 2023-24, the active licensing
population under the Board's jurisdiction included 13,722 licensed veterinarians, 8,901 registered
veterinary technicians, and 3,905 veterinary premises." The ~840 gap is the non-active statuses.
**Plan on ~3,900 live premises**, and note that the 4,744 in the existing dataset is the disclosable
figure, not the live one.

### The legal question — resolved further than "UNCERTAIN", in both directions

The first pass found two official California pages that disagree and called the conflict
unresolvable. **The second pass resolved it, and the answer is `conditional`, not `unclear`.**

**(a) DCA's own disclaimer**, [dca.ca.gov/about_us/disclaim.shtml](https://www.dca.ca.gov/about_us/disclaim.shtml),
under "Copying of Documents":

> "The Department of Consumer Affairs authorizes the user to copy, **for non-commercial use only**,
> documents published by the Department of Consumer Affairs on the World Wide Web."

> "Except as expressly provided above, nothing contained herein shall be construed as conferring any
> license or right under any Department of Consumer Affairs copyright."

And its preamble claims the widest possible reach: "All access to, and any use of, the Department of
Consumer Affairs' Home Page and any Web page or Internet site established by any of the Department's
boards, bureaus, programs or divisions, is governed by the following disclaimers and limits on use."

**(b) The statewide Conditions of Use**, [ca.gov/legal/conditions-of-use](https://www.ca.gov/legal/conditions-of-use/),
**linked from DCA's own footer**, under "Ownership":

> "In general, information presented on this website, unless otherwise indicated, is considered in
> the public domain. It may be distributed or copied as permitted by law."

**The conflict resolves in DCA's favour, on the ca.gov page's own words.** Two sentences do it,
**both read LIVE on ca.gov during this spike** (that page is reachable even though DCA's is not):

- The public-domain sentence **self-limits**: "unless otherwise indicated". It does not claim
  everything on every state site is public domain.
- The same page then defers expressly: "**Each department within the State may have additional
  privacy and use policies specific to the mission and needs of their work. Be sure to review those
  policies as you access additional sites within the State.**" (The page's own footer: "This Use
  policy is dated December 7, 2000.")

And the licence search's own disclaimer, at
[search.dca.ca.gov/disclaimer](https://search.dca.ca.gov/disclaimer) — **live and reachable** —
incorporates the DCA terms by reference: "All access to and use of this web page and any other web
page or internet site of the Department is governed by the Disclaimers and Conditions for Access and
Use as set forth at California Department of Consumer Affairs' Disclaimer Information and Use
Information." Footer: "© Department of Consumer Affairs".

**So the DCA "non-commercial use only" clause is the "otherwise indicated", and it controls.** That
makes the verdict **conditional** — terms exist and they say something definite — rather than
`unclear`. The existing dataset's `UNCERTAIN` is directionally right but under-specified: **the
uncertainty is not whether terms exist, it is whether a practice marketplace run by a 501(c)(3) is
"non-commercial use".** That is a question for the VIN Foundation's counsel, and it is the only
question left.

**Everything underneath points the other way, which is why this is worth counsel's time.** Business
and Professions Code **§27(c)(17)** *compels* publication — "The Veterinary Medical Board shall
disclose information on its licensees, registrants, and permitholders" — so this is a statutory
disclosure, not a courtesy. **§4853(a)** is the registration itself: "All veterinary premises shall
be registered with the board", with "Premises" defined at §4853(b) as "**the location of
operation** … a building, kennel, mobile unit, or vehicle". **B&P §161** authorises DCA to publish
"compilations, extracts, or summaries" at cost recovery, and the Public Information Files channel
charges nothing. Civil Code **§1798.61(a)** expressly permits release — "Nothing in this chapter
shall prohibit the release of only names and addresses of persons possessing licenses to engage in
professional occupations" — **with no purpose limitation** (the purpose limitation in §1798.61(b)
applies to *applicants* only). And Civil Code **§1798.60**, the solicitation clause, binds **the
agency** ("by an agency"), not the downstream recipient, and speaks of "**An individual's** name and
address" while a premises registration is an organisation record.

**A correction to the brief's own premise:** the candidate statute Government Code **§7927.310 does
not exist** — leginfo returns an empty section and the chapter range ends earlier. Former §6254.29
recodified to §7927.200, which is about social-security-number redaction and is unrelated. **There is
no California statute restricting a downstream recipient's use of a DCA licensee list for
solicitation.** The only commercial restriction that reaches a user is the contractual
"non-commercial use only" clause above.

**Two further conditions, independent of copyright, and one is decisive about method.**
`search.dca.ca.gov/robots.txt` reads, in its entirety:

```
User-agent: *
Disallow: /details/
Disallow: /download*
```

`/details/` is the individual licensee record path. **The site's own machine-readable policy refuses
automated retrieval of exactly the per-record pages that carry the managing licensee and the
enforcement flags** — and the DCA terms invoke **Penal Code §502** against "unauthorized use of any
State computing system", which is what gives that directive teeth. So the per-record enrichment route
is closed by the site's own policy even though the monthly bulk channel is not. **If California is
ever used, it must be through the Public Information Files bulk channel and not the search portal.**

### The finding that outranks the legal question

**California carries Florida's mailing-address defect, at Florida's magnitude, and it is visible in
the board's own published table before anything is downloaded.**

The bulk layout's address field is documented by DCA as "**Public Address of Record**" — there is no
premises or physical-location field in the layout at all. **B&P §27(a)** then states the hazard in
statute: each entity "shall allow a licensee to provide a post office box number or other alternate
address, instead of the licensee's home address, as the address of record", and may require a
physical address "**only for the entity's internal administrative use and not for disclosure**". The
VMB's own Administrative Procedure Manual confirms it publishes "the address of record".

And the board's own licensee-population table shows **654 of 3,905 active Veterinary Premises —
16.7% — flagged Out of State**. A veterinary premises is *by statutory definition* "the location of
operation" and must be in California to be registrable, so an out-of-state flag on a premises record
can only mean the published address is a mailing address, typically a corporate head office. Florida
measured 20.2% by the same logic. **This is a data-fitness blocker that would survive even a clean
"reuse allowed".**

**Counts, reconciled and slightly at odds with the existing dataset.** The VMB's 2025 Sunset Review
Report, Table 6, gives **3,905 active** Veterinary Premises at close of FY 2023/24, plus 654
delinquent/expired — **4,559 in total**. DCA's own monthly counts file dated 2026-09-01 gives
**4,744** disclosable records, which is the figure in the existing dataset. 4,744 is **above** the
board's most recent published active-plus-delinquent total, so **the 4,744 is not an active-premises
count and should not be quoted as one**. Plan on **~3,900 live premises**.

**A caveat that must travel with this row.** The whole DCA/VMB estate (`www.dca.ca.gov`,
`dca.ca.gov`, `vmb.ca.gov`, `solid.dca.ca.gov` — all on `159.145.8.19`) was **unreachable from this
environment** on every attempt by both passes and by a direct check from this session; it is an
egress block, not a dead site. The DCA disclaimer and the Public Information Files page were
therefore read from **Internet Archive snapshots of DCA's own URLs** (2026-08-20 and 2026-09-04), and
the Sunset Review PDF from a 2026-08-25 snapshot. The ca.gov Conditions of Use,
`search.dca.ca.gov/disclaimer`, `robots.txt` and the leginfo statutes were all read **live**. **A
rerun from an unblocked network should re-verify the DCA disclaimer against live HTML before counsel
relies on it** — it is the single sentence the whole California question turns on. The actual bulk
file URLs inside DCA's Box.com-embedded folder could not be enumerated at all and remain **UNKNOWN**.

---

## Colorado — the one genuinely unreviewed state

Colorado was the only one of the five with no prior review and a board request drafted but unsent.
**The answer is a clean NO, and the request does not need to be sent** — not because nobody answered
it, but because the statute answers it.

**No agency registers a veterinary facility in Colorado.** Three independent primary proofs:

1. **DORA issues no facility credential.** The Division of Professions and Occupations' own licence
   type table lists ten types in the Veterinary category — Veterinarian, Veterinary Technician,
   Veterinary Technician Provisional, Academic Veterinarian, Veterinary Professional Associate and
   military-spouse variants — and **every one is flagged as an individual, not a business entity**.
   Across the whole of DORA only 24 business-entity licence types exist (pharmacy outlets, funeral
   homes, crematories, barber and cosmetology shops, contractors, tissue banks) and **none is
   veterinary**. At record level, veterinary rows carrying an entity name: **zero**.
2. **PACFA expressly exempts veterinary hospitals.** This is the trap the Colorado row exists to
   avoid: the Pet Animal Care Facilities Act *is* a facility-licensing regime, and it does *not*
   cover veterinary clinics. **C.R.S. §35-80-103(2)(a)**, verbatim: "This article 80 does not apply
   to: (a) Any veterinary hospital which boards pet animals for the purpose of veterinary medical
   care only and does not actively solicit boarding business in any way". The Department of
   Agriculture's live Active Facilities list carries 23 licence categories — grooming, boarding,
   shelters, rescues, breeders, transporters, retail, aquarium, sanctuary — and **no veterinary
   category**.
3. **"Veterinary premises" in Colorado is a duty, not a registration.** C.R.S. **§12-315-122** is
   actually titled "Veterinary premises - licensed veterinarian responsible for veterinary medical
   decisions" and requires that a licensed vet be *designated* as responsible when a patient is
   present — fineable per day, but no registration, no permit and no list. **§12-315-106(6)**: "The
   board may, at any time, inspect veterinary premises to assure that they are clean and sanitary."
   **An inspection power without an enumeration.** Premises are inspected; premises are not
   enumerated.

**What is obtainable without contacting the board, and it is not premises data.** Two real bulk
artefacts exist, both free and unauthenticated:

- **DORA's licensee dataset** on the Colorado Information Marketplace
  (`data.colorado.gov/d/7s5z-vewr`) — 1.6 M rows across all professions, unrestricted CSV/SoQL, no
  row cap, stated cadence "Every day after midnight". Field names: lastName · firstName ·
  middleName · suffix · entityName · city · state · mailZipCode · licensePrefix · subCategory ·
  licenseNumber · licenseFirstIssueDate · licenseLastRenewedDate · licenseExpirationDate ·
  licenseStatusDescription · specialty · title · degrees · caseNumber · programAction ·
  disciplineEffectiveDate · disciplineCompleteDate · linkToVerifyLicense ·
  linkToViewHealthcareProfile. **No street address.**
- **The PACFA active-facilities Google Sheet**, which the Department of Agriculture tells users to
  download. Fields: Account Name · Doing Businsess As (DBA) *[sic]* · City · State · County ·
  Business License Category Name · Expire Date. **No street address, no ZIP** — and no veterinary
  hospitals in it anyway.

DORA's *own* roster generator (`apps2.colorado.gov/dora/licensing/Lookup/GenerateRoster.aspx`) is a
genuine bulk download but sits behind an AWS WAF CAPTCHA, so it is fine for a human and not
machine-retrievable. Whether it carries a street address the Socrata mirror lacks is **UNKNOWN**.

**Legal reuse: the cleanest of the five, and it does not help.** Both DORA datasets carry an
explicit `licenseId: PUBLIC_DOMAIN` dedication. The portal's terms
([data.colorado.gov/terms](https://data.colorado.gov/terms)) impose **no** bar on commercial reuse or
redistribution; they require an attribution string — applications "must include … 'The data made
available here has been modified for use from its original source, which is the State of
Colorado'" — and reserve the State's right to require termination of use. **C.R.S. §24-72-305.5**,
the CORA solicitation bar, was read and **does not reach this data**: it is confined to "Records of
official actions and criminal justice records", and a sweep of Title 24 Part 2 found it is the only
solicitation bar there. One trap worth naming: the Department of Agriculture quotes a **statute-
reprint** restriction (§2-5-118, LexisNexis, permission needed above 200 sections) — that governs
reprinting the C.R.S. *text*, not licence data.

**Coordinates: none, and not even a usable address.** No lat/lng and no street-address field in
either source. DORA gives city, state and a *mailing* ZIP for a *person*; PACFA gives city, state
and county. Everything would need geocoding from a partial address that does not identify a clinic.

**Counts, honestly labelled.** No veterinary-facility count exists. As of 2026-09-14/15: **6,259**
active Veterinarian licences, plus 264 Academic Veterinarian, 4,135 Veterinary Technician, 356
Provisional and 7 military-spouse — **individuals, not premises**. And **3,077** active PACFA
facility licences across 23 categories — **containing no veterinary hospitals, by statutory
exemption**.

**Legal verdict: reuse allowed** — for DORA's licensee data, which is explicitly public domain with
one required attribution string and no solicitation bar reaching it. That is a verdict about a
register of **people**, because Colorado has no register of premises to have a verdict about.

**Caveats on this row, which are real.** The pass that produced it was **geo-blocked**:
`dpo.colorado.gov`, `ag.colorado.gov` and `leg.colorado.gov` all returned CloudFront 403
("configured to block access from your country"), so those agency pages were read from **Wayback
snapshots of the agencies' own URLs** (DPO 2026-02-02, PACFA 2026-02-28 and 2025-11-18, Active
Facilities 2025-08-08) and from archived official OLLS C.R.S. PDFs. The live Google Sheet and the
Socrata APIs were read live. And **4 CCR 727-1**, the Board of Veterinary Medicine's own rules, could
not be read at all — `sos.state.co.us` was geo-blocked and no snapshot was found. The statute is
unambiguous, but a rules-level premises requirement cannot be excluded from what was actually read.

**On the second pass: it did not return.** An independent second Colorado pass was dispatched and had
not reported when this document was finalised, so **Colorado is the one row here standing on a single
pass.** Two things partly make up for it. First, the row does not rest on one source: it has three
independent proofs (no business-entity licence type at DORA, the PACFA statutory exemption, and the
duty-not-registration reading of §12-315-122), and they are of different kinds — an administrative
fact, a statute and a statute. Second, **I re-tested the geo-block myself from this session** and
reproduced it exactly — `ag.colorado.gov` and the OLLS C.R.S. PDF on `leg.colorado.gov` both return
**HTTP 403**, and a Justia mirror of §35-80-103 returns 403 as well — which corroborates pass 1's
account of *why* it had to read archived copies, without corroborating what it read in them.
**Treat Colorado as well-evidenced but single-sourced, and re-verify from a US network before it is
relied on.**

---

## Florida — carried from the existing dataset, incidentally corroborated

Florida was **not** re-researched as an open question. A pass completed before the sweep was
stopped, and it is recorded here only because it **independently reproduced the existing dataset's
Florida row** from primary sources, which is evidence about the file's reliability rather than about
Florida:

- **3,127** `VE` "Veterinarian Establishment" permits (plus 64 `VL` limited-service) — the file says
  3,127.
- The published address is the **mailing** address — the file says `address_type: MAILING`. The
  proof is arithmetic: **645 of 3,191 establishment rows (20.2%) carry a non-Florida state**, and a
  Florida veterinary premises cannot be in another state. DBPR's per-record lookup exposes
  `Main Address` **and** `License Location` as separate fields; the bulk file carries only the
  first.
- The regime is **permissive** — the file says `legal_regime: YES`. DBPR's own words: "the DBPR
  provides copies of electronic records to the public through free download", under Chapter 119,
  Florida Statutes. The statutory solicitation bars in Chapter 119 reach motor-vehicle records
  (§119.0712(2)(b)) and police reports (§119.105), and **not** professional licensee data.

Three fields reproduced, three matches. That is one state's worth of evidence that the file's
`State audit` sheet can be relied on, not a general warrant.

---

## What an enrichment could honestly add — and what it could not

**What the product counts today.** The "Veterinary Competition" figure is `establishments` from ZIP
Code Business Patterns at NAICS 541940, shaded at the ZIP Code Tabulation Area
(`app/api/market.py`: `BOUNDARY_METRIC["competition"] = ("establishments", "zbp")`,
`SHADING["competition"]["summary_level"] = "860"`). It is a **business register**, not a register of
veterinary premises, and the code already says so in the caveat it serves to integrators:
"Establishment counts (NAICS 541940) include corporate-owned and specialty locations; a proxy for
competitive density, not a count of independent practices."

That figure has three named gaps, and a state premises register is the only kind of source that
addresses any of them:

1. **The employer universe.** `EMPLOYER_UNIVERSE`, served with the layer: "The Census counts
   business locations with paid employees, so a practice with no paid staff is not in this figure."
   A single-vet clinic with no payroll is invisible to CBP/ZBP. It is not invisible to a state board
   that licenses the facility.
2. **The suppression floor.** `THRESHOLD_RULE`: "The Census does not publish a ZIP-level count for a
   category with fewer than three establishments, though they are counted in its all-industry
   total." A ZIP with one or two practices reads as no data. A state register has no such floor —
   its unit of publication is the licence, not a disclosure-protected cell.
3. **Industry code versus regulated activity.** NAICS 541940 is an industry classification applied
   to a business location. A state premises licence is a regulator's determination that *this
   address is a veterinary facility*, which is a different and stronger statement.

**What an enrichment would look like, concretely.** For a state that both registers premises and
permits reuse, the honest artefact is: *a count of currently-licensed veterinary facilities whose
registered address falls inside the practice's own 8 km ring* — the same ring the Community Context
card already names ("Within about 5 miles of the practice") — displayed as **its own figure, with
its own title, its own geography word and its own dataset name**, under ruling D-C51's grammar
(`<statistic> · <geography> · <basis>`). It would read as a state-board count and never as a Census
one.

**It must never be merged into the Census count, and this is not a stylistic preference.** The two
universes overlap in an unknown and unmeasurable way: the same physical clinic is one ZBP
establishment and one state premises licence, so addition double-counts, and subtraction requires an
address match nobody has validated. That is the evidence hierarchy's own rule one level down — CBP
and NES "are never added unless compatibility and non-duplication are established" — applied to a
source that is weaker on both counts than either Census product.

**What it could not establish, plainly:**

- **It is not nationwide and cannot be made so.** Of the five states looked at, **two have no
  register at all** (NY, CO), **one has none operating yet** (TX, from 2027), and the two that do
  publish (CA, FL) both publish a **mailing** address rather than the clinic's. The Browse map's
  class breaks are cut over *national* distributions (`AREA_LAYERS` competition stops `[4, 6, 10]`,
  measured over 4,720 US ZIP areas carrying a 541940 count), so a count that exists in a handful of
  states has no national scale to be classed against and no legend that could honestly colour it.
  **It is a number beside the map, not a layer on it.**
- **The address problem is the binding constraint, not the legal one.** This is the finding that
  most changes the shape of the work. Florida's bulk file carries the licensee's mailing address —
  proved arithmetically, 20.2% of "Florida premises" rows carry a non-Florida state — and California
  publishes an address of record with no separate premises field in the bulk layout. Both agencies
  hold the real location (DBPR's per-record page exposes `License Location` beside `Main Address`;
  California's exposes an address per premises), but **only one record at a time**. So the cost is
  not "geocode ~7,900 addresses"; it is "retrieve ~7,900 records individually, *then* geocode", and
  a ring count built on mailing addresses would place practices in the wrong ring — silently.
- **A licence is not a business trading today.** Registers carry licence status and expiry, which is
  the *licence's* lifecycle. A practice that closed last month may hold a live licence until
  renewal; one that opened last week may not appear. Florida's premises permits carry **no expiry at
  all** (only its 64 limited-service permits do), so "current" there means "not affirmatively
  revoked".
- **It carries no size, no weight and no revenue.** A licensed premises is one row whether it is a
  one-room clinic or a forty-vet referral hospital — exactly as an establishment is. Employment and
  payroll are the Census's contribution and no state register carries them, so the enrichment cannot
  improve the payroll layer or the opportunity score.
- **Coverage is definitional, not just partial.** What counts as a premises is each state's own
  statute. Florida exempts house-call-only and agricultural-animal-only practitioners from needing a
  permit at all (§474.215(4) and (6)); Colorado's PACFA expressly exempts veterinary hospitals from
  the one facility regime it has. Two states' counts are not comparable with each other, let alone
  with a Census cell.
- **The veterinarian-in-charge is mostly not published.** Only Texas's forthcoming regime requires a
  named **medical director** per facility (§801.602). California exposes a "Premises to Managing
  Licensee" relationship on the per-record page but not in the bulk layout; Florida's statute
  requires the name on the application but the extract omits it; Colorado requires a responsible
  veterinarian under §12-315-122 and publishes nothing.

## The registry rows the VIN Foundation would have to clear — written, NOT inserted

Nothing below has been inserted into any database, migration or seed. These are the rows that would
have to exist, and be moved off `unresolved`, **before a single record is fetched** — the same gate
`practice_locations` and `pet_ownership` already sit behind in `migrations/017_census_registry.sql`.

Two notes on shape. The brief writes the licence column as `licence_state`; the actual column is
**`license_status`**, and `'unresolved'` is one of its three permitted values
(`CHECK (license_status IN ('cleared','unresolved','blocked'))`). And `attribution_text` is
`NOT NULL`, so each row must carry a credit line even while unresolved — the strings below are
placeholders to be replaced with whatever each state's terms require, which is the rule
`dataset_registry.attribution_text` already follows for every other row.

```sql
-- NOT APPLIED. Written for the VIN Foundation to rule on, per D-C58.
-- Every row is license_status = 'unresolved'. None may be cleared without counsel reading the
-- state's own terms, and none may be fetched before it is cleared.
INSERT INTO dataset_registry
  (dataset_key, display_name, api_dataset_id, base_url, vintage, naics_param,
   refresh_cadence, license_status, license_name, license_url, attribution_text, notes) VALUES

  ('state_premises_tx','Texas veterinary medical facility registrations',NULL,
   'https://veterinary.texas.gov','not yet published',NULL,'unknown','unresolved',NULL,NULL,
   'Source: Texas Board of Veterinary Medical Examiners',
   'NO RECORDS EXIST YET. Occupations Code ch. 801 Subchapter M (SB 2155, 89th R.S.) took effect 2026-09-01; board rules due 2027-03-01; portal summer 2027; all facilities must register by 2027-09-01. Re-open this row after the rules are adopted, when reuse terms will exist to read. Today the only Texas source is the individual-licensee lookup, reCAPTCHA-gated with no bulk export.'),

  ('state_premises_ca','California veterinary premises permits',NULL,
   'https://www.dca.ca.gov/consumers/public_info/index.shtml','monthly',NULL,
   'Monthly','unresolved',NULL,NULL,
   'Source: California Department of Consumer Affairs, Veterinary Medical Board',
   'THE GATE IS ONE QUESTION: is a VIN Foundation marketplace "non-commercial use"? DCA''s Conditions for Access and Use authorise copying "for non-commercial use only", and search.dca.ca.gov/disclaimer makes that document govern all DCA sites; the statewide ca.gov "public domain" sentence self-limits with "unless otherwise indicated" and defers to departmental policies, so it does not override. Everything else points permissive: B&P s27(c)(17) COMPELS publication, s4853 is the registration, s161 authorises bulk compilations, Civ. Code s1798.61(a) permits release of licensee names and addresses with no purpose limit, and s1798.60 binds the agency not the recipient. NOTE: robots.txt disallows /details/ and /download*, so the per-record route (managing licensee, enforcement flags) is refused by the site''s own policy; only the monthly Public Information Files bulk channel is open. DATA-FITNESS BLOCKER independent of the licence: the published field is "Public Address of Record", B&P s27(a) lets a registrant substitute an alternate address and keep the physical one non-disclosable, and the board''s own table flags 654 of 3,905 active premises (16.7%) as out of state. 3,905 active at FY2023/24; the 4,744 disclosable figure is NOT an active count.'),

  ('state_premises_fl','Florida veterinary establishment permits',NULL,
   'https://www2.myfloridalicense.com/veterinary-medicine/public-records/','weekly',NULL,
   'Weekly','unresolved',NULL,NULL,
   'Source: Florida Department of Business and Professional Regulation',
   'Terms are permissive (ch. 119 F.S.; DBPR publishes the extract as a free download and no solicitation bar in ch. 119 or ch. 455 reaches licensee data), but the row stays unresolved until the VIN Foundation rules, and one question is open: myfloridalicense.com carries a bare "Copyright 2007-2025 State of Florida" notice with no use terms attached. 3,127 establishment + 64 limited-service permits. THE ADDRESS IS THE LICENSEE''S MAILING ADDRESS, not the clinic: 20.2% of establishment rows carry a non-Florida state. Host is Cloudflare bot-challenged; a browser-capable fetcher is required.'),

  ('state_premises_ny','New York veterinary premises',NULL,'n/a','n/a',NULL,
   'n/a','blocked',NULL,NULL,
   'Not in use — New York registers no veterinary premises',
   'NO SUCH REGISTER EXISTS. Education Law art. 135 and 8 NYCRR Subpart 62 license individuals only — while the same agency DOES register pharmacy premises under art. 137 s6808, so the veterinary absence is deliberate. Recorded as blocked rather than unresolved because the only NY register that does exist enumerates individuals, gives no practice address, and carries NYSED terms barring commercial republishing, aggregation and automated harvesting; reuse is conditional on written permission (legal@nysed.gov) plus a purpose-screened Bulk Verifications Request. Radiation-installation registers (10 NYCRR Part 16 s16.54; NYC Health Code art. 175 s175.51) do key veterinary premises to a street location but register imaging equipment rather than practices and are not published. Per-county registered-veterinarian counts ARE published and are the one reusable NY artefact.'),

  ('state_premises_co','Colorado veterinary premises',NULL,'n/a','n/a',NULL,
   'n/a','blocked',NULL,NULL,
   'Not in use — Colorado registers no veterinary premises',
   'NO SUCH REGISTER EXISTS. DORA licenses individuals only (no business-entity veterinary licence type); C.R.S. 35-80-103(2)(a) expressly exempts veterinary hospitals from PACFA, the one facility regime Colorado has; C.R.S. 12-315-122 imposes a responsible-veterinarian DUTY and 12-315-106(6) an inspection power, neither of which enumerates premises. DORA''s licensee data is explicitly public domain but carries no street address (city/state/mailing ZIP only). Residual UNKNOWN: 4 CCR 727-1 could not be read.');
```

## Method, and where the two passes disagreed

Every state was worked twice, by separate researchers, the second re-fetching the primary source and
trying to refute the first. **That is the part that earned the spike**, and it is worth recording
what it caught, because three of the five rows would have shipped wrong:

| State | What the second pass changed |
|---|---|
| **TX** | **Reversed the premise.** Pass 1 read the board's licence types and rulebook and concluded "no facility register, and none coming". Pass 2 read the *statute* and found SB 2155's Subchapter M, in force since 1 Sep 2026. Re-verified by a third party (me) against the enrolled bill and the board's announcement. |
| **NY** | Answer held, three supporting claims fell: a **bulk route does exist** (request-gated Downloads tab, "Veterinarian" among its 80 professions); the count **8,314 is worldwide, 5,765 is New York** — a 44% overstatement; and **two other NY agencies do register veterinary premises** (10 NYCRR §16.54, NYC Health Code §175.51), unpublished. Verdict moved **prohibited → conditional**. Pass 1's "TLS failure" on the site-wide terms was a tooling artefact — pass 2 read the page live. |
| **CA** | **Resolved what pass 1 called unresolvable.** The ca.gov/DCA conflict breaks in DCA's favour on ca.gov's own "unless otherwise indicated" plus its express deferral to departmental policies. Verdict **unclear → conditional**. Pass 2 also found the `robots.txt` bar on `/details/`, that **GC §7927.310 (named in the brief) does not exist**, and the **16.7% out-of-state** figure that makes California a data-fitness problem regardless of the licence. |
| **FL** | Not re-run — the sweep was stopped. Single pass. |
| **CO** | Second pass did not return in time. **Single-sourced**; see the note in that section. |

Where the passes disagreed, this document carries the second pass's finding and says so in the text
rather than quietly picking a winner.

## What I could not establish, and why

A spike that reports five clean rows is less trustworthy than one that reports its gaps. These are
the gaps.

1. **Colorado got one pass, not two, and its board rules were never read.** The second pass did not
   return in time, so Colorado is the one single-sourced row here. Separately, **4 CCR 727-1** (the
   Board of Veterinary Medicine's own rules) could not be read at all — `sos.state.co.us` was
   geo-blocked and no usable snapshot was found. The statute is unambiguous that no facility
   registration exists, but a rules-level premises requirement cannot be excluded from what was
   actually read. **UNKNOWN**, and it is the one hole in an otherwise clean Colorado row.
2. **Several Colorado and California primary pages were read from Wayback snapshots, not live.**
   `dpo.colorado.gov`, `ag.colorado.gov` and `leg.colorado.gov` returned CloudFront 403
   ("configured to block access from your country"), and `www.dca.ca.gov` and `vmb.ca.gov` were
   unreachable from this environment. Archived copies of the **agencies' own URLs** were used and
   are labelled as such, but **a rerun from a US network should re-verify California's two terms
   pages against live HTML** before anything is relied on. That is not a formality: California's
   terms are the deciding fact for the largest block of records.
3. **Texas's forthcoming register has no terms to read.** Subchapter M is in force but the board has
   not adopted rules or opened a portal, so there is no publication format, no field list, no
   cadence and no reuse term to assess. Everything about Texas after 2027 is a plan, not a fact.
4. **Neither California's nor Florida's bulk file was opened.** Both contain real licensee records
   and the no-storage rule forbids fetching them, so both field lists are the **published** record
   layouts, not verified against an actual header row. Florida's two most common establishment class
   codes (`VEC`, `VEM`) are not in DBPR's published code tables at all — the obvious reading is
   clinic and mobile, but that is a guess. **UNKNOWN.**
5. **No count of veterinary facilities was obtainable from any Texas state source**, which is
   expected — there is no register — but it also means there is no state-published baseline to check
   a future Texas register against.
6. **Whether any state asserts copyright in the data itself** is unresolved everywhere. Florida
   carries a bare copyright notice with no terms attached to it; Texas publishes no terms page at
   all; California's two official pages contradict each other. In no case did a primary source say
   plainly "you may redistribute this".
7. **A national anchor for NAICS 541940 was not taken.** `api.census.gov` now requires a key, and
   `CENSUS_API_KEY` is worker-only and was deliberately not used here.
8. **Adjacent federal regimes were not researched** and are named only so a reader does not assume
   they were missed: DEA controlled-substance registration is per-location for practices holding
   controlled substances, and appears to be gated to existing registrants. **Not established from a
   primary source, and out of scope for a state-register question.**
