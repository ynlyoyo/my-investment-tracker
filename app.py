import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.express as px
import plotly.graph_objects as go
import numpy as np
import os
from datetime import datetime

# --- CONFIG & PERSISTENCE ---
st.set_page_config(page_title="Portfolio Pro", layout="wide")
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
st.info("💡 Edit cells. Use 'Manual Price' for private assets. Click 'Save & Refresh' to update.")

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
    # Force numeric conversion before saving
    for col in ['Shares', 'Cost Basis', 'Manual Price']:
        edited_df[col] = pd.to_numeric(edited_df[col], errors='coerce').fillna(0)
    st.session_state.portfolio = edited_df
    save_data(edited_df)
    st.rerun()

# --- 2. PRICE ENGINE ---
if not st.session_state.portfolio.empty:
    df = st.session_state.portfolio.copy()
    
    # Pre-clean data: ensure numbers are numbers
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
                        current_prices[str(ticker).upper()] = ticker_series.iloc[-1]
                last_update = datetime.now().strftime("%H:%M:%S")
            except:
                st.warning("⚠️ Market data feed interrupted. Check internet connection.")

    def get_final_price(row):
        if row['Category'] == 'Cash': return 1.0
        # Check API
        tick = str(row['Ticker']).upper().strip()
        api_val = current_prices.get(tick)
        if pd.notna(api_val): return float(api_val)
        # Check Manual
        if pd.notna(row['Manual Price']) and row['Manual Price'] != 0: 
            return float(row['Manual Price'])
        return None

    df['Current Price'] = df.apply(get_final_price, axis=1)
    st.markdown(f"**Last Refresh:** `{last_update}`")

    # Filter out rows missing prices
    df_calc = df.dropna(subset=['Current Price']).copy()

    if not df_calc.empty:
        try:
            # FORCE NUMERIC ONE LAST TIME
            df_calc['Shares'] = df_calc['Shares'].astype(float)
            df_calc['Current Price'] = df_calc['Current Price'].astype(float)
            
            df_calc['Total Value'] = df_calc['Shares'] * df_calc['Current Price']
            total_val = df_calc['Total Value'].sum()
            df_calc['Weight'] = df_calc['Total Value'] / total_val if total_val > 0 else 0
            df_calc['G/L'] = (df_calc['Current Price'] - df_calc['Cost Basis'].astype(float)) * df_calc['Shares']

            tab1, tab2, tab3 = st.tabs(["📊 Performance", "🛡️ Risk", "⚖️ Rebalance"])

            with tab1:
                m1, m2 = st.columns(2)
                m1.metric("Total Value", f"${total_val:,.2f}")
                t_gl = df_calc['G/L'].sum()
                m2.metric("Gain/Loss", f"${t_gl:,.2f}", delta=f"{(t_gl/total_val)*100:.2f}%" if total_val > 0 else "0%")
                
                fig_pie = px.pie(df_calc, values='Total Value', names='Category', hole=0.4)
                st.plotly_chart(fig_pie, use_container_width=True)

            with tab2:
                st.subheader("Risk Analytics")
                if len(api_tickers) > 0:
                    try:
                        hist = yf.download(api_tickers + ['^GSPC'], period="1y")['Close'].pct_change().dropna()
                        valid_t = [t for t in api_tickers if t in hist.columns]
                        if valid_t and '^GSPC' in hist.columns:
                            port_ret = hist[valid_t].mul(df_calc[df_calc['Ticker'].isin(valid_t)].set_index('Ticker')['Weight'], axis=1).sum(axis=1)
                            vol = port_ret.std() * np.sqrt(252)
                            cov = np.cov(port_ret, hist['^GSPC'])[0][1]
                            beta = cov / hist['^GSPC'].var()
                            
                            r1, r2 = st.columns(2)
                            r1.metric("Volatility", f"{vol:.2%}")
                            r2.metric("Beta (β)", f"{beta:.2f}")
                    except:
                        st.write("Insufficient historical data for risk metrics.")
                else:
                    st.write("Add Tickers to see Risk Analytics.")

            with tab3:
                st.subheader("Rebalance Instructions")
                t_cols = st.columns(4)
                targets = {
                    "Stock": t_cols[0].number_input("Stock %", 0, 100, 40) / 100,
                    "ETF": t_cols[1].number_input("ETF %", 0, 100, 30) / 100,
                    "Bond/Fund": t_cols[2].number_input("Bond %", 0, 100, 20) / 100,
                    "Cash": t_cols[3].number_input("Cash %", 0, 100, 10) / 100
                }
                
                actuals = df_calc.groupby('Category')['Total Value'].sum()
                re_data = []
                for c, t_p in targets.items():
                    a_v = actuals.get(c, 0)
                    diff = (total_val * t_p) - a_v
                    re_data.append({"Category": c, "Target %": f"{t_p:.0%}", "Action": "BUY" if diff > 0 else "SELL", "Amount": f"${abs(diff):,.2f}"})
                st.table(pd.DataFrame(re_data))
        except Exception as e:
            st.error(f"Calculation Error: {e}. Please check that all 'Shares' and 'Prices' are numbers.")
    else:
        st.warning("No valid prices found. Ensure Tickers are correct or add Manual Prices.")
else:
    st.info("Add assets to the table to begin your snapshot.")