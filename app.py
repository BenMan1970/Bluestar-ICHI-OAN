import streamlit as st
import pandas as pd
import pandas_ta as ta
from oandapyV20 import API
import oandapyV20.endpoints.instruments as instruments
import os

# --- Configuration et Constantes ---
st.set_page_config(layout="wide")

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

# --- Connexion API ---
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

# --- Fonctions ---

# @@@@@@ LA CORRECTION EST ICI @@@@@@
@st.cache_data(ttl=300)
def fetch_candles(instrument, timeframe, count=200):
    """Récupère les bougies avec Open, High, Low, Close."""
    params = {"count": count, "granularity": timeframe}
    try:
        r = instruments.InstrumentsCandles(instrument=instrument, params=params)
        api.request(r)
        data = []
        for candle in r.response['candles']:
            time = pd.to_datetime(candle['time'])
            o = float(candle['mid']['o'])
            h = float(candle['mid']['h'])
            l = float(candle['mid']['l'])
            c = float(candle['mid']['c'])
            data.append([time, o, h, l, c])
        df = pd.DataFrame(data, columns=['time', 'open', 'high', 'low', 'close'])
        df.set_index('time', inplace=True)
        return df
    except Exception:
        return None
# @@@@@@ FIN DE LA CORRECTION @@@@@@


def analyze_instrument(instrument):
    """Analyse un instrument sur H1 et le valide avec la tendance de fond H4."""
    # --- 1. Analyse du Signal sur H1 ---
    df_h1 = fetch_candles(instrument, "H1")
    if df_h1 is None or df_h1.empty:
        return None

    # Calcul Ichimoku sur H1
    df_h1.ta.ichimoku(append=True)
    df_h1.rename(columns={"ITS_9": "tenkan", "IKS_26": "kijun"}, inplace=True)
    
    last_two_h1 = df_h1.iloc[-2:]
    if len(last_two_h1) < 2: return None
    previous_h1, last_h1 = last_two_h1.iloc[0], last_two_h1.iloc[1]

    signal_type_h1 = None
    if last_h1['tenkan'] > last_h1['kijun'] and previous_h1['tenkan'] <= previous_h1['kijun']:
        signal_type_h1 = "Haussier"
    elif last_h1['tenkan'] < last_h1['kijun'] and previous_h1['tenkan'] >= previous_h1['kijun']:
        signal_type_h1 = "Baissier"

    if not signal_type_h1:
        return None

    # --- 2. Analyse de la Tendance sur H4 ---
    df_h4 = fetch_candles(instrument, "H4")
    if df_h4 is None or df_h4.empty:
        return None

    df_h4['ema20'] = ta.ema(df_h4['close'], length=20)
    df_h4['ema50'] = ta.ema(df_h4['close'], length=50)
    last_h4 = df_h4.iloc[-1]

    trend_h4 = "Neutre"
    if last_h4['ema20'] > last_h4['ema50']:
        trend_h4 = "Haussier"
    elif last_h4['ema20'] < last_h4['ema50']:
        trend_h4 = "Baissier"

    # --- 3. Validation ---
    if signal_type_h1 == trend_h4:
        signal_info = {
            "Actif": instrument,
            "Signal H1": f"✅ {signal_type_h1}",
            "Tendance H4": f"👍 {trend_h4}",
            "Heure Signal (UTC)": last_h1.name.strftime('%Y-%m-%d %H:%M'),
            "Dernier Prix": last_h1['close'],
        }
        return signal_info
    
    return None

# --- Interface Streamlit ---
st.title("🚀 BlueStar - Scanner de Marché Ichimoku")

if st.button("Lancer le Scan", type="primary"):
    st.subheader(f"Analyse en cours sur {len(INSTRUMENTS_TO_SCAN)} instruments...")
    
    progress_bar = st.progress(0, text="Initialisation...")
    all_signals = []

    for i, instrument in enumerate(INSTRUMENTS_TO_SCAN):
        progress_text = f"Analyse de {instrument}..."
        progress_bar.progress((i + 1) / len(INSTRUMENTS_TO_SCAN), text=progress_text)
        
        signal = analyze_instrument(instrument)
        if signal:
            all_signals.append(signal)

    progress_bar.empty()

    st.subheader("Résultats du Scan : Signaux H1 validés par Tendance H4")
    if not all_signals:
        st.info("Aucun signal H1 aligné avec la tendance de fond H4 n'a été trouvé.")
    else:
        results_df = pd.DataFrame(all_signals)
        st.dataframe(results_df, use_container_width=True, hide_index=True)
