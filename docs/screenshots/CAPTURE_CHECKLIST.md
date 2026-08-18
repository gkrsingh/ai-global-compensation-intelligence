# Screenshot capture checklist

## Status: 2 captured, 2 outstanding

| Shot | File | Status |
| --- | --- | --- |
| Calculator + market context (US) | `us-calculation-with-market-context.png` | **Captured** — embedded as the README hero |
| Calculator input form | `calculator-form.png` | **Captured** — embedded under "Getting started" |
| AI insight panel | `ai-insight.png` | **Outstanding** — see shot 3 below |
| Comparison view | `comparison.png` | **Outstanding** — see shot 4 below |

The two outstanding embeds are **commented out** in the README, so nothing
renders as a broken image. Capture them, save with the exact filenames above,
and uncomment the two `![...]` lines in the README's "The AI layer, and the
comparison view" section — the paths are already correct.

### What changed from the original plan

The captured pair does not map one-to-one onto the four shots this checklist
originally specified, and the filenames were corrected to describe what the
images actually show rather than what was planned:

- **`us-calculation-with-market-context.png`** is a single full-page capture
  that covers what were originally shots 1 *and* 2 — a complete calculation
  with its per-bracket tax breakdown, and directly below it the market context
  panel with both sources. It is a **US $120,000 Product Management** case, not
  the India case shot 1 specified, so it is named and captioned accordingly.
  It happens to be a better illustration than the original plan: BLS offers
  only a *poor match* for product management while the survey offers a *close
  match*, which puts the match-quality labelling on display.
- **`calculator-form.png`** is the input form before submission — not one of
  the four originally planned shots, but useful, so it is used under
  "Getting started".

Shot 1 (the India case) and shot 2 (a market-panel-only crop) are **not
outstanding** — the captured full-page image covers both. Only shots 3 and 4
below remain.

---

Automated capture is not available in the environment this was prepared in
(the headless browser pane does not composite frames, so `screenshot` times
out), which is why these are captured by hand.

Every expected value below was verified by actually driving the running app —
they are the real figures the app produces, not predictions. If what you see
differs, something has genuinely changed and is worth investigating rather
than screenshotting.

---

## Setup (once, before any shot)

```bash
# Terminal 1 — backend
cd backend
set -a && source .env && set +a
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8001

# Terminal 2 — frontend
cd frontend
npm run dev
```

Open <http://localhost:5173>.

Data must already be ingested (all three commands are idempotent):

```bash
cd backend
.venv/bin/python -m app.reference_data.seed
.venv/bin/python -m app.market_data.ingest                       # BLS OEWS
.venv/bin/python -m app.market_data.ingest_survey <results.csv>  # Stack Overflow
```

Capture at roughly **1280px wide**. Light mode. Crop to the described region —
no need to include the whole page.

---

## 1. `calculator-india.png` — NOT NEEDED (covered)

> Superseded by `us-calculation-with-market-context.png`, which already
> shows a complete calculation with its bracket breakdown. Kept only
> because the India case is the hand-verified one and is worth capturing
> if you ever want a second calculator shot.

**The hand-verified India case.**

| Field | Value |
| --- | --- |
| Country | India (IN) |
| Job family | *(leave "Not specified")* |
| Target currency | Indian Rupee (INR) |
| Tax regime | New regime *(the default)* |
| Component | Base salary |
| Amount | `1500000` |
| Component currency | INR |

Click **Calculate**.

**Expected on screen — verified:**

- Gross compensation (cash only, before tax) — **₹1,500,000.00**
- Total compensation — **₹1,500,000.00**
- Total tax — **₹93,750.00**
- Net compensation (cash only, after tax) — **₹1,406,250.00**
- Standard deduction applied to income tax: **₹75,000.00**
- Bracket table showing 0% / 5% / 10% / 15% rows

**Capture:** the results summary plus enough of the tax-breakdown bracket
table to show the per-bracket math. That bracket table is the point of the
shot — it shows the calculation is transparent, not a black box.

---

## 2. `market-context-two-sources.png` — NOT NEEDED (covered)

> Superseded by `us-calculation-with-market-context.png`, whose lower
> half is exactly this panel with both sources. Kept in case you later
> want a tighter crop of just the market panel.

**The most distinctive feature: two sources, side by side, never averaged.**

| Field | Value |
| --- | --- |
| Country | United States (US) |
| Job family | **Software Engineering** *(required — the panel needs it)* |
| Target currency | US Dollar (USD) |
| Component | Base salary |
| Amount | `150000` |
| Component currency | USD |

Click **Calculate**, then scroll to **Market context**.

**Expected on screen — verified:**

- Banner: *"2 sources are shown below, separately. They measure different
  things and will not agree — they are never combined or averaged…"*
- **Source 1 — US Bureau of Labor Statistics** (`May 2025 · published
  2026-05-15`)
  - Amber warning: *"These figures exclude bonuses and equity."*
  - Software Developers · CLOSE MATCH · median **$135,980**
- **Source 2 — Stack Overflow Annual Developer Survey 2025** (`2025 survey`)
  - Red banner: *"How representative is this?…"*
  - Developer, back-end · CLOSE MATCH · median **$176,000**
  - Experience rows: `0-2 yrs`, `3-5 yrs`, `6-10 yrs`, `11+ yrs` with `n=` counts
  - At least one `Insufficient sample (only N responses) — not published` row

**Capture:** both source blocks in one frame if possible — the two different
medians ($135,980 vs $176,000) sitting side by side, unreconciled, is exactly
what the shot needs to convey. Include the "never combined or averaged"
banner. If it will not fit at 1280px, zoom the browser to 80% rather than
splitting it into two images.

---

## 3. `ai-insight.png` — OUTSTANDING

**Requires being logged in** (AI insight is auth-only), and makes one real
Gemini API call. `GEMINI_API_KEY` must be set in `backend/.env`.

1. Click **Log in**, register or sign in with any email/password.
2. Run the **US $150,000 Software Engineering** calculation from shot 2 —
   confirm *"Saved to your history."* appears.
3. Scroll to **AI-generated insight** and click **Generate AI insight**.
4. Wait for the text (a few seconds).

**Expected on screen:**

- Purple-accented panel headed *AI-generated insight*
- Real generated prose referencing figures from the calculation
- Footer disclaimer: *"Generated by AI from the figures above — it does not
  compute, verify, or add any numbers of its own. Every number it states is
  checked against the calculation above before being shown to you."*

**Capture:** the generated text **and** the disclaimer together. The
disclaimer is the whole point — it is what distinguishes this from a chatbot
guessing at salaries.

> If generation fails with *"AI insight could not be generated"*, that is the
> numeric-consistency checker refusing unverified output. Click **Try again**.
> Do not screenshot the failure state for the README — though it is a
> perfectly honest thing to show elsewhere.

---

## 4. `comparison.png` — OUTSTANDING

**Requires being logged in**, and two saved calculations.

1. While logged in, run two calculations so both save to history — e.g.
   the **US $150,000** one from shot 2, and an **India ₹1,500,000** one.
2. Click **Compare**.
3. Select **both** calculations (the submit button stays disabled until two
   are selected).
4. Name it something neutral like `US vs India offer`, pick a comparison
   currency (**USD** reads most clearly), and submit.

**Expected on screen:**

- Both offers side by side, normalised into the chosen currency
- Per-metric gap analysis (gross, net, effective tax rate)
- The exchange rate used, with its date and ECB source

**Capture:** the side-by-side entries plus the gap analysis. The visible
exchange-rate provenance is worth including — it shows the conversion is
cited rather than assumed.

---

## After capturing

```bash
git add docs/screenshots/*.png
git commit -m "docs: add AI insight and comparison screenshots"
git push
```

Then uncomment the two `![...]` lines in the README's "The AI layer, and the
comparison view" section. The paths there already match these filenames.

**Real screenshots of real data only.** No mockups, no edited numbers. A
fabricated screenshot in a project whose entire premise is that numbers must
trace to a source would undercut the thing it is demonstrating.
