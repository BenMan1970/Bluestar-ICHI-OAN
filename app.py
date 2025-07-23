import streamlit as st
import pandas as pd
import numpy as np
import datetime as dt
from oandapyV20 import API
import oandapyV20.endpoints.instruments as instruments

st.set_page_config(layout="wide")
st.title("🟢 Scanner Ichimoku - OANDA API")

# Paramètres utilisateur
api_key = st.secrets["oanda_api_key"]
account_type = st.radio("Type de compte", ("practice", "live"))
api = API(access_token=api_key, environment=account_type)

granularity = st.selectbox("Unité de temps", ["H1", "H4", "D"], index=0)
count = 100

col1, col2 = st.columns([3, 1])

with col1:
    pairs_to_scan = st.multiselect(
        "Choisissez les paires à analyser",
        [
            "EUR_USD", "GBP_USD", "USD_JPY", "USD_CHF", "USD_CAD", "AUD_USD", "NZD_USD",
            "EUR_GBP", "EUR_JPY", "EUR_CHF", "EUR_CAD", "EUR_AUD", "EUR_NZD",
            "GBP_JPY", "GBP_CHF", "GBP_CAD", "GBP_AUD", "GBP_NZD",
            "AUD_JPY", "AUD_CHF", "AUD_CAD", "AUD_NZD",
            "NZD_JPY", "NZD_CHF", "NZD_CAD",
            "CHF_JPY", "CAD_JPY",
            "XAU_USD"
        ],
        default=["EUR_USD", "GBP_USD", "USD_JPY", "XAU_USD", "AUD_USD"]
    )

with col2:
    show_signals_only = st.checkbox("Afficher uniquement les signaux", value=True)

def get_ichimoku_data(pair):
    params = {"granularity": granularity, "count": count}
    r = instruments.InstrumentsCandles(instrument=pair, params=params)
    api.request(r)
    candles = r.response["candles"]

    df = pd.DataFrame([{
        "time": c["time"],
        "open": float(c["mid"]["o"]),
        "high": float(c["mid"]["h"]),
        "low": float(c["mid"]["l"]),
        "close": float(c["mid"]["c"])
    } for c in candles if c["complete"]])

    # Calcul Ichimoku
    nine_high = df["high"].rolling(window=9).max()
    nine_low = df["low"].rolling(window=9).min()
    df["tenkan"] = (nine_high + nine_low) / 2

    period26_high = df["high"].rolling(window=26).max()
    period26_low = df["low"].rolling(window=26).min()
    df["kijun"] = (period26_high + period26_low) / 2

    df["senkou_a"] = ((df["tenkan"] + df["kijun"]) / 2).shift(26)
    period52_high = df["high"].rolling(window=52).max()
    period52_low = df["low"].rolling(window=52).min()
    df["senkou_b"] = ((period52_high + period52_low) / 2).shift(26)
    df["chikou"] = df["close"].shift(-26)

    return df

def detect_signal(df):
    latest = df.iloc[-1]
    previous = df.iloc[-2]

    tenkan = latest["tenkan"]
    kijun = latest["kijun"]
    price = latest["close"]
    senkou_a = latest["senkou_a"]
    senkou_b = latest["senkou_b"]
    chikou = df["chikou"].iloc[-28]
    past_price = df["close"].iloc[-28]

    bullish = tenkan > kijun and price > senkou_a and price > senkou_b and chikou > past_price
    bearish = tenkan < kijun and price < senkou_a and price < senkou_b and chikou < past_price

    if bullish:
        return "🔼 Achat"
    elif bearish:
        return "🔽 Vente"
    else:
        return "🔍 Neutre"

# Analyse des paires
results = []
for pair in pairs_to_scan:
    try:
        df = get_ichimoku_data(pair)
        signal = detect_signal(df)
        results.append({"Paire": pair.replace("_", "/"), "Signal": signal})
    except Exception as e:
        results.append({"Paire": pair.replace("_", "/"), "Signal": f"Erreur : {str(e)}"})

df_results = pd.DataFrame(results)

if show_signals_only:
    df_results = df_results[df_results["Signal"].str.contains("Achat|Vente")]

st.dataframe(df_results, use_container_width=True)
