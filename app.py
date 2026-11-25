"""
app.py - Streamlit front end for the "Global Growth 80/15/5" retirement portfolio.

Run locally:   streamlit run app.py
All calculations come from portfolio.py (same formulas as the Colab notebook).
"""
from datetime import date

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import portfolio as pf

st.set_page_config(page_title='Global Growth 80/15/5 - backtest', page_icon='📈', layout='wide')

BLUE, ORANGE, GREY = '#1f4e79', '#c55a11', '#8c8c8c'
DATA_START = '2008-03-01'                       # ACWI (benchmark) launched 26 March 2008
PROSPECTUS_END = pd.Timestamp('2026-10-01')     # last month used in the prospectus


# ---------------------------------------------------------------------------
# 1. Data: downloaded once and cached for 12 hours.
#    Every slider change re-runs the script, so without caching we would hit
#    Yahoo and FRED on every click (slow, and Yahoo rate-limits).
# ---------------------------------------------------------------------------
@st.cache_data(ttl=12 * 3600, show_spinner='Downloading prices from Yahoo Finance and FRED...')
def load_data():
    end = (pd.Timestamp.today().normalize().replace(day=1)).strftime('%Y-%m-%d')  # only complete months
    prices = pf.load_prices(DATA_START, end)
    rf = pf.load_risk_free(prices.index)
    return prices, rf


try:
    prices_all, rf_all = load_data()
except Exception as e:  # network problems should produce a message, not a stack trace
    st.error(f'Could not download the data ({e}). Please reload the page in a minute.')
    st.stop()

months = list(prices_all.index)


# ---------------------------------------------------------------------------
# 2. Sidebar: the assumptions the user can change
# ---------------------------------------------------------------------------
st.sidebar.title('Your assumptions')

st.sidebar.subheader('1. Portfolio mix')
mode = st.sidebar.radio('How do you want to set the weights?',
                        ['Equity share (simple)', 'Custom weight per ETF'], index=0,
                        help='The simple mode keeps the regional split of our strategy and only changes '
                             'how much is in equities versus bonds and gold.')

if mode == 'Equity share (simple)':
    equity = st.sidebar.slider('Equities (%)', 0, 100, 80, 5,
                               help='Our strategy uses 80%. Within equities: 62.5% US, 25% developed ex-US, '
                                    '12.5% emerging. The rest goes 3:1 into bonds and gold.') / 100
    w = {'IVV': 0.625 * equity, 'EFA': 0.25 * equity, 'EEM': 0.125 * equity,
         'AGG': 0.75 * (1 - equity), 'GLD': 0.25 * (1 - equity)}
else:
    w = {}
    for t, name in pf.ASSETS.items():
        w[t] = st.sidebar.number_input(f'{t} - {name} (%)', 0.0, 100.0,
                                       pf.STRATEGY_WEIGHTS[t] * 100, 5.0) / 100
    total = sum(w.values())
    if total == 0:
        st.sidebar.error('Please give at least one ETF a positive weight.')
        st.stop()
    if abs(total - 1) > 1e-9:
        st.sidebar.warning(f'Weights add up to {total:.0%}; they are rescaled to 100%.')
        w = {t: v / total for t, v in w.items()}
weights = np.array([w[t] for t in pf.ASSETS])

st.sidebar.subheader('2. Rebalancing and costs')
schedule = st.sidebar.selectbox('Rebalancing schedule', list(pf.REBALANCE_SCHEDULES), index=0)
use_band = st.sidebar.checkbox('Also rebalance when a weight drifts too far', value=False,
                               help='Threshold rebalancing: at any month-end, trade back to target if any '
                                    'ETF is more than the band away from its target weight.')
band = st.sidebar.slider('Tolerance band (percentage points)', 1, 15, 5) / 100 if use_band else None
tc = st.sidebar.slider('Transaction cost (% of amount traded)', 0.0, 1.0, 0.10, 0.05) / 100

st.sidebar.subheader('3. Benchmark and period')
bench_choice = st.sidebar.radio('Benchmark', ['MSCI ACWI (100% global equities)',
                                              '60/40: ACWI / AGG (rebalanced monthly)'])
default_end = PROSPECTUS_END if PROSPECTUS_END in months else months[-1]
start_m, end_m = st.sidebar.select_slider(
    'Sample period (month-end prices)', options=months, value=(months[0], default_end),
    format_func=lambda d: d.strftime('%b %Y'))

st.sidebar.subheader('4. Savings plan')
initial = st.sidebar.number_input('Initial investment ($)', 0, 1_000_000, 0, 1000)
monthly = st.sidebar.number_input('Monthly contribution ($)', 0, 50_000, 300, 50)


# ---------------------------------------------------------------------------
# 3. Calculations (all in portfolio.py)
# ---------------------------------------------------------------------------
prices = prices_all.loc[start_m:end_m]
returns = prices.pct_change().dropna()
if len(returns) < 36:
    st.warning('Please choose a sample of at least 3 years (36 months) so that the statistics mean something.')
    st.stop()

asset_rets = returns[list(pf.ASSETS)]
rf = rf_all.loc[returns.index]
if bench_choice.startswith('MSCI'):
    bench = returns[pf.BENCHMARK]
    bench_name = 'MSCI ACWI'
else:
    bench = 0.6 * returns[pf.BENCHMARK] + 0.4 * returns['AGG']
    bench_name = '60/40 ACWI/AGG'

strat, w_hist, turnover = pf.backtest(asset_rets, weights, pf.REBALANCE_SCHEDULES[schedule], tc, band)
perf_s = pf.performance(strat, bench, rf)
perf_b = pf.performance(bench, bench, rf)

# reference: our prospectus strategy over the same period, for comparison
ref_w = np.array([pf.STRATEGY_WEIGHTS[t] for t in pf.ASSETS])
ref, _, _ = pf.backtest(asset_rets, ref_w, [12], 0.001)
perf_ref = pf.performance(ref, bench, rf)


# ---------------------------------------------------------------------------
# 4. Page
# ---------------------------------------------------------------------------
st.title('Global Growth 80/15/5: a retirement portfolio for investors in their 30s')
st.caption(f'Backtest {returns.index[0]:%b %Y} – {returns.index[-1]:%b %Y} ({len(returns)} months), '
           f'monthly total returns in USD. Benchmark: {bench_name}. '
           'With the default settings the numbers match our prospectus.')

mix = ' · '.join(f'{t} {v:.0%}' for t, v in zip(pf.ASSETS, weights) if v > 0)
st.markdown(f'**Your portfolio:** {mix}  |  **Rebalancing:** {schedule}'
            + (f' + {band:.0%} band' if band else '') + f'  |  **Cost:** {tc:.2%} per trade')

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric('Growth of $1', f"{perf_s['Final value of $1']:.2f}",
          f"{perf_s['Final value of $1'] - perf_b['Final value of $1']:+.2f} vs benchmark")
c2.metric('CAGR', f"{perf_s['CAGR']:.2%}", f"{(perf_s['CAGR'] - perf_b['CAGR']) * 100:+.2f} pp")
c3.metric('Volatility', f"{perf_s['Annualized volatility']:.2%}",
          f"{(perf_s['Annualized volatility'] - perf_b['Annualized volatility']) * 100:+.2f} pp", delta_color='inverse')
c4.metric('Sharpe ratio', f"{perf_s['Sharpe ratio']:.2f}", f"{perf_s['Sharpe ratio'] - perf_b['Sharpe ratio']:+.2f}")
c5.metric('Max drawdown', f"{perf_s['Maximum drawdown']:.1%}",
          f"{(perf_s['Maximum drawdown'] - perf_b['Maximum drawdown']) * 100:+.1f} pp")


def line_chart(df, title, yfmt=None, log=False, colors=(BLUE, ORANGE, GREY)):
    fig = go.Figure()
    for col, color in zip(df.columns, colors):
        fig.add_trace(go.Scatter(x=df.index, y=df[col], name=col, mode='lines', line=dict(color=color, width=2)))
    fig.update_layout(title=title, height=420, hovermode='x unified', legend=dict(orientation='h', y=-0.15),
                      margin=dict(l=10, r=10, t=50, b=10))
    if yfmt:
        fig.update_yaxes(tickformat=yfmt)
    if log:
        fig.update_yaxes(type='log')
    return fig


tab1, tab2, tab3, tab4, tab5 = st.tabs(['Performance', 'Risk', 'Holdings & trading', 'Savings plan',
                                        'Method & assumptions'])

with tab1:
    start_row = pd.DataFrame(1.0, index=[prices.index[0]], columns=['Your portfolio', bench_name])
    cum = pd.concat([start_row, pd.DataFrame({'Your portfolio': (1 + strat).cumprod(),
                                              bench_name: (1 + bench).cumprod()})])
    log = st.toggle('Logarithmic scale', value=False,
                    help='On a log scale equal percentage changes look equally large, which makes early years readable.')
    st.plotly_chart(line_chart(cum, 'Growth of $1 (both series start at 1)', log=log), use_container_width=True)

    table = pd.DataFrame({'Your portfolio': perf_s, bench_name: perf_b, 'Our strategy (80/15/5, annual)': perf_ref})
    pct = ['Annualized average return', 'Annualized volatility', 'Alpha (annualized)', 'CAGR', 'Maximum drawdown']
    shown = table.copy().astype(object)
    for row in table.index:
        shown.loc[row] = ['n/a' if pd.isna(v) else (f'{v:.2%}' if row in pct else f'{v:.2f}') for v in table.loc[row]]
    st.subheader('Performance measures')
    st.dataframe(shown, use_container_width=True)
    st.caption('Sharpe ratio, alpha and information ratio use excess returns over the 3-month T-bill (FRED: TB3MS). '
               'Alpha and beta come from regressing excess returns on the benchmark\'s excess returns; '
               'alpha is annualized x12, beta is not annualized. IR = annualized alpha / annualized residual volatility.')

    yearly = pd.DataFrame({'Your portfolio': (1 + strat).groupby(strat.index.year).prod() - 1,
                           bench_name: (1 + bench).groupby(bench.index.year).prod() - 1})
    fig = go.Figure([go.Bar(x=yearly.index, y=yearly[c], name=c, marker_color=col)
                     for c, col in zip(yearly.columns, [BLUE, ORANGE])])
    fig.update_layout(title='Calendar-year returns (first and last year are partial)', barmode='group',
                      height=380, yaxis_tickformat='.0%', legend=dict(orientation='h', y=-0.15),
                      margin=dict(l=10, r=10, t=50, b=10))
    st.plotly_chart(fig, use_container_width=True)

with tab2:
    dd = pd.DataFrame({'Your portfolio': pf.drawdown(strat), bench_name: pf.drawdown(bench)})
    st.plotly_chart(line_chart(dd, 'Drawdown: loss from the previous peak', yfmt='.0%'), use_container_width=True)
    worst = dd['Your portfolio'].idxmin()
    st.markdown(f"Worst loss of your portfolio: **{dd['Your portfolio'].min():.1%}** (trough in {worst:%B %Y}). "
                f"Ask yourself honestly: would you have kept saving through that?")
    if len(strat) >= 72:
        ex_s, ex_b = strat - rf, bench - rf
        rb = (ex_s.rolling(60).cov(ex_b) / ex_b.rolling(60).var()).dropna().to_frame('Rolling 60-month beta')
        st.plotly_chart(line_chart(rb, f'Rolling 60-month beta vs {bench_name}'), use_container_width=True)
    else:
        st.info('Choose a period of at least 6 years to see the rolling 60-month beta.')

with tab3:
    fig = go.Figure()
    for t, col in zip(pf.ASSETS, ['#1f4e79', '#5b9bd5', '#9dc3e6', '#a9d18e', '#ffc000']):
        fig.add_trace(go.Scatter(x=w_hist.index, y=w_hist[t], name=t, stackgroup='one', mode='none', fillcolor=col))
    fig.update_layout(title='Portfolio weights at each month-end (before rebalancing)', height=420,
                      yaxis_tickformat='.0%', legend=dict(orientation='h', y=-0.15), margin=dict(l=10, r=10, t=50, b=10))
    st.plotly_chart(fig, use_container_width=True)

    n_years = len(turnover) / 12
    a, b, c = st.columns(3)
    a.metric('Rebalancing trades', int((turnover > 0).sum()))
    b.metric('Turnover per year', f'{turnover.sum() / n_years:.1%}')
    c.metric('Cost drag per year', f'{tc * turnover.sum() / n_years:.3%}')
    st.caption('Turnover = value bought + value sold, as a fraction of the portfolio. '
               'The cost drag ignores bid-ask spreads beyond the cost you entered, taxes and FX conversion costs.')

with tab4:
    plan_s = pf.savings_plan(strat, initial, monthly)
    plan_b = pf.savings_plan(bench, initial, monthly)
    paid = pd.Series(initial + monthly * np.arange(1, len(strat) + 1), index=strat.index)
    plan = pd.DataFrame({'Your portfolio': plan_s, bench_name: plan_b, 'Money paid in': paid})
    st.plotly_chart(line_chart(plan, 'Value of the savings plan ($)'), use_container_width=True)
    a, b, c = st.columns(3)
    a.metric('Money paid in', f'${paid.iloc[-1]:,.0f}')
    b.metric('Your portfolio at the end', f'${plan_s.iloc[-1]:,.0f}')
    c.metric(f'{bench_name} at the end', f'${plan_b.iloc[-1]:,.0f}')
    st.caption('Contributions are invested at each month-end, after that month\'s return. No taxes, no inflation adjustment.')

with tab5:
    st.markdown("""
**Data.** Monthly month-end prices from Yahoo Finance (`yfinance`, `auto_adjust=True`: adjusted for splits and
dividends, so returns are total returns, net of ETF fees). Risk-free rate: 3-month US T-bill (FRED `TB3MS`),
converted to a monthly rate. Prices are cached for 12 hours.

**Backtest.** The value held in each ETF grows with its own return. On a rebalancing date (month-end close),
the portfolio is traded back to the target weights and pays *cost × amount traded*. Decisions use only
prices already known at that close, so there is no look-ahead bias.

**Measures.** Simple monthly returns. Average return ×12, volatility ×√12, Sharpe ratio on excess returns,
beta = cov/var of excess returns (not annualized), alpha annualized ×12, information ratio = alpha / residual
volatility (annualized).

**Limitations.** Results are in US dollars; a euro investor would use UCITS versions of these ETFs and bear
EUR/USD currency risk. The past 18 years were unusually good for US equities. A backtest is not a forecast.
This app is a teaching tool, not investment advice.
""")
    out = pd.DataFrame({'portfolio_return': strat, 'benchmark_return': bench, 'risk_free': rf, 'turnover': turnover})
    st.download_button('Download monthly results (CSV)', out.to_csv().encode(), 'backtest_results.csv', 'text/csv')
    st.caption(f'Self-check: monthly-rebalanced loop vs weights @ returns, max difference = '
               f'{pf.self_check(asset_rets, weights):.1e}')
