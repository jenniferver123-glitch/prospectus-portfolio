"""
portfolio.py - the calculation engine of the app.

Everything that produces a number lives here, and nothing in this file knows
about Streamlit. That separation is deliberate:
  * the formulas are the SAME as in our Colab notebook (backtest loop,
    performance measures), so the app and the prospectus cannot drift apart;
  * the engine can be tested on its own (see the check at the bottom).
"""
import numpy as np
import pandas as pd
import yfinance as yf

# ---------------------------------------------------------------------------
# Universe
# ---------------------------------------------------------------------------
ASSETS = {
    'IVV': 'US equities (S&P 500)',
    'EFA': 'Developed ex-US equities',
    'EEM': 'Emerging-market equities',
    'AGG': 'US investment-grade bonds',
    'GLD': 'Gold',
}
EQUITIES = ['IVV', 'EFA', 'EEM']
BENCHMARK = 'ACWI'

# our strategy (the one in the prospectus)
STRATEGY_WEIGHTS = {'IVV': 0.50, 'EFA': 0.20, 'EEM': 0.10, 'AGG': 0.15, 'GLD': 0.05}

FRED_URL = 'https://fred.stlouisfed.org/graph/fredgraph.csv?id=TB3MS'

REBALANCE_SCHEDULES = {
    'Annual (every December)': [12],
    'Semi-annual (June, December)': [6, 12],
    'Quarterly': [3, 6, 9, 12],
    'Monthly': list(range(1, 13)),
    'Never (buy and hold)': [],
}


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------
def load_prices(start, end):
    """Monthly dividend-adjusted month-end prices from Yahoo Finance."""
    tickers = list(ASSETS) + [BENCHMARK]
    data = yf.download(tickers, start=start, end=end, interval='1mo',
                       auto_adjust=True, progress=False)
    prices = data['Close'][tickers]
    prices.index = pd.to_datetime(prices.index).tz_localize(None)
    return prices.dropna(how='all')


def load_risk_free(index):
    """3-month T-bill (FRED: TB3MS), % per year -> decimal per month, aligned to `index`."""
    rf = pd.read_csv(FRED_URL, index_col=0, parse_dates=True).iloc[:, 0]
    rf = pd.to_numeric(rf, errors='coerce') / 100 / 12
    # forward-fill only if the latest month has not been published yet
    return rf.reindex(index).ffill()


# ---------------------------------------------------------------------------
# Backtest  (identical to the notebook when band=None)
# ---------------------------------------------------------------------------
def backtest(asset_rets, weights, rebalance_months, tc, band=None):
    """
    Track the dollar value held in each asset month by month.
    - holdings drift with each asset's own return;
    - at the close of a rebalancing month (or, if `band` is set, whenever any
      weight is more than `band` away from its target) we trade back to the
      target weights and pay `tc` x (fraction of the portfolio traded).
    Decisions use only month-end prices that are already known -> no look-ahead.
    """
    weights = np.asarray(weights, dtype=float)
    holdings = weights * 1.0
    port_rets, turnover, weights_hist = [], [], []

    for date, r in asset_rets.iterrows():
        value_start = holdings.sum()
        holdings = holdings * (1 + r.values)
        value_end = holdings.sum()
        current_w = holdings / value_end
        weights_hist.append(current_w)

        scheduled = date.month in rebalance_months
        drifted = band is not None and np.abs(current_w - weights).max() > band
        traded = 0.0
        if scheduled or drifted:
            target = weights * value_end
            traded = np.abs(target - holdings).sum() / value_end
            value_end = value_end * (1 - tc * traded)
            holdings = weights * value_end

        port_rets.append(value_end / value_start - 1)
        turnover.append(traded)

    port_rets = pd.Series(port_rets, index=asset_rets.index, name='strategy')
    turnover = pd.Series(turnover, index=asset_rets.index, name='turnover')
    weights_hist = pd.DataFrame(weights_hist, index=asset_rets.index, columns=asset_rets.columns)
    return port_rets, weights_hist, turnover


# ---------------------------------------------------------------------------
# Performance measures (identical to the notebook)
# ---------------------------------------------------------------------------
def drawdown(r):
    wealth = (1 + r).cumprod()
    return wealth / np.maximum(wealth.cummax(), 1) - 1


def performance(r, bench, rf):
    ex = r - rf
    ex_b = bench - rf
    beta = np.cov(ex, ex_b)[0, 1] / np.var(ex_b, ddof=1)
    alpha_m = ex.mean() - beta * ex_b.mean()
    resid = ex - alpha_m - beta * ex_b
    wealth = (1 + r).cumprod()
    return pd.Series({
        'Annualized average return': 12 * r.mean(),
        'Annualized volatility': np.sqrt(12) * r.std(),
        'Sharpe ratio': 12 * ex.mean() / (np.sqrt(12) * ex.std()),
        'Beta': beta,
        'Alpha (annualized)': 12 * alpha_m,
        'Information ratio': 12 * alpha_m / (np.sqrt(12) * resid.std()) if resid.std() > 1e-12 else np.nan,
        'CAGR': wealth.iloc[-1] ** (12 / len(r)) - 1,
        'Maximum drawdown': drawdown(r).min(),
        'Final value of $1': wealth.iloc[-1],
    })


def savings_plan(r, initial=0.0, monthly=300.0):
    """Value path of a plan that invests `initial` at the start and `monthly` at each month-end."""
    value, path = float(initial), []
    for ret in r:
        value = value * (1 + ret) + monthly
        path.append(value)
    return pd.Series(path, index=r.index)


# ---------------------------------------------------------------------------
# Self-check: with monthly rebalancing and no costs the loop must equal w @ r
# ---------------------------------------------------------------------------
def self_check(asset_rets, weights):
    r, _, _ = backtest(asset_rets, weights, list(range(1, 13)), 0.0)
    return float(np.abs(r - asset_rets @ np.asarray(weights)).max())
