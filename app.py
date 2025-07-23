import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go

st.set_page_config(layout="wide")
st.title("Scanner Ichimoku - Croisement Tenkan / Kijun")

symbols = [
    "EURUSD", "GBPUSD", "USDJPY", "USDCHF", "USDCAD", "AUDUSD", "NZDUSD",
    "EURGBP", "EURJPY", "EURCHF", "EURCAD", "EURAUD", "EURNZD",
    "GBPJPY", "GBPCHF", "GBPCAD", "GBPAUD", "GBPNZD",
    "CHFJPY", "CADJPY", "AUDJPY", "NZDJPY",
    "AUDCAD", "AUDCHF", "AUDNZD",
    "CADCHF", "NZDCAD", "NZDCHF"
]

@st.cache_data
def fetch_data(symbol):
    df = yf.download(symbol, period="1mo", interval="1h")
    df.dropna(inplace=True)
    return df

def calculate_ichimoku(df):
    nine_period_high = df["High"].rolling(window=9).max()
    nine_period_low = df["Low"].rolling(window=9).min()
    df["Tenkan"] = (nine_period_high + nine_period_low) / 2

    period26_high = df["High"].rolling(window=26).max()
    period26_low = df["Low"].rolling(window=26).min()
    df["Kijun"] = (period26_high + period26_low) / 2

    return df

def find_last_tk_cross_info(df):
    df = df.dropna(subset=["Tenkan", "Kijun"]).copy()
    prev_diff = df["Tenkan"].shift(1) - df["Kijun"].shift(1)
    curr_diff = df["Tenkan"] - df["Kijun"]

    bullish_cross = (prev_diff <= 0) & (curr_diff > 0)
    bearish_cross = (prev_diff >= 0) & (curr_diff < 0)

    last_bullish = df[bullish_cross].index.max() if bullish_cross.any() else None
    last_bearish = df[bearish_cross].index.max() if bearish_cross.any() else None

    if last_bullish and (not last_bearish or last_bullish > last_bearish):
        return last_bullish, "✅ Haussier"
    elif last_bearish and (not last_bullish or last_bearish > last_bullish):
        return last_bearish, "❌ Baissier"
    else:
        return pd.NaT, "Neutre"

results = []

for symbol in symbols:
    try:
        df = fetch_data(symbol)
        df = calculate_ichimoku(df)
        date, direction = find_last_tk_cross_info(df)
        results.append((symbol, date, direction))
    except Exception as e:
        results.append((symbol, "Erreur", str(e)))

results_df = pd.DataFrame(results, columns=["Paire", "Dernier Croisement", "Direction"])
results_df.sort_values(by="Dernier Croisement", ascending=False, inplace=True)

st.dataframe(results_df, use_container_width=True)
