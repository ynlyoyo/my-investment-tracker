import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.express as px
import plotly.graph_objects as go
import numpy as np
import os
from datetime import datetime, timedelta

# --- CONFIG & PERSISTENCE ---
st.set_page_config(page_title="Global Portfolio Snapshot", layout="wide")
DATA_FILE = "my_portfolio.csv"

def load_data():
    required_cols = ['Ticker', 'Category', 'Shares', 'Cost Basis', 'Manual Price', 'Currency']
    if os.path.exists(DATA_FILE):
        try:
            df = pd.read_csv(DATA_FILE)
            for col in required_cols:
                if col not in df.columns:
                    if col == 'Currency': df[col] = 'USD' # Default to USD
                    else: df[col] = np.nan
            return df[required_cols]
        except:
            return pd.DataFrame(columns=required_cols)
    return pd.DataFrame(columns=required_cols)

def save_data(df):
    df.to_csv(DATA_FILE, index=False)

if 'portfolio' not in st.session_state:
    st.session_state.portfolio = load_data()

st.title("🌎 Global Portfolio Visualizer (USD/HKD)")

# --- 1. DATA MANAGEMENT ---
st.header("📋 Portfolio Management")
st.info("💡 Set the **Currency** for each asset. 'Manual Price' should be in the asset's local currency.")

edited_df = st.data_editor(
    st.session_state.portfolio,
    num_rows="dynamic",
    column_config={
        "Category": st.column_config.SelectboxColumn("Category", options=["Stock", "ETF", "Bond/Fund", "Cash"]),
        "Currency": st.column_config.SelectboxColumn("Currency", options=["USD", "HKD"]),
        "Manual Price": st.column_config.NumberColumn("Manual Price (Local)"),
    },
    use_container_width=True,
    key="portfolio_editor"
)

# Sidebar settings for display
display_currency = st.sidebar.selectbox("View Portfolio In:", ["HKD", "USD"])

if st.button("💾 Save Changes & Refresh Prices"):
    for col in ['Shares', 'Cost Basis', 'Manual Price']:
        edited_df[col] = pd.to_numeric(edited_df[col], errors='coerce').fillna(0)
    st.session_state.portfolio = edited_df
    save_data(edited_df)
    st.rerun()

# --- 2. PRICE & FX ENGINE ---
if not st.session_state.portfolio.empty:
    df = st.session_state.portfolio.copy()
    api_tickers = df[(df['Category'] != 'Cash') & (df['Ticker'].notna()) & (df['Ticker'] != "")]['Ticker'].unique().tolist()
    
    current_prices = {}
    fx_rate = 7.82 # Default fallback
    
    with st.spinner('Updating market data...'):
        try:
            # 1. Fetch Tickers + FX Rate (USD to HKD)
            all_to_fetch = api_tickers + ["HKD=X", "^GSPC"]
            price_data = yf.download(all_to_fetch, period="1d", interval="1m")['Close']
            
            # 2. Extract Prices
            for ticker in api_tickers:
                t_series = price_data[ticker].dropna()
                if not t_series.empty: current_prices[str(ticker).upper().strip()] = t_series.iloc[-1]
            
            # 3. Extract FX Rate
            fx_series = price_data["HKD=X"].dropna()
            if not fx_series.empty: fx_rate = fx_series.iloc[-1]
            
            # 4. UTC+8 Time Conversion
            utc_now = datetime.utcnow()
            local_time = (utc_now + timedelta(hours=8)).strftime("%Y-%m-%d %H:%M:%S")
        except:
            local_time = "Error fetching live data"

    def get_local_price(row):
        if row['Category'] == 'Cash': return 1.0
        tick = str(row['Ticker']).upper().strip()
        api_val = current_prices.get(tick)
        if pd.notna(api_val): return float(api_val)
        if pd.notna(row['Manual Price']) and row['Manual Price'] != 0: return float(row['Manual Price'])
        return 0.0

    # Calculate Values
    df['Local Price'] = df.apply(get_local_price, axis=1)
    
    # Currency Normalization Logic
    # If display is HKD: Multiply USD assets by FX rate
    # If display is USD: Divide HKD assets by FX rate
    def convert_to_display(row):
        price = row['Local Price']
        asset_curr = row['Currency']
        
        if display_currency == "HKD":
            return price * fx_rate if asset_curr == "USD" else price
        else: # Displaying in USD
            return price / fx_rate if asset_curr == "HKD" else price

    df['Display Price'] = df.apply(convert_to_display, axis=1)
    df['Total Value'] = df