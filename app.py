import streamlit as st
import pandas as pd
import pandas_ta as ta
from oandapyV20 import API
import oandapyV20.endpoints.instruments as instruments
import os

# --- Configuration (À METTRE DANS LES SECRETS STREAMLIT) ---
# Pour le développement local, vous pouvez utiliser des variables d'environnement
# os.environ['OANDA_ACCESS_TOKEN'] = 'VOTRE_TOKEN'
# os.environ['OANDA_ACCOUNT_ID'] = 'VOTRE_ACCOUNT_ID'

ACCESS_TOKEN = os.getenv('OANDA_ACCESS_TOKEN', 'METTRE_VOTRE_TOKEN_ICI')
ACCOUNT_ID = os.getenv('OANDA_ACCOUNT_ID', 'METTRE_VOTRE_ID_ICI')

api = API(access_token=ACCESS_TOKEN, environment="practice") # "practice" ou "live"

# --- Fonctions ---

# Utiliser le cache de Streamlit pour ne pas surcharger l'API
@st.cache_data(ttl=300) # Cache les données pour 5 minutes (300s)
def fetch_candles(instrument, timeframe, count):
    """Récupère les données de chandeliers depuis OANDA."""
    params = {
        "count": count,
        "granularity": timeframe
    }
    try:
        r = instruments.InstrumentsCandles(instrument=instrument, params=params)
        api.request(r)
        
        # Formater les données dans un DataFrame Pandas
        data = []
        for candle in r.response['candles']:
            time = pd.to_datetime(candle['time'])
            volume = candle['volume']
            o = float(candle['mid']['o'])
            h = float(candle['mid']['h'])
            l = float(candle['mid']['l'])
            c = float(candle['mid']['c'])
            data.append([time, o, h, l, c, volume])

        df = pd.DataFrame(data, columns=['time', 'open', 'high', 'low', 'close', 'volume'])
        df.set_index('time', inplace=True)
        return df
    except Exception as e:
        st.error(f"Erreur lors de la récupération des données pour {instrument}: {e}")
        return None

def add_ichimoku(df):
    """Ajoute les indicateurs Ichimoku au DataFrame."""
    if df is not None:
        # Les noms par défaut sont ITS_9, IKS_26, etc.
        # On peut les renommer pour plus de clarté si on veut.
        df.ta.ichimoku(append=True)
    return df

# --- Interface Streamlit ---
st.title("Scanner de Marché Ichimoku")
st.write("Analyse les croisements Tenkan/Kijun avec filtres sur H1 et H4.")

# Test sur un instrument pour commencer
instrument_test = "EUR_USD"
timeframe_test = "H1"

st.header(f"Analyse test pour {instrument_test} sur {timeframe_test}")

if st.button("Lancer le test"):
    # Étape 1: Récupérer les données
    df_candles = fetch_candles(instrument_test, timeframe_test, 150)

    if df_candles is not None:
        # Étape 2: Calculer Ichimoku
        df_with_indicators = add_ichimoku(df_candles)
        
        st.success("Données récupérées et indicateurs calculés !")
        
        # Afficher les dernières lignes pour vérifier
        st.write("Dernières données avec indicateurs Ichimoku :")
        st.dataframe(df_with_indicators.tail(10))
