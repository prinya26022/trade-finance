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
  fundamental leg, not tuning individual valuation constants.

Remaining (beyond the audit roadmap): deeper crypto on-chain metrics (active addresses, fees, TVL),
macro/rates valuation context beyond CAPM WACC, triggering investigation/narration from the UI,
cyclical-industry normalization. (Bank/insurance alt framework and the predictive backtest are now
folded into Phase 20 below.)

## Phase 20 -- planning (fit the tool to how I actually use it)
NOT STARTED -- planning only, nothing here implemented.

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

## Guardrails (always)
- Analysis to help *me* decide — never "buy/sell" calls
- Research tool, not investment advice
- Summarize / alert only — never auto-execute trades

## Reference files
- `PROJECT.md`, `rules.md`, `remote_roadmap_12month.md` — my trade-discipline project and
  12-month remote plan. This agent is the "AI agent" portfolio piece in that roadmap.
