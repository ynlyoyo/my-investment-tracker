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
    """Loads CSV and ensures all required columns exist."""
    required_cols = ['Ticker', 'Category', 'Shares', 'Cost Basis', 'Manual Price']
    if os.path.exists(DATA_FILE):
        try:
            df = pd.read_csv(DATA_FILE)
            # Add missing columns if user is upgrading from an older version
            for col in required_cols:
                if col not in df.columns:
                    df[col] = np.nan
            return df[required_cols] # Ensure column order
        except Exception:
            return pd.DataFrame(columns=required_cols)
    return pd.DataFrame(columns=required_cols)

def save_data(df):
    """Saves the dataframe to CSV."""
    df.to_csv(DATA_FILE, index=False)

# Initialize Session State
if 'portfolio' not in st.session_state:
    st.session_state.portfolio = load_data()

# --- HEADER ---
st.title("📈 Investment Portfolio Visualizer")

# --- 1. DATA MANAGEMENT ---
st.header("📋 Portfolio Management")
st.info("💡 **Tips:** Click cells to edit. Select a row and press 'Delete' to remove. Use 'Manual Price' if the Ticker is not found by the API.")

# Dynamic Data Editor
edited_df = st.data_editor(
    st.session_state.portfolio,
    num_rows="dynamic",
    column_config={
        "Ticker": st.column_config.TextColumn("Ticker", help="Stock/ETF symbol"),
        "Category": st.column_config.SelectboxColumn("Category", options=["Stock", "ETF", "Bond/Fund", "Cash"]),
        "Shares": st.column_config.NumberColumn("Shares", min_value=0.0),
        "Cost Basis": st.column_config.NumberColumn("Avg Cost ($)", min_value=0.0),
        "Manual Price": st.column_config.NumberColumn("Manual Price ($)", help="Override API price here"),
    },
    use_container_width=True,
    key="portfolio_editor"
)

# Explicit Save Button
if st.button("💾 Save Changes & Refresh Prices"):
    st.session_state.portfolio = edited_df
    save_data(edited_df)
    st.rerun()

# --- 2. PRICE ENGINE ---
if not st.session_state.portfolio.empty:
    df = st.session_state.portfolio.copy()
    
    # Identify tickers for API (exclude Cash and empty Tickers)
    api_tickers = df[(df['Category'] != 'Cash') & (df['Ticker'].notna()) & (df['Ticker'] != "")]['Ticker'].unique().tolist()
    
    current_prices = {}
    last_update = "Waiting for refresh..."
    
    if api_tickers:
        with st.spinner('Updating market prices...'):
            try:
                # Try to get live prices
                # Note: interval='1m' ensures the most recent price is pulled
                price_data = yf.download(api_tickers + ['^GSPC'], period="1d", interval="1m")['Close']
                
                for ticker in api_tickers:
                    # Get last available non-NaN price
                    ticker_series = price_data[ticker].dropna()
                    if not ticker_series.empty:
                        current_prices[ticker] = ticker_series.iloc[-1]
                
                last_update = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            except Exception as e:
                st.warning("⚠️ Market data API is currently busy or offline. Using Manual/Fallback prices.")

    # Pricing Logic: API -> Manual Entry -> 1.0 (Cash)
    def get_final_price(row):
        if row['Category'] == 'Cash':
            return 1.0
        
        # 1. Try API
        api_val = current_prices.get(row['Ticker'])
        if pd.notna(api_val):
            return api_val
        
        # 2. Try Manual Entry
        if 'Manual Price' in row and pd.notna(row['Manual Price']):
            return float(row['Manual Price'])
            
        return None

    df['Current Price'] = df.apply(get_final_price, axis=1)
    
    # UI Timestamp
    st.markdown(f"**Last Market Refresh:** `{last_update}`")

    # Filter out rows with missing prices for analysis
    missing_prices = df[df['Current Price'].isna()]
    if not missing_prices.empty:
        st.error(f"❌ Missing prices for: {', '.join(missing_prices['Ticker'].tolist())}. Please enter a 'Manual Price' in the table above.")
    
    df_calc = df.dropna(subset=['Current Price'])

    # --- 3. DASHBOARD ---
    if not