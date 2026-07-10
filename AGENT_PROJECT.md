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
Remaining: deeper crypto on-chain metrics (active addresses, fees, TVL), macro/rates valuation
context, deeper equity valuation (reverse-DCF), extending XBRL coverage beyond margins/ROE.

## Guardrails (always)
- Analysis to help *me* decide — never "buy/sell" calls
- Research tool, not investment advice
- Summarize / alert only — never auto-execute trades

## Reference files
- `PROJECT.md`, `rules.md`, `remote_roadmap_12month.md` — my trade-discipline project and
  12-month remote plan. This agent is the "AI agent" portfolio piece in that roadmap.
