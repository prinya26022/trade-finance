# AGENT_PROJECT.md — Investment Research Analyst Agent

## What this is
An agent that helps me research assets I'm watching. I add a ticker to a watchlist; the
agent pulls news, price, and (later) fundamentals, and produces an analyst-style summary
of whether the asset is worth a closer look — the kind of first-pass work a junior finance
analyst does. Built for **US stocks first**, designed so I can **add crypto later**.

**This is NOT a trading bot.** It summarizes so *I* decide. It is a research tool, not
investment advice — for me or anyone who might use it.

## Why it exists (context for any AI assistant reading this)
Two goals at once:
1. **Skill-building for a remote AI/dev job.** This is my "AI agent" portfolio piece (see
   `remote_roadmap_12month.md`). It must show *real* agent skills — not another RAG app:
   a planning loop, multiple tool calls, handling tool failures, and **evals** (measuring
   how often the agent is actually correct).
2. **A tool I actually use** for my own portfolio (I hold US stocks and crypto).

## How to work with me (READ BEFORE WRITING ANY CODE)
I am strong in frontend (React / TypeScript / Next.js). New to me here: **agent loops,
Python, financial-data parsing, and evals.** My goal is to BUILD the skill, not just ship.

- For anything **new to me** (the agent loop, Python, parsing financial data, writing
  evals): **do NOT write it for me.** Help me plan, let me write it, then review my code
  and explain *why*. If I'm stuck, give hints, not the full answer.
- For **boilerplate** I already understand: you can write it, I'll read it.
- Explain trade-offs when you suggest something, so I can judge it.
- **Goal check:** I should be able to rebuild any part of this from scratch without you.

## Stack (decided — Python, on purpose)
- **Language: Python.** A deliberate stretch — I'm strong in TS, but Python is the right
  tool here (best ecosystem for financial data + the lingua franca of AI, which my remote
  target values). Ramp me using the tutor rule above.
  - *(If staying one language matters more to me later, TS is possible via LangChain.js —
    but the financial-data ecosystem is weaker. Default is Python.)*
- **LLM:** plain OpenAI / Anthropic SDK first (understand the raw loop before frameworks)
- **Data:** yfinance (price + news) to start; SEC EDGAR for financials (Phase 2)
- **Storage:** SQLite to start; Postgres later only if needed
- **Scheduling:** simple scheduler / cron (Phase 3)

## Core design principle: asset-agnostic from day 1
The agent must not care whether it's analyzing a stock or crypto. Design **one interface
for "fundamentals" with swappable implementations**:
- stocks -> financial statements (EDGAR)
- crypto -> on-chain metrics + tokenomics (added later)

Everything else — watchlist, news, price, LLM summary, scheduling, evals — is **shared**.
=> Build stocks first, but structure it so adding crypto = writing **one** new fundamentals
module and reusing the rest. This "extend without rewriting" design is the engineering
signal that matters in interviews.

## What makes this an AGENT (not a script)
1. **Planning** — given a ticker, it decides what to pull (some need news focus, some need
   financials)
2. **Tool calling** — news tool, price tool, (later) fundamentals tool
3. **Tool-failure handling** — if a source is down or data is missing, it adapts instead of
   crashing
4. **Loop with a stop condition** — gather -> assess -> decide if enough -> summarize
5. **Evals** — measure correctness (see below)

## Phase 1 scope (current — do NOT jump ahead)
Build the skeleton for **one US stock**:
1. **Watchlist store** — include an `asset_type` field (`"stock" | "crypto"`) now, even
   though crypto isn't built yet (this forces the asset-agnostic shape early)
2. **Price tool** (yfinance) and **news tool** (yfinance news or a free news API)
3. **LLM summary step with STRUCTURED output** (not free text), e.g.:
   `{ ticker, price_snapshot, key_news[], sentiment, what_to_watch[], confidence }`
4. **A simple agent loop** that ties it together for one ticker, on demand

**Do NOT build yet:** financial-statement parsing (Phase 2), crypto/on-chain (later),
daily scheduling (Phase 3), the full eval harness (Phase 4 — but seed it below).

## Eval seed (start thinking in Phase 1)
The portfolio-grade part is measuring correctness. Even in Phase 1, add **one** basic
check: does the structured summary pull the *real* current price and a *real* headline
(not a hallucinated one)? Later phases measure harder things (did it read the revenue
figure from the filing correctly, and how accurate as a %).
**Rule:** evals compare against ground truth (real prices, real filing numbers) — never
let the LLM grade itself on facts it may have made up.

## Later phases (sketch only — direction, do NOT build now)
- **Phase 2:** stock fundamentals module (EDGAR) -> parse revenue / profit / debt /
  cashflow -> feed the LLM -> "is the fundamental strong or weak, and where." *(The hard,
  impressive part.)*
- **Phase 3:** daily scheduled runs + history + cross-day change detection (new filing,
  major news, unusual price move)
- **Phase 4:** real eval harness — extraction accuracy on financials measured as a %
- **Phase 5:** **Thesis Journal + invalidation tracking** — record *why* I hold each ticker
  (free-text thesis) plus machine-checkable invalidation rules (e.g. "exit if operating
  margin < 10%") + optional fair-value estimate. Change detection becomes *thesis-aware*:
  it alerts when MY specific exit conditions trip, and the LLM analysis is told my thesis so
  it judges "does today's data still support your reason for holding?". This closes the loop
  on the checklist's ด่าน 4 (invalidation point) + ด่าน 7 (thesis stop) + journal (ด่าน 182).
- **Phase 6:** eval maturity — pytest test suite + golden dataset + CI (tests green on every
  push), extraction accuracy reported as a headline %.
- **Phase 7:** dashboard UX — triage-first view (needs-attention vs quiet), per-ticker detail
  page with multi-year trend charts, ranking/screener, mobile-friendly.
- **Later:** add crypto as a second `asset_type` (on-chain / tokenomics module), reusing
  everything else; deeper valuation (reverse-DCF / margin of safety / peer comparison).

Phases 1-8 are COMPLETE (incl. Phase 6 pytest+CI: tests run offline on every push).
Phase 9 (crypto thin slice) DONE: second asset_type wired end-to-end (price/news/tokenomics
fundamentals via yfinance + crypto framework), reusing watchlist/loop/eval/dashboard — proving
the asset-agnostic design.
Phase 10 (persisted health score) DONE: health score moved from a frontend-only computed value
to a Python source of truth (src/agent/health.py), computed at analyze() time using in-memory
facts + this run's invalidation breaches (not stale DB reads), and stored on every history row
(health_score, health_reasons_json) — so it's a real eval signal with trend + a reasons trail
to debug sudden drops, not just a live snapshot. Dashboard/detail page read the persisted value
(resolveHealth), falling back to the old client-side formula only for pre-Phase-10 rows.
Phase 11 (portfolio page + holding management UI) DONE: /portfolio page shows dollar PnL
(cost basis / market value / unrealized $ + %), edge vs benchmark, health, and breach flags per
holding, anchored on edge+thesis (not raw profit) to stay a research tool, not a money tracker.
portfolio_edge() extended with dollar figures + portfolio weights (uses shares). Holdings are now
managed from the web (set/add-shares/sell) via PUT/POST/DELETE endpoints — add_shares does
weighted-average cost automatically — replacing the CLI-only bridge.
Phase 12 (SEC XBRL ground-truth eval) DONE: src/providers/stock/xbrl.py pulls real 10-K figures
(Revenue/NetIncome/OperatingIncome/StockholdersEquity/Assets) via data.sec.gov/api/xbrl/
companyfacts, reusing edgar.py's CIK lookup — disk-cached 7 days. check_xbrl_accuracy compares
our computed margins/ROE against ratios computed from these raw XBRL numbers directly: a real
independent ground truth, unlike Phase 4's check_extraction_accuracy which only checks
consistency against yfinance's own numbers (same ultimate source as ours). Verified 100% match
across the whole watchlist on real data. Wired into analyze() (stock only), persisted per row
(xbrl_accuracy/xbrl_json), surfaced in the dashboard meta row and folded into the quality report
alongside Phase 4's check (both layers flagged separately, alert-only).
Phase 13 (agentic investigation loop) DONE: closes the biggest gap vs this project's own thesis
— until now the "agent" was a straight pipeline (gather -> one LLM call). src/agent/investigate.py
is a real agentic loop: the LLM plans and calls tools one at a time (list_metrics,
get_metric_trend, get_recent_news, check_sec_filing), follows the evidence, and concludes on its
own — with a bounded step budget (stop condition) and full tool-failure handling. The loop
(run_investigation) is separated from the brain (GeminiPolicy, manual google-genai
function-calling) so it's unit-tested offline with a scripted fake policy. Every step (tool + args
+ observation) is logged, persisted (investigations table), served (/api/investigation/{ticker}),
and rendered on the ticker detail page as a "how the agent investigated" transcript — both a demo
artifact and an eval artifact. Opt-in (CLI / on-demand) so daily runs stay cheap on quota.
Phase 14 (company biography timeline) DONE: the on-brand answer to "why is this business where
it is over the years" — deliberately NOT news→price attribution (that's the backtest/hindsight
trap). src/agent/timeline.py::build_timeline merges multi-year material events (full 8-K history
via edgar.material_8k_history) with fundamental inflection points (margin swings >= 3pp, revenue
declines, FCF sign-flips — computed from facts + XBRL), fully deterministic and unit-tested.
narrate_timeline has the LLM weave that skeleton into a THAI multi-year story (injectable
generator for offline tests; explicitly told not to attribute price moves). Exposed at
/api/timeline (events computed live, no LLM) + a persisted narrative, rendered as a biography
section on the ticker detail page, and added as a get_event_timeline tool the Phase 13 agent can
call mid-investigation.
Phase 15 (reverse-DCF valuation) DONE: closes the "deeper equity valuation" roadmap item.
src/agent/valuation.py::reverse_dcf solves a two-stage DCF *backwards* — instead of forecasting
growth and deriving a price (easy to get wrong), it takes today's market cap as given and finds
the FCF growth rate that would justify it (bisection on a deterministic, monotonic
intrinsic_equity_value() function; fully unit-tested including a round-trip recovery test).
That implied growth is then compared against the company's own historical revenue CAGR (already
computed in StockFundamentals) — the gap is the headline signal: how much more (or less) growth
is priced in than the company has actually delivered. Verified live on AAPL: market pricing in
~16.7%/yr FCF growth vs ~1.8%/yr historical revenue CAGR, a +14.9pp gap. Wired into analyze()
(stock only, deterministic, no LLM call), persisted per row (valuation_json), rendered as a
valuation card on the ticker detail page, and added as a get_reverse_dcf tool the Phase 13 agent
can call mid-investigation to ground its conclusion in what the market is actually pricing in.
Phase 16 (health-jump explanations) DONE: compute_health() also returns a numeric `components`
breakdown; changes.py::_diff detects health-score swings >= 1.5 points between consecutive runs
and names the single biggest driver by diffing components, instead of just noting the score
changed. Motivated by a real MSFT/NVDA case (score jumping ~2.5 points same-day purely from the
LLM recategorizing "expensive" as "cheap" on identical underlying data).
Phase 17 (health score grounded in real numbers) DONE, then superseded by Phase 18 below — kept
for history: replaced flat LLM-label-bucket scoring with a hybrid preferring computed numbers
(Piotroski-style checklist for strength, reverse-DCF gap for valuation) and falling back to the
LLM's label only when the numbers weren't available.
Phase 18 (scoring_spec.md — rigorous, backtestable health score) DONE: replaces Phase 17's
fallback-to-LLM-label design with a stricter spec aimed at genuine cross-stock comparability
(external doc: scoring_spec.md). Total = Fundamental(/8) + Valuation reverse-DCF(/3) +
News(/1) = /12 — confidence dropped entirely as a scoring input (LLM metadata only, not part of
the score).
- Fundamental (/8): 8 Piotroski-style criteria (ROIC>WACC, ROE trend, FCF+accruals quality
  [CFO>Net Income], revenue CAGR>3%, leverage level+trend, liquidity level+trend, margin trend,
  no dilution) with a FIXED denominator of 8 — missing input on a checkable criterion counts as
  fail(0), never skipped (spec explicitly forbids normalizing by computable-count, since that
  would reward low-disclosure companies). A data gate requires >=6/8 criteria computable at all,
  else the ticker is DISQUALIFIED (score=None) rather than scored on thin data.
- Valuation (/3): reverse-DCF rewritten to use company-specific CAPM WACC (Rf from live ^TNX
  10-year treasury yield via the new src/providers/stock/market.py, cached daily, + beta from
  yfinance, clamped to [0.7, 1.6]), EV = Market Cap + Net Debt (not market cap alone), a 3-year
  average FCF base (not just TTM), and "realistic growth" = sustainable growth
  (reinvestment_rate x ROIC, capped at 20%, cross-checked against historical CAGR with a
  divergence flag) instead of raw historical CAGR. Gap maps to a 0-3 step-function score per the
  spec's fixed bands. A company whose reverse-DCF can't resolve (negative FCF, out-of-model-range
  price) is EXCLUDED (score=None), not fallback-scored.
- StockFundamentals gained the raw Facts the above needs: Net Income, CFO, Net Debt (dollar),
  Capex, D&A, NWC Change, NOPAT, Invested Capital, Beta, plus multi-year ROE/Net-Debt-to-EBITDA/
  Current-Ratio series (previously scalar-only).
- Crypto and any stock missing >=3 years of key financials are therefore intentionally excluded
  from this score entirely (out of scope per spec) rather than papered over.
- Backfilled all existing history rows via backfill_health.py (reuses each row's own persisted
  facts_json, so it's point-in-time correct) — nearly all pre-Phase-18 rows became "excluded"
  since the new criteria need Facts that didn't exist before this phase; this is accurate (the
  historical data genuinely isn't there), not a bug, and resolves automatically as each ticker
  gets re-analyzed.
Phase 18b (valuation_guard_growth_lens.md — fix sustainable_growth for asset-light/deferred-
revenue stocks) DONE: Phase 18's sustainable_growth = reinvestment_rate x ROIC broke for
companies like DUOL, where growing deferred revenue (customers pay upfront) makes yfinance's
"Change In Working Capital" strongly positive, which the reinvestment formula's sign convention
reads as "NWC freeing up cash" -- producing a nonsensical -8.9% realistic_growth for a company
that actually grew revenue 41%/year, and a wrongly "very expensive" valuation score. valuation_guard()
detects when sustainable_growth shouldn't be trusted (NOPAT margin too thin, reinvestment rate
negative, or sustainable_growth diverging from actual historical CAGR by >15pp) and routes to a
"growth lens" instead: realistic_growth becomes the company's actual most-recent-year revenue
growth (capped at 35%, nobody sustains more forever) faded linearly to the terminal growth rate
over the 10-year horizon and converted to a CAGR-equivalent, plus a Rule-of-40 modifier
(revenue growth% + FCF margin% < 20 caps the score at 1) so a company that's "growing but burning
cash" can't be scored "cheap" just because the growth-lens anchor looks generous. Verified live:
DUOL's realistic_growth went from -8.9% to +18.3%, valuation score from 0/3 to 3/3, total health
9.0 (was 6.0). Also fixed a real ordering bug surfaced while wiring this in: StockFundamentals.
revenue_series is newest-first but health.py's _fy_series() (used to reconstruct facts into a
duck object for the production analyze() path) returns oldest-first -- _rev_growth_recent() was
silently reading the wrong two years through that path (caught by comparing the standalone
script's correct output against compute_health()'s wrong one, not by a crash).
Phase 18c (frozen watchlist status) DONE: a ticker fully sold has two options before this --
stay in the watchlist (daily analysis, burns 1/20 of a scarce daily Gemini quota on something no
longer held) or get removed entirely (never analyzed again, permanently stuck "excluded" once its
facts predate a scoring change, as SBUX was). Added a third status, 'frozen': stays in the
watchlist and keeps its history, but src/agent/loop.py::_due_for_analysis skips it in
run_watchlist() unless >=30 days have passed since its last analysis -- cheap way to keep an eye
on whether a name someone sold is fundamentally recovering, without daily cost. Folded into the
existing daily cron rather than a second GitHub Actions workflow (one code path checks eligibility
per ticker). Store: set_frozen()/CLI `freeze` subcommand mirroring set_watching(). API:
PUT/DELETE /api/watchlist/{ticker}/freeze. Dashboard: a distinct blue "frozen" tag and a
freeze/unfreeze toggle button next to remove (holding tickers can't be frozen -- sell first via
the portfolio page). Verified live: froze SBUX, confirmed it's correctly gated out of today's
automated run, then ran one manual one-time refresh to give it a real score now (5.0/12, 3/8
Piotroski, bearish sentiment) rather than waiting the full 30 days for its first check.
Phase 18d (audit fix — quality-inversion in the fundamental leg) DONE: a methodology audit
(Claude critiquing the scoring against finance best-practice, grounded in AAPL/DUOL real numbers)
found 4 of 8 Piotroski criteria were fooled by the traits of *great* companies -- AAPL (ROIC 82%)
scored 4.5/12 "weak", face-invalid. Fixed: #2 ROE-trend -> ROIC>=15% level (ROE trend is
buyback-distorted); #3 accruals CFO>NI -> CFO>=0.9*NI (knife-edge tolerance); #5 leverage net-cash
auto-passes + drop noisy YoY trend; #6 current-ratio>1 -> interest-coverage>=3x (current<1 is a
strength for high-bargaining-power firms). Verified the screen still discriminates (INTC/F score
2/8, quality names 6-8/8). AAPL 4.5->7.5. Backfilled.

## Audit remediation roadmap (Phase 19 — close the remaining audit gaps, in order)
The 18d audit found more than the one face-invalid bug it fixed. Remaining, prioritized:
- **19.1 Ground-truth the derived inputs (ROIC/NOPAT/Net Debt/FCF) vs SEC XBRL** DONE -- extended
  check_xbrl_accuracy to recompute FCF/NOPAT/ROIC from raw SEC XBRL concepts (tax, pretax income,
  CFO, capex, cash, long-term debt) and compare to our yfinance-derived numbers. Result: FCF and
  NOPAT match XBRL exactly across the whole watchlist; ROIC within ~5-10% (definitional, invested-
  capital varies by lease treatment). Net Debt deliberately excluded from the eval -- found a real
  sign-flip (NVDA/AMZN read net-debt in our calc, net-cash under a naive XBRL long-term-debt calc)
  with no canonical definition to arbitrate it; that finding fed directly into 19.2.
- **19.2 Reduce single-input concentration** DONE -- ROIC drove 2 of 8 criteria (#1 ROIC>WACC, #2
  ROIC>=15%) sharing one measurement pipeline; a bad invested-capital calc would corrupt both at
  once. Replaced #2 with Net Margin>=10% (Net Income/Revenue -- zero shared inputs with NOPAT/
  invested-capital). Also fixed #6 solvency: it auto-passed on Net Debt<=0 *before* even checking
  Interest Coverage, but net-cash doesn't guarantee no real interest expense (large gross debt +
  even larger cash pile still pays real interest). Reordered: Interest Coverage now checked first
  whenever data exists; net-cash is only a fallback when Interest Coverage truly isn't reported
  (e.g. DUOL, genuinely debt-free). Verified via dry-run backfill against the full watchlist: 11/100
  rows changed, exactly as predicted from the real numbers -- SBUX -1 (Net Margin ~5% now fails the
  new bar, previously passed on ROIC 17%), AMZN +1 (Net Margin ~11% now passes, previously failed
  ROIC's 15% bar at 13.5%). AAPL/DUOL/GOOGL/MSFT/NVDA untouched. Applied.
- **19.3 Binary-cliff -> graded scoring** DONE -- every criterion is pass/fail at an exact
  threshold, so a rounding-level change swings the score ~2/12 (root of the Phase-16 "score
  jumped" problem). Replaced every criterion with a linear 0.0-1.0 ramp across a band around
  its threshold (full credit at threshold+band, zero at threshold-band, 0.5 exactly at the
  threshold). Verified via backfill dry-run: 40/107 rows changed, mostly -0.1 to -1.1 (partial
  credit near a threshold used to round up to a full point) with one flip each way at the
  latest-row level (MSFT strong->ok, GOOGL ok->strong). Applied.
- **19.3.1 Decouple sentiment from the score** DONE -- moved up from "Remaining" below once 19.3's
  own audit surfaced hard evidence: measuring real score swings across 84 consecutive-pair
  history rows and decomposing every jump >=0.5 by component showed sentiment drove 57.4% of
  them (fundamentals 24.3%, valuation 18.4%) -- the health score was tracking daily LLM
  bullish/neutral/bearish flips more than the business itself, directly contradicting both the
  code's own stated intent ("tie-breaker only, must not flip /8+/3") and the project's investing
  thesis (daily news = noise). Sentiment is still computed and shown as a reason/component for
  transparency, just no longer summed into the score; TOTAL_MAX dropped 12->11.
  changes.py::_health_jump_driver was also fixed to stop naming sentiment as the "driver" of a
  jump, since it can no longer cause one. Verified: average swing across the same 84 pairs fell
  54% (0.25->0.12); max swing (2.00) is unchanged and comes entirely from 19.4's still-open
  valuation step-function plus one genuine new-fiscal-year data update (DUOL), not noise.
  Backfill: GOOGL's latest row flips strong->ok (8.5/12->7.5/11) -- its "strong" rating was
  partly propped up by bullish sentiment, not fundamentals/valuation. Applied.
- **19.4 Valuation unit mismatch** DONE -- found two issues in reverse-DCF while auditing this:
  (1) a real ordering bug in `_fcf_base_3yr` -- it assumed fcf_series always arrives newest-first
  and sliced `[:3]` directly, matching the live path (fundamentals.py), but the path that computes
  the health score's valuation component (health.py::_build_duck_fundamentals -> _fy_series) feeds
  it oldest-first -- averaging the *oldest* 3 years instead of the newest 3. Same root cause as the
  earlier DUOL revenue-growth bug. Confirmed live: NVDA's fcf_base was understated 2x (30.6B vs the
  correct 61.5B) because it's a hyper-growth stock where the oldest-vs-newest 3-year average
  diverges enormously. Fixed by sorting internally, same pattern as `_rev_growth_recent`.
  (2) The originally-planned mismatch: growth lens compared implied_growth (FCF growth the market
  is pricing) against realistic_growth anchored on *revenue* growth -- apples-to-oranges whenever
  margin is expanding (DUOL real numbers: 41.08% revenue CAGR vs 102.3% FCF CAGR over the same
  span, from operating leverage). Added `_fcf_growth_multiyear()`; growth lens now anchors on FCF
  CAGR whenever computable (same unit as implied_growth), falling back to revenue growth only when
  FCF history is too short or sign-flips (CAGR undefined). Backfill dry-run: 14/107 rows changed
  (NVDA/GOOGL/MSFT +1.0 from the fcf_base fix; DUOL hit the same bug but its score didn't move
  because gap was already deeply negative both before and after). Applied.
- **19.5 Threshold/tier calibration** PARTIAL -- every threshold (0.9 tolerance, WACC bounds,
  tier cutoffs 70/45%, gap bands) is an unvalidated prior. Full *predictive* calibration ("does
  the score predict returns") is still deferred -- it needs a point-in-time backtest over a broad,
  survivorship-bias-free universe; the current 7-name watchlist is hand-picked survivors, so no
  amount of historical data calibrates it (EDGAR *is* point-in-time and prices are easy, so this
  is blocked on universe breadth + engineering, NOT on waiting to accumulate history -- correcting
  an earlier framing). What WAS doable and is DONE: a sensitivity/robustness map
  (src/agent/sensitivity.py) that sweeps every threshold and reports which are load-bearing (a
  small move flips a tier/ranking) vs inert (never binds for this watchlist). Findings on the live
  7-stock watchlist: (a) ROIC_MIN_PCT was a dead constant (unused since 19.2 moved #2 to Net
  Margin) -- removed. (b) Every load-bearing threshold is on the *valuation* side -- NOPAT-margin
  route guard (0.02, flips at 0.07), lens caps, and the gap bands (10pp flips at 9.5 -- razor
  thin) -- because valuation /3 is still a step function (1 step = ~9% of total) while the
  fundamental side is graded (19.3) and moves smoothly. (c) beta clamps, Rule-of-40, and coverage
  band are inert *for this watchlist* (caveat: adding a levered/weak/cyclical name could make them
  bind). GOOGL is the swing name -- 1.8% under the strong line, so most tier flips are GOOGL's.
  Direct implication: the natural next fragility-reducer is making valuation graded like the
  fundamental leg, not tuning individual valuation constants. **-> CLOSED by 20.1 below.**

Remaining (beyond the audit roadmap): macro/rates valuation context beyond CAPM WACC, triggering
investigation/narration from the UI, cyclical-industry normalization. (Crypto on-chain metrics were
done in 33.5. Bank/insurance alt framework -> done in 33.3. The predictive backtest is folded into
Phase 20 below and remains blocked on universe breadth.)

## Phase 20 -- fit the tool to how I actually use it
20.1/20.2/20.3 DONE (below); the rest of this section is planning notes, not implemented.

Who this is really for (established in planning, do not lose it): I am NOT a finance expert and have no
adviser. Today I mostly read the single `health` number and ignore the rest because I can't interpret
it yet; I use chart-reading (TA) as a light entry double-check. I'm about to put ~10k (THB) of REAL
money in to test the system live. North star stays "grow a retirement portfolio faster than a global
index (VT)", but the sober framing matters more now: beating VT over years is what most professionals
fail at, concentration raises risk, and this tool is decision-support + a learning instrument, not an
alpha machine. Guardrail on the 10k: it is TUITION (a small, losable learning cost), NOT the seed of
the retirement portfolio -- one round proves nothing either way.

The pivot that came out of planning: DON'T add finance sophistication I can't yet interpret (portfolio
correlation, margin-of-safety, drawdown, FX-adjust -- all real, all PARKED below). More numbers I can't
read = harder decisions, not easier. The two directions that actually match how I use the tool are
(a) make it TEACH me as it analyzes, and (b) the simplest possible "did my picks beat VT" measurement.
Honest boundary on (a): teaching improves my COMPREHENSION and decision quality, it does NOT make the
score's predictions more accurate -- health is still an unvalidated heuristic (see 19.5).

Critical reframe (carry-over from 19.5, still true): diversifying the watchlist with hand-picked
mega-trend names solves DISCOVERY, not validation -- curating "interesting" names just moves selection
bias and N=a-handful has ~no statistical power. The only honest, doable substitute is forward-tracking:
the history store already saves point-in-time scores; adding realized return vs VT over time turns the
watchlist into a live forward-test (slow, low-N, directional-not-proof, but real). Note: current data
can only confirm the engine RUNS correctly (numbers are sane) -- it cannot confirm the score PREDICTS;
only forward time + the VT comparison can.

- **20.1 Valuation graded (fragility close-out)** DONE. Replaced the reverse-DCF /3 step function
  (_gap_to_score) with a graded ramp -- sum of 3 independent graded transitions around the original
  boundaries (0/5/10pp), GAP_BAND_PP=2.0 (narrower than health.py's usual 3pp since the boundaries
  themselves are only 5pp apart). Extracted graded_above/graded_below out of health.py into a new
  src/agent/grading.py (health.py already imports valuation.py, so valuation.py importing back from
  health.py would be circular) -- health.py's behavior is unchanged, just re-pointed at the shared
  module. Scoping nuance from planning, still true: this grades the gap->score CURVE only, not the
  lens-ROUTING discontinuity (NOPAT-margin guard, divergence trigger -- binary lens *selection*,
  deliberately untouched) or the Rule-of-40 cap (sensitivity found it inert, out of scope). Verified:
  margin before a tier flip on GAP_PP_FAIR went 0.5pp->1.25pp (2.5x), GAP_PP_GOOD 1.0pp->2.80pp
  (2.8x). Backfill dry-run on the real watchlist: 14/107 rows shifted slightly (0.1-0.5 pts), zero
  tier flips at the latest-row level (MSFT 8.3->7.9 stayed strong, SBUX 5.9->5.6 stayed ok). Applied.
- **20.2 Explain/teach the score (the real need)** DONE (first pass). Was: I trust the top-line health
  number blind because the rest is opaque and buried in hover tooltips. Built web/app/health-breakdown.tsx
  -- a "ทำไมได้คะแนนนี้" panel under the verdict that splits the single number into its two legs:
  "สุขภาพ 9.9/11 = พื้นฐาน 6.9/8 + ราคา 3.0/3", each as a labelled bar, plus the 8 Piotroski criteria
  shown one-by-one as pass(✓)/partial(◐)/fail(✗) with a plain-Thai per-criterion explanation on hover,
  plus a note that news sentiment is context-only (not scored, per 19.3.1). The teaching point made
  visible: health 8 from strong-fundamentals+expensive is a different animal from health 8 from
  average-fundamentals+cheap. Frontend-only -- the components/fundamental.criteria data was already in
  the stored health JSON (health.py), the TS types just never declared it; added HealthComponents/
  HealthCriterion/HealthFundamental to types.ts and Piotroski/reverse-DCF/net-cash to the glossary.
  Verified live via SSR (uvicorn+next dev): DUOL renders the split with 7✓/1✗ (only "ไม่เจือจางหุ้น"
  fails, degree 0.0 -- matches the real data), excluded tickers (BTC) render no breakdown and don't
  crash. Follow-up (same session) DONE: each criterion now also shows the real metric value behind
  it, not just the label + pass/fail (e.g. "✓ ROIC>WACC · ROIC 76.1%", "◐ หนี้ไม่บานปลาย · Net
  Debt/EBITDA 2.7x"), pulled from the already-stored facts (no live recompute). Verified across 4
  tickers covering all branches: DUOL (net-cash path for #5/#6), SBUX (leveraged path -- Net
  Debt/EBITDA 2.7x lands partial, matching the exact figure from the 19.5 sensitivity audit),
  MSFT/AAPL (Interest Coverage with real debt, AAPL's low Revenue CAGR 1.8% correctly shown partial).
- **20.3 Simplest VT tracking (record + compare)** DONE. The existing edge/compute_edge() (Phase 5.5)
  already compared realized return vs VT since the buy date, but never linked it to the health score
  that motivated the buy -- couldn't answer the real question ("does picking high-health names myself
  actually beat VT") vs the weaker one ("did the price go up"). Added
  performance.py::_health_at_entry(ticker, entry_date) -> (score, exact): pulls the health score from
  the already-stored point-in-time history (no recompute, no new schema) for the analysis run closest
  to (at-or-before) the entry date -- using "at-or-before" specifically to avoid look-ahead bias (must
  reflect what was known when the buy decision was made, not a later score). When no analysis exists
  before the buy at all, falls back to the earliest available one but flags it `exact=False` and the
  UI shows it with a "~" and an honest tooltip -- caught live with the real DUOL holding: bought
  2026-05-06 but the earliest point-in-time analysis in the system starts 2026-07-07, so its "health at
  entry" is only ever an estimate, and the tool says so rather than presenting it as fact. Surfaced in
  both the portfolio table (small "ซื้อ ~8.0" under the current health meter) and the ticker detail
  hero. 6 new tests (exact match, fallback, no-data, end-to-end). This is the slow, honest bridge
  toward the deferred 19.5-full predictive validation -- accumulates real data over time instead of
  faking it from the 7-name survivor watchlist.
- **TA-as-entry-check (discipline note, not a build item)** -- using charts to time entry is fine ONLY
  as a light double-check with fundamentals leading. Watch the inversion failure mode: never let the
  chart VETO a strong-conviction long-term pick, and never let it turn a thesis-driven hold into a
  short-term trade. The project's spine is "exit on thesis-break, not chart-break."

## Phase 21 -- screener (discovery, not just analysis of what I already named)
DONE. The gap this closes: every phase up to 20 only analyzes tickers I already typed in myself --
the tool couldn't answer "where do I even find candidates" (US, cheap + strong fundamentals). Built
src/agent/screener.py: runs the exact same scoring engine as the daily watchlist (Piotroski /8 +
reverse-DCF /3, health.py + valuation.py) across a hand-curated UNIVERSE of ~40 large-cap/liquid US
tickers spread across sectors (tech, semis, consumer, healthcare, financials, industrials, energy,
communication) -- but skips Gemini entirely, since fundamental+valuation scoring never needed the LLM
(sentiment has been metadata-only since 19.3.1). Same DISQUALIFY/EXCLUDE-not-fallback discipline as
health.py: tickers failing the data gate (<6/8 computable criteria) or where reverse-DCF can't solve
are silently dropped, not guessed at.
Honesty notes baked into the docstring itself (same pattern as every prior phase): UNIVERSE is a
curated list, NOT the S&P 500 or a full market scan -- it's a starting point for exploration, not "the
best is guaranteed to be in here." A high score means "strong fundamentals + priced cheaper than
realistic growth justifies TODAY" -- it does NOT mean picking from this list beats VT (same unproven-
heuristic caveat as 19.5/20.3; this screener has no point-in-time tracking of its own yet).
Refactor: extracted `tier_from_score()` out of health.py's compute_health() (was inlined) so both
compute_health and the screener share the identical 70%/45% tier boundary on the /11 scale --
duplicating that specific threshold risked silent drift between the two call sites.
Full scan hits yfinance ~4x/ticker (.info/financials/balance_sheet/cashflow) -- minutes, not seconds --
so results are cached to disk (data/screener_cache.json, gitignored like risk_free_rate_cache.json,
TTL 12h). GET /api/screener reads the cache by default (fast); `?force=true` forces a full rescan, used
only by the UI's explicit "รีเฟรชผลสแกน" button (with a confirm() warning it takes a while), never on
every page load. New page web/app/screener/screener-view.tsx: table of candidates sorted by score,
P/E, ROIC, valuation gap (green when negative = cheap), lens, and a "+ เพิ่มเข้า watchlist" button
(disabled + relabeled if already being watched) that reuses the existing addToWatchlist() mutation --
no new watchlist-mutation code needed.
Verified live end-to-end against real yfinance data (not mocked): first request with no cache computed
fresh in well under the 120s call window, returned 37/41 tickers (4 dropped by the data gate --
ORCL/JPM/GS/AXP), sorted correctly (ADBE 10.7/11 top, CVX 3.2/11 bottom), `already_watching` correctly
flagged the 6 tickers already in my real watchlist (META/GOOGL/MSFT/AAPL/NVDA/AMZN). Repeat request
served from cache in 0.27s (no re-scan). SSR-rendered /screener page confirmed via curl: scores, tier
labels, P/E/ROIC/gap, and the add-to-watchlist button all render correctly (checked via raw HTML
inspection, not just tsc -- same lesson as 20.3's grep-vs-React-comment-marker gotcha). 8 new offline
tests (tests/test_screener.py) covering scoring, data-gate skip, reverse-DCF-None skip, fetch-error
skip (1 bad ticker doesn't kill the scan), sort order, and the disk-cache TTL logic -- no network in
CI. Full suite: 184 passed.

## Phase 22 -- "what changed since last time" moved to the top (UI/readability pass)
DONE. Context: talked through what makes a long-term research tool bearable to read for years without
resorting to gamification (streaks/badges/notifications), which would actively fight the project's own
thesis (daily news = noise, thesis-driven not chart-driven). Landed on: don't make it "sticky", make it
worth opening -- lead with what's DIFFERENT since last time, not static numbers, since nobody re-reads
unchanged data twice.
changes.py (Phase 3) already computed exactly this (diff between the two latest analysis runs, plus any
invalidation breach) but it was buried at the bottom of the ticker detail page, under the valuation box
-- the highest-value-per-pixel content on the whole page was the least visible. Built
web/app/ticker/[symbol]/whats-new.tsx and moved it to right after the hero, before even the LLM verdict
paragraph. Two things this pass insisted on: (1) the date range context ("เมื่อวาน → เมื่อวาน", or the
`note` text when there's only one analysis ever) so the reader knows what window the diff covers --
diffs without a timeframe read as arbitrary; (2) an explicit calm-state message when there's nothing to
report ("✓ ไม่มีอะไรสำคัญเปลี่ยน...") instead of rendering nothing -- "silence by default" is the right
policy for what counts as a change (changes.py's own principle), but rendering literally nothing on a
UI element reads as broken/not-loaded, not as "checked, all clear." Removed the old duplicate block at
the bottom of the page (same data, now shown once, at the top).
Verified live against real data across all 3 states: AMZN (4 real changes: strength flip, thesis news,
grounding-trust drop, ROIC metric move -- glossary tooltips still resolve correctly inside the new
component), MSFT (0 changes, calm state, same-day range), META (note case -- only one analysis ever
exists, no invalidation breach either). Confirmed via raw HTML inspection (not just tsc) that the old
duplicate section is fully gone. tsc clean, full suite still 184/184 (backend untouched, this was
frontend-only).

## Phase 23 -- health-score sparklines everywhere (trend, not just a snapshot number)
DONE. Follow-up to the Phase 22 UI/readability conversation -- landed on "the change IS the content"
as the throughline. A single health number ("7.9") says how strong RIGHT NOW but nothing about which
way it's moving, which matters more than the snapshot for someone who reads mostly the one health
number (my own stated habit). A tiny 30-ish-point trend line next to the number turns a static snapshot
into a direction: MSFT 7.9 (was climbing) reads completely differently from DUOL 8.0 (was falling) even
though the current numbers alone don't show that.
Turned out most of the plumbing already existed and was unused: web/lib/charts.tsx already had a
`Sparkline` component (SVG polyline, no axes) sitting there dead code, never imported anywhere -- just
needed real data wired to it. Added `health_trends()` to src/history/store.py: a lightweight query
(3 columns only, no summary_json/facts_json parsing -- deliberately NOT reusing the heavier
history()/latest_per_ticker()) returning the last N health scores per ticker, oldest-to-newest. New
`GET /api/health-trends` endpoint. Added a small `trendColor()` helper (green/red/muted hex, mirroring
globals.css's --green/--red/--muted -- matched existing convention of passing resolved hex from the
caller rather than raw CSS var() strings into SVG attributes) and wired the sparkline into all 3 places
that show a health number: home dashboard cards, the portfolio table, and the screener table.
Screener nuance: most screener candidates won't have a trend at all (they're not in the watchlist, so
there's no history to show) -- handled the same way as every other "maybe no data" case in this
codebase, a length>=2 guard that just renders nothing rather than a placeholder.
Verified live against real data (not synthetic): AAPL genuinely climbing 6.0->7.0 rendered upward/green,
NVDA genuinely falling 6.9->5.9 rendered downward/red, META (only 2 identical points, 10.2/10.2)
rendered flat/muted -- confirmed the color logic is correct, not just "a line exists." Portfolio showed
exactly 1 sparkline, matching that DUOL is the only actual holding right now. Screener showed 6 (the
tickers that happen to already be in the analyzed watchlist). 5 new offline tests
(tests/test_history_store.py) covering ordering, the no-health-score skip, per-ticker separation, the
limit cutoff (keeps the LATEST N, not the first N), and empty-DB. tsc clean, full suite 185/185.
Follow-up fix (same session, caught by asking "does this actually cover weeks/months over time"):
`health_trends()` was returning one point per RAW analysis run, not per calendar day -- a ticker
re-run multiple times in one sitting (e.g. AAPL got run 4x on 07-07 during earlier dev/testing) wasted
sparkline points on the same day instead of stretching further back in time. The bigger ticker-detail
trend chart already handled this (`healthByDay` dedup), the new sparkline endpoint didn't. Fixed by
collapsing to 1 point/day server-side (keeps the LATEST run's value for that day), so the fix benefits
all 3 UI spots for free. Confirmed against the real production DB before/after: AAPL went from 20
padded/duplicate-heavy points down to 10 honest calendar-day points. Also surfaced the honest limit of
the "weeks/months" question directly, unprompted: there's currently only ~12 days of real health-score
history in the whole system, so a week/month ROLLUP view has nothing meaningful to show yet -- revisit
once there's a couple months of real data (not a code gap, a data-maturity one). 2 new tests added for
the dedup behavior specifically (same-day collapse keeps latest value; limit counts days, not raw rows)
-- full suite 187/187.

## Phase 25 -- "ask your portfolio" (portfolio chat, on top of the Phase 13 agent)
DONE. Context: asked for a "cool feature" idea beyond incremental UI polish. Landed on chat over
building a bear-case agent or a multi-agent debate (both real ideas, parked) because this one directly
answers my own stated blocker -- "ส่วนอื่นยังดูไม่รู้เรื่อง, ดูแค่ health เลย" -- by letting me ask in
plain language instead of decoding the dashboard myself, and it activates Phase 13's agentic loop
(tool-calling, planning, stop conditions) which had been sitting unused except for the single-ticker
investigation panel.
Reuse, not a rewrite: refactored `GeminiPolicy.__init__` in investigate.py to take `prompt`/`system`
directly (was hardcoded to "Investigate {ticker}." + a single-company persona) so the exact same
google-genai function-calling plumbing serves both Phase 13 (deep-dive one ticker) and this new
src/agent/chat.py (Q&A across the whole watchlist) -- zero duplicated API-wiring code. New toolbox
(`build_portfolio_toolbox`) is read-only against data ALREADY computed and stored (latest_per_ticker,
detect_changes, portfolio_edge, get_thesis) -- deliberately does not re-fetch yfinance, so a chat
question is fast and reflects exactly what the dashboard already shows, not a fresh (expensive) re-
analysis. New `POST /api/chat` -- the one LLM-touching endpoint in the whole API (called out explicitly
in main.py's module docstring, which previously claimed the file never touches an LLM). No server-side
conversation persistence -- history is plain-text turns kept in the browser tab and replayed into the
prompt each question; refreshing the page starts a new conversation (matches the "lightweight helper,
not an audit trail" framing -- Phase 13's actual investigations already have that persistence job).
Real bug found DURING verification, not invented for the exercise: the first two live test calls hit an
actual Gemini `503 UNAVAILABLE` ("high demand") on gemini-3.5-flash -- the google-genai SDK's own
tenacity-based retry silently chewed on it for 2-3 minutes before finally raising, and that raw
exception was completely uncaught, crashing the whole HTTP request as a bare 500. Turned out
`Investigation.stopped` already had an "error" value in its type signature from Phase 13 -- nothing had
ever actually produced it. Fixed at the shared loop level (`run_investigation` in investigate.py): wrap
`policy.decide()` specifically (distinct from the tool-call try/except already there) and return a
graceful `Investigation(..., stopped="error")` with a plain-Thai message instead of propagating.
Benefits both investigate() and chat() automatically since they share the loop. Added
test_policy_crash_returns_graceful_error_not_raise to prove it without needing a real API failure.
Verified end-to-end against real Gemini (three genuine live calls, not mocked): call #1 hung ~3min then
hit the raw crash (confirmed the bug); call #2 after the fix hit the *same* 503 again but now returned
a clean HTTP 200 with the friendly error message (confirmed the fix works against a real failure, not
just a synthetic one); call #3, run against gemini-2.5-flash as a diagnostic since 3.5-flash was still
congested, succeeded fully -- asked "ตอนนี้ตัวไหนน่าห่วงสุด" and the agent called list_portfolio, saw
SBUX had the lowest health score, then specifically drilled into get_ticker_changes for SBUX (didn't
just report the raw number) and found the real signal: fundamental_strength flipped mixed->weak even
though the health score technically rose (+1.7, entirely from valuation re-rating, not fundamentals) --
correctly synthesized that the strength flip is the actual concern, not the score movement, and closed
with the required "not a buy/sell call" caveat. 16 new offline tests (tests/test_chat.py, tools only --
GeminiPolicy itself needs a real key so isn't unit-testable) + 1 new test on the shared loop. tsc clean,
full suite 204/204. New nav entry ("ถามพอร์ต →") + /chat page, reusing the Phase 13 investigation-step
CSS classes for the collapsible tool-trace under each answer (transparency: see what it looked up).

PARKED (real ideas, deliberately deferred until I can read `reasons` fluently -- adding them now would
pile on numbers I can't interpret and make decisions harder, the exact trap planning flagged):
mega-trend discovery-map UI (themed idea generation across AI/semis/energy/healthcare/... ; design fork
= curated seed list vs LLM-generated-then-verified, hallucination risk); portfolio concentration/
correlation (am I diversified across trends or fake-diversified across correlated tech names); position
sizing; margin-of-safety off reverse-DCF; drawdown vs VT; FX-adjusted (USD vs THB) returns; dividend
safety; and pre-profit / financials alternate scoring frameworks for names the current engine excludes.

## Phase 26 -- Macro Event Radar (short-term, deliberately firewalled from the long-term app)
DONE (core). Context: asked for a war-news / macro-event alert bot for the *short-term* side of trading
(4h crypto/futures) -- "gold will go up, crypto down, alt season coming" + alerts when CPI/PPI/jobs drop.
Split the request honestly into two piles: things a bot CAN do (facts + timing) vs things NO bot does
reliably (directional predictions). Built only the first pile. The whole point of the feature is to show
-- with real numbers -- that "CPI hot -> crypto down" is folk-wisdom that doesn't hold, instead of me (or
a bot) pretending to call direction. Kept as a separate `src/macro/` package + its own /macro page, walled
off from watchlist/health/thesis so it never pollutes the calm "no-noise" long-term surface.
Data sources are ALL free / no-key (verified live before building): FRED CSV endpoint (fredgraph.csv, no
API key -- CPI/PPI/UNRATE/PAYEMS back to 1947) + yfinance (gold GC=F, ^GSPC, BTC/ETH) + Google News RSS
(geopolitical headlines, stdlib xml.etree). Zero new pip deps.
- fred.py: keyless CSV fetch. Honest gap surfaced: the CSV gives the *reference month*, not the actual
  *release date* (CPI for June drops mid-July). release_dates() upgrades to real release timestamps IF a
  free FRED_API_KEY is set, else baserate approximates release = ref_date + per-series lag and flags it.
- baserate.py: the honest core. Instead of "index level vs prior month" (almost always up -> useless
  signal) it computes the *trader-relevant* signal -- CPI/PPI = YoY inflation rate (accelerating vs
  decelerating), NFP = net jobs added vs prior month, UNRATE = level -- then for each direction reports
  the historical DISTRIBUTION of next-day moves for BTC/ETH/gold/S&P: mean, min..max range, %up, and n.
  Deliberately NOT a prediction: e.g. CPI-accelerating -> BTC came out +0.1% mean, -18.7%..+10.4% range,
  up 55% of 78 times = a coin flip, and the UI shows that so the user sees the noise themselves. approx
  flag reflects whether real release dates were actually used (not just whether a key exists -- falls back
  to approx if the release-date/observation alignment looks off, since that path isn't key-verified yet).
  _price_history lru_cached so one /macro load fetches each asset once (4 not 16).
- store.py (SQLite self-init, shares watchlist.db): remembers the last release ref_date alerted per series
  so radar fires once per new print; first-ever run bootstraps silently (no backfill spam).
- radar.py: dashboard() (read-only, for the web page) + scan_for_alerts() (detects a newly-appeared print
  via the store, builds the alert with base-rate context, marks seen -- for a future cron/Discord push).
- geonews.py: passive Google News RSS watch for war/sanctions/strike keywords -> warn-level headlines only,
  explicitly NO direction call ("gold up on war" breaks constantly). Dedupes, splits "- Source", ISO dates.
- GET /api/macro (no LLM; ~3.7s live -- FRED+yfinance+RSS) -> {releases[], geopolitical[]}. New /macro page
  + nav entry ("เรดาร์มหภาค →"); each release card shows signal prev->now, a min..max range bar with a
  mean dot per asset, %up and n, and the approx-date caveat; geopolitical block styled as a warn.
- altseason.py: user asked about "alt season" (ETH up, BTC down). blockchaincenter's index is JS-rendered
  (not cleanly scrapable -> would break silently), so instead of a fragile scrape it self-computes the
  ETH/BTC ratio momentum from yfinance -- transparent, every number explainable. Reports current ratio,
  30d/90d % change of the ratio, and each coin's 30d return, with a descriptive state (alt/btc/neutral).
  Deliberately descriptive not predictive: e.g. live it showed ETH leading (+9% ratio/30d, ETH +12.6% vs
  BTC +3.2%) while the 90d ratio was -3% -- the card says the timeframes can disagree, no "season incoming".
- 17 new offline tests (tests/test_macro.py -- CSV parse, signal math per series, direction, stats
  filtering + approx flag, store roundtrip, scan bootstrap/new-print, geonews parse/dedup/fail, alt
  momentum alt/btc/insufficient). Network fully monkeypatched (CI-safe per the no-yfinance/Gemini rule).
  tsc clean, full suite 221/221.
NOT built (on purpose): any "gold will go up / alt season is coming" directional call -- can't be done
honestly; the whole subsystem gives facts + historical distributions and lets the user see the noise.

Phase 26b -- Discord alert when a number drops (like an investor econ-calendar). notify.py::send_macro_alert
reuses scan_for_alerts -> format_alert -> notify/discord.post: silent unless a NEW monthly print appeared,
posts the summary+base-rate, appends the geopolitical warn block only when there's an actual event (news is
context, not the trigger). Own webhook DISCORD_WEBHOOK_URL_MACRO (falls back to the main one). Moved macro
state to a SEPARATE data/macro.db (was watchlist.db) so its own frequent workflow can commit state back
without colliding with daily-report.yml's watchlist.db commit -- and because state MUST persist across CI
runs or every run is a silent "bootstrap" and nothing ever alerts. New .github/workflows/macro-radar.yml
runs hourly 12-21 UTC Mon-Fri (covers US 8:30am-ET release window; FRED updates its CSV minutes-to-hours
after the official print) + commits macro.db back. 4 new notify tests (post-on-new, silent-when-nothing,
geo-appended). Full suite 225/225. This is the POST-RELEASE "here's the number + summary" flavour -- it does
NOT need a FRED key. PENDING option: a PRE-release "CPI in 30 min" heads-up needs the forward release
calendar (free FRED_API_KEY -> release/dates) + a scheduler firing ahead of time -- offered, not yet built.

## Phase 27 -- thesis/invalidation wired to the UI + decision journal
DONE (commit a1378cc, backfilled into this doc during Phase 28 -- the commit itself didn't update the
roadmap). thesis.py / invalidation.py had existed since Phase 5 but no endpoint ever exposed them, so
`theses` was empty forever and the "sell alarm" never actually ran on anything. Added GET/PUT/DELETE
/api/thesis/{ticker} + GET /api/invalidation/{ticker}, a thesis-panel.tsx editor on the ticker page, and
a red banner when a rule is breached. Plus a NEW decisions table + decision-log.tsx journaling every
buy/pass/wait/sell -- including "pass", which was never recorded anywhere before -- with gate2 (the
chart/EW check result at that moment, free-form note; EW itself is a separate project) so it can later be
measured whether the second gate actually helps. Set real thesis + invalidation rules for DUOL (the live
holding, which until then had no exit condition at all).

## Phase 28 -- run the agent from the web (the agentic loop was CLI-only)
DONE. Same class of gap Phase 27 closed, one layer up: the Phase 13 agentic loop is the piece that makes
this an agent rather than a script, but it could only be fired from `python -m src.agent.investigate` --
the product surface could only *read back* a stale transcript (the GET endpoint's own docstring said
"do it via CLI / a separate button", and that button was never built).
- run_investigation(..., on_step=) -- optional per-step callback. The loop is otherwise unchanged; the
  callback is a pure observer (wrapped in try/except -- a broken observer must never kill an
  investigation) and exists so progress can be watched live instead of appearing as one lump at the end.
- src/agent/investigate_runner.py -- in-memory job registry + background thread. Why a job at all: one
  investigation = fundamentals/news/XBRL fetch, then up to MAX_STEPS Gemini turns = tens of seconds to a
  minute, too long to hold a browser request open (dev server/proxy cuts it, and the user stares at
  nothing meanwhile). So POST = start (202 immediately), GET /status = poll. Accepted limits, on purpose:
  state is a dict+Lock in one process (restart the API = in-flight job is lost), which is fine because the
  *result* is persisted to the investigations table by investigate() as always, and this app runs
  single-process/single-user. One running job per ticker (AlreadyRunning -> 409) because a double-click
  would otherwise burn Gemini quota twice. Thread exceptions AND the "policy died mid-loop" case
  (stopped == "error", which run_investigation returns rather than raises) both become status="error" --
  no job is ever left stuck on "running".
- POST /api/investigation/{ticker} {focus?} + GET /api/investigation/{ticker}/status. Only the 2nd
  LLM-touching endpoint in main.py (with /api/chat), never auto-triggered. Guards: 503 if no
  GEMINI_API_KEY, 400 if the ticker is a non-stock in the watchlist (the toolbox is stock-only --
  yfinance fundamentals + SEC XBRL/EDGAR -- so crypto would spend quota to get "no data" from every tool).
  `focus` is an optional free-form prompt ("why did margin fall two years running?") passed through as
  the investigate() context.
- investigate-panel.tsx (client) replaces the read-only transcript block in detail.tsx: button + 🎯 focus
  box, polls every 1.5s, and renders steps as they arrive ("agent is thinking about step 3…" with a
  live elapsed counter) -- which is the honest demo of the loop, not a spinner. Remounting/refreshing
  mid-run re-attaches to the running job; on finish it router.refresh()es so the persisted transcript
  becomes the server-rendered state again.
- 12 new offline tests (9 runner + 3 loop-callback): background start returns before finishing, steps are
  visible *while* running, duplicate start rejected then allowed once done, two tickers run concurrently,
  exception and policy-failure paths both land on error, focus passes through as context, as_dict has no
  thread object in it. Gemini/network never touched (fake investigate_fn injected). tsc + next build
  clean. Endpoint behaviour (202/409/400/404/503 + live step visibility) verified separately against a
  TestClient with a gated fake, since httpx isn't a committed test dep.

Two REAL bugs the live verification exposed (the button failed on the first try against real Gemini --
both fixed, both pre-existing and NOT caused by Phase 28; the new button just made them visible):
1. generate_with_fallback raised instead of falling through when a 5xx persisted past max_attempts, so
   one model being busy killed the whole chain. Hit live: gemini-3.5-flash returned 503 "high demand"
   (and later 429) while gemini-3-flash-preview and gemini-2.5-flash answered fine -- meaning the DAILY
   analyze() pipeline was equally exposed, not just the new button. Now an exhausted 5xx is treated like
   429 (advance to the next model); only a truly permanent code (e.g. 400) still raises immediately, and
   the chain-exhausted raise is unchanged. 6 new offline tests (tests/test_llm_fallback.py) with a fake
   client per model: healthy first model, persistent 5xx falls through after N retries, 429 skips without
   retrying, 400 raises immediately, whole chain down raises last error, models= override.
2. GeminiPolicy pinned MODEL_CHAIN[0] with no fallback at all (documented as a "known gap" since Phase
   13) -- so investigation AND the Phase 25 chat page were both dead whenever the head model was busy.
   The stated reason for the gap (multi-turn tool-calling makes mid-conversation model switching hard)
   turned out not to hold: `contents` is sent whole on every turn and its parts (text / function_call /
   function_response) are model-agnostic, so it just reuses generate_with_fallback with the chain
   reordered to prefer its configured model.
   Bonus third fix: the fallback's Thai log lines crashed with UnicodeEncodeError under uvicorn on
   PowerShell (cp1252) and killed the run mid-loop -- a logging side-effect must never fail the job, so
   they now go through llm._log() which degrades to backslash-escaped ASCII instead of raising.
Then a follow-up from the same session: **quota lanes**. Free-tier quota is per-model per-day, so the
scarce resource is a *bucket*, not model strength -- and the two workloads compete: analyze() must run
daily (8 non-frozen tickers = 8 calls) while the investigate button can be pressed at will (up to 7 calls
each) and chat draws from the same pool. Measured live: a handful of button tests put gemini-3.5-flash --
the daily pipeline's primary -- into 429 the same afternoon. So llm.INTERACTIVE_CHAIN now rotates the
chain (MODEL_CHAIN[1:] + head) for user-pressed work, and GeminiPolicy takes `models=` (replacing the
single `model=`) with investigate() and chat.ask() both passing the interactive lane. Rotate, not
reverse, and the reason is empirical: run live on the tail model (gemini-2.5-flash) the agent burned all
6 steps on get_metric_trend and never touched news / SEC / reverse-DCF, whereas gemini-3-flash-preview
walked timeline -> reverse-DCF -> news and flagged the tax-driven net margin unprompted. Deciding what to
look at next IS the agentic loop, so the lane starts at the best model that isn't the daily one and only
falls back onto the daily model as a last resort (tested). 5 new lane tests.
Full suite 245/245 after the fixes.
Verified live end-to-end on DUOL (the real holding): POST -> 202, duplicate POST -> 409, /status showed
4 steps mid-run then 6 at done (37s), transcript persisted to the investigations table, and the ticker
page SSR renders it with the button + glossary tooltips. The agent chose list_metrics -> Revenue CAGR ->
Revenue -> get_event_timeline -> get_reverse_dcf -> get_recent_news and concluded strong fundamentals
(41% revenue CAGR, operating margin from negative in 2022 to 13.07% in 2025) against a market pricing in
only 7.5%/yr FCF growth -- it also flagged on its own that the 39.9% net margin looks tax/one-off driven
rather than core. stopped="max_steps" (it used all 6), which the UI labels "ชนเพดาน".

## Phase 29 -- "ประเมินราคาไม่ได้" != "ประเมินอะไรไม่ได้เลย" (partial health for cash-burners)
DONE. Found by looking at how the tool is ACTUALLY used rather than at the roadmap: of 12 watchlist
names, SPCX is analyzed every day (spending quota) yet the one number the user actually reads -- health
-- was blank forever, because reverse-DCF needs positive FCF and SPCX burns cash, and the old rule
excluded the WHOLE score whenever either leg failed. So the tool went silent exactly on the
"fast-growing, not yet profitable" names a beginner needs most help with (DUOL itself was once one).
This also answers the crypto question honestly: BTC is blank for a *different* reason -- 0/8 fundamental
criteria are computable, i.e. the framework assumes a company -- so crypto needs a whole parallel scoring
framework, not a data source, and it's the only crypto ticker and currently frozen. Deferred on evidence,
not vibes.
- health.py: fundamental-gate failure still => excluded (crypto, thin data -- nothing is trustworthy).
  Valuation-only failure => NEW partial result: score = the fundamental leg, max = PARTIAL_MAX (8),
  tier from the /8 scale, partial=True, plus a reason line stating in words that it can't be compared
  against /11. Deliberately NOT normalized up to /11 -- that would invent a price score that doesn't
  exist. Breach penalty still applies (thesis breakage is independent of whether price is computable).
- The scale-mixing hazard is the real design work here, since analyses.health_score is a silent
  "comparison arena" for the sparkline, Phase 20.3 health-at-entry, and changes.py health_jump. New
  health.comparable_score() returns None for partial/excluded, and history/store.py writes THAT to the
  column (the full number still lives in health_reasons_json for the UI). Result: every existing
  consumer keeps behaving exactly as before instead of silently averaging /8 with /11. changes.py
  additionally requires ch["max"] == ph["max"] before reporting a health jump -- otherwise a company
  turning FCF-positive (partial -> full) would be announced as a score surge when nothing changed but
  the unit.
- UI: HealthMeter shows the denominator and the label "พื้นฐานล้วน" only when partial (a bare "3.0"
  would read as 3.0/11 -- this is what keeps "a number beats a blank" from becoming "a number that
  fools you"). HealthBreakdown no longer bails out when the valuation leg is missing: it renders the
  fundamental leg normally, the price leg as a striped "—/3" (empty, NOT zero), and an amber caution
  saying explicitly that this does not mean cheap, it means unanswerable.
- backfill_health.py gained --only-excluded so recomputing history touches only previously-excluded
  rows: a full re-run also shifts already-scored rows by ±0.1 because it applies TODAY's risk-free rate
  to every historical row (documented caveat), and that noise shouldn't be written into history as a
  side effect of shipping this. Applied: 15 rows, all SPCX (-> 3.0/8 weak) plus one MA day that had a
  transient Market-Cap fetch failure (-> 8.0/8 strong).
- Screener deliberately still skips these names: it exists to find "strong AND cheap", and "cheap" is
  exactly the part that can't be computed here.
- 4 new health tests (partial shape, comparable_score gating, breach penalty on partial, gate failure
  still excluded) + the old "excluded when valuation unresolvable" test rewritten to the new intent.
  Suite 248/248, tsc + next build clean. Verified live via SSR: dashboard renders SPCX as
  "3.0/8 พื้นฐานล้วน" while BTC stays "— ประเมินไม่ได้", and the ticker page shows the caution block.

## Phase 30 -- turning other people's stock narratives into things that can be wrong
DONE. Trigger: brought me a list of claims from someone's analysis (AMZN good because AWS/Bedrock +
"if Claude IPOs Amazon must pump", TSMC "can't lose money", MSFT "P/E very low", META "declining, no
product", NVDA good because OpenAI buys from them, ASML best because EUV monopoly) and asked to make
the tool dig like that -- but "filter the claims first". Checking them against data we already stored
was the answer to both: 5 of 10 weren't wrong so much as UNFALSIFIABLE (no number would make the author
admit error), and 2 of the checkable ones are contradicted by our own numbers (MSFT P/E 23.4, PEG 1.20,
reverse-DCF gap +9.7pp -> 0.57/3, not "very low"; META is the HIGHEST health in the watchlist at
10.2/11 with net margin 19.9->37.9% and gap -3.2pp -> 3.0/3, the opposite of "declining"). AMZN's story
may be true while its price already embeds 36.1%/yr FCF growth vs 18.0% realistic -> 0/3. So the feature
to build was NOT "make the agent write narratives like that" -- that machine would just manufacture
reasons to buy. Two pieces instead:
- **A. expectations** ("เรื่องเล่าที่รอพิสูจน์"): a 4th field on thesis next to invalidation rules and
  fair value. Structure is deliberately the same shape as an invalidation rule (same _OPS) but the
  intent is mirrored: invalidation = "if this becomes true, the thesis is dead"; expectation = "if the
  story is true, this number MUST arrive by this date". A deadline is REQUIRED at validation time --
  a claim with no expiry is a claim that can never be wrong, which is exactly what this filters out.
  Four states: hit / pending (not-yet is NOT a failure) / missed (deadline passed, still short ->
  warn, and warn only: a dead story is not a sell signal, invalidation covers that) / unmeasurable
  (metric absent from the filings -- say so, never guess). Each row keeps `source` so it's possible to
  ask later which pundit was actually right. Deterministic, no LLM.
- **B. correlation** ("ถือเดิมพันเดียวกันกี่ชั้น"): the four names being pitched are one chain --
  ASML -> TSM -> NVDA -> AMZN is a single AI-capex bet in four layers, and nothing in the tool said so.
  src/agent/correlation.py measures Pearson correlation of DAILY RETURNS (not prices -- two names that
  merely trend up would show fake-high correlation) over 90d/1y, from yfinance closes cached 12h.
  Pairs are flagged at >=0.7, escalated when BOTH names are actually held (reports their combined
  portfolio weight). Ships with a caveat printed alongside the numbers: correlation is unstable and
  jumps toward 1 in a crash, i.e. it is a FLOOR on concentration risk, not a ceiling. `extra=` lets a
  ticker be tested against the portfolio without adding it to the watchlist (no daily-quota cost).
- New endpoints GET /api/expectations/{ticker} and GET /api/correlation (both LLM-free); thesis PUT
  gained `expectations`. UI: expectations editor + status rows in thesis-panel with an amber banner for
  missed ones; a SameBet panel on /portfolio that loads on click (a 1y price pull per ticker is too
  slow to fire on every page view).
- 23 new offline tests (12 expectations incl. deadline/metric validation and all four states, 11
  correlation incl. returns-not-prices, minimum-overlap refusal, held-pair weighting, sort order,
  caveat always present). Suite 271/271, tsc + next build clean. Verified live: all four expectation
  states render (temporarily written into DUOL's thesis, then restored byte-for-byte), and the real
  correlation run surfaced ASML~TSM at 0.74 (90d) -- the highest pair in the whole list.
- Live-data finding worth keeping: the watchlist now contains **TSMC**, which is not a Yahoo symbol
  (the correct one is TSM) -- it silently returns no data, so it can never be analyzed AND it hid the
  single most important correlation pair until TSM was passed in via `extra`.

## Phase 31 -- the claim translator (completes Phase 30's other half)
DONE. Phase 30 built the storage and the checker for "stories waiting to be proven", but the user still
had to do the hard part alone: turning "Bedrock will drive AWS" into metric + threshold + deadline. For
someone who is explicitly not a finance person that is the whole difficulty, and an unusable field is an
empty field -- exactly how thesis sat unused for 22 phases. So: paste the raw commentary, get back each
claim sorted into checkable / needs_data / unfalsifiable / timing / factual, with a proposed metric,
threshold and deadline for the checkable ones, and one click to store the selected ones as expectations.
- src/agent/claims.py -- one structured-output Gemini call (not the agentic loop; this is a single
  translation, not an investigation), on the interactive quota lane. The LLM's output is NEVER trusted
  directly: `_vet()` re-checks every proposal deterministically -- the metric must be one that actually
  exists in that ticker's stored facts (otherwise downgraded to needs_data with the invented name
  quoted in the reason), the operator must be in VALID_OPS, the value must be numeric, the deadline must
  parse (if missing it is filled with +1y and flagged `deadline_defaulted` so the UI asks for
  confirmation rather than silently inventing an expiry).
- The unfalsifiable/timing/factual buckets are kept and displayed, never filtered out -- seeing that a
  confident-sounding paragraph contains more unprovable claims than provable ones IS the product.
- **Unit anchoring, found by running it for real**: given only metric NAMES, the model proposed
  `Revenue > 700000` for AMZN whose stored Revenue fact is 6.4e11 (it was thinking in millions) -- an
  expectation that would read "hit" forever, i.e. one that can never be wrong, the exact failure this
  feature exists to prevent. Fix: the prompt now lists each metric WITH its current value, unit and
  period, formatted with thousands separators rather than scientific notation (6.37959e+11 is what
  invites the millions misreading). Re-run live: it produced `Revenue FY > 800,000,000,000 by
  2027-08-02` -- correct scale.
- POST /api/claims/{ticker} (3rd LLM-touching endpoint, user-pressed only, 503 without a key) +
  claim-parser.tsx on the ticker page (collapsed by default; checkboxes only on checkable rows; saving
  APPENDS to existing expectations and preserves the hand-written thesis/rules).
- 13 offline tests with an injected fake LLM (invented metric, bad operator, missing value, missing
  deadline, unfalsifiable kept + explained, empty text never reaching the LLM, prompt contains only real
  metrics and their current values). Suite 284/284, tsc + next build clean.
- Live result on the user's own pasted paragraph about AMZN: 6 claims -> 1 checkable, 1 needs_data,
  1 factual, **3 unfalsifiable** ("aws bedrock ดีสุด", "โมเดล claude จะชนะ", "amazon จะรวยมหาศาลถ้า
  claude IPO"), each with a written reason why no number could settle it.

## Phase 32 -- the agent's own report card (pointing Phase 31 at ourselves)
DONE. Phase 31 grades other people's claims on whether they can be wrong. Our own health score had
never been held to that standard once. This closes the asymmetry, using only the point-in-time data
already in `analyses` (every row's health_reasons_json carries the full criteria list + valuation
inputs) -- no LLM, no Gemini quota, no new price fetches.

Deliberately split into two questions, because "answerable now" differs and merging them is the
easiest way to fool yourself:
- **(1) Is the score stable enough to believe? -- answerable today.** The score of an unchanged
  company should not move several points in a month with no new filing in between. If it does, we are
  measuring the readiness of our own data, not the strength of the business.
- **(2) Do high scores actually outperform low ones? -- not yet answerable.** History is 26 days
  (2026-07-06 -> 2026-08-01); the shortest horizon needs 90. The machinery is written and tested, but
  it reports "รออีก 64 วัน" instead of statistics over a sample of zero. Publishing a number computed
  from 0 eligible snapshots would be worse than publishing nothing.

- src/agent/scorecard.py -- attributes every day-over-day score move into buckets that always sum
  back to the actual delta (anything unexplained lands in `other`, openly, rather than being absorbed
  to make the numbers tidy):
  `business` (criteria computable in both rounds whose value moved) / `data` (criteria flipping
  null <-> number, or a valuation lens change) / `estimate` (our own realistic_growth revised) /
  `price` (implied_growth moving with EV). Only `data` + `estimate` count as concerning -- business
  is what we mean to measure and price is what the valuation leg is designed to react to; counting
  those as noise would flag everything and mean nothing.
- Price vs estimate are separated exactly, not proportionally, by scoring a hypothetical middle gap
  (`f(implied_new − realistic_old)`) with valuation.py's own `_gap_to_score`, so the parts add back up.
  Across a lens change they are not separated at all -- comparing gaps across lenses is comparing
  scores from different exams; the whole delta goes to `data` with the reason stated.
- Measured **gross (summed per consecutive pair), not first-vs-last**: a score that runs up 3 and back
  down 3 is the worst instability there is, but head-to-tail scores it 0 and it would rank as the
  calmest row in the table.
- **What it found on the real DB, immediately -- 7 of 15 tickers flagged:**
  - GOOGL 4.9 unexplained points: realistic growth oscillating 15.7% <-> 12.5% <-> 15.7% <-> 12.5%
    <-> 15.7% across four consecutive runs. A deterministic formula bouncing between two answers.
  - MSFT 6.3 -> 9.1 in 26 days (the case that prompted the feature): +1.0 from 'FCF+คุณภาพกำไร'
    flipping null -> 1.0, +0.66 from lens growth -> standard, +1.66 from a realistic-growth revision.
    Business contribution: +0.1.
  - ASML: the same criterion toggling computable/uncomputable on three consecutive days.
  - MA: swings 2 points purely by flipping between /8 (partial) and /11. `unexplained` is 0 there by
    construction (cross-basis deltas can't be bucketed), so `trustworthy` also requires
    basis_changes == 0 -- otherwise the ticker that flips basis most often ranks as the most stable.
- GET /api/scorecard + /scorecard page (bucket bars per ticker, click a row for the dated list of what
  changed; the pending half is a separate dashed card with a per-horizon countdown and the caveats
  about overlapping windows and watchlist survivorship spelled out).
- 21 offline tests on injected history: each bucket's attribution, the sum-to-total invariant,
  oscillation caught when start == end, business+price staying trustworthy, basis flipping, same-day
  rerun collapse, and two look-ahead guards on the forward-return half (snapshots inside the horizon
  excluded, partial /8 rows excluded from the bands). Suite 312/312, tsc clean.

## Phase 33 -- second opinion without a second API key (chat handoff + head-to-head)
DONE. Everything the pipeline judges is judged by one model family (Gemini free tier). Buying a second
API key isn't in the budget, but a second opinion doesn't actually require one: the data can be
exported to a file, pasted into a chat with any model, and the answer imported back. Monthly, by hand
-- this leg is powered by a human, so it is not a cron job.

The point is not "now there are two opinions". It is that the two are **comparable**:
- The pack is assembled from the *same prompt pieces* Gemini reads (`asset_profile` / `data_block` /
  `TASK_BLOCK` in summarize.py), rearranged only in layout -- framework once at the top instead of
  once per ticker (the checklist is 20KB; 11 copies is not pasteable). Nothing is retyped here, so
  editing the prompt can't silently make the comparison unfair. A test asserts the exact data block.
- The answer must validate against the **same `Summary` schema**, then runs the **same evals**
  (check_grounding / check_facts_grounding) and the same garbled-text scrub as the API path. So
  "more detailed" is settled by numbers -- cited figures that match a real Fact -- not by vibes.
- The `.json` snapshot is written next to the `.md`, and import checks the reply against *that*, not
  against today's data. Otherwise price_ok would degrade with time and blame the model for it.

- What can't differ, stated up front: **health_score is not LLM output** (Piotroski + reverse-DCF
  since Phase 17/18). Same data = identical score whoever answers. The comparison is over what the
  LLM actually decides: the three labels, grounding accuracy, and countable depth.
- src/history/claude_store.py -- separate table on purpose. Hand-carried rows must never leak into
  `analyses`, or changes/timeline/scorecard/performance would quietly mix a monthly manual row into
  daily statistics. UNIQUE(ticker, period, model) + upsert, because re-pasting is the normal case.
- src/agent/compare.py -- pairs each row with the exact `analyses.id` recorded at export time
  (falls back to the newest row in the period, flagged `same_snapshot: false`). Gemini's
  `cited_count` was never stored, so it is recomputed from that row's own summary+facts with the
  same eval rather than shown as N/A -- otherwise the depth column is empty on one side and useless.
- `python scripts/claude_handoff.py export | import | compare` (export costs zero Gemini quota --
  price/news/fundamentals only), plus GET /api/claude-analyses and GET /api/compare/{period}.
- `/compare` page, shaped entirely by the fact that this leg runs **rarely, by hand**: it opens on
  the newest period that *has* data (never the current month, which is empty most of the time and
  would read as broken), the not-yet-pasted state is a neutral how-to card rather than a warning
  colour, and it never enumerates which tickers are missing -- that would be nagging about a job
  deliberately done a few times a year. Rows expand to both sides' reasons side by side, because
  when two verdicts differ the useful question is "what did the other one see", which a label
  can't answer.
- Honesty fix caught while verifying the page: the row flag was called `same_snapshot`, which was
  not true -- it only meant "paired with the analyses row recorded at export time". The chat side
  reads a fresh snapshot; the daily row is its own run, up to a day or more earlier. Renamed to
  `linked` and the row now reports `data_gap_days`, with a chip from 2 days apart. Annual
  fundamentals don't move day to day, but price and news do, so a disagreement is only evidence
  about interpretation once the gap is known.
- 13 offline tests: pack carries the identical data block, framework/task appear once, crypto items
  get the crypto framework, invented numbers land in `unmatched_numbers`, code-fenced replies parse,
  re-import overwrites, a bad ticker doesn't fail the batch, and import without a snapshot refuses
  rather than silently grading against today's prices. Suite 325/325.

## Phase 33.1 -- acting on what the second opinion found (compute it, don't ask for it)
DONE. The first head-to-head produced one substantive disagreement worth acting on: DUOL, where the
daily model called the stock cheap off `P/E 15.42x` without noticing that `Net Margin 39.91%` sits
far above `Operating Margin 13.07%`, `CFO < Net Income`, and `Forward P/E > trailing P/E` -- i.e. the
P/E is flattered by something below the operating line, not by a low price.

**The tempting fix was the wrong one.** "Improve the prompt so Gemini reasons like Claude" fails on
two counts, and both are checkable rather than matters of taste:
- `stock_analysis_checklist.md:51` **already says** "Operating Cash Flow เทียบ Net Income — ถ้ากำไร
  ทางบัญชีสูงแต่เงินสดไม่เข้า = คุณภาพกำไรต่ำ (ธงแดง)", and both numbers were in the DATA it was
  given. It is a compliance gap, not a missing-instruction gap; sentence 52 does not fix sentence 51
  being ignored.
- Writing one model's reasoning into the shared prompt destroys the instrument that found the
  problem: next month's comparison would measure "who follows my checklist" instead of "who sees
  more", with the same author writing both the checklist and one of the answers. Two opinions are
  only worth having while they can differ.

So the rule applied instead: **if it can be computed, compute it and put it in the DATA** -- the same
principle that already makes health and reverse-DCF deterministic. Three derived facts
(`fundamentals.py::_derived_facts`), skipped rather than faked when they can't be compared (loss-making
=> no CFO/NI ratio; mismatched periods => no margin gap):
- `Earnings Quality Gap` (Net Margin − Operating Margin) -- caught both directions on real data
  immediately: DUOL +26.84pp (flattered), META −11.36pp (business is *better* than net income says)
- `CFO / Net Income` -- DUOL 0.937x, META 1.915x
- `Forward P/E - P/E` -- positive means the market itself expects EPS to fall (DUOL +1.78x)

Now no one has to notice: both models read it as a line, health can score it, and the eval can check
whether anyone misquoted it.

- health criterion #2 is now `min(graded(Net Margin), graded(Operating Margin))` -- fuzzy AND, the
  same shape criterion #3 already used. Net income the business didn't earn no longer gets full
  credit (synthetic case OM 5% / NM 30%: 1.0 -> 0.0). **The label string is deliberately unchanged**:
  scorecard.py matches criteria across days by label, so renaming would register as a null<->number
  flip for every ticker at once and flag the whole board as `data` noise.
- **A/B over all 279 stored rows with identical inputs: 0 scores change.** DUOL only ever passed
  because OM 13.07% grazed the band edge at 13.0 -- lucky, not correct. This is a guard against a
  case the watchlist hasn't hit yet, and it needs no backfill.
- **The eval itself was measuring writing style.** Two bugs, both biasing the score of whoever writes
  numbers plainly: Thai scale words ("2.69 หมื่นล้าน" = the exact Fact value) were counted as
  unmatched because only 1e3/1e6/1e9 multipliers were tried, and dates/form names ("8-K วันที่
  2026-06-10") were parsed as cited metrics. Fixed both; numbers that carry an explicit unit no
  longer get the loose multiplier sweep, so the check gets *stricter* about order-of-magnitude
  errors while it stops punishing readable prose. compare.py now prefers the freshly recomputed
  ratio over the stored column so both sides are always scored by the same eval version -- the same
  cross-basis trap `comparable_score` guards against for /8 vs /11.
- Effect on the same 11 tickers, nothing else changed: Claude 98% -> 100%, Gemini 93% -> 98%. NVDA's
  Gemini row went 50% -> 100% -- that entire gap was measurement error. What survives is real: TSLA's
  Gemini row still cites "ยอดส่งมอบ Q2 เพิ่ม 25% มาที่ 480,126 คัน ตามข้อมูลจากข่าวล่าสุด", numbers
  that appear nowhere in the news it was given. That fabrication is the one thing no other layer
  catches, and it is now the only thing the metric is complaining about.
- 9 new offline tests (scale units, order-of-magnitude still caught, dates ignored, criterion capped/
  not double-penalised/period-matched, derived facts present and skipped correctly). Suite 335/335.

## Phase 33.2 -- the two things the comparison exposed that were never about the models
DONE. Both items came out of the same head-to-head, and neither is fixable by prompting.

**1. Foreign ADRs: statements and price are in different currencies, and nothing knew.**
`info['financialCurrency'] != info['currency']` for ASML (EUR/USD) and TSM (TWD/USD). Every fact was
labelled "USD" regardless, so the DATA claimed TSM earns 4.44e12 **USD**, and every ratio dividing a
price-side number by a statement-side one was meaningless while looking perfectly reasonable:
- TSM showed `P/S 0.47x` (reads as "extremely cheap"), `P/B 84.3x`, `FCF Yield 35.25%`
- ASML showed `EV/EBITDA 2576.692x`, `P/B 1380.7482x`
- Worse, silently: `reverse_dcf` builds `EV = market_cap + net_debt`. ASML scored its valuation leg
  **0.0/3 off an implied growth of 31.4%/yr computed from a USD EV over EUR FCF** -- a fabricated
  number sitting in the health score on the dashboard. TSM escaped only because the garbage landed
  outside the model's interpretable range. Escaped by luck, not by design.
- The daily model's TSM answer contradicted itself as a result: verdict `cheap`, while its own weak
  point said `P/B 84.30622x` means a very high premium. Both readings came from broken inputs.

Fix: **do not convert** (which yfinance field sits on which side is not knowable, and a wrong FX
guess is worse than no number) -- instead tell the truth and refuse. Units now carry the reporting
currency (`Revenue: ... TWD` next to `Market Cap: ... USD`), the four cross-currency ratios are
dropped entirely, and `reverse_dcf` returns None on mismatch. P/E / Forward P/E / PEG survive:
Yahoo puts EPS on the same side as price, verified against both tickers' actual numbers.
- The suppression lives in `to_facts()`, not in the provider, so an object built anywhere gets the
  same rule. Detection for the health path reads **fact unit strings**, because that path runs off
  facts loaded from the DB during backfill where no source object exists -- and old rows labelled
  "USD" everywhere therefore evaluate to "no mismatch", leaving history untouched.
- Result on live data: ASML 6.9/11 (with a fabricated price leg) -> **7.9/8 partial**, TSM ->
  7.5/8 partial, both with the honest reason "งบกับราคาคนละสกุลเงิน". DUOL unchanged.

**2. Framework versioning -- the prerequisite for ever touching the checklist.**
`summarize.framework_version()` hashes checklist + crypto framework + TASK block into 12 chars,
stored on every `analyses` row, every `claude_analyses` row, and inside the pack snapshot (the
imported row records the version from **export** time, since that is the framework the answer was
written against). compare.py reports `same_framework`, and the CLI/UI flag mismatches loudly.
- A hash, not a hand-maintained number: a version you have to remember to bump is a version you
  forget to bump.
- Three states, not two: `null` means "one side predates the column" and must never render as
  "same framework" -- unknown is not agreement.
- This is the same failure mode as Phase 32's `basis_changes` and Phase 29's /8-vs-/11 split: when
  the measuring basis changes, the comparison has to know, or the difference gets misread as signal.

- 8 + 4 new offline tests. Suite 347/347, tsc clean.
- **The 2026-08 round was deliberately not re-exported.** Rerunning a recorded comparison against
  changed data and a changed framework is exactly the mid-exam rule change this phase exists to
  prevent. The fixes apply from the next round forward.

## Phase 33.3/33.4 -- clearing the queue, then proving the claim the whole comparison rests on

**GOOGL's oscillating growth estimate (open since Phase 32) -- found, and it was a silent fallback.**
`realistic_growth` flipped 15.7 <-> 12.51 across consecutive runs with no flag and no lens change.
Diffing the stored facts between a 15.7 day and a 12.51 day left exactly one culprit: **`D&A` was
present on one and `None` on the other**, because yfinance returns a different set of cashflow rows
between calls. With D&A missing, `reinvestment_rate` correctly returns None -> `sustainable_pct` is
None -> `valuation_guard` adds no flag -> `flags` is empty -> `route = "standard"` -> and then
reverse_dcf's standard branch quietly substitutes `historical_cagr` while still labelling the lens
`standard`. A missing input became a different anchor with nothing recording that it happened.
- Missing input *is* "sustainable can't be trusted", which is the same condition as every other flag
  in that function -> now raises `SUSTAINABLE_UNCOMPUTABLE` and routes to the growth lens, which
  anchors on real FCF/revenue growth and needs no D&A. The fallback is now visible and consistent.
- `_first()` also stopped at the first *existing* row name and gave up if that cell was NaN, ignoring
  later aliases that had the number. It now walks every alias until one yields a value, and D&A gained
  two more aliases. That removes the flapping at source.
- A/B across all 203 stored rows with a real lens: **exactly the 8 GOOGL rows change**, all of them
  the ones that were flipping. AAPL/SPCX/JPM also differ from stored values, but re-running with the
  *old* guard reproduces those too -- they are a pre-existing loop-vs-duck path difference, not this.

**Banks: a second criteria set, built from what can actually be fetched.**
JPM had been "ประเมินไม่ได้" every day since being added: 5 of the 8 standard criteria need numbers
that are meaningless for a bank (deposits aren't leverage; lending drives CFO/FCF to
-147,782,000,000 USD without anything being wrong), so only 4/8 were computable and the data gate
disqualified it. Adapting the existing criteria was not an option -- they measure the wrong things.
- `BANK_CRITERIA` (still /8, so scores stay on one scale with every other holding): ROTCE, ROE,
  Net Margin, Equity/Assets, NII/Assets, Cost+Provision/Revenue, revenue growth, dilution.
- Built from fetchable data, not from a wish list: CET1, NPLs and provisions are not in yfinance, so
  they are simply absent rather than approximated into a score. Where a proxy *is* used the name says
  so -- `NII / Assets` not "NIM" (the denominator should be earning assets), `Cost+Provision /
  Revenue` not "efficiency ratio" (no non-interest expense line) -- because a label that implies an
  industry-standard metric invites comparison against industry-standard thresholds for a different
  number.
- Detection is `Net Interest Income / Revenue >= 20%` read from **facts**, not a sector string:
  facts are what the backfill path has, and "Financial Services" also covers insurers and asset
  managers, which this framework cannot read either.
- Valuation uses justified P/B = (ROTCE − g) / (COE − g) with the same CAPM and terminal growth as
  everything else. It deliberately does **not** reuse `_gap_to_score`'s bands: those are percentage
  points of annual growth, where 10pp is enormous, while this is a percentage premium over fair
  value, where 10% is unremarkable -- sharing the bands would put nearly every bank at 0 or 3 and
  reintroduce the binary cliff that audit 19.3 removed. Bank bands are 0/15/35% with a 7pp taper.
- JPM now scores 10.6/11 (fundamental 7.6/8, price 2.68/3 at a 2.6% discount to justified P/B).

**Model invariance -- the claim is now measured, not asserted.**
Every answer given about this feature has leaned on "health score isn't LLM output, so the model
doesn't change the numbers" -- justified by reading the code, which is exactly the evidence that
already failed once this month on currency. `src/evals/check_model_invariance.py` feeds **one fact
set** through the whole deterministic layer twice, changing only whose analysis it is, and diffs
score, tier, max, partial, every sub-criterion, the valuation leg and its reason, and the breach
penalty. `python scripts/claude_handoff.py invariance` runs it on real data.
- **11/11 tickers identical on the 2026-08 round, with the two models disagreeing on sentiment for
  10 of them.** Different reading, same numbers -- which is the property the entire comparison
  depends on.
- Locked in as tests for both the standard and bank frameworks, including one that deliberately
  feeds *different* data and asserts the checker reports a difference -- a check that can only pass
  proves nothing.
- 15 new tests. Suite 362/362, tsc clean.

## Phase 33.5 -- the last two queue items: ground truth for ADRs, real data for crypto

**20-F / IFRS: TSM and ASML had never once been checked against what they actually filed.**
The XBRL eval matched `form == "10-K"`, taxonomy `us-gaap`, unit `USD` -- all three assumptions fail
for foreign filers, so both returned N/A forever. That is the worst possible pair to have no ground
truth for, since Phase 33.2 had just found their yfinance data broken in another way. What the real
companyfacts show: **ASML files 20-F but tags in us-gaap** (only the form filter was wrong), while
**TSM uses `ifrs-full` throughout and reports in TWD** (taxonomy *and* currency).
- Annual forms widened to 10-K/10-K/A/20-F/20-F/A; IFRS concept names added per key, verified
  against TSM's actual filings rather than guessed. Keys with no confident IFRS counterpart are
  left out -- when the reference itself is wrong, the eval reports *us* as wrong.
- `reporting_currency()` picks one currency **per company**, not per concept. TSM attaches USD
  convenience translations to some concepts (usually latest year only); letting each concept choose
  would take Revenue in TWD and Net Income in USD and produce a margin that is garbage but looks
  plausible -- the identical bug shape as Phase 33.2, so it gets the identical treatment.
- Result: **ASML 12/12 concepts, TSM 10/12, both 100% accurate** on every margin the eval checks
  (AAPL/JPM unchanged). Independent confirmation of the 33.2 diagnosis too: the statement-side
  numbers were always right, only the price-derived ratios were broken.

**Crypto on-chain: the framework had been asking for evidence that was never supplied.**
`CRYPTO_FRAMEWORK` has instructed the model to judge "real usage, integrations, upgrades" and
security since Phase 9, while the DATA block carried nothing but tokenomics. Asking for a verdict
with no data for it is a recipe for confident guessing -- the same lesson as 33.1.
- `src/providers/crypto/onchain.py` -- active addresses, transactions/day, transaction fees and
  hash rate from blockchain.info (free, no key), 1-day cache, failures degrade to `{}` rather than
  raising, and each metric ships as a **30-day average plus a YoY change**: daily on-chain values
  swing hard enough that a single day is noise, and a level with no trend has no benchmark to be
  read against.
- **Bitcoin only, deliberately.** blockchain.info covers one chain; bolting on per-chain endpoints
  would file numbers with different definitions under one label (an account-based chain's "active
  addresses" is not BTC's).
- First real read is immediately non-obvious: active addresses **−13.2%** YoY and fees **−21.7%**
  while transactions/day is **+42.5%** -- more transactions from fewer addresses paying less.
  Exactly the kind of thing the old DATA block could not have surfaced at all.

**What was deliberately not built: a crypto /8 score.** The bank framework was justified because
ROTCE, capital ratios and cost/income are established metrics with defensible thresholds. Crypto has
no equivalent -- any eight cutoffs I picked would be invented, and the project's own rule is that a
number nobody can justify is worse than an honest gap (partial /8, "excluded", "unclear" all exist
for this reason). Crypto still scores `excluded`; what changed is that the *analysis* now has
evidence to work from. Note also that BTC is still frozen in the watchlist, so nothing consumes this
until it is unfrozen -- that is the owner's call, not a code change.

- 15 new offline tests (no network): 20-F accepted, IFRS fallback, us-gaap precedence, quarterly rows
  still excluded inside annual filings, one-currency-per-company enforced, 10-K path unchanged,
  unsupported chains return nothing, short series produce no fake trend, API failure degrades
  quietly, zero baseline yields a level without a fabricated trend. Suite 377/377.

## Phase 33.6 -- the DB stopped being mergeable the day the UI started writing to it

Pushing Phase 33 took three attempts, and none of the failures were about the code. `data/watchlist.db`
is tracked in git and written by two parties who never see each other: CI commits a daily analysis
round every day, and I edit watchlist/thesis/decisions through the web UI. SQLite is binary, so git's
only options are "take ours" or "take theirs" -- both of which mean deleting someone's work. I got
through it by hand-verifying that local was a strict subset of CI's rows and then rebuilding the file
programmatically. **That worked on luck**: the moment the UI deletes a ticker or edits a thesis, local
stops being a subset and the manual trick silently drops whichever side loses.

`src/db/merge.py` + `scripts/merge_db.py` -- a **three-way merge that works on rows, not files**,
installed as a git merge driver so `git pull` / `rebase` / `merge` handle DB conflicts with no
intervention at all.
- Edited on one side -> take that side. **Deleted on one side and untouched on the other -> actually
  delete**; a delete button whose effect gets overwritten by tomorrow's CI commit is a broken feature,
  not a merge policy.
- Rows added on both sides -> keep both. Their ids collide (each side allocates from its own
  AUTOINCREMENT) so the newcomer is renumbered -- and **`claude_analyses.analysis_id` is rewritten to
  follow it**. A remap that doesn't chase its foreign keys is worse than a failed merge: the link
  still resolves, just to the wrong row.
- **An id freed by a delete is never recycled.** Handing a deleted row's number to a new row turns any
  surviving reference into a silent mis-point instead of a detectable dangling link (which gets
  cleared and reported).
- Identity is a natural key, not the id: `(ticker, run_at)` for `analyses`, `(ticker, period, model)`
  for `claude_analyses`. When CI and I both record the same daily run it is deduped, not duplicated.
- **Schema branches too.** The output schema is the *union* of all three sides, because my file had
  the `framework_version` migration applied and CI's did not -- picking either side's schema drops a
  whole column with no diff to show for it. (My hand merge did exactly that; replaying it through the
  script recovered the column.)
- Genuine conflicts -- both sides edited the same row differently, or one deleted what the other
  edited -- are resolved by newest-timestamp (keeping the row in the delete-vs-edit case, since
  removing something unwanted is easier than recovering something gone) and **always printed**.
  Deciding on the owner's behalf without saying so is indistinguishable from losing the data.
- No common ancestor -> union mode, and it refuses to delete anything: without a base, "deleted" and
  "never existed" are the same observation, and guessing between them is how data disappears.

Verified by replaying the two real conflicts from 2026-08-04 (296 and 307 rows) and by driving actual
`git merge` / `git rebase` in a scratch clone, including a UI-delete-vs-CI-commit case. CI now runs
`install` in both workflows and `daily-report.yml` gained the `git pull --rebase` it never had -- its
bare `git push` would simply fail and take that day's round down with the runner.

- 16 new offline tests (no network, temp SQLite only): both-sides-added survive with unique ids, FK
  follows a remapped id, same daily run deduped, one-sided edit taken, UI delete honoured,
  delete-vs-edit keeps and reports, newest wins on a double edit, dangling link cleared, freed id not
  reused, one-sided migration column preserved, one-sided table carried over, unique indexes rebuilt,
  identical files unchanged, no-base refuses to delete, AUTOINCREMENT still usable afterwards, and the
  project's real stores can read *and write* the merged file. Suite 394/394.

## Phase 26.1 (revisited) -- a radar whose normal output and whose failure look identical

Owner's observation: "macro doesn't seem to do much." Investigation says the radar is fine -- it runs
~5 times a day, reaches FRED, and is silent because **FRED itself has nothing newer than June**. July
payrolls land 2026-08-07, July CPI around 08-13. Every part of that is correct behaviour.

The complaint is still valid, and it points at a real defect: **a working radar and a dead radar
produce the same observable output -- nothing.** This isn't hypothetical. The workflow already
carries a comment about the July 2026 incident where FRED (behind Cloudflare) silently throttled the
runner's IP and every series failed to fetch; `scan_for_alerts` swallowed it with `if pair is None:
continue`, so the job stayed green and quiet for days. `data/macro.db` has exactly one commit in its
entire history, which is what that period looks like from the outside: nothing to see.

- `radar.status()` -- read-only, no `mark_seen`, per series: did the fetch succeed, what does FRED
  have, what have we alerted, when is the next release expected (`ref month + approx_lag_days`), how
  far past due. Four states: `ok`, `unreported`, `overdue`, `fetch_failed`. The point is that
  "quiet" now splits into "quiet because nothing is due" and "quiet because we can't see".
- **`OVERDUE_GRACE_DAYS = 7`.** Release dates here are estimates (`approx_lag_days`) and real releases
  slip a couple of days. A tripwire that fires every month teaches you to ignore it, and then it is
  worth nothing on the month that matters.
- Every CI run now prints the status table, so the workflow log is *evidence* rather than an
  unfalsifiable "ไม่มีตัวเลขใหม่ — เงียบ".
- `notify.send_health_warning()` posts to Discord when the radar **cannot do its job** -- explicitly
  not when the market is quiet. At most once a day (state under a `__health` key in `macro_seen`,
  which `scan_for_alerts` never sees because it iterates `fred.SERIES`); hourly warnings would train
  the owner to mute the channel.
- The macro page gained a status strip up top, deliberately drab when healthy: the page previously
  showed only "latest numbers", which reads exactly the same whether the data is current or three
  months stale.
- `fred.fetch_series` gained a 10-minute in-process cache -- `dashboard()`, `status()` and `baserate`
  all pull the same monthly series within one request. **Failures are not cached**: remembering a
  failure means staying broken for the rest of the TTL after FRED recovers.

Found while writing the tests: `notify.py` calls `load_dotenv()` at import, so importing it in the
suite leaked the real `FRED_API_KEY` into `os.environ` for the whole session and `fetch_series` would
take the live-API path. Existing tests survived only because they patch `urlopen`, which happens to
cover both paths. The macro fixture now deletes the key -- the no-network rule shouldn't depend on a
coincidence.

- 13 new offline tests: correct-and-quiet is `ok`, overdue is flagged with the right day count, the
  grace window doesn't cry wolf, a fetch failure never looks calm, unreported data is visible,
  `status()` never marks anything seen, health warning fires on fetch failure, stays quiet when
  healthy, sends at most once a day, `__health` never leaks into a scan, cache avoids refetching, and
  cache does not remember a failure. Suite 407/407.

## Phase 34 -- the screener was hiding companies, and nobody could tell

Started as "what's left to do", which is itself worth recording: the answer I first gave was wrong.
The 19.5 section still ends with "the natural next fragility-reducer is making valuation graded like
the fundamental leg" -- prose written *before* 20.1 did exactly that. Reading a roadmap without
checking the code produced a confident recommendation for work already finished. Both stale markers
(that line, and the "Phase 20 NOT STARTED" header above three DONE sub-phases) are now corrected;
a plan that lies about its own state is worse than no plan.

What the check-before-building did surface, by running the real engine over the real universe:

- AXP / GS / JPM were absent from the screener cache purely because that cache predates 33.3. Live,
  they now score 6.00, 5.96 and 9.51 -- **33.3 confirmed end-to-end on live data**, not just in
  tests. LLY had recovered on its own.
- **ORCL is genuinely dropped, and shouldn't be.** Its 3-year average FCF is negative (the AI
  datacenter capex cycle), so reverse-DCF can't run, so `screen_one` returned `None` and the name
  vanished -- while `health.py` scores it 4.8/8 via the Phase 29 partial path. The same "two paths,
  one engine, different answers for one stock" shape as the bank bug in 33.3, mirrored.

`screen_one` now returns a partial row (`max=8`, `partial=True`, `valuation_score=None`,
`partial_reason`) instead of dropping the name, matching health.py exactly -- verified live: ORCL
4.81/8, ASML 7.9/8, TSM 7.5/8, all equal to what compute_health() returns for the same inputs.
- **Partial rows sort into their own block after every full row, never interleaved.** 8/8 is not
  better than 10/11; they are different rulers. Ranking them together would make the *ordering* lie
  while every individual number stayed correct -- the same reason `comparable_score()` excludes
  partials from cross-name comparison.
- The screener page shows them under a divider that says so, with the reason on hover, and the
  "passed" KPI counts full rows with the partial count called out separately rather than folded in.
- A stock that fails the *data gate* is still dropped. Partial means "the price leg is unavailable",
  not "score it anyway" -- otherwise the number would be conjured from data that isn't there.

Why this matters more for the screener than anywhere else: this is the **discovery** tool. Silently
hiding companies that are investing heavily enough to run FCF negative is the worst possible
direction for that bias to point -- exactly the names worth looking at and deciding on yourself.
Phase 29 made this argument once already for SPCX; the screener path just never got the fix.

- 5 new offline tests: partial row returned instead of None, partial rows sort last, a cash-burner is
  shown not hidden, full rows unchanged, data-gate failures still dropped, and screener/health agree
  numerically on the same partial stock. Suite 412/412.

## Phase 35 -- the trend was measured from a peak, and nothing said so

Chasing "cyclical-industry normalization" (CVX sits at 3.2/11) produced a better diagnosis than the
one on the roadmap. It is **not** that cyclicals need their own /8 framework. It is that the growth
anchor is computed over whatever window yfinance happens to return -- always about 4 years -- and for
CVX that window begins at FY2022, the top of the oil spike:

```
what the system sees:                    FY2022 236 -> 197 -> 193 -> FY2025 184    CAGR -7.85%
what SEC XBRL has:  FY2018 159 -> 140 -> 94 -> 156 -> 236 -> 197 -> 193 -> 184     CAGR +2.15%
                                          ^covid   ^war spike
```

Revenue today is *above* 2018. That is a cycle, not a decline -- but every year after the first is
mechanically "down", so FCF CAGR lands around -24%/yr, realistic growth -11.09%, valuation 0/3.

The bias is not oil-specific and not one-directional. Measured across the watchlist: **NVDA's 4-year
window says +100%/yr while the full 10-year history says +46.6%**, and **AAPL's says +1.8% while 9
years say +7.7%** -- AAPL's "low revenue CAGR" noted back in 20.2 turns out to be a window artifact.
Any company whose first window year is unusual is distorted; only the direction changes.

**Deliberately did not change any score.** Re-anchoring would move NVDA and AAPL as much as CVX and
needs a backfill dry-run behind it; that is the owner's call, made on numbers. This phase only makes
the window visible:
- `valuation._anchor_window()` -- pure, no network, no effect on scoring: which series fed the
  anchor, how many years, first/last period, and whether the window starts at its own max or min.
  Rides along in `reverse_dcf()`'s result, so it lands in the stored `valuation_json` with no schema
  change. Verified after the change: CVX still 0.0/3, realistic growth still -11.09.
- `src/evals/check_anchor_window.py` -- the conclusive comparison, using the SEC XBRL history already
  fetched and disk-cached for the Phase 12 accuracy eval. Flags a sign flip, a materially different
  trend (>=10pp), or a window starting in the top/bottom quartile of the full history.
- The ticker page's reverse-DCF box now states the anchor window inline, with the peak/trough warning.

**The eval's own first version was wrong, which is the part worth remembering.** It compared the
XBRL CAGR against the provider CAGR directly -- but XBRL *ends* where yfinance *begins* (NVDA: XBRL
through FY2022, yfinance from FY2023). So it reported "4yr +100% vs 6yr +31%" as though that were one
trend measured over a longer window, when the two numbers describe different eras entirely, and it
flagged NVDA as "starts at a cycle high" merely because FY2023 exceeded every year in the older set.
Fixed by merging the two into one history before measuring anything, plus a contiguity guard that
refuses to compute across a hole (CAGR divides by point count, so a gap silently inflates it). A tool
that compares two different things and looks authoritative doing it is the exact failure this
project keeps finding elsewhere -- worth noting that it appeared in the detector itself.

Also surfaced: **XOM returns zero years from XBRL** despite being an ordinary US 10-K filer -- a
concept-name coverage gap of the same kind 33.5 closed for ADRs, and it means XOM has no ground-truth
cross-check at all today.

`SHORT_WINDOW` is reported but deliberately does **not** count as concerning: yfinance gives everyone
4 years, so a flag that fires on every ticker every day carries no information -- the same reasoning
as the macro radar's grace window in 26.1.

- 12 new offline tests: window metadata reported, peak-start and trough-start both flagged, series
  ordering irrelevant, thin series report nothing rather than guessing, the CVX case end-to-end,
  gapped histories refused, adjoining histories still compared, newer years merged in not dropped,
  an agreeing longer window stays quiet, missing long history says so, and the opposite (understated)
  bias is caught too. Suite 424/424.

## Phase 36 -- anchoring on the filed history, and the four bugs found on the way there

Phase 35 measured the problem and deliberately left scores alone. This phase moves the anchor to the
history companies actually file with the SEC. Only **2 of 12** scores move: **CVX 0.0 -> 1.0/3**
(health 3.2 -> 4.2/11, the case that started this) and ADBE 2.66 -> 2.89. Everything else is
untouched, because most names route through the `sustainable` lens where no window is involved.

**Design: one computed number, not a longer series.** The long FCF history is condensed to a single
`FCF CAGR (long-run)` fact rather than 19 extra series rows, because `data_block()` pastes every Fact
into the prompt verbatim -- adding 15 lines per stock per day silently changes the question the model
is asked, which is also the instrument the whole two-model comparison rests on. Storing it as a
**Fact** (not just an attribute) is what keeps `health.py`'s facts-rebuilt duck object and the live
provider object producing identical anchors -- verified live on CVX/ADBE/AAPL. That divergence is the
bug shape this project has now hit three times (33.3, 34).

**Four guards, each earned from a real failure, all of which must pass before the anchor changes:**
1. the SEC history must be genuinely longer than what we already have;
2. endpoints must be positive (CAGR is meaningless across zero);
3. the two sources must **overlap** in at least one year -- adjoining is not enough;
4. **every overlapping year must agree within 2%.** Revenue fails this: XBRL's best-covered concept
   for XOM is `Revenues` (total revenues *and other income*), which sits 3-4% above yfinance's every
   year. Splicing those would read as growth where the only thing that changed is the definition.
   FCF (CFO − capex) passes exactly -- CVX's 37.6/19.8/15.0/16.6 match to the cent -- which is why
   only the FCF anchor moved and revenue was left alone.

**What went wrong on the way, in order:**
- **XOM had no XBRL history at all, and the Phase 35 writeup blamed the wrong thing.** It is not a
  concept-name gap: `XOM` now resolves to **ExxonMobil Holdings Corp** (CIK 2115436), a holdco
  created in July 2026 with nothing but 10-Qs. The 17 years of annual filings live under **EXXON
  MOBIL CORP** (CIK 34088). A reorganisation silently erased the largest oil company's ground truth
  and the eval just went quiet. Fixed with a curated `PREDECESSOR_CIK` map (hand-checked with
  evidence -- matching "the same company" across legal entities by name is a mistake that is
  expensive when wrong) plus `has_annual_data()`, which distinguishes a successor shell from a
  company that genuinely has no data.
- **`_annual_values` stopped at the first concept that had any rows** -- the same defect as
  `_first()` in 33.3. XOM's `RevenueFromContractWithCustomerExcludingAssessedTax` covers 5 years and
  sits first in the alias list; `Revenues` covers 17.
- **"Most years wins" was then wrong too.** It sent AAPL and ASML back to ending at FY2017, because
  their pre-ASC-606 tag has more years than the one they use today. A long history that stopped eight
  years ago is not this company's history. Correct rule: **most recent first, then longest** -- and
  never merge two concepts into one line.
- **The eval caught a bug in the anchor code I had just written.** CAGR was computed as
  `(last/first)^(1/(len(points)-1))`, which is only right when no year is missing. AAPL is missing
  FY2014, MSFT FY2014-15, XOM FY2013-14 (the tag changed those years) -- so 12 points spanning 13
  years were divided by 11, **inflating the CAGR silently**. Fixed properly in a shared
  `src/domain/series.py` (span between endpoints, not sample count) rather than by refusing gapped
  histories, and the eval's gap check downgraded from a refusal to a report. AAPL's anchor moved
  4.89 -> 4.58 on that fix alone.

`check_anchor_window` now defaults to **FCF**, not revenue, because FCF is what the growth lens
actually anchors on -- a tool that measures something other than what the system decides on answers a
question nobody asked.

- 17 new offline tests: each of the four guards refused in isolation, SEC failure degrading to the
  old behaviour, the long anchor replacing the short window, unchanged behaviour without it, the
  facts path and object path agreeing, window-years parsed not guessed, recency-beats-length,
  length-breaks-the-tie, concepts never merged, successor shell told apart from no-data, overlap
  required, one overlapping year sufficient, and a mid-series gap reported but still compared.
  Suite 441/441.

## Phase 37 -- the scorer had no version, so every rule change looked like news

Phase 33.2 stamped the **prompt** with `framework_version` on the argument that a comparison across
periods is unreadable unless the basis travels with the data. The number the user actually reads
every day does not come from the prompt -- it comes from `health.py` and `valuation.py`, which had no
stamp at all. Phases 33.1, 33.2, 33.3 and 36 each changed how the score is computed, and nothing in
the stored data recorded it. The next daily run would have shown CVX's realistic growth jumping
-11.09% -> +3.21% and the scorecard would have filed it under `estimate` -- literally true, and
useless, because "new data moved our estimate" and "we changed the method yesterday" land in the same
bucket.

**A hash of the code, not a number anyone maintains.** Same reasoning as `framework_version`: a
number you have to remember to bump is a number you forget to bump, and the day you forget is exactly
the day the stamp mattered. `engine_version()` normalises `health.py` / `valuation.py` / `grading.py`
through `ast` -- **comments and docstrings stripped** -- and hashes the result. Stripping is not
cosmetic: these files carry more Thai prose than code and are edited nearly every phase, so hashing
raw source would flag a rule change every time a typo was fixed, and a flag that fires every day
carries no information (the same lesson as the macro grace window).

**Deliberately over-detects rather than under-detects.** The alternative considered was running the
engine against a fixed fixture and hashing the output -- semantically tighter, but it would have
stayed silent when the bank framework was added, because the fixture is not a bank, while JPM moved
from excluded to 9.5/11. This stamp exists to catch *silent* rule changes; missing one is worse than
an occasional unnecessary bump.

**Two detectors, because one is not enough.** The hash is a system-wide label and cannot know that a
single stock changed method. So `_valuation_delta` also watches `anchor_window.source` -- the day
NVDA's XBRL history reaches six years, its anchor switches from the 4-year window to the filed
history with no code change at all. Both route to a new `method` bucket.

**`method` does not count as instability.** On the day a rule changes, *every* stock changes version
at once; folding that into `unexplained` would flag the whole board simultaneously, which separates
nothing. But it is not swallowed either -- it is counted, noted with the date, and reported beside
the headline. A rule change is the *best*-explained kind of movement, not an unexplained one.
It also only counts as "touched this stock" when the score actually moved (`METHOD_NOISE = 0.05`):
18 commits hit these files in five weeks, and without the gate MSFT read "rules changed 9x" with
three of those moving 0.00 points, crowding the real events out of the notes.

**Backfilled from git, and it changed the verdict.** A stamp that starts today cannot read the
history that already exists -- and that history *is* the churn: 18 commits to the scoring files
between 2026-07-06 and 2026-08-10, the same window in which all 357 `analyses` rows were written.
`scripts/backfill_engine_version.py` walks those commits, computes each one's version through the
**production functions** (`parts_from`/`version_from`, not a copy), and stamps 320 rows by run time.
It uses committer date, not author date -- Phase 33's commit was rebased and its author date sits 21
hours early, which would have stamped rows with code that was not on `main` yet. Rows older than the
first commit stay NULL, because NULL means "unknown" and guessing would make the remaining NULLs
unreadable. The error mode is one-directional: CI runs always use committed code, so they are exact;
a manual run against uncommitted code inherits the previous commit's stamp, i.e. a *missed* change,
never an invented one.

Result: the flagged count fell **7 of 16 -> 5 of 16**. MSFT's unexplained movement 3.3 -> 1.7, GOOGL
4.9 -> 2.3, and AAPL/NVDA/DUOL cleared entirely -- their 1-point step on 2026-07-11 sat on top of
Phase 17/18, the rewrite of the health score from LLM labels to real numbers. The scorecard had been
reading our own rewrite as flaky data.

`changes.py` gets the same treatment: a jump across engine versions is reported as `engine_change` at
**info** severity ("this came from us changing the scoring rules, not the company") instead of
`health_jump` at warn, whose driver attribution would have pointed at the business every time.

- 36 new offline tests: threshold/logic/deletion changes bump the version; comments, docstrings,
  reformatting and inserted lines do not; docstring-only functions survive stripping; the version is
  stable, short, sensitive to every module and indifferent to their order; the module list is checked
  against what the scoring code actually imports (so a future dependency cannot slip out of scope
  silently) with the `__main__` demo block excluded; backfill and production agree on the formula; a
  module that did not exist yet is a different ruleset; the timeline boundary picks pre-change code
  for a run earlier the same day; an engine change is not called an estimate revision; unstamped rows
  behave exactly as before; a basis change still outranks a method change; a zero-net move across
  versions is still not split into buckets; and the migration fills the column on an old DB.
  Suite 477/477.

## Phase 38 -- the inputs flicker, and the scorecard was blaming the market

Phase 37 made the scorecard honest enough to point at something specific, and it pointed at **ASML:
7.0 points of movement with no business cause**, three times worse than anything else on the board.
This phase followed that finger.

**The cause was a row name.** ASML's criterion #3 (FCF + earnings quality) flipped computable /
uncomputable **six times in seventeen days**. Diffing the stored facts across one flip left exactly
one difference: `CFO` present on 08-08, absent on 08-09, everything else identical. yfinance returns
`Cash Flow From Continuing Operating Activities` for ASML on some calls and `Operating Cash Flow` on
others; we only knew the second name. Before adding the alias, the "same concept?" question was
checked the way Phase 36 taught: across 16 tickers, **15/15 that carry both rows report identical
values to the cent**, and ASML is the only one missing the primary name. It is ordered last, so a
company with genuine discontinued operations still gets the total, not the continuing-only figure.
(`Total Cash From Operating Activities`, the legacy alias we had, exists for **nobody** — it was
guarding nothing.)

**The scorecard had a matching blind spot, and finding it was the more valuable half.** `beta` also
vanishes from yfinance intermittently, and `capm_wacc` falls back to β=1.0 -- documented, recorded in
`beta_used`, not silent. But **GOOGL on 2026-07-24 went β 1.25 → 1.0, WACC 11.20% → 9.95% in a
single day**, which moves implied growth, which the scorecard filed under `price` -- the bucket whose
whole meaning is "the market moved, this is fine." A gap in our own data was being charged to the
market, in the one file whose job is to prevent exactly that.

Fixed by an exact counterfactual rather than a heuristic: the stored valuation row keeps `ev`,
`fcf_base`, `wacc`, `beta_used`, `terminal_growth` and `years`, and CAPM is linear, so Rf can be
recovered as `wacc − beta_used × ERP` and `implied_growth_rate` -- **the production solver, imported
not copied**, same discipline as `_gap_to_score` -- re-solved at today's EV with yesterday's beta.
Verified first: recomputing implied growth from the stored fields reproduces the stored value on
**276 of 277 rows** (the last differs by 0.02pp, rounding). The split then falls out of the existing
mid-point trick, and `price + beta_data` still equals the old `price`, so the buckets keep summing to
the total. Risk-free movement deliberately **stays** in `price`: a bond yield is a price the market
sets, the same as EV. A beta that went missing is not.

Effect: GOOGL's unexplained movement went **2.3 → 3.7**. The scorecard got *stricter*, not cleaner --
1.4 points that had been hiding inside an "expected" bucket are now counted, which is the point.

**`src/evals/check_fact_stability.py` -- so the next one takes minutes, not weeks.** This is the
project's fourth bug of this exact shape (33.3 GOOGL D&A, 33.3 `_first()` stopping at a NaN, now
ASML's CFO); each took weeks to surface because the scorecard reports *symptoms* -- "ASML moved 7
points on data" -- and finding the cause meant diffing facts by hand. The eval reports the cause
directly, from stored rows only, no network and no LLM.

Two design choices carry it:
- **Oscillation, not change.** A value that disappears *and comes back* is an unstable source; a
  value that vanishes once is us (Phase 17/18 added ten facts in a day; 33.2 deleted P/S and P/B for
  ADRs permanently). Things we delete never return on their own. `MIN_FLIPS = 2`.
- **"Did it reach the score?"** measured from the whole score shape, not the criteria count. Market
  Cap disappearing changes **zero** fundamental criteria -- it feeds the valuation leg -- yet it drops
  the row to partial /8. That is the unexplained 2-point flapping Phase 32 flagged on **MA** and
  nobody accounted for: MA's basis flips on 07-28/07-29 land on exactly the days its Market Cap
  went missing. A detector that watched only criteria would have missed the most expensive case.

Wired into the existing quality channel (alert-only, silent when healthy), reporting only entries
that moved a score, over a **14-day window** measured from the newest run in the data rather than the
clock -- history keeps old events forever, so a windowless report would re-send the same alert every
day until nobody read it, and a clock-based window would go quiet on days CI didn't run, which reads
as "all stable" when it means "not checked."

- 21 new offline tests: the alias falls back and the exact row still wins when both exist; flicker
  detected, ranked by score impact, silent for one-way additions and removals, silent for
  same-day reruns, exempt for metrics designed to appear later, surviving rows with no health at all;
  the window ages events out and is anchored to the data not the clock; beta vanishing is charged to
  data with the buckets still summing; an unchanged beta leaves `price` alone; rows without the DCF
  fields degrade to the old behaviour. Suite 498/498.

Also fixed while here: `build_quality_report` now takes injectable `rows`, because adding the
stability layer made it read the real `data/watchlist.db` during tests -- two existing tests passed or
failed depending on the owner's live data.

### Phase 37's own stamp broke on its first real day

The first CI run after Phase 37 stamped its rows `3f8757f9835a`; the same commit on the owner's
machine produced `b7b9b79ef876`. **Identical source, different hash** -- CI runs Python 3.12 and the
laptop runs 3.13, and `ast.dump()` embeds the node/field schema of the running interpreter. The
docstring had flagged this as a known risk; it took one day to happen. Left alone, every row would
alternate versions by *where it ran*, and the `method` bucket would fire daily -- precisely the
failure the stamp was built to avoid.

`normalize()` now works on **text, not AST structure**: strip docstrings (via `ast` node *positions*),
strip comments (via `tokenize`, which knows a `#` inside a string is not a comment), drop blank lines
and trailing whitespace, hash what's left. The only things still supplied by Python are line and
column numbers, which don't move between releases.

The cost is real and accepted: **reformatting now bumps the version** where `ast.dump` was immune.
That trade is deliberate -- a reflow happens rarely and always has a commit to point at, while a
Python upgrade shifts every stamp silently with nothing to point at. Two pinned tests (`_SAMPLE` →
exact normalized text, and its exact digest) turn any future divergence into a red CI run instead of
quietly mislabelled data -- and because CI is on 3.12 and development is on 3.13, those tests are a
genuine cross-version check every push.

Restamped with `--rewrite` (new flag: the old labels are on a different scale, so leaving them would
have manufactured exactly one phantom rule change at the seam). The 18 detected rule changes and
their row counts came out **identical** to the previous algorithm -- same events, new labels.

## Phase 39 -- "we couldn't fetch it" and "this company can't be valued" were the same sentence

Phase 38's new detector left one finding unexplained rather than unfixed: **MA and JPM kept losing
`Market Cap`**, and MA's two basis flips landed on exactly those days. Pulling the stored row for
2026-07-28 showed what Mastercard was actually told:

> `ราคา: ไม่มี Market Cap/FCF พอคำนวณ reverse-DCF — ตัดออกจาก screen นี้`

One of the most liquid equities on earth, recorded as unvaluable, because `yf.Ticker(t).info` came
back without `marketCap` on one call. Score 10.0/11 → 8.0/8, back the next day. JPM lost the same
field six times in seventeen days.

**The obvious fallback was wrong, and checking took two minutes.** Price and `Diluted Shares` were
both present on the bad day, so `price × shares` looks like a free recovery -- except it lands
**9.9% high** (971M weighted-average diluted shares vs 883.58M actually outstanding). That is the
Phase 36 `Revenues` trap again: a number that looks right, is defensible in isolation, and quietly
poisons EV → implied growth → the valuation score. Not used. (Worth noting for later: the *implied*
share count was identical to five figures across both good days, so it -- not market cap -- is the
stable quantity if a carry-forward is ever wanted.)

**Fixed at the source instead.** `_fetch_info()` retries when `.info` comes back thin, with two
details that matter:
- **A new `Ticker` per attempt.** yfinance memoises `.info` on the object, so retrying on the same
  instance returns the identical thin dict forever and the retry is decorative. A test asserts three
  distinct constructions, because this is precisely the line a future cleanup would "simplify."
- **`marketCap` as the canary, not `beta` or `PEG`.** Those go missing legitimately (recent IPO, no
  analyst coverage); picking one of them would make every healthy stock retry three times daily and
  buy nothing. A traded equity always has a market cap.

Giving up stays quiet and returns whatever arrived -- one ticker must not kill the run -- but the
verdict downstream is no longer a lie.

**`no_valuation_reason()` now separates three different things** that had been collapsed into one
string: a fetch gap (`data_gap=True`, "this is a data problem, not a conclusion about the company"),
a currency mismatch (a known limitation from 33.2), and a genuine business fact -- ORCL's negative
three-year FCF during the AI datacenter capex cycle *is* the answer, not a failure. It lives in
`health.py` alone and `screener.py` calls it, because those two files have already given different
answers for the same stock twice (33.3 banks, 34 ORCL), both times from the same logic existing in
two places. A test asserts they agree across every branch.

The flag rides alongside the sentence rather than replacing it: prose is for the reader, `data_gap`
is for the code (screener UI shows `⚠ ดึงข้อมูลไม่สำเร็จ` instead of "ประเมินราคาไม่ได้").

Verified live: **MA now scores 9.91/11** with no gap, while **ORCL stays partial at 4.8/8 with
`data_gap=False`** and its real reason intact -- the two cases are finally distinguishable.

- 14 new offline tests (fake `Ticker`, no network): thin response retried until whole, a new object
  built per attempt, exceptions on one attempt not stopping the next, quiet surrender returning what
  it has, the attempt count respected, the canary pinned, and each reason branch named correctly with
  health and screener agreeing on all of them. Suite 516/516.

## Phase 40 -- the same gap, in the unit the owner actually trades in

`gap +14.8pp` is a number nobody feels. "The market is asking 67% more than our own growth estimate
supports" is the identical information, and it lands. This phase is a **unit conversion, not a new
signal** -- the project does not call timing, and nothing here does either.

**The inversion is easier than the thing it inverts.** `reverse_dcf` solves "given EV, what growth
is priced in?" by bisection. Going the other way just substitutes our growth into
`intrinsic_value()` -- the same function that produces the score -- and reads EV off the other side.
No second formula, so the fair price cannot drift from the score. A test asserts the round trip:
feed the fair market cap back into `implied_growth_rate` and you get `realistic_growth` returned.

**It reports a ratio, not a price per share.** Phase 39 had just proved that MA's `Diluted Shares`
(971M, weighted average) differs from actual shares outstanding (883.58M) by 9.9% -- dividing by it
would have produced a silently wrong dollar figure. `discount_pct` needs no share count at all, and
the caller, which already knows today's price, multiplies back exactly.

**Sensitivity is not an optional extra here, it is the guard rail.** A 10-year DCF amplifies a growth
disagreement geometrically, so the price number is far more fragile than the growth number it comes
from -- and Phases 35, 36 and 38 were spent proving how fragile that growth input is. Every fair
value therefore ships with a ±3pp band and `pct_per_pp`, one number for "how much should you trust
the number next to it": **DUOL moves 15.2% per point of growth, AAPL 2.5%** -- six times the
fragility behind two figures that look equally precise. The UI puts them in one box for that reason;
a lone price figure reads as a target.

**Banks get their own, rather than a hole.** They use justified P/B, not DCF, and `justified_pb / pb`
*is* the ratio directly -- no share count, no book value per share. Sensitivity is quoted per point of
ROTCE, the unit that means something for a bank. Skipping this is how the whole sector vanished from
the screener in 33.3.

**The absolute level is not calibrated, and the docstring says so.** Measured across six names it is
negative every time (AAPL −67% … JPM −10%), because our anchors are systematically more conservative
than what the market prices. What can be read is the *cross-sectional* comparison and the
sensitivity -- AAPL at −67% / 2.5%/pp is a far sturdier statement than CVX at −28% / 6.2%/pp, which
is the opposite of what the headline figures suggest.

Surfaced on the ticker page (with band, sensitivity and the "not a target price" tooltip) and as a
screener column -- where comparing forty names at once is what makes it useful. **Deliberately not a
sort key:** ranking by discount would be manufacturing a buy signal, so the ordering stays on
quality score and this rides alongside as data.

- 14 new offline tests: the round trip lands exactly on our growth, the same model as the score is
  reused rather than copied, a zero gap prices at exactly fair, net debt genuinely enters the
  equation, the band always straddles the estimate, sensitivity matches the band it came from, a
  longer horizon amplifies the same disagreement, and it stays silent for cash burners, for debt
  exceeding enterprise value, for an invalid Gordon model and for rows with no anchor at all --
  plus the bank lens carrying its own. Suite 530/530.

## Phase 41 -- the fragility number from Phase 40 was measuring itself

Asked how we actually *know* DUOL is six times more fragile than AAPL, I measured `pct_per_pp`
across the whole watchlist instead of trusting the story I had told about it. **It carries almost no
information that is not already in the number printed beside it.**

The elasticity of enterprise value to growth turns out to be nearly constant across every name --
6.5% to 7.7% of EV per point -- because `intrinsic_value` is *linear* in `fcf_base`, so the derivative
depends on `(wacc, growth, horizon)` and not on the company at all. What is left is arithmetic:

    pct_per_pp ≈ 7 × (fair value ÷ market cap)

Mean error 8.2%, worst 21.2% across the 12 names that compute. Since `discount_pct` **is**
`fair ÷ price − 1`, the sensitivity column was a restatement of the discount column. "DUOL is six
times more sensitive than AAPL" is true and mechanical -- DUOL's fair value is six times larger
relative to its price -- and says nothing whatsoever about which business is harder to value, which
is exactly what the word "sensitivity" invites you to conclude. A pinned test now asserts the
identity, so if the model constants ever change enough to break it, the rationale for this phase
gets re-examined instead of silently rotting.

**The real fragility is which anchor got picked, not ±1pp around the anchor already picked.** We have
several defensible ways to measure growth -- structure (`reinvestment × ROIC`) and history (FCF CAGR
short and long, revenue growth). `anchor_agreement()` re-prices the stock under each one and reports
the range *in price units*. Every candidate passes through its own family's rules first (sustainable
capped at 20%, history faded through `growth_lens_realistic`), because comparing a faded anchor to a
raw one compares two different things.

What it found, live:

| | discount | `pct_per_pp` | range across anchors |
|---|---|---|---|
| MA | −23% | 6.1 | **−30% … −19%** (every method agrees, 8.1–9.9%) |
| MSFT | −27% | 5.4 | **−74% … −27%** (structure 17.2%, FCF history 3.3–5.0%) |
| DUOL | +121% | 15.3 | **−56% … +121%** |
| TSLA | −96% | 0.2 | **−97% … −96%** |

MA has the *higher* `pct_per_pp` of the first pair and the sturdiest number on the board; MSFT's
−27% rests entirely on believing that reinvestment converts to growth at ROIC, which is defensible
but is a modelling choice, not a measurement. The old column ranked those two backwards.

**Two things it says out loud that the honest version requires:**

- **The chosen anchor is the most generous of the candidates in 11 of 13 names.** Not a bug --
  `reinvestment × ROIC` *should* exceed an FCF CAGR that growth capex is suppressing, by definition
  -- but it means the discount on screen is the best edge of the range, not its middle.
- **Narrow is not always agreement.** NVDA's three history anchors say 193.9%, 65.5% and 100.1% per
  year -- different planets -- yet all three hit `CAP_INITIAL_GROWTH` (35%) and fade out to *exactly*
  18.29%, collapsing the range to 10.7pp. That narrowness is a property of our own rules, not
  evidence about NVDA, and unflagged it would make the display most confident precisely where it
  should be most careful. `narrow_by_cap` catches it; DUOL, whose width is real, is correctly not
  flagged.

Anchors the guard already rejected stay in the list, marked `rejected`, rather than being hidden --
dropping the candidates we dislike is how a number gets made to look sturdier than it is. The range
is an **upper bound on uncertainty**, and labelled as one; it is not a confidence interval, and we
have no distribution to claim one from.

Screener swaps the redundant `±%/pp` sub-line for `±Npp ตามวิธีวัด`, colour-coded, never green when
narrowness came from the cap. Ticker page lists every candidate with its growth, its resulting
discount, and which one is live.

- 18 new offline tests, plus one that pins the `7 × (fair ÷ price)` finding itself. Suite 548/548.

## Guardrails (always)
- Analysis to help *me* decide — never "buy/sell" calls
- Research tool, not investment advice
- Summarize / alert only — never auto-execute trades

## Reference files
- `PROJECT.md`, `rules.md`, `remote_roadmap_12month.md` — my trade-discipline project and
  12-month remote plan. This agent is the "AI agent" portfolio piece in that roadmap.
