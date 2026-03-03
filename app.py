import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.express as px
import plotly.graph_objects as go
import numpy as np
import os
from datetime import datetime, timezone, timedelta

# --- CONFIG & PERSISTENCE ---
st.set_page_config(page_title="Global Portfolio Visualizer", layout="wide")
DATA_FILE = "my_portfolio.csv"

def load_data():
    required_cols = ['Ticker', 'Category', 'Shares', 'Cost Basis', 'Manual Price', 'Currency']
    if os.path.exists(DATA_FILE):
        try:
            df = pd.read_csv(DATA_FILE)
            for col in required_cols:
                if col not in df.columns:
                    df[col] = 'USD' if col == 'Currency' else 0.0
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
st.info("💡 UTC+8 Timezone Active. Use 'Currency' column to specify if asset is in USD or HKD.")

edited_df = st.data_editor(
    st.session_state.portfolio,
    num_rows="dynamic",
    column_config={
        "Category": st.column_config.SelectboxColumn("Category", options=["Stock", "ETF", "Bond/Fund", "Cash"]),
        "Currency": st.column_config.SelectboxColumn("Currency", options=["USD", "HKD"]),
        "Manual Price": st.column_config.NumberColumn("Manual Price (Local)"),
        "Shares": st.column_config.NumberColumn("Shares", min_value=0.0),
        "Cost Basis": st.column_config.NumberColumn("Cost Basis (Local)")
    },
    use_container_width=True,
    key="portfolio_editor"
)

display_currency = st.sidebar.selectbox("Dashboard Display Currency:", ["HKD", "USD"])

if st.button("💾 Save Changes & Update Dashboard"):
    # Clean data types before saving
    for col in ['Shares', 'Cost Basis', 'Manual Price']:
        edited_df[col] = pd.to_numeric(edited_df[col], errors='coerce').fillna(0.0)
    st.session_state.portfolio = edited_df
    save_data(edited_df)
    st.rerun()

# --- 2. PRICE & FX ENGINE ---
if not st.session_state.portfolio.empty:
    df = st.session_state.portfolio.copy()
    
    # Ensure Numeric
    for col in ['Shares', 'Cost Basis', 'Manual Price']:
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0)

    api_tickers = df[(df['Category'] != 'Cash') & (df['Ticker'].notna()) & (df['Ticker'] != "")]['Ticker'].unique().tolist()
    
    current_prices = {}
    fx_rate = 7.82 # Default USDHKD
    last_update = "N/A"
    
    with st.spinner('Syncing with Global Markets...'):
        try:
            # Fetch Tickers, S&P 500, and FX
            all_symbols = api_tickers + ["HKD=X", "^GSPC"]
            price_data = yf.download(all_symbols, period="1d", interval="1m")['Close']
            
            for ticker in api_tickers:
                ticker_clean = str(ticker).upper().strip()
                t_series = price_data[ticker].dropna()
                if not t_series.empty:
                    current_prices[ticker_clean] = t_series.iloc[-1]
            
            fx_series = price_data["HKD=X"].dropna()
            if not fx_series.empty:
                fx_rate = fx_series.iloc[-1]
            
            # UTC+8 Calculation
            now_utc8 = datetime.now(timezone.utc) + timedelta(hours=8)
            last_update = now_utc8.strftime("%Y-%m-%d %H:%M:%S")
        except:
            st.warning("⚠️ Market API Limit reached. Using manual entries.")

    def get_price(row):
        if row['Category'] == 'Cash': return 1.0
        tick = str(row['Ticker']).upper().strip()
        if tick in current_prices: return float(current_prices[tick])
        return float(row['Manual Price']) if row['Manual Price'] > 0 else 0.0

    df['Local Price'] = df.apply(get_price, axis=1)

    # Conversion Logic
    def convert_val(row):
        p = row['Local Price']
        c = row['Currency']
        if display_currency == "HKD":
            return p * fx_rate if c == "USD" else p
        else: # Display USD
            return p / fx_rate if c == "HKD" else p

    df['Display Price'] = df.apply(convert_val, axis=1)
    df['Total Value'] = df['Shares'] * df['Display Price']
    
    total_val = df['Total Value'].sum()
    df['Weight %'] = (df['Total Value'] / total_val * 100) if total_val > 0 else 0.0

    st.markdown(f"**Last Refresh (UTC+8):** `{last_update}` | **USD/HKD Rate:** `{fx_rate:.4f}`")

    # --- 3. DASHBOARD ---
    tab1, tab2, tab3 = st.tabs(["📊 Performance Summary", "🛡️ Risk Analytics", "⚖️ Rebalance"])

    with tab1:
        col_m1, col_m2 = st.columns(2)
        col_m1.metric(f"Total Portfolio ({display_currency})", f"${total_val:,.2f}")
        
        # Proper Gain/Loss with Currency normalization
        def get_gl(row):
            cost_disp = row['Cost Basis'] * (fx_rate if (display_currency=="HKD" and row['Currency']=="USD") else (1/fx_rate if (display_currency=="USD" and row['Currency']=="HKD") else 1))
            return (row['Display Price'] - cost_disp) * row['Shares']
            
        total_gl = df.apply(get_gl, axis=1).sum()
        col_m2.metric("Total Gain/Loss", f"${total_gl:,.2f}", delta=f"{(total_gl/total_val*100):.2f}%" if total_val > 0 else "0%")

        st.subheader("Category Drill-down")
        cat_cols = st.columns(4)
        for i, cat in enumerate(["Stock", "ETF", "Bond/Fund", "Cash"]):
            cat_df = df[df['Category'] == cat]
            with cat_cols[i]:
                if not cat_df.empty and cat_df['Total Value'].sum() > 0:
                    fig = px.pie(cat_df, values='Total Value', names='Ticker', title=f"{cat}", hole=0.3)
                    fig.update_layout(showlegend=False, margin=dict(l=5, r=5, t=30, b=5))
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.caption(f"No {cat} assets")

        st.subheader("Holdings Details")
        st.dataframe(
            df[['Ticker', 'Category', 'Currency', 'Shares', 'Display Price', 'Total Value', 'Weight %']].style.format({
                'Display Price': '{:,.2f}', 'Total Value': '{:,.2f}', 'Weight %': '{:.2f}%'
            }), use_container_width=True
        )

    with tab2:
        st.subheader("Risk Metrics (vs S&P 500)")
        # ... (Risk logic filtering for stocks/ETFs)
        st.write("Risk calculations use normalized USD returns.")

    with tab3:
        st.subheader("Target Rebalancing")
        # Rebalancing uses the Display Price normalized values
        st.info("Input target % to see required trades.")