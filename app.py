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
    if os.path.exists(DATA_FILE):
        return pd.read_csv(DATA_FILE)
    return pd.DataFrame(columns=['Ticker', 'Category', 'Shares', 'Cost Basis', 'Manual Price'])

def save_data(df):
    df.to_csv(DATA_FILE, index=False)

if 'portfolio' not in st.session_state:
    st.session_state.portfolio = load_data()

# Header with dynamic timestamp
st.title("📈 Investment Portfolio Visualizer")

# --- 1. DATA ENTRY & EDITING ---
st.header("📋 Portfolio Management")
st.info("Edit cells directly. Use 'Manual Price' for private funds or if the Ticker fails. Click 'Save Changes' to update your CSV.")

# Use data_editor for direct editing and deletion
edited_df = st.data_editor(
    st.session_state.portfolio,
    num_rows="dynamic",
    column_config={
        "Category": st.column_config.SelectboxColumn(options=["Stock", "ETF", "Bond/Fund", "Cash"]),
        "Manual Price": st.column_config.NumberColumn("Manual Price ($)", help="Enter price here if API fails"),
    },
    use_container_width=True,
    key="portfolio_editor"
)

if st.button("💾 Save Changes"):
    st.session_state.portfolio = edited_df
    save_data(edited_df)
    st.rerun()

# --- 2. UPDATING PRICES ---
if not st.session_state.portfolio.empty:
    df = st.session_state.portfolio.copy()
    api_tickers = df[(df['Category'] != 'Cash') & (df['Ticker'].notna())]['Ticker'].unique().tolist()
    
    current_prices = {}
    last_update = "N/A"
    
    if api_tickers:
        with st.spinner('Updating market prices...'):
            try:
                # Fetching live minute-level data
                price_data = yf.download(api_tickers + ['^GSPC'], period="1d", interval="1m")['Close']
                
                for ticker in api_tickers:
                    last_price = price_data[ticker].dropna().iloc[-1]
                    current_prices[ticker] = last_price
                
                # Capture the current time of the update
                last_update = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            except Exception:
                st.error("Market data connection error. Showing fallback prices.")

    # Price Logic: API -> Manual -> 1.0 (Cash)
    def get_final_price(row):
        if row['Category'] == 'Cash': return 1.0
        api_val = current_prices.get(row['Ticker'])
        if pd.notna(api_val): return api_val
        if pd.notna(row['Manual Price']): return row['Manual Price']
        return None

    df['Current Price'] = df.apply(get_final_price, axis=1)

    # --- UI TIMESTAMP DISPLAY ---
    st.markdown(f"**Last Market Refresh:** `{last_update}`")

    # Check for N/A prices
    na_prices = df[df['Current Price'].isna()]
    if not na_prices.empty:
        st.warning(f"⚠️ Price missing for: {', '.join(na_prices['Ticker'].tolist())}. Enter 'Manual Price' above.")

    # --- 3. CALCULATIONS & VISUALS ---
    df_calc = df.dropna(subset=['Current Price'])
    df_calc['Total Value'] = df_calc['Shares'] * df_calc['Current Price']
    total_val = df_calc['Total Value'].sum()
    
    tab1, tab2, tab3 = st.tabs(["📊 Performance", "🛡️ Risk", "⚖️ Rebalance"])

    with tab1:
        m1, m2 = st.columns(2)
        with m1:
            st.metric("Total Portfolio Value", f"${total_val:,.2f}")
        with m2:
            df_calc['G/L'] = (df_calc['Current Price'] - df_calc['Cost Basis']) * df_calc['Shares']
            total_gl = df_calc['G/L'].sum()
            st.metric("Total Gain/Loss", f"${total_gl:,.2f}", delta=f"{(total_gl/total_val)*100:.2f}%" if total_val > 0 else "0%")

        fig_pie = px.pie(df_calc, values='Total Value', names='Category', hole=0.4, title="Allocation Breakdown")
        st.plotly_chart(fig_pie, use_container_width=True)

    # ... (Risk and Rebalance tabs use df_calc for their logic) ...

else:
    st.info("Start by adding a Ticker or Cash amount in the management table.")