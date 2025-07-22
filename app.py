import streamlit as st
import pandas as pd
import pandas_ta as ta
from oandapyV20 import API
import oandapyV20.endpoints.instruments as instruments
import os

# --- Configuration et Constantes ---
st.set_page_config(layout="wide") # <-- Met la page en pleine largeur !

# Liste des instruments à scanner (vous pouvez la personnaliser)
INSTRUMENTS_TO_SCAN = [
    "EUR_USD", "GBP_USD", "USD_JPY", "AUD_USD", "USD_CAD", "NZD_USD",
    "EUR_JPY", "GBP_JPY", "XAU_USD", "US30_USD", "NAS100_USD", "SPX500_USD"
]
TIMEFRAME = "H1" # Pour l'instant on se concentre sur une seule timeframe

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

# --- Fonctions (améliorées) ---

@st.cache_data(ttl=300)
def fetch_candles(instrument, timeframe, count):
    # ... (cette fonction ne change pas)
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

def analyze_instrument(instrument, timeframe):
    """
    Analyse un seul instrument et retourne un dictionnaire si un signal est trouvé.
    Sinon, retourne None.
    """
    df = fetch_candles(instrument, timeframe, 150)
    if df is None or df.empty:
        return None

    # Calcul et renommage Ichimoku
    df.ta.ichimoku(append=True)
    df.rename(columns={"ITS_9": "tenkan", "IKS_26": "kijun"}, inplace=True)

    # Isoler les deux dernières bougies
    last_two = df.iloc[-2:]
    if len(last_two) < 2:
        return None

    previous = last_two.iloc[0]
    last = last_two.iloc[1]

    signal_type = None
    # Croisement Haussier
    if last['tenkan'] > last['kijun'] and previous['tenkan'] <= previous['kijun']:
        signal_type = "✅ Haussier"
    # Croisement Baissier
    elif last['tenkan'] < last['kijun'] and previous['tenkan'] >= previous['kijun']:
        signal_type = "❌ Baissier"

    if signal_type:
        # Si un signal est trouvé, on crée un dictionnaire de résultat
        signal_info = {
            "🌟 Signal": signal_type,
            "Actif": instrument,
            "Timeframe": timeframe,
            "Heure du Signal (UTC)": last.name.strftime('%Y-%m-%d %H:%M'),
            "Dernier Prix": last['close'],
            "Tenkan": round(last['tenkan'], 5),
            "Kijun": round(last['kijun'], 5)
        }
        return signal_info
    
    return None

# --- Interface Streamlit ---
st.title("🚀 BlueStar - Scanner de Marché Ichimoku")

if st.button("Lancer le Scan", type="primary"):
    st.subheader(f"Analyse en cours sur {len(INSTRUMENTS_TO_SCAN)} instruments ({TIMEFRAME})...")
    
    progress_bar = st.progress(0, text="Initialisation...")
    all_signals = []

    for i, instrument in enumerate(INSTRUMENTS_TO_SCAN):
        # Mise à jour de la barre de progression
        progress_text = f"Analyse de {instrument}..."
        progress_bar.progress((i + 1) / len(INSTRUMENTS_TO_SCAN), text=progress_text)

        # Analyse de l'instrument
        signal = analyze_instrument(instrument, TIMEFRAME)
        if signal:
            all_signals.append(signal)

    progress_bar.empty() # Fait disparaître la barre de progression

    st.subheader("Résultats du Scan")
    if not all_signals:
        st.info("Aucun nouveau signal de croisement Tenkan/Kijun détecté pour le moment.")
    else:
        # Affichage du tableau de résultats
        results_df = pd.DataFrame(all_signals)
        st.dataframe(
            results_df,
            use_container_width=True, # <-- Affiche le tableau en pleine largeur !
            hide_index=True
        )
       
