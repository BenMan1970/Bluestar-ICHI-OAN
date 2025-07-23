import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib
import pytz  # Bibliothèque pour les fuseaux horaires
from oandapyV20 import API
from oandapyV20.exceptions import V20Error
from oandapyV20.endpoints.instruments import InstrumentsCandles

# --- Configuration de la page ---
matplotlib.use("Agg")
st.set_page_config(page_title="Scanner Ichimoku Pro", layout="wide")

# --- Fonctions Cœur ---

@st.cache_resource(ttl=3600)
def get_oanda_client():
    try:
        access_token = st.secrets["OANDA_ACCESS_TOKEN"]
        return API(access_token=access_token)
    except (KeyError, AttributeError):
        st.error("Erreur de configuration : Le secret 'OANDA_ACCESS_TOKEN' est introuvable.")
        return None

@st.cache_data(ttl=300)
def get_ohlc_data(_client, pair, count, granularity):
    if not _client: return None
    params = {"count": count, "granularity": granularity, "price": "M"}
    r = InstrumentsCandles(instrument=pair, params=params)
    try:
        _client.request(r)
        data = [{"Time": c["time"], "Open": float(c["mid"]["o"]), "High": float(c["mid"]["h"]), "Low": float(c["mid"]["l"]), "Close": float(c["mid"]["c"])} for c in r.response.get("candles", []) if c.get("complete")]
        if not data: return None
        df = pd.DataFrame(data)
        df["Time"] = pd.to_datetime(df["Time"])
        return df.set_index("Time")
    except V20Error:
        return None

def calculate_ichimoku(df):
    df["Tenkan"] = (df["High"].rolling(window=9).max() + df["Low"].rolling(window=9).min()) / 2
    df["Kijun"] = (df["High"].rolling(window=26).max() + df["Low"].rolling(window=26).min()) / 2
    df["Senkou_A"] = ((df["Tenkan"] + df["Kijun"]) / 2).shift(26)
    df["Senkou_B"] = ((df["High"].rolling(window=52).max() + df["Low"].rolling(window=52).min()) / 2).shift(26)
    df["Chikou"] = df["Close"].shift(-26)
    return df

def find_last_tk_cross_info(df):
    is_bullish = df['Tenkan'] > df['Kijun']
    crosses = is_bullish.ne(is_bullish.shift(1))
    if crosses.any():
        last_cross_time = crosses[crosses].index[-1]
        is_bullish_at_cross = df.loc[last_cross_time, 'Tenkan'] > df.loc[last_cross_time, 'Kijun']
        direction = "✅ Haussier" if is_bullish_at_cross else "❌ Baissier"
        return last_cross_time, direction
    return pd.NaT, "Neutre"

def analyze_ichimoku_status(df):
    if df is None or len(df) < 78:
        return {"Statut": "Données Insuffisantes", "Conditions": {}, "cross_time": pd.NaT}

    last = df.iloc[-2]
    last_chikou = df.iloc[-28]
    cross_time, cross_direction = find_last_tk_cross_info(df)

    conditions = {"Prix vs Kumo": "Neutre", "Croisement TK": cross_direction, "Chikou Libre": "Neutre", "Kumo Futur": "Neutre"}
    
    if last["Close"] > last["Senkou_A"] and last["Close"] > last["Senkou_B"]: conditions["Prix vs Kumo"] = "✅ Haussier"
    elif last["Close"] < last["Senkou_A"] and last["Close"] < last["Senkou_B"]: conditions["Prix vs Kumo"] = "❌ Baissier"
    if last["Chikou"] > last_chikou["High"]: conditions["Chikou Libre"] = "✅ Haussier"
    elif last["Chikou"] < last_chikou["Low"]: conditions["Chikou Libre"] = "❌ Baissier"
    if last["Senkou_A"] > last["Senkou_B"]: conditions["Kumo Futur"] = "✅ Haussier"
    elif last["Senkou_A"] < last["Senkou_B"]: conditions["Kumo Futur"] = "❌ Baissier"

    is_buy = all(c.startswith("✅") for c in conditions.values())
    is_sell = all(c.startswith("❌") for c in conditions.values())
    
    status = "🟡 Neutre"
    if is_buy: status = "🟢 ACHAT FORT"
    elif is_sell: status = "🔴 VENTE FORTE"
        
    return {"Statut": status, "Conditions": conditions, "data": df, "cross_time": cross_time}

def plot_ichimoku(df, pair, granularity):
    fig, ax = plt.subplots(figsize=(12, 7))
    ax.plot(df.index, df["Close"], label="Prix", color="black", lw=1.5)
    ax.plot(df.index, df["Tenkan"], label="Tenkan", color="blue", lw=1)
    ax.plot(df.index, df["Kijun"], label="Kijun", color="red", lw=1)
    ax.plot(df.index, df["Chikou"], label="Chikou", color="purple", lw=1.2, ls='--')
    ax.fill_between(df.index, df["Senkou_A"], df["Senkou_B"], where=df["Senkou_A"] >= df["Senkou_B"], color='lightgreen', alpha=0.4, label="Kumo Haussier")
    ax.fill_between(df.index, df["Senkou_A"], df["Senkou_B"], where=df["Senkou_A"] < df["Senkou_B"], color='lightcoral', alpha=0.4, label="Kumo Baissier")
    ax.set_title(f"Ichimoku pour {pair} ({granularity})", fontsize=16)
    ax.legend()
    ax.grid(True, linestyle='--', alpha=0.6)
    plt.tight_layout()
    return fig

# --- INTERFACE UTILISATEUR STREAMLIT ---

st.title("🔎 Scanner Ichimoku Pro (H1 & H4)")
st.markdown("Analyse simultanée des conditions Ichimoku sur les unités de temps H1 et H4.")

client = get_oanda_client()

if client:
    with st.expander("⚙️ Configuration du Scan", expanded=True):
        col1, col2 = st.columns(2)
        with col1:
            pairs_to_scan = st.multiselect(
                "
