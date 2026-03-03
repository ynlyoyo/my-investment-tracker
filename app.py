import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.express as px
import plotly.graph_objects as go
import numpy as np
import os

# --- CONFIG & PERSISTENCE ---
st.set_page_config(page_title="Portfolio Snapshot", layout="wide")
DATA_FILE = "my_portfolio.csv"

def load_data():
    if os.path.exists(DATA_FILE):
        return pd.read_csv(DATA_FILE)
    return pd.DataFrame(columns=['Ticker', 'Category', 'Shares', 'Cost Basis'])

def save_data(df):
    df.to_csv(DATA_FILE, index=False)

if 'portfolio' not in st.session_state:
    st.session_state.portfolio = load_data()

# --- SIDEBAR: INPUT & DATA MGMT ---
with st.sidebar:
    st.header("📋 Manage Assets")
    ticker = st.text_input("Ticker (e.g., VTI, AAPL)").upper()
    category = st.selectbox("Category", ["Stock", "ETF", "Bond/Fund", "Cash"])
    shares = st.number_input("Shares", min_value=0.0, step=0.1)
    cost = st.number_input("Avg Cost", min_value=0.0)
    
    if st.button("Add to Portfolio"):
        new_row = pd.DataFrame([[ticker, category, shares, cost]], columns=st.session_state.portfolio.columns)
        st.session_state.portfolio = pd.concat([st.session_state.portfolio, new_row], ignore_index=True)
        save_data(st.session_state.portfolio)
        st.success(f"Added {ticker}")

    st.markdown("---")
    st.header("💾 Data Operations")
    if st.button("Save to Disk"):
        save_data(st.session_state.portfolio)
        st.toast("Portfolio saved!")
    
    # File Uploader to restore data if cloud resets
    uploaded_file = st.file_uploader("Upload portfolio.csv", type="csv")
    if uploaded_file:
        st.session_state.portfolio = pd.read_csv(uploaded_file)
        save_data(st.session_state.portfolio)

# --- MAIN APP LOGIC ---
st.title("📈 Portfolio Snapshot Visualizer")

if not st.session_state.portfolio.empty:
    df = st.session_state.portfolio.copy()
    
    # Fetch Prices
    tickers_to_fetch = df[df['Category'] != 'Cash']['Ticker'].unique().tolist()
    with st.spinner('Fetching market data...'):
        data = yf.download(tickers_to_fetch + ['^GSPC'], period="1y")['Close']
    
    current_prices = data.iloc[-1]
    df['Current Price'] = df.apply(lambda x: current_prices[x['Ticker']] if x['Category'] != 'Cash' else 1.0, axis=1)
    df['Total Value'] = df['Shares'] * df['Current Price']
    total_port_value = df['Total Value'].sum()
    df['Weight'] = df['Total Value'] / total_port_value

    # TABS
    tab_summary, tab_risk, tab_rebalance = st.tabs(["📊 Summary", "🛡️ Risk", "⚖️ Rebalance"])

    with tab_summary:
        col1, col2 = st.columns([1, 1])
        with col1:
            fig_pie = px.pie(df, values='Total Value', names='Category', hole=0.5, title="Allocation by Category")
            st.plotly_chart(fig_pie, use_container_width=True)
        with col2:
            returns = data.pct_change().dropna()
            port_daily_ret = returns[tickers_to_fetch].mul(df.set_index('Ticker')['Weight'], axis=1).sum(axis=1)
            cum_port = (1 + port_daily_ret).cumprod() * 100
            cum_mkt = (1 + returns['^GSPC']).cumprod() * 100
            
            fig_perf = go.Figure()
            fig_perf.add_trace(go.Scatter(x=cum_port.index, y=cum_port, name='Portfolio'))
            fig_perf.add_trace(go.Scatter(x=cum_mkt.index, y=cum_mkt, name='S&P 500', line=dict(dash='dash')))
            fig_perf.update_layout(title="Performance vs Benchmark (Growth of $100)")
            st.plotly_chart(fig_perf, use_container_width=True)
        
        st.dataframe(df.drop(columns=['Weight']), use_container_width=True)

    with tab_risk:
        st.subheader("Risk Analytics")
        p_vol = port_daily_ret.std() * np.sqrt(252)
        m_vol = returns['^GSPC'].std() * np.sqrt(252)
        beta = np.cov(port_daily_ret, returns['^GSPC'])[0][1] / returns['^GSPC'].var()
        
        r_col1, r_col2, r_col3 = st.columns(3)
        r_col1.metric("Ann. Volatility", f"{p_vol:.2%}")
        r_col2.metric("Market Volatility", f"{m_vol:.2%}")
        r_col3.metric("Portfolio Beta (β)", f"{beta:.2f}")

    with tab_rebalance:
        st.subheader("Target vs Actual")
        t_col1, t_col2, t_col3, t_col4 = st.columns(4)
        targets = {
            "Stock": t_col1.number_input("Target Stock %", 0, 100, 40) / 100,
            "ETF": t_col2.number_input("Target ETF %", 0, 100, 30) / 100,
            "Bond/Fund": t_col3.number_input("Target Bond %", 0, 100, 20) / 100,
            "Cash": t_col4.number_input("Target Cash %", 0, 100, 10) / 100
        }
        
        rebal_list = []
        actual_grp = df.groupby('Category')['Total Value'].sum()
        for cat, t_pct in targets.items():
            actual_v = actual_grp.get(cat, 0)
            target_v = total_port_value * t_pct
            diff = target_v - actual_v
            rebal_list.append({"Category": cat, "Actual %": f"{actual_v/total_port_value:.1%}", "Action": "BUY" if diff > 0 else "SELL", "Amount": abs(diff)})
        
        st.table(pd.DataFrame(rebal_list))

else:
    st.info("Please add assets in the sidebar to begin.")