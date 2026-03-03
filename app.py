import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.express as px
import plotly.graph_objects as go
import numpy as np
import os
from datetime import datetime

# --- CONFIG & PERSISTENCE ---
st.set_page_config(page_title="Portfolio Snapshot Pro", layout="wide")
DATA_FILE = "my_portfolio.csv"

def load_data():
    required_cols = ['Ticker', 'Category', 'Shares', 'Cost Basis', 'Manual Price']
    if os.path.exists(DATA_FILE):
        try:
            df = pd.read_csv(DATA_FILE)
            for col in required_cols:
                if col not in df.columns:
                    df[col] = np.nan
            return df[required_cols]
        except:
            return pd.DataFrame(columns=required_cols)
    return pd.DataFrame(columns=required_cols)

def save_data(df):
    df.to_csv(DATA_FILE, index=False)

if 'portfolio' not in st.session_state:
    st.session_state.portfolio = load_data()

st.title("📈 Investment Portfolio Visualizer")

# --- 1. DATA MANAGEMENT ---
st.header("📋 Portfolio Management")
edited_df = st.data_editor(
    st.session_state.portfolio,
    num_rows="dynamic",
    column_config={
        "Category": st.column_config.SelectboxColumn("Category", options=["Stock", "ETF", "Bond/Fund", "Cash"]),
        "Manual Price": st.column_config.NumberColumn("Manual Price ($)"),
        "Shares": st.column_config.NumberColumn("Shares"),
        "Cost Basis": st.column_config.NumberColumn("Avg Cost ($)")
    },
    use_container_width=True,
    key="portfolio_editor"
)

if st.button("💾 Save Changes & Refresh Prices"):
    for col in ['Shares', 'Cost Basis', 'Manual Price']:
        edited_df[col] = pd.to_numeric(edited_df[col], errors='coerce').fillna(0)
    st.session_state.portfolio = edited_df
    save_data(edited_df)
    st.rerun()

# --- 2. PRICE ENGINE ---
if not st.session_state.portfolio.empty:
    df = st.session_state.portfolio.copy()
    for col in ['Shares', 'Cost Basis', 'Manual Price']:
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
    
    api_tickers = df[(df['Category'] != 'Cash') & (df['Ticker'].notna()) & (df['Ticker'] != "")]['Ticker'].unique().tolist()
    current_prices = {}
    last_update = "N/A"
    
    if api_tickers:
        with st.spinner('Fetching market prices...'):
            try:
                price_data = yf.download(api_tickers + ['^GSPC'], period="1d", interval="1m")['Close']
                for ticker in api_tickers:
                    ticker_series = price_data[ticker].dropna()
                    if not ticker_series.empty:
                        current_prices[str(ticker).upper().strip()] = ticker_series.iloc[-1]
                last_update = datetime.now().strftime("%H:%M:%S")
            except:
                st.warning("⚠️ Market data API busy. Using Manual/Fallback prices.")

    def get_final_price(row):
        if row['Category'] == 'Cash': return 1.0
        tick = str(row['Ticker']).upper().strip()
        api_val = current_prices.get(tick)
        if pd.notna(api_val): return float(api_val)
        if pd.notna(row['Manual Price']) and row['Manual Price'] != 0: return float(row['Manual Price'])
        return None

    df['Current Price'] = df.apply(get_final_price, axis=1)
    st.markdown(f"**Last Refresh:** `{last_update}`")

    df_calc = df.dropna(subset=['Current Price']).copy()

    if not df_calc.empty:
        df_calc['Total Value'] = df_calc['Shares'] * df_calc['Current Price']
        total_val = df_calc['Total Value'].sum()
        df_calc['Weight'] = df_calc['Total Value'] / total_val if total_val > 0 else 0

        tab1, tab2, tab3 = st.tabs(["📊 Performance Summary", "🛡️ Risk Analytics", "⚖️ Rebalance"])

        with tab1:
            m1, m2 = st.columns(2)
            m1.metric("Total Value", f"${total_val:,.2f}")
            t_gl = ((df_calc['Current Price'] - df_calc['Cost Basis']) * df_calc['Shares']).sum()
            m2.metric("Total Gain/Loss", f"${t_gl:,.2f}", delta=f"{(t_gl/total_val)*100:.2f}%" if total_val > 0 else "0%")

            # --- DETAILED CATEGORY PIE CHARTS ---
            st.subheader("Category Distribution")
            categories = ["Stock", "ETF", "Bond/Fund", "Cash"]
            cols = st.columns(len(categories))
            
            for i, cat in enumerate(categories):
                cat_df = df_calc[df_calc['Category'] == cat]
                with cols[i]:
                    if not cat_df.empty:
                        fig = px.pie(cat_df, values='Total Value', names='Ticker', 
                                     title=f"{cat} Distribution", hole=0.3)
                        fig.update_layout(showlegend=False, margin=dict(l=20, r=20, t=40, b=20))
                        st.plotly_chart(fig, use_container_width=True)
                    else:
                        st.caption(f"No {cat} assets")

            # --- PERFORMANCE TABLE ---
            st.subheader("Portfolio Performance Details")
            # Format the display table
            display_df = df_calc[['Ticker', 'Category', 'Shares', 'Current Price', 'Total Value']].copy()
            st.dataframe(
                display_df.style.format({
                    'Shares': '{:,.2f}',
                    'Current Price': '${:,.2f}',
                    'Total Value': '${:,.2f}'
                }),
                use_container_width=True
            )

        with tab2:
            st.subheader("Risk Analytics")
            if len(api_tickers) > 0:
                try:
                    hist = yf.download(api_tickers + ['^GSPC'], period="1y")['Close'].pct_change().dropna()
                    valid_t = [t for t in api_tickers if t in hist.columns]
                    if valid_t and '^GSPC' in hist.columns:
                        port_ret = hist[valid_t].mul(df_calc[df_calc['Ticker'].isin(valid_t)].set_index('Ticker')['Weight'], axis=1).sum(axis=1)
                        vol = port_ret.std() * np.sqrt(252)
                        beta = np.cov(port_ret, hist['^GSPC'])[0][1] / hist['^GSPC'].var()
                        r1, r2 = st.columns(2)
                        r1.metric("Volatility", f"{vol:.2%}")
                        r2.metric("Beta (β)", f"{beta:.2f}")
                except:
                    st.write("Fetching historical risk data...")

        with tab3:
            st.subheader("Rebalance Instructions")
            # ... (Rebalance logic remains same) ...
            t_cols = st.columns(4)
            targets = {
                "Stock": t_cols[0].number_input("Stock Target %", 0, 100, 40) / 100,
                "ETF": t_cols[1].number_input("ETF Target %", 0, 100, 30) / 100,
                "Bond/Fund": t_cols[2].number_input("Bond Target %", 0, 100, 20) / 100,
                "Cash": t_cols[3].number_input("Cash Target %", 0, 100, 10) / 100
            }
            actuals = df_calc.groupby('Category')['Total Value'].sum()
            re_data = []
            for c, t_p in targets.items():
                a_v = actuals.get(c, 0)
                diff = (total_val * t_p) - a_v
                re_data.append({"Category": c, "Action": "BUY" if diff > 0 else "SELL", "Amount": f"${abs(diff):,.2f}"})
            st.table(pd.DataFrame(re_data))
else:
    st.info("Start by entering your portfolio data in the management table above.")