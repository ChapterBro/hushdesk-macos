PRD: HushDesk BP Audit (macOS)
Version: 1.0
Rules Master: hushdesk/config/rules_master_v1.1.1.json
Building Master (mac): hushdesk/config/building_master_mac.json
Output: TXT only
Timezone: America/Chicago

# HushDesk (BP Audit) for macOS — Product Requirements Document (PRD)

**Last updated:** 2025-11-04  
**Product:** HushDesk — BP Audit Module (macOS)  
**Owner:** Nursing Leadership / “HelpDesk” (weekend)  
**Status:** PRD v1.0 (ship-minded)

---

## 1) Product Overview

**What HushDesk is:** A local-first desktop app that automates **blood pressure (BP) medication hold-rule audits** from eMAR/MAR PDFs and produces binder-ready TXT outputs (HIPAA-safe). HushDesk parses each hallway’s MAR, applies strict BP hold rules, and emits clear exceptions without exposing names.

**Why it exists:** Reduce audit time, prevent parameter mistakes, and standardize weekend leadership reviews across halls—turning nurse documentation into actionable, binder-ready checklists.

**Platform target:** **macOS** (Apple Silicon). Runs **offline at runtime**.

**Out of scope (v1):** Modules only — **Showers**, **Point-of-Care (POC) Completion**, **Skilled Charting / Daily Skilled Evaluations**, **MAR/TAR Completion**, **ABX (Antibiotics) Watch** *(optional later).* No references to jurisdiction-specific policies.

---

## 2) Goals & Non-Goals

### 2.1 Primary goals (v1, macOS)
- Parse hall-specific MAR PDFs and evaluate **BP medication hold compliance** using strict rules.
- Produce **one output per hall**: **TXT checklist** (binder-ready with counts).
- Enforce HIPAA/PII guardrails: outputs show **room-bed only** (no names).
- Operate **offline**; no network dependency to process PDFs.

### 2.2 Non-goals (v1)
- Cross-tab audits beyond BP.  
- Web/mobile/Windows packaging.  
- Any cloud sync or telemetry.

---

## 3) Target Users & Environments

- **Primary user:** Weekend “HelpDesk” / Nursing leadership running Risky Business audits.  
- **Environment:** macOS (Apple Silicon), PDFs exported from PCC MAR/eMAR.  
- **Operating style:** Drag-and-drop → Review exceptions → Print/Save **TXT**.

---

## 4) Core Canon — BP Audit (authoritative rules)

> These rules are **canonical** and non-negotiable for v1.

1) **Vitals locality (same-column surgery):** For each medication and due time (AM/PM), use vitals **from the same date column within that medication block**. Prefer the **BP sub-row**; fall back to the **AM/PM cell** if needed. **Never** cross columns.

2) **Strict rules only:** Evaluate **SBP (systolic)** and **HR (pulse)** against explicit rules containing **only** “less than N” or “greater than N”, including symbol forms “< N” or “> N”. Reject **≤, ≥, “at or”, “equal/=”, “no less/more than”, “at least/most”. **Ignore DBP** for the hold decision.

3) **Administration state (per due cell) & precedence:**  
Resolve in this exact order (stop on first match):  
**(a) DC’D.** If the due cell shows an **X**, or the **entire date column for that med block is X’d**, classify **DC’D**.  
**(b) Allowed numeric code (4, 6, 11, 12, 15).** Treat as **not given** and **confirm the rule** for that dose/date (see §4).  
**(c) Given.** If the due cell shows **√** or a **HH:MM** time, classify **Given** and evaluate the rule.  
*Notes:* “H” is never used. Other numeric codes **should not occur**; if encountered, add a TXT **Notes** line: “Unexpected code (ignored)”.

4) **Decision logic (SBP & HR evaluated independently; one dose may emit two exceptions):**  
- **DC’D:** If §3(a) is true → **DC’D** (reviewed, excluded from exceptions).  
- **HELD-OK:** If §3(b) code is present **and** the rule **triggers** (vitals meet the threshold in the Audit Date column) → **HELD-OK** (include the vital in the line).  
- **HOLD-MISS:** If **Given** and the rule **triggers** → **HOLD-MISS**.  
- **COMPLIANT:** If **Given** and the rule **does not** trigger → **COMPLIANT** (silent).  
*Vitals are expected to be present for parametered orders unless DC’D; if unexpectedly missing in a non-DC’D column, add TXT “Notes — Vitals missing (unexpected)”.*

5) **Priority order:**  
1. **DC’D** checks first.  
2. **Allowed numeric code + confirm rule ⇒ HELD-OK.**  
3. **Given ⇒** evaluate rules ⇒ **HOLD-MISS** or **COMPLIANT**.

6) **Tokenizer & detection (surgical):**  
- Stitch BP tokens split across lines (example: “120/ [line break] 80” becomes “120/80”).  
- Detect HR (Pulse/HR/Heart rate).  
- Detect **√** or **HH:MM** as **Given**.  
- Detect numeric codes; drop initials.  
- Detect **X** (text X or drawn cross) as DC’D (cell or entire column).

7) **Review policy:** Every parametered due dose processed emits `reviewed: true` and contributes to **Reviewed**.

8) **Output discipline & phrasing:**  
- **TXT-only**; no JSON/CSV files.  
- Lines use **“Hold if …”** phrasing, for example: “Hold if SBP greater than 160; BP 165/70; given 08:00”.

9) **PII policy:** **Room & hall only** in outputs (no names, no initials).  
- Room-bed mapping: A→“-1”, B→“-2”. Bare room implies “-1” unless “-2” specified.

10) **Baked-in constants (read-only):**  
- **Building Master (mac):** `hushdesk/config/building_master_mac.json` — hall/room validation and mapping (room-bed only).  
- **Rules Master (v1.1.1):** `hushdesk/config/rules_master_v1.1.1.json` — strict SBP/HR phrasing (symbols **and** word forms) with rejected phrases; **DBP ignored**; **filename-first** date policy (**Audit Date = filename date minus 1 day**, **America/Chicago**; filename wins conflicts; display **MM/DD/YYYY**; clamp to that column); **vitals presence policy** (required unless DC’D); and **due-cell precedence** (DC’D → allowed code plus confirm rule → Given). Versioned, read-only, never printed in TXT.

---

## 5) Scope & Functional Requirements (v1, macOS)

### 5.1 Ingestion & Pre-processing
- Accept one or more **hall-specific MAR PDFs** (drag-and-drop or file picker).  
- Per page, build a dependable grid; if a page grid can’t be built, **skip safely** and continue (never crash the run).

### 5.2 Parsing pipeline (modules)

**Semantic-anchor navigation (no fixed sizes):**
- **Left rule block** (semantic anchor): detect **SBP/HR** hold phrasing using both **symbol** (“<”, “>”) and **strict word** forms (“less than” / “greater than”); reject fuzzy operators.
- **Day header line** (semantic anchor): detect printed **day numbers 1–31** and build **column bands** by **midpoints between adjacent day labels** (robust to spacing/kerning changes).
- **Row labels per block** (semantic anchor): detect **BP**, **Pulse/HR**, **AM**, **PM** and turn them into **y-bands per medication block** (do not use global bands).
- **Audit Date clamp:** read **only** the column that matches the **Audit Date** (filename date minus 1 day, Central; filename wins conflicts).  
- **Vitals extraction:** prefer **BP row**; fallback to **AM/PM cell inline** (same column).  
- **Due-cell precedence:** DC’D → allowed code plus confirm rule → Given.  
- **Decide:** emit **HELD-OK / HOLD-MISS / COMPLIANT / DC’D** per dose.

### 5.3 Output generation
- **TXT checklist** (binder-ready; only output):
  - **Header:** “MM/DD/YYYY · Hall: <HALL> · [optional] Source: <filename>”
  - **Counts line:** “Reviewed: N · Hold-Miss: N · Held-OK: N · Compliant: N · DC’D: N”
  - **Exceptions:**  
    - “HOLD-MISS — ROOM-BED (AM|PM) — Hold if SBP less than 110; BP 101/44”  
    - “HELD-OK — ROOM-BED (AM|PM) — Hold if HR less than 60; HR 58 | code 12”  
  - **Reviewed (collapsed by default):** Group by **HOLD-MISS / HELD-OK / COMPLIANT / DC’D**, sorted by room; AM before PM.  
  - **Notes:** Only for anomalies (for example, “Vitals missing (unexpected)”, “Unexpected code (ignored)”).  
  - **Generated stamp:** “Generated: MM/DD/YYYY HH:MM (Central)”.

---

## 6) UI/UX — Final Greenlight Spec (Run Audit only)

**Global shell**  
- Title: **HushDesk**  
- Kebab (••• “Modules”): BP Meds (current), Showers 🔒, Point-of-Care 🔒, Skilled Charting 🔒, MAR/TAR Completion 🔒, ABX Watch 🔒.  
- **Theme toggle:** Light/Dark; default to OS theme; persist choice.  
- UI label mapping: logic “Held-Appropriate” → user label **Held-OK**.

**Startup pop-up (every launch)**  
- *What HushDesk does:* Checks BP med-pass compliance by matching hold rules to documentation for the chosen date.  
- *What you’ll see:* **Hold-Miss, Held-OK, Compliant, DC’D, Reviewed.**  
- *Privacy:* Offline; no PHI/PII; room-bed only; local files; encryption at rest (planned).  
- Button: **Got it**.

**Header**  
- **Audit Date (Central):** Big stamp “MM/DD/YYYY — Central”.  
  - Default: **Yesterday** in **America/Chicago**.  
  - Filename strategy: If filename contains a date (for example, “2025-11-04”), set **Audit Date = filename date minus 1 day (Central)**; filename wins conflicts.  
  - Clamp: Always process **only** the Audit Date column; others ignored.  
  - Manual override: compact date picker; default reverts to yesterday each new run.
- **MAR PDF:** Drag-and-drop / Browse… (show filename only).  
- **Hall (auto):** Detected via room IDs vs Building Master; show “Hall: 100 / 200 / 300 / 400 (auto)”. If uncertain: yellow banner “Hall couldn’t be confirmed.”  
- **Run:** **Run Audit** (writes TXT).

**Progress**  
- **Run Audit:** Determinate bar “Page X of Y”.

**Summary**  
- Chips: **Reviewed | Hold-Miss | Held-OK | Compliant | DC’D**.  
- Only **Hold-Miss** shows red when count > 0.

**Results**  
1) **Exceptions** — Show **Summary**; if Hold-Miss = 0, display “Hold-Miss: 0 (no exceptions)”; otherwise list violations.  
2) **All Reviewed** (collapsed) — Row formats (no timestamps):  
   - **HOLD-MISS:** “ROOM (AM|PM) — BP S/D or HR N”  
   - **HELD-OK:** “ROOM (AM|PM) — … | code N”  
   - **COMPLIANT:** “ROOM (AM|PM) — … | ✓”  
   - **DC’D:** “ROOM (AM|PM) — X in due cell” or “column X’d”  
   Sort rooms ascending; AM before PM.

**Actions**  
- **Copy Checklist** (clipboard exact TXT) · **Save TXT** (private perms; toast path).

**Footer**  
- **Time:** duration of last run.  
- **Safety:** “Safety: On” badge opens privacy panel.  
- **TXT stamp:** “Generated: MM/DD/YYYY HH:MM (Central)”.

---

## 7) Non-Functional Requirements

- **Offline** at runtime; development may use network for installs/docs.  
- **Performance:** Typical hall PDF (about 10–30 pages) parsed in **20 seconds or less** on Apple Silicon; UI responsive; queue supports multiple PDFs.  
- **Reliability:** Skip malformed pages safely; never crash a run.  
- **Security/Privacy:** No names/initials; room-bed only; local paths; no telemetry.  
- **Compliance posture:** No jurisdiction-specific policy baked in.

---

## 8) Data & File Formats

### 8.1 Inputs
- **PDF**: PCC MAR/eMAR exports (per hall). Tolerate minor layout drift.

### 8.2 TXT export (binder-ready; only output)
- **Header:** “MM/DD/YYYY · Hall: <HALL> · Source: <filename>”  
- **Counts line:** “Reviewed: N · Hold-Miss: N · Held-OK: N · Compliant: N · DC’D: N”  
- **Body:** “Hold if …” lines, grouped by room-bed (no names).  
- **Notes:** Only for anomalies (for example, “Vitals missing (unexpected)”, “Unexpected code (ignored)”).  
- **Generated stamp:** “Generated: MM/DD/YYYY HH:MM (Central)”.

### 8.3 Rules Master (read-only; **v1.1.1**)  
- **Path:** `hushdesk/config/rules_master_v1.1.1.json`  
- **Purpose:** Define strict accepted phrasing for SBP/HR rules (symbol “<”/“>” and word forms), rejected phrases, date derivation, vitals presence policy, due-cell precedence, and **semantic-anchor navigation hints**. Never printed in TXT.  
- **Date policy (filename-first):** Parse filename date using patterns: “YYYY-MM-DD”, “MM-DD-YYYY”, “MM_DD_YYYY”, “YYYY_MM_DD”. **Audit Date = filename date minus 1 day (America/Chicago)**; filename wins conflicts; clamp to that date; display **MM/DD/YYYY**.  
- **Accepted strict patterns:**  
  - **SBP below:** “SBP/Systolic … below/less than N” or “SBP < N”  
  - **SBP above:** “SBP/Systolic … above/greater than N” or “SBP > N”  
  - **HR/Pulse below:** “… below/less than N” or “HR < N” / “Pulse < N”  
  - **HR/Pulse above:** “… above/greater than N” or “HR > N” / “Pulse > N”  
  - **DBP** ignored for decisions.  
- **Rejected phrasing:** “≤, ≥, at or above/below, equal/=, at least/at most, no less/no more”.  
- **Administration precedence:** “DC’D” (X cell/column) → “Allowed code (4,6,11,12,15) plus confirm rule” → “Given (√/time)”.  
- **Vitals presence policy:** Required for parametered orders unless DC’D; if missing, add TXT Note.  
- **Semantic anchors:** left rule block for rules; day numbers → column midpoints; row labels (BP/Pulse/AM/PM) → per-block y-bands; prefer BP row, fallback AM/PM inline.

### 8.4 Building Master (mac) — hall roster (read-only)
- **Path:** `hushdesk/config/building_master_mac.json`  
- **Mapping:** Room-bed only; default bed if unspecified = “-1”.  
- **Halls & splits:**  
  - **Mercer:** 101–118 (splits **107-1/2**, **118-1/2**)  
  - **Holaday:** 201–218 (splits **207-1/2**, **218-1/2**)  
  - **Bridgeman:** 301–318 (splits **307-1/2**, **318-1/2**)  
  - **Morton:** 401–418 (splits **407-1/2**, **418-1/2**)  
- **Use:** Validation (is_valid_room), hall detection (hall_of(room)), TXT grouping.

---

## 9) macOS Technical Plan

- **Date/Timezone:** All date logic uses **America/Chicago**; default Audit Date is **yesterday** (or **filename date minus 1 day**).  
- **Column clamp:** Parser selects only the Audit Date column; others ignored.  
- **Missing column:** If the selected date column doesn’t exist, show yellow banner “No data for selected date” and allow manual override.  
- **DST:** Treat audits as **date-based** (AM/PM cells evaluated normally across DST).

**Stack & packaging**  
- Python 3.11 + PySide6 UI; PyMuPDF + PDFMiner fallback.  
- PyInstaller → “.app” → signed & notarized “.dmg” (Developer ID; Hardened Runtime; notarytool).  
- App data under “~/Library/Application Support/HushDesk/”.

---

## 10) Repo Layout & “AI-Ready” Conventions

- `README.md` — quick start.  
- `ARCHITECTURE.md` — blocks → tracks → grid → tokenizer → holds → decide → outputs.  
- `TASKS.md` — bite-size issues (30 minutes or less each).  
- `scripts/` — `dev`, `build`, `sign`, `notarize`, `qa`.  
- `tests/` — synthetic MAR fixtures + golden TXT snapshots.  
- `hushdesk/config/building_master_mac.json` & `hushdesk/config/rules_master_v1.1.1.json` — read-only constants.  
- CI: lint/format/tests; no telemetry.

---

## 11) QA & Acceptance

### 11.1 Unit tests
- BP stitcher; HR detector; Given vs code vs X precedence; strict rule parser (symbols + words); filename-first date clamp; decision engine priority.

### 11.2 Golden fixtures (verified set)
- **Filename → previous day (Central).** “...2025-11-04.pdf” ⇒ Audit Date “11/03/2025” only.  
- **Filename vs Printed-on conflict (filename wins).**  
- **SBP symbol “<”.** One compliant, one HOLD-MISS.  
- **SBP phrase “less than”.** HOLD-MISS when threshold crossed.  
- **HR phrase and symbol.** One HOLD-MISS (for example, HR 58), one COMPLIANT (for example, HR 62).  
- **Reject fuzzy operators.** Phrases with “≤/≥/at or …” produce **no exceptions**.  
- **Dual rule “SBP < 110 and/or HR < 60”.** When both trigger, emit **two exceptions**; when only one triggers, emit one.  
- **DC’D — due-cell X.** AM DC’D; PM evaluated normally.  
- **DC’D — whole column X’d.** Both AM/PM DC’D; no rule checks/codes.  
- **Allowed code plus confirmed trigger ⇒ HELD-OK.** Code 15 with BP 101/44 under “SBP < 110”.  
- **Vitals presence fallback.** BP row missing; AM cell contains “102/60” → value echoed.  
- **Column clamp and anchors.** Neighboring columns with distractor vitals ignored; slight kerning perturbation tolerated.  
- **DST weekend sanity.** After fall-back Sunday, correct date clamp and stable chips.

### 11.3 Manual checks
- Process 1–2 real hall PDFs end-to-end: verify counts (**Reviewed · Hold-Miss · Held-OK · Compliant · DC’D**), “Hold if …” phrasing, **no names**, DC’D behaves as defined.

### 11.4 Acceptance criteria (MVP)
- On the **Audit Date**:  
  - **HOLD-MISS** when Given and threshold crossed.  
  - **HELD-OK** when allowed code present **and** rule triggers; vital echoed.  
  - **DC’D** when X in due cell or entire column X’d.  
  - No cross-column vitals; always same-column.  
  - All records show **room-bed** only.

---

## 12) Milestones & Deliverables (macOS)

- **M0 — Port & scaffold (0.5–1 day):** New Mac repo; add configs, scripts, CI skeleton.  
- **M1 — App bundle baseline (1–2 days):** “.app” opens; drop-zone; can load PDF.  
- **M2 — Parser parity (2–4 days):** Pipeline running on macOS; unit tests pass; golden fixtures green.  
- **M3 — Outputs & UX polish (1–2 days):** TXT finalized; chips & counts; errors polished.  
- **M4 — Package, sign, notarize (0.5–1 day):** Signed “.dmg” opens clean on a fresh account; release notes and checksum posted.

---

## 13) Future Roadmap (module order — post-BP)

These map 1:1 to the Modules menu (kebab) and inherit offline, TXT-only, room-bed privacy canon.

1) **Showers** (Fri/Sat master → completion + refusals)  
   - Inputs: PCA/PCC exports or scanned logs; Friday/Saturday Shower Master (future read-only constant).  
   - Output: TXT checklist with “Done · Refused · Still Due” by room-bed; includes “resident signed refusal” note requirement.  
   - Cross-checks: Date clamp (yesterday, Central); room validation via Building Master.

2) **Point-of-Care (POC) Completion**  
   - Inputs: POC summary exports; staff 7–7 shifts.  
   - Output: TXT with per-hall completion percentage by shift (Day 7:00–18:59; Night 19:00–06:59), halls only.  
   - Rule: Anything not **Restorative** counts as **missing**.

3) **Skilled Charting / Daily Skilled Evaluations**  
   - Inputs: Daily Skilled Evaluation exports.  
   - Output: TXT with completion audit by hall; missing entries flagged; binder-ready.

4) **MAR/TAR Completion**  
   - Inputs: MAR/TAR completion exports for the Audit Date.  
   - Output: TXT with “Unsigned / Late / Missing” by hall; binder-ready summary chips.

5) **ABX (Antibiotics) Watch** *(optional later)*  
   - Inputs: ABX start/stop, culture dates, MAR administrations.  
   - Output: TXT with course windows, missed doses, availability checks (pharmacy vs Cubex).

---

## 14) Glossary

- **BP:** Blood pressure (SBP/DBP).  
- **SBP:** Systolic blood pressure (used for decisions).  
- **HR:** Heart rate / pulse (used for decisions).  
- **DC’D:** Discharged / not in facility for that date/time (X in due cell or whole column X’d).  
- **Held-OK (Held-Appropriate):** Not given with allowed numeric code **and** rule confirmed triggered.  
- **Hold-Miss:** Should have been held (rule triggered) but **Given**.  
- **Compliant:** Given and rule did **not** trigger.
