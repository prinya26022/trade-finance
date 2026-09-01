# Investment Research Agent

A deterministic stock-analysis engine I built for my own investing, and then spent most of my
time trying to prove wrong.

It scores companies out of 11 — a Piotroski-style fundamentals check out of 8, plus a reverse-DCF
valuation leg out of 3 — and tracks every score it has ever produced so that a change can be
attributed to *the data moving*, *the company changing*, or *me changing the rules*.

**The part worth your time is not the scoring. It is the record of the scoring being wrong.**

---

## Three times the tool was wrong, and how I found out

### 1. The version stamp broke on its first real day

To tell "the rules changed" apart from "the market moved," I fingerprint the scoring code with a
content hash, stored alongside every score. I normalised away comments and formatting with
`ast.dump()` so that cosmetic edits would not bump the version.

CI (Python 3.12) and my machine (3.13) produced **different hashes from byte-identical source**.
`ast.dump()` embeds the interpreter's own node and field schema, so the "normalised" form was
version-dependent. My own docstring had listed this as a risk. It happened the first day the stamp
ran anywhere but my laptop.

Fixed by making normalisation text-based, and pinning two tests — the exact normalised text and the
exact digest — which now act as a live cross-version check on every push, since CI and dev run
different interpreters.

### 2. A "fragility" metric that was measuring itself

I shipped a sensitivity figure next to each valuation: how much the fair value moves per 1
percentage point of error in the growth estimate. I used it to claim one stock was "six times more
fragile" than another.

Asked to justify that, I measured it across the whole watchlist instead of trusting my own story.
The elasticity of enterprise value to growth turns out to be **nearly constant across every
company** — 6.5% to 7.7% — because the DCF is linear in its cash-flow base, so the derivative
depends on the discount rate and horizon, not on the business. What was left was arithmetic:

```
sensitivity  ≈  7 × (fair value ÷ market price)
```

Mean error 8.2% across the twelve names that compute. Since the discount shown *is*
`fair ÷ price − 1`, the column was a restatement of the number printed beside it. "Six times more
fragile" was true and mechanical, and said nothing about which business is harder to value.

Replaced with a measure of how much the answer moves when you swap the growth anchor for another
defensible one — which ranked the two headline stocks in the **opposite** order from the metric it
replaced.

### 3. A fix that shipped, and barely did anything

The check deciding whether to trust a structural growth estimate compared it against *revenue*
CAGR — while the model had already concluded, in an earlier audit, that *FCF* CAGR was the correct
unit. The trust check was running on a quantity the model itself called the wrong measure.

Two findings from A/B-ing the fix across all 423 stored analyses:

- **The obvious version would have been worse.** Switching to FCF alone stops flagging AAPL — whose
  structural estimate is 19.07%/yr against a long-run FCF CAGR of 6.67%, 12.4pp apart and under the
  15pp trigger — and hands it **2.42/3 instead of 0.0/3**, on a company whose revenue compounded at
  1.81% a year. The rule that shipped is "one piece of contrary evidence is enough."
- **The fix is nearly inert, and I said so.** It moved **6 rows out of 423, by 0.09 points**, and did
  not fix the case that motivated it — that one comes from the *threshold*, not from which history
  the threshold is measured against, and moving the threshold shifts the whole board, so it is a
  separate job with its own A/B rather than something to smuggle in alongside a consistency fix.

---

## What it actually does

- **Deterministic scoring, no LLM in the number.** Fundamentals `/8` and reverse-DCF `/3`. An LLM
  writes summaries and answers questions about the portfolio; it never touches a score. Sentiment
  used to be worth points until measurement showed it was driving 57% of all score jumps ≥0.5 while
  fundamentals sat still — so it was cut from the score and kept as commentary.
- **Reverse-DCF instead of a forecast.** Rather than predicting growth and deriving a price, it
  solves the market price for the growth rate implied by it, then compares that with what the
  company has actually done. Every constant is locked identically across every stock, so the gap is
  comparable between them.
- **Every number carries its provenance.** Which data window an anchor came from, whether that
  window starts on an anomalous year, which of five growth estimates was used and which were
  rejected and why, and the engine version that produced the score.
- **Point-in-time history.** 550+ stored analyses across 17 names. Nothing is recomputed backwards
  with today's inputs — including exchange rates, which are stored per-run for exactly that reason.
- Screener over a hand-picked universe, thesis + invalidation rules, decision journal, a
  tool-calling investigation agent, and a Next.js front end.

## What it cannot do yet, stated plainly

**I cannot prove that picking stocks this way beats simply buying an index.** The history is eight
weeks and there is one real position. That is a question about elapsed time, not about code, and
building a dashboard to display an answer I do not have would be worse than having no dashboard.
The point-in-time record exists so the question becomes answerable in twelve months.

Also open, and visible in the tool rather than hidden: an anchor threshold that swings one large-cap
valuation by 47 percentage points, and a growth cap that makes three wildly different estimates
collapse to the same number, which the interface flags as **agreement that is an artefact of my own
rules** rather than evidence about the company.

## Rules that survived contact

- **A number that is wrong but looks credible is worse than no number.** Foreign filers whose
  statements and price are in different currencies were refused outright rather than divided
  together — for two months, including the two highest-quality businesses on the board — until
  conversion could be done properly with the rate stored per-run.
- **Never hide the estimate you dislike.** Growth anchors the model rejects stay in the range,
  labelled, because dropping them makes the answer look sturdier than it is.
- **Report units people can argue with.** "The market prices 33.8%/yr FCF growth" is unfalsifiable.
  "This price requires revenue to reach roughly three times today's entire global semiconductor
  market" can be checked against the world.
- **No timing calls, and no sort-by-cheapest.** Ordering the board by discount would manufacture a
  buy list, which is not what this is.

## Stack

Python 3.12+ · FastAPI · SQLite · pytest · Next.js 15 · Gemini via `google-genai`.

648 tests, **fully offline** — no test reaches yfinance, SEC or an LLM, and the whole suite runs in
~8 seconds. GitHub Actions runs it on every push, plus a daily analysis job that commits its own
results back to the repo.

```bash
pip install -r requirements.txt
python -m pytest                                   # 648 tests, offline
uvicorn src.api.main:app --port 8000               # API
cd web && npm install && npm run dev               # UI on :3000
```

`AGENT_PROJECT.md` is the full engineering log — every phase, including the ones that found the
bugs above and the ones that concluded there was nothing to fix.

---

*Research tooling for my own decisions. Not investment advice, and it deliberately never says
buy or sell.*
