import streamlit as st
import pandas as pd
import pandas_ta as ta
from oandapyV20 import API
import oandapyV20.endpoints.instruments as instruments
import os

# --- Configuration des Secrets (Robuste pour Streamlit Cloud) ---
try:
    ACCESS_TOKEN = st.secrets["OANDA_ACCESS_TOKEN"]
    ACCOUNT_ID = st.secrets["OANDA_ACCOUNT_ID"]
except KeyError:
    st.error("Erreur: Veuillez configurer les secrets OANDA (OANDA_ACCESS_TOKEN, OANDA_ACCOUNT_ID) dans les paramètres de l'application.")
    st.stop()

# Initialisation de l'API
try:
    api = API(access_token=ACCESS_TOKEN, environment="practice") # "practice" ou "live"
except Exception as e:
    st.error(f"Impossible de se connecter à l'API OANDA. Erreur: {e}")
    st.stop()


# --- Fonctions ---

@st.cache_data(ttl=300) # Cache les données pour 5 minutes
def fetch_candles(instrument, timeframe, count):
    """Récupère les données de chandeliers depuis OANDA."""
    params = {
        "count": count,
        "granularity": timeframe
    }
    try:
        r = instruments.InstrumentsCandles(instrument=instrument, params=params)
        api.request(r)
        
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
    if df is not None and not df.empty:
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

    if df_candles is not None and not df_candles.empty:
        # Étape 2: Calculer Ichimoku
        df_with_indicators = add_ichimoku(df_candles)
        
        st.success("Données récupérées et indicateurs calculés !")
        st.dataframe(df_with_indicators.tail(5))

        # --- ÉTAPE 3: DÉTECTION DU CROISEMENT ---

        # 3.A - Renommer les colonnes pour la lisibilité
        df_with_indicators.rename(columns={
            "ITS_9": "tenkan",
            "IKS_26": "kijun",
            "ISA_26": "senkou_a",
            "ISB_52": "senkou_b",
            "ICS_26": "chikou"
        }, inplace=True)

        # 3.B - Isoler les deux dernières bougies
        last_two_candles = df_with_indicators.iloc[-2:]
        
        if len(last_two_candles) < 2:
            st.warning("Pas assez de données pour détecter un croisement.")
        else:
            previous_candle = last_two_candles.iloc[0]
            last_candle = last_two_candles.iloc[1]

            # 3.C - Logique de détection du croisement
            st.subheader("Résultat de l'analyse du croisement :")

            # Condition pour un croisement haussier
            if last_candle['tenkan'] > last_candle['kijun'] and previous_candle['tenkan'] <= previous_candle['kijun']:
                st.success(f"✅ Signal de croisement HAUSSIER détecté sur {instrument_test} !")
                st.write(f"Heure du signal (UTC) : {last_candle.name}")

            # Condition pour un croisement baissier
            elif last_candle['tenkan'] < last_candle['kijun'] and previous_candle['tenkan'] >= previous_candle['kijun']:
                st.error(f"❌ Signal de croisement BAISSIER détecté sur {instrument_test} !")
                st.write(f"Heure du signal (UTC) : {last_candle.name}")

            else:
                st.info("Aucun croisement Tenkan/Kijun détecté sur la dernière bougie.")
    else:
        st.error("Impossible de récupérer les données pour l'analyse.")
       
