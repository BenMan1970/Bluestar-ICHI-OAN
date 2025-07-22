import streamlit as st
import pandas as pd
import pandas_ta as ta
from oandapyV20 import API
import oandapyV20.endpoints.instruments as instruments
import os

# --- Configuration et Constantes ---
st.set_page_config(layout="wide")

# ... (La liste des instruments et la connexion API ne changent pas)
INSTRUMENTS_TO_SCAN = [
    # Majeures
    "EUR_USD", "GBP_USD", "USD_JPY", "USD_CHF", "USD_CAD", "AUD_USD", "NZD_USD",
    # Mineures (EUR)
    "EUR_GBP", "EUR_JPY", "EUR_CHF", "EUR_CAD", "EUR_AUD", "EUR_NZD",
    # Mineures (GBP)
    "GBP_JPY", "GBP_CHF", "GBP_CAD", "GBP_AUD", "GBP_NZD",
    # Mineures (Autres)
    "AUD_JPY", "AUD_CAD", "AUD_CHF", "AUD_NZD",
    "CAD_JPY", "CAD_CHF",
    "CHF_JPY",
    "NZD_JPY", "NZD_CAD", "NZD_CHF",
    # Or et Indices
    "XAU_USD", "US30_USD", "NAS100_USD", "SPX500_USD"
]

# --- Connexion API (inchangée) ---
try:
    ACCESS_TOKEN = st.secrets["OANDA_ACCESS_TOKEN"]
    ACCOUNT_ID = st.secrets["OANDA_ACCOUNT_ID"]
except KeyError:
    st.error("Erreur: Veuillez configurer les secrets OANDA.")
    st.stop()

try:
    api = API(access_token=ACCESS_TOKEN, environment="practice")
except Exception as e:
    st.error(f"Impossible de se connecter à l'API OANDA. Erreur: {e}")
    st.stop()

# --- Fonctions (inchangées) ---
@st.cache_data(ttl=300)
def fetch_candles(instrument, timeframe, count=200):
    params = {"count": count, "granularity": timeframe}
    try:
        r = instruments.InstrumentsCandles(instrument=instrument, params=params)
        api.request(r)
        data = []
        for candle in r.response['candles']:
            time = pd.to_datetime(candle['time'])
            o, h, l, c = (float(candle['mid']['o']), float(candle['mid']['h']),
                          float(candle['mid']['l']), float(candle['mid']['c']))
            data.append([time, o, h, l, c])
        df = pd.DataFrame(data, columns=['time', 'open', 'high', 'low', 'close'])
        df.set_index('time', inplace=True)
        return df
    except Exception:
        return None

def analyze_instrument(instrument):
    # La logique d'analyse reste exactement la même que la version précédente
    df_h1 = fetch_candles(instrument, "H1")
    if df_h1 is None or len(df_h1) < 52: return None
    df_h1.ta.ichimoku(append=True)
    df_h1.rename(columns={"ITS_9": "tenkan", "IKS_26": "kijun", "ISA_9": "senkou_a", "ISB_26": "senkou_b"}, inplace=True)
    last_two_h1 = df_h1.iloc[-2:]
    if len(last_two_h1) < 2 or pd.isna(last_two_h1.iloc[1]['senkou_a']): return None
    previous_h1, last_h1 = last_two_h1.iloc[0], last_two_h1.iloc[1]
    signal_type_h1 = None
    if last_h1['tenkan'] > last_h1['kijun'] and previous_h1['tenkan'] <= previous_h1['kijun']: signal_type_h1 = "Haussier"
    elif last_h1['tenkan'] < last_h1['kijun'] and previous_h1['tenkan'] >= previous_h1['kijun']: signal_type_h1 = "Baissier"
    if not signal_type_h1: return None
    kumo_top, kumo_bottom = max(last_h1['senkou_a'], last_h1['senkou_b']), min(last_h1['senkou_a'], last_h1['senkou_b'])
    kumo_status = "❌ Invalide"
    if signal_type_h1 == "Haussier" and last_h1['close'] > kumo_top and last_h1['senkou_a'] > last_h1['senkou_b']: kumo_status = "🟢 Valide"
    elif signal_type_h1 == "Baissier" and last_h1['close'] < kumo_bottom and last_h1['senkou_a'] < last_h1['senkou_b']: kumo_status = "🔴 Valide"
    if "Valide" not in kumo_status: return None
    df_h4 = fetch_candles(instrument, "H4")
    if df_h4 is None or len(df_h4) < 50: return None
    df_h4['ema20'], df_h4['ema50'] = ta.ema(df_h4['close'], length=20), ta.ema(df_h4['close'], length=50)
    last_h4 = df_h4.iloc[-1]
    trend_h4 = "Neutre"
    if last_h4['ema20'] > last_h4['ema50']: trend_h4 = "Haussier"
    elif last_h4['ema20'] < last_h4['ema50']: trend_h4 = "Baissier"
    if signal_type_h1 == trend_h4:
        return {"Actif": instrument, "Signal H1": f"✅ {signal_type_h1}", "Statut Kumo H1": kumo_status, "Tendance H4": f"👍 {trend_h4}", "Heure Signal (UTC)": last_h1.name.strftime('%Y-%m-%d %H:%M'), "Dernier Prix": last_h1['close']}
    return None

# --- Interface Streamlit ---
st.title("🚀 BlueStar - Scanner de Marché Ichimoku")

# 1. Initialisation de l'état de session
if 'scan_results' not in st.session_state:
    st.session_state.scan_results = None

# Création de colonnes pour les boutons
col1, col2 = st.columns([1, 6]) # Crée deux colonnes, la première plus petite
with col1:
    if st.button("Lancer le Scan", type="primary"):
        with st.spinner(f"Analyse en cours sur {len(INSTRUMENTS_TO_SCAN)} instruments..."):
            all_signals = []
            for instrument in INSTRUMENTS_TO_SCAN:
                signal = analyze_instrument(instrument)
                if signal:
                    all_signals.append(signal)
            
            if not all_signals:
                st.session_state.scan_results = pd.DataFrame() # DataFrame vide pour signifier "rien trouvé"
            else:
                # 2. Stockage des résultats dans l'état de session
                st.session_state.scan_results = pd.DataFrame(all_signals)
with col2:
    if st.button("Effacer les résultats"):
        st.session_state.scan_results = None
        st.experimental_rerun() # Force le rafraîchissement de la page

# 3. Affichage permanent des résultats (s'ils existent)
if st.session_state.scan_results is not None:
    st.subheader("Résultats du Dernier Scan")
    if st.session_state.scan_results.empty:
        st.info("Aucun signal de haute qualité n'a été trouvé lors du dernier scan.")
    else:
        st.dataframe(st.session_state.scan_results, use_container_width=True, hide_index=True)
