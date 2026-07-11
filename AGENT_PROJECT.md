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
Remaining: deeper crypto on-chain metrics (active addresses, fees, TVL), macro/rates valuation
context beyond CAPM WACC, extending XBRL coverage beyond margins/ROE, triggering investigation/
narration from the UI, bank/insurance alternate scoring framework (FCF-based ratios don't apply),
cyclical-industry normalization.

## Guardrails (always)
- Analysis to help *me* decide — never "buy/sell" calls
- Research tool, not investment advice
- Summarize / alert only — never auto-execute trades

## Reference files
- `PROJECT.md`, `rules.md`, `remote_roadmap_12month.md` — my trade-discipline project and
  12-month remote plan. This agent is the "AI agent" portfolio piece in that roadmap.
