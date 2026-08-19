# Screenshots

Real captures of the running application against real seeded data. No
mockups, and no hand-edited numbers — a fabricated screenshot in a project
whose entire premise is that figures must trace to a source would undercut
the thing it is demonstrating.

## What is here

### `us-calculation-with-market-context.png`

Embedded as the README hero. A single full-page capture of a **US $120,000
Product Management** calculation:

- Gross $120,000 → total tax **$26,750** → net **$93,250**
- The complete per-bracket tax breakdown (social security, income tax,
  medicare, additional surtax), showing the calculation is transparent rather
  than a black box
- Below it, the **market context** panel with **both sources shown
  separately** — BLS OEWS and the Stack Overflow survey — each with its own
  methodology note, its own warning banner, and no attempt to reconcile them

It happens to land on the most instructive role available: BLS offers only a
**poor match** for product management, because SOC-2018 has no product
management occupation at all, while the survey offers a **close match**. The
match-quality labelling is visible in the shot rather than merely described.

### `calculator-form.png`

Embedded under "Getting started". The input form — country, optional job
family, target currency, and one or more compensation components each with
its own amount and currency.

## What is deliberately not here

Screenshots of the **AI insight panel** and the **comparison view** were
planned and then decided against. Recorded as a decision rather than left
looking like an oversight, since both are real features described in the
README:

- The **AI insight panel** would cost a real, billed API call to produce a
  shot whose most important element is a disclaimer — that the model does not
  compute, verify, or add any number of its own. That guarantee is enforced in
  code and covered by tests (see `backend/app/ai/services/consistency.py` and
  its test suite), which is a stronger demonstration than a picture of it.
- The **comparison view** requires two saved calculations behind auth, and
  what it shows — normalisation into one currency, per-metric gaps, and a
  cited exchange rate — is already stated in the README and exercised by
  `backend/tests/test_comparison_api.py`.

If either is ever captured, save as `ai-insight.png` / `comparison.png` and
add the embed to the README's "The AI layer, and the comparison view"
section.

## Note on capture

These were captured by hand. Automated capture was unavailable in the
environment this project was built in — the headless browser pane does not
composite frames, so programmatic screenshots time out. Both existing shots
are dark-mode at roughly 1280px wide; anything added later should match.
