import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime
import requests

# --- CONFIGURATION ---
PAIR_LIST = [
    "AUDCAD", "AUDCHF", "AUDJPY", "AUDNZD", "AUDUSD",
    "CADCHF", "CADJPY", "CHFJPY", "EURAUD", "EURCAD",
    "EURCHF", "EURGBP", "EURJPY", "EURNZD", "EURUSD",
    "GBPAUD", "GBPCAD", "GBPCHF", "GBPJPY", "GBPNZD",
    "GBPUSD", "NZDCAD", "NZDCHF", "NZDJPY", "NZDUSD",
    "USDCAD", "USDCHF", "USDJPY"
]

@st.cache_data
def load_data(symbol, interval="1h", count=150):
    url = f"https://api.twelvedata.com/time_series?symbol={symbol}=X&interval={interval}&outputsize={count}&apikey=demo"
    response = requests.get(url)
    if response.status_code != 200 or "values" not in response.json():
        return None
    df = pd.DataFrame(response.json()["values"])
    df = df.rename(columns={"datetime": "Date", "high": "High", "low": "Low", "close": "Close"})
    df["Date"] = pd.to_datetime(df["Date"])
    df[["High", "Low", "Close"]] = df[["High", "Low", "Close"]].astype(float)
    df = df.sort_values("Date").reset_index(drop=True)
    return df

def calculate_ichimoku(df):
    df["Tenkan"] = (df["High"].rolling(window=9).max() + df["Low"].rolling(window=9).min()) / 2
    df["Kijun"] = (df["High"].rolling(window=26).max() + df["Low"].rolling(window=26).min()) / 2
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
        return df.loc[last_bullish, "Date"], "✅ Haussier"
    elif last_bearish and (not last_bullish or last_bearish > last_bullish):
        return df.loc[last_bearish, "Date"], "❌ Baissier"
    else:
        return pd.NaT, "Neutre"

# --- STREAMLIT APP ---
st.set_page_config(page_title="Ichimoku Cross Scanner", layout="wide")
st.title("📈 Scanner Croisement Tenkan/Kijun (Ichimoku)")

with st.spinner("Chargement des données..."):
    results = []
    for pair in PAIR_LIST:
        df = load_data(pair)
        if df is not None:
            df = calculate_ichimoku(df)
            cross_date, cross_type = find_last_tk_cross_info(df)
            results.append({
                "Paire": pair,
                "Dernier croisement": cross_date,
                "Type": cross_type
            })

    result_df = pd.DataFrame(results)
    result_df = result_df.sort_values("Dernier croisement", ascending=False).reset_index(drop=True)

st.dataframe(result_df, use_container_width=True)
