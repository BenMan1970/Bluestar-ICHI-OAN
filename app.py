import streamlit as st
import pandas as pd
import pandas_ta as ta
from oandapyV20 import API
import oandapyV20.endpoints.instruments as instruments
import os

# --- Configuration et Constantes ---
st.set_page_config(layout="wide")

INSTRUMENTS_TO_SCAN = [
    # Liste volontairement réduite pour des tests plus rapides.
    # Remettez la liste complète quand vous le souhaitez.
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

# --- Fonctions (inchangées) ---
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

def get_ema_trend(df):
    if df is None or len(df) < 50: return "Indisponible"
    df['ema20'] = ta.ema(df['close'], length=20)
    df['ema50'] = ta.ema(df['close'], length=50)
    last = df.iloc[-1]
    if pd.isna(last['ema20']) or pd.isna(last['ema50']): return "Indisponible"
    if last['ema20'] > last['ema50']: return "Haussier"
    return "Baissier"

def analyze_kumo_breakout(instrument, main_tf, sub_tf1, sub_tf2):
    df = fetch_candles(instrument, main_tf)
    if df is None or len(df) < 52: return None
    df.ta.ichimoku(append=True)
    df.rename(columns={"ITS_9": "tenkan", "IKS_26": "kijun", "ISA_9": "senkou_a", "ISB_26": "senkou_b"}, inplace=True)
    for i in range(2, 4):
        last, previous = df.iloc[-i], df.iloc[-i-1]
        if pd.isna(last['senkou_a']) or pd.isna(previous['senkou_a']): continue
        kumo_top_last, kumo_bottom_last = max(last['senkou_a'], last['senkou_b']), min(last['senkou_a'], last['senkou_b'])
        kumo_top_prev, kumo_bottom_prev = max(previous['senkou_a'], previous['senkou_b']), min(previous['senkou_a'], previous['senkou_b'])
        signal_type = None
        if last['tenkan'] > kumo_top_last and previous['tenkan'] < kumo_top_prev and last['senkou_a'] > last['senkou_b']:
            signal_type = "Haussier"
        elif last['tenkan'] < kumo_bottom_last and previous['tenkan'] > kumo_bottom_prev and last['senkou_a'] < last['senkou_b']:
            signal_type = "Baissier"
        if signal_type:
            trend1 = get_ema_trend(fetch_candles(instrument, sub_tf1))
            trend2 = get_ema_trend(fetch_candles(instrument, sub_tf2))
            if signal_type == trend1 and signal_type == trend2:
                return {"Actif": instrument, "Signal": f"✅ Breakout {signal_type}", "Conf. 1": trend1, "Conf. 2": trend2, "Heure (UTC)": last.name.strftime('%Y-%m-%d %H:%M')}
    return None

# --- Interface Streamlit ---
st.title("🚀 BlueStar - Scanner de Breakout Ichimoku")

# NOUVEAU : Initialisation de l'état de session
if 'scan_complete' not in st.session_state:
    st.session_state.scan_complete = False
    st.session_state.results_h4 = pd.DataFrame()
    st.session_state.results_h1 = pd.DataFrame()

# NOUVEAU : Un seul bouton pour lancer le scan complet
if st.button("Lancer le Scan Complet (H4 & H1)", type="primary"):
    st.session_state.scan_complete = True
    with st.spinner("Analyse complète en cours... Cela peut prendre un moment."):
        signals_h4 = []
        signals_h1 = []
        
        # NOUVEAU : Boucle unique qui fait les deux analyses
        for inst in INSTRUMENTS_TO_SCAN:
            # Analyse pour H4
            signal_h4 = analyze_kumo_breakout(inst, "H4", "H1", "M15")
            if signal_h4:
                signals_h4.append(signal_h4)
            
            # Analyse pour H1
            signal_h1 = analyze_kumo_breakout(inst, "H1", "M15", "M5")
            if signal_h1:
                signals_h1.append(signal_h1)
        
        st.session_state.results_h4 = pd.DataFrame(signals_h4)
        st.session_state.results_h1 = pd.DataFrame(signals_h1)

# NOUVEAU : Affichage conditionnel basé sur le fait que le scan a été lancé au moins une fois
if st.session_state.scan_complete:
    st.subheader("Tableau des Signaux de Fond (H4)")
    if st.session_state.results_h4.empty:
        st.info("Aucun breakout H4 validé n'a été trouvé.")
    else:
        st.dataframe(st.session_state.results_h4, use_container_width=True, hide_index=True)

    st.subheader("Tableau des Signaux Intraday (H1)")
    if st.session_state.results_h1.empty:
        st.info("Aucun breakout H1 validé n'a été trouvé.")
    else:
        st.dataframe(st.session_state.results_h1, use_container_width=True, hide_index=True)
