import streamlit as st
import pandas as pd
import pandas_ta as ta
from oandapyV20 import API
import oandapyV20.endpoints.instruments as instruments
import os

# --- Configuration et Constantes ---
st.set_page_config(layout="wide")

INSTRUMENTS_TO_SCAN = [
    "EUR_USD", "GBP_USD", "USD_JPY", "USD_CHF", "USD_CAD", "AUD_USD", "NZD_USD",
    "EUR_JPY", "GBP_JPY", "XAU_USD", "US30_USD", "NAS100_USD", "SPX500_USD"
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

# --- Fonctions ---
@st.cache_data(ttl=60)
def fetch_candles(instrument, timeframe, count=200):
    # ... (inchangée)
    params = {"count": count, "granularity": timeframe}
    try:
        r = instruments.InstrumentsCandles(instrument=instrument, params=params)
        api.request(r)
        data = []
        for candle in r.response['candles']:
            time = pd.to_datetime(candle['time'])
            o, h, l, c = (float(candle['mid']['o']), float(candle['mid']['h']), float(candle['mid']['l']), float(candle['mid']['c']))
            data.append([time, o, h, l, c])
        df = pd.DataFrame(data, columns=['time', 'open', 'high', 'low', 'close'])
        df.set_index('time', inplace=True)
        return df
    except Exception:
        return None

def get_ichimoku_trend(df):
    """Détermine la tendance Ichimoku (Haussier, Baissier, Neutre)."""
    if df is None or len(df) < 52: return "Indisponible"
    df.ta.ichimoku(append=True)
    df.rename(columns={"ISA_9": "senkou_a", "ISB_26": "senkou_b"}, inplace=True)
    last = df.iloc[-1]
    if pd.isna(last['senkou_a']) or pd.isna(last['senkou_b']): return "Indisponible"
    kumo_top, kumo_bottom = max(last['senkou_a'], last['senkou_b']), min(last['senkou_a'], last['senkou_b'])
    if last['close'] > kumo_top: return "Haussier"
    if last['close'] < kumo_bottom: return "Baissier"
    return "Neutre"

def analyze_signal_with_double_confirmation(instrument, main_tf, conf_tf1, conf_tf2):
    """Cherche un croisement TK et le valide avec une DOUBLE confirmation MTF."""
    df_main = fetch_candles(instrument, main_tf)
    if df_main is None or len(df_main) < 52: return None

    df_main.ta.ichimoku(append=True)
    df_main.rename(columns={"ITS_9": "tenkan", "IKS_26": "kijun", "ISA_9": "senkou_a", "ISB_26": "senkou_b"}, inplace=True)
    
    # On regarde le croisement sur les deux dernières bougies finalisées
    last, previous = df_main.iloc[-2], df_main.iloc[-3]
    if pd.isna(last['tenkan']) or pd.isna(last['senkou_a']): return None

    signal_type = None
    if last['tenkan'] > last['kijun'] and previous['tenkan'] <= previous['kijun']:
        signal_type = "Haussier"
    elif last['tenkan'] < last['kijun'] and previous['tenkan'] >= previous['kijun']:
        signal_type = "Baissier"
    
    if not signal_type: return None

    # Filtre 1: Contexte Kumo sur la timeframe du signal
    kumo_top = max(last['senkou_a'], last['senkou_b'])
    kumo_bottom = min(last['senkou_a'], last['senkou_b'])
    if signal_type == "Haussier" and not (last['tenkan'] > kumo_top and last['senkou_a'] > last['senkou_b']):
        return None
    elif signal_type == "Baissier" and not (last['tenkan'] < kumo_bottom and last['senkou_a'] < last['senkou_b']):
        return None
            
    # Filtre 2: Double confirmation MTF
    trend1 = get_ichimoku_trend(fetch_candles(instrument, conf_tf1))
    trend2 = get_ichimoku_trend(fetch_candles(instrument, conf_tf2))

    if signal_type == trend1 and signal_type == trend2:
        return {
            "Actif": instrument,
            "Signal": f"✅ {signal_type}",
            f"Conf. {conf_tf1}": "👍",
            f"Conf. {conf_tf2}": "👍",
            "Heure (UTC)": last.name.strftime('%Y-%m-%d %H:%M')
        }
    return None

# --- Interface Streamlit ---
st.title("🚀 BlueStar - Scanner Ichimoku à Double Confirmation")

if 'scan_complete' not in st.session_state:
    st.session_state.scan_complete = False
    st.session_state.results_h4 = pd.DataFrame()
    st.session_state.results_h1 = pd.DataFrame()

if st.button("Lancer le Scan Complet (H4 & H1)", type="primary"):
    st.session_state.scan_complete = True
    with st.spinner("Analyse complète en cours (H1, H4, D1, W1)..."):
        signals_h4 = []
        signals_h1 = []
        
        for inst in INSTRUMENTS_TO_SCAN:
            # Analyse H4, confirmée par D1 et W1
            signal_h4 = analyze_signal_with_double_confirmation(inst, "H4", "D", "W") # D=Daily, W=Weekly
            if signal_h4:
                signals_h4.append(signal_h4)
            
            # Analyse H1, confirmée par H4 et D1
            signal_h1 = analyze_signal_with_double_confirmation(inst, "H1", "H4", "D")
            if signal_h1:
                signals_h1.append(signal_h1)
        
        st.session_state.results_h4 = pd.DataFrame(signals_h4)
        st.session_state.results_h1 = pd.DataFrame(signals_h1)

if st.session_state.scan_complete:
    st.subheader("Tableau des Signaux H4 (Confirmés par D1 & W1)")
    if st.session_state.results_h4.empty:
        st.info("Aucun signal H4 avec double confirmation n'a été trouvé.")
    else:
        st.dataframe(st.session_state.results_h4, use_container_width=True, hide_index=True)

    st.subheader("Tableau des Signaux H1 (Confirmés par H4 & D1)")
    if st.session_state.results_h1.empty:
        st.info("Aucun signal H1 avec double confirmation n'a été trouvé.")
    else:
        st.dataframe(st.session_state.results_h1, use_container_width=True, hide_index=True)

   
