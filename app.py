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
] # Liste réduite pour des scans plus rapides

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
@st.cache_data(ttl=60) # Cache de 1 minute
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
    """
    Détecte un croisement du nuage sur la timeframe principale (main_tf)
    et le valide avec les timeframes inférieures (sub_tf1, sub_tf2).
    """
    df = fetch_candles(instrument, main_tf)
    if df is None or len(df) < 52: return None

    df.ta.ichimoku(append=True)
    df.rename(columns={"ITS_9": "tenkan", "IKS_26": "kijun", "ISA_9": "senkou_a", "ISB_26": "senkou_b"}, inplace=True)
    
    # On regarde les 3 dernières bougies pour un croisement récent
    for i in range(2, 4):
        last = df.iloc[-i]
        previous = df.iloc[-i-1]

        if pd.isna(last['senkou_a']) or pd.isna(previous['senkou_a']): continue

        kumo_top_last, kumo_bottom_last = max(last['senkou_a'], last['senkou_b']), min(last['senkou_a'], last['senkou_b'])
        kumo_top_prev, kumo_bottom_prev = max(previous['senkou_a'], previous['senkou_b']), min(previous['senkou_a'], previous['senkou_b'])

        signal_type = None
        # Croisement Haussier du Kumo : La Tenkan passe au-dessus du nuage
        if last['tenkan'] > kumo_top_last and previous['tenkan'] < kumo_top_prev:
            if last['senkou_a'] > last['senkou_b']: # Le nuage doit être haussier
                signal_type = "Haussier"
        # Croisement Baissier du Kumo : La Tenkan passe en-dessous du nuage
        elif last['tenkan'] < kumo_bottom_last and previous['tenkan'] > kumo_bottom_prev:
            if last['senkou_a'] < last['senkou_b']: # Le nuage doit être baissier
                signal_type = "Baissier"
        
        if signal_type:
            # --- Filtre de confirmation MTF ---
            trend1 = get_ema_trend(fetch_candles(instrument, sub_tf1))
            trend2 = get_ema_trend(fetch_candles(instrument, sub_tf2))

            if signal_type == trend1 and signal_type == trend2:
                return {
                    "Actif": instrument,
                    "Signal": f" breakout {signal_type}",
                    f"Conf. {sub_tf1}": "✅",
                    f"Conf. {sub_tf2}": "✅",
                    "Heure Signal (UTC)": last.name.strftime('%Y-%m-%d %H:%M')
                }
    return None

# --- Interface Streamlit ---
st.title("🚀 BlueStar - Scanner de Breakout Ichimoku")

if 'scan_results_h4' not in st.session_state: st.session_state.scan_results_h4 = None
if 'scan_results_h1' not in st.session_state: st.session_state.scan_results_h1 = None

col1, col2 = st.columns(2)
with col1:
    if st.button("Lancer Scan H4", type="primary"):
        with st.spinner("Analyse des signaux de fond H4..."):
            signals = [analyze_kumo_breakout(inst, "H4", "H1", "M15") for inst in INSTRUMENTS_TO_SCAN]
            st.session_state.scan_results_h4 = pd.DataFrame([s for s in signals if s])
with col2:
    if st.button("Lancer Scan H1", type="primary"):
        with st.spinner("Analyse des signaux intraday H1..."):
            signals = [analyze_kumo_breakout(inst, "H1", "M15", "M5") for inst in INSTRUMENTS_TO_SCAN]
            st.session_state.scan_results_h1 = pd.DataFrame([s for s in signals if s])

st.subheader("Tableau des Signaux de Fond (H4)")
if st.session_state.scan_results_h4 is not None:
    if st.session_state.scan_results_h4.empty:
        st.info("Aucun breakout H4 validé n'a été trouvé.")
    else:
        st.dataframe(st.session_state.scan_results_h4, use_container_width=True, hide_index=True)

st.subheader("Tableau des Signaux Intraday (H1)")
if st.session_state.scan_results_h1 is not None:
    if st.session_state.scan_results_h1.empty:
        st.info("Aucun breakout H1 validé n'a été trouvé.")
    else:
        st.dataframe(st.session_state.scan_results_h1, use_container_width=True, hide_index=True)
