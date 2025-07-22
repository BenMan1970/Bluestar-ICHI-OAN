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
    """Détermine la tendance basée sur la position du prix par rapport au Kumo."""
    if df is None or len(df) < 52: return "Indisponible"
    # S'assurer que les indicateurs sont présents
    if not all(col in df.columns for col in ["senkou_a", "senkou_b"]):
        df.ta.ichimoku(append=True)
        df.rename(columns={"ISA_9": "senkou_a", "ISB_26": "senkou_b"}, inplace=True)

    last = df.iloc[-1]
    if pd.isna(last['senkou_a']) or pd.isna(last['senkou_b']): return "Indisponible"
    
    kumo_top = max(last['senkou_a'], last['senkou_b'])
    kumo_bottom = min(last['senkou_a'], last['senkou_b'])

    if last['close'] > kumo_top: return "Haussier"
    if last['close'] < kumo_bottom: return "Baissier"
    return "Neutre"

def analyze_signal(instrument, main_tf, confirmation_tf):
    """
    Cherche un croisement TK sur main_tf et le valide avec la tendance Ichimoku de confirmation_tf.
    """
    df_main = fetch_candles(instrument, main_tf)
    if df_main is None or len(df_main) < 52: return None

    df_main.ta.ichimoku(append=True)
    df_main.rename(columns={"ITS_9": "tenkan", "IKS_26": "kijun", "ISA_9": "senkou_a", "ISB_26": "senkou_b"}, inplace=True)
    
    last, previous = df_main.iloc[-2], df_main.iloc[-3]
    if pd.isna(last['tenkan']) or pd.isna(last['senkou_a']): return None

    signal_type = None
    # --- Déclencheur : Croisement TK ---
    if last['tenkan'] > last['kijun'] and previous['tenkan'] <= previous['kijun']:
        signal_type = "Haussier"
    elif last['tenkan'] < last['kijun'] and previous['tenkan'] >= previous['kijun']:
        signal_type = "Baissier"
    
    if not signal_type: return None

    # --- Filtre 1 : Contexte Kumo sur la timeframe du signal ---
    kumo_top = max(last['senkou_a'], last['senkou_b'])
    kumo_bottom = min(last['senkou_a'], last['senkou_b'])

    if signal_type == "Haussier":
        if not (last['tenkan'] > kumo_top and last['senkou_a'] > last['senkou_b']):
            return None # Rejet : le croisement n'est pas au-dessus d'un nuage haussier
    elif signal_type == "Baissier":
        if not (last['tenkan'] < kumo_bottom and last['senkou_a'] < last['senkou_b']):
            return None # Rejet : le croisement n'est pas en-dessous d'un nuage baissier
            
    # --- Filtre 2 : Confirmation par la tendance Ichimoku de l'autre timeframe ---
    df_confirmation = fetch_candles(instrument, confirmation_tf)
    confirmation_trend = get_ichimoku_trend(df_confirmation)

    if signal_type == confirmation_trend:
        # Signal validé !
        return {
            "Actif": instrument,
            "Signal": f"✅ Croisement {signal_type}",
            f"Conf. {confirmation_tf} (Ichi)": "👍",
            "Heure (UTC)": last.name.strftime('%Y-%m-%d %H:%M')
        }
    return None

# --- Interface Streamlit ---
st.title("🚀 BlueStar - Scanner Ichimoku Pur")

if 'scan_complete' not in st.session_state:
    st.session_state.scan_complete = False
    st.session_state.results_h4 = pd.DataFrame()
    st.session_state.results_h1 = pd.DataFrame()

if st.button("Lancer le Scan Complet (H4 & H1)", type="primary"):
    st.session_state.scan_complete = True
    with st.spinner("Analyse Ichimoku complète en cours..."):
        signals_h4 = []
        signals_h1 = []
        
        for inst in INSTRUMENTS_TO_SCAN:
            # Analyse H4, confirmée par H1
            signal_h4 = analyze_signal(inst, "H4", "H1")
            if signal_h4:
                signals_h4.append(signal_h4)
            
            # Analyse H1, confirmée par H4
            signal_h1 = analyze_signal(inst, "H1", "H4")
            if signal_h1:
                signals_h1.append(signal_h1)
        
        st.session_state.results_h4 = pd.DataFrame(signals_h4)
        st.session_state.results_h1 = pd.DataFrame(signals_h1)

if st.session_state.scan_complete:
    st.subheader("Tableau des Signaux de Fond (H4)")
    if st.session_state.results_h4.empty:
        st.info("Aucun signal H4 validé n'a été trouvé.")
    else:
        st.dataframe(st.session_state.results_h4, use_container_width=True, hide_index=True)

    st.subheader("Tableau des Signaux Intraday (H1)")
    if st.session_state.results_h1.empty:
        st.info("Aucun signal H1 validé n'a été trouvé.")
    else:
        st.dataframe(st.session_state.results_h1, use_container_width=True, hide_index=True)
