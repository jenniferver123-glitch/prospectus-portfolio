# Global Growth 80/15/5 — interactive backtest

A Streamlit app for our 2270 Financial Modeling group assignment (Nova SBE).
It backtests a long-term retirement portfolio for a retail investor in their early 30s and lets the user change the main assumptions.

* **Live app:** _[https://your-app.streamlit.app]_
* **Prospectus and notebook:** submitted on Moodle (group _[name]_)

## What the app does

The strategy holds five ETFs at fixed target weights and rebalances once a year:

| ETF | Asset class | Weight |
|---|---|---|
| IVV | US equities (S&P 500) | 50% |
| EFA | Developed-market equities ex-US | 20% |
| EEM | Emerging-market equities | 10% |
| AGG | US investment-grade bonds | 15% |
| GLD | Gold | 5% |

The user can change:

1. **the portfolio mix** — one equity-share slider (keeps our regional split), or a custom weight per ETF;
2. **the rebalancing rule** — annual, semi-annual, quarterly, monthly or never, optionally with a tolerance band;
3. **the transaction cost** per trade;
4. **the benchmark** — MSCI ACWI or a 60/40 ACWI/AGG portfolio;
5. **the sample period**;
6. **a savings plan** — initial amount plus a monthly contribution.

The app then shows growth of $1 against the benchmark (both starting at 1), the performance table (average return, volatility, Sharpe ratio, alpha, beta, information ratio, CAGR, maximum drawdown), calendar-year returns, drawdowns, the rolling 60-month beta, the weight drift and turnover, and the result of the savings plan.

With the default settings the app reproduces the numbers in our prospectus (April 2008 – October 2026).

## Run it locally

```bash
git clone https://github.com/<your-user>/<your-repo>.git
cd <your-repo>
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

The app opens at http://localhost:8501. It needs internet access (Yahoo Finance and FRED).

## Deploy on Streamlit Community Cloud

1. Push this folder to a **public** GitHub repository (`app.py`, `portfolio.py`, `requirements.txt`, `.streamlit/config.toml`, `README.md`).
2. Go to https://share.streamlit.io, sign in with GitHub, click **Create app → Deploy a public app from GitHub**.
3. Choose the repository, branch `main` and main file `app.py`, then **Deploy**.
4. Copy the app URL into this README, the prospectus and the notebook.

## Design rationale

**Two files, two jobs.** `portfolio.py` contains every calculation (data download, backtest loop, performance measures) and knows nothing about Streamlit; `app.py` only handles inputs and charts. The assignment asks that the app stays consistent with the notebook, and the simplest way to guarantee that is to copy the notebook's functions into one module and never re-implement a formula in the interface. The engine can also be tested on its own.

**The backtest tracks holdings, not weights.** Writing `weights @ returns` every month assumes monthly rebalancing at zero cost. Our investor rebalances once a year, so the loop tracks the dollar value held in each ETF, lets it drift with prices, and trades back to the targets only on rebalancing dates, paying a cost proportional to the amount traded. A built-in self-check (shown at the bottom of the *Method* tab) confirms that monthly rebalancing with zero cost gives exactly `weights @ returns`.

**No look-ahead.** Rebalancing decisions use the month-end close that has just been observed, and the new weights only earn the following months' returns. The optional tolerance band also only looks at weights that are already known.

**Caching.** Streamlit re-runs the whole script after every click. Data are therefore downloaded once and cached for 12 hours with `st.cache_data`; changing a slider only re-runs the (fast) backtest on the cached data. This keeps the app responsive and avoids Yahoo's rate limits.

**Only complete months.** The download ends at the first day of the current month, so a half-finished month never enters the statistics. The sample-period slider then works on the cached data, without new downloads.

**Simple inputs first.** Most retail users think in "how much in stocks?", not in five separate weights, so the default control is a single equity-share slider; custom weights are available and are rescaled to 100% with a warning if they do not add up.

**Guard rails.** A minimum sample of 36 months, a clear error message if the data source is unavailable, and an explicit note that results are in USD and are not investment advice.

**Plotly charts** give hover values and zoom, so users can inspect, for example, the 2008 or 2022 drawdowns month by month.

## Files

```
app.py                  Streamlit interface
portfolio.py            calculation engine (same formulas as the notebook)
requirements.txt        Python dependencies
.streamlit/config.toml  colour theme
```

## Data and disclaimer

Prices: Yahoo Finance via `yfinance` (monthly, adjusted for splits and dividends). Risk-free rate: FRED series `TB3MS`.
This app is a university project and not investment advice. Past performance does not guarantee future results.

## Use of generative AI

The app was written with the help of an AI coding assistant (Claude). The group reviewed the code, checked that the default output matches the notebook, and tested the inputs.
