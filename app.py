
import streamlit as st
import pandas as pd
import numpy as np
import oandapyV20
import oandapyV20.endpoints.instruments as instruments
from datetime import datetime, timedelta

# --- CONFIGURATION ---
OANDA_ACCOUNT_ID = st.secrets["OANDA_ACCOUNT_ID"]
OANDA_ACCESS_TOKEN = st.secrets["OANDA_ACCESS_TOKEN"]
client = oandapyV20.API(access_token=OANDA_ACCESS_TOKEN)
PAIRS = [
    "AUDCAD", "AUDCHF", "AUDJPY", "AUDNZD", "AUDUSD",
    "CADCHF", "CADJPY", "CHFJPY", "EURAUD", "EURCAD",
    "EURCHF", "EURGBP", "EURJPY", "EURNZD", "EURUSD",
    "GBPAUD", "GBPCAD", "GBPCHF", "GBPJPY", "GBPNZD",
    "GBPUSD", "NZDCAD", "NZDCHF", "NZDJPY", "NZDUSD",
    "USDCAD", "USDCHF", "USDJPY"
]
CANDLE_COUNT = 200

def get_ohlc(pair, granularity="H1", count=200):
    params = {"granularity": granularity, "count": count}
    r = instruments.InstrumentsCandles(instrument=pair, params=params)
    client.request(r)
    candles = r.response["candles"]
    data = [{"Date": c["time"],
              "High": float(c["mid"]["h"]),
              "Low": float(c["mid"]["l"]),
              "Close": float(c["mid"]["c"])}
            for c in candles if c["complete"]]
    df = pd.DataFrame(data)
    df["Date"] = pd.to_datetime(df["Date"])
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

# --- INTERFACE ---
st.set_page_config(page_title="Ichimoku TK Cross - OANDA", layout="wide")
st.title("📊 Croisement Tenkan/Kijun (Ichimoku) - OANDA")

with st.spinner("Chargement des données depuis OANDA..."):
    results = []
    for pair in PAIRS:
        try:
            df = get_ohlc(pair, count=CANDLE_COUNT)
            df = calculate_ichimoku(df)
            cross_date, cross_type = find_last_tk_cross_info(df)
            results.append({
                "Paire": pair,
                "Dernier croisement": cross_date,
                "Type": cross_type
            })
        except Exception as e:
            results.append({
                "Paire": pair,
                "Dernier croisement": "Erreur",
                "Type": "❌ " + str(e)[:30]
            })

df_results = pd.DataFrame(results)
df_results = df_results.sort_values("Dernier croisement", ascending=False).reset_index(drop=True)
st.dataframe(df_results, use_container_width=True)
