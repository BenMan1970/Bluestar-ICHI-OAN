import streamlit as st
import pandas as pd
import pytz
import numpy as np
from oandapyV20 import API
from oandapyV20.exceptions import V20Error
from oandapyV20.endpoints.instruments import InstrumentsCandles

st.set_page_config(page_title="Scanner Ichimoku Pro", layout="wide")

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
        response = _client.request(r)
        data = [{"Time": c["time"], "Open": float(c["mid"]["o"]), "High": float(c["mid"]["h"]), "Low": float(c["mid"]["l"]), "Close": float(c["mid"]["c"])} for c in response.get("candles", [])]
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
    df = df.dropna(subset=["Tenkan", "Kijun"]).copy()
    prev_diff = df["Tenkan"].shift(1) - df["Kijun"].shift(1)
    curr_diff = df["Tenkan"] - df["Kijun"]
    bullish_cross = (prev_diff <= 0) & (curr_diff > 0)
    bearish_cross = (prev_diff >= 0) & (curr_diff < 0)
    last_bullish = df[bullish_cross].index.max() if bullish_cross.any() else None
    last_bearish = df[bearish_cross].index.max() if bearish_cross.any() else None
    if last_bullish and (not last_bearish or last_bullish > last_bearish): return last_bullish
    elif last_bearish and (not last_bullish or last_bearish > last_bullish): return last_bearish
    else: return pd.NaT

def generate_visual_score(score):
    if score > 0: return '🔵' * score
    elif score < 0: return '🔴' * abs(score)
    elif score == 0: return '⚪'
    return "N/A"

# --- DÉBUT DE LA SECTION MODIFIÉE (1/2) ---
# La fonction d'analyse retourne maintenant si le signal est "fort" selon les nouveaux critères
def analyze_ichimoku_status(df_full):
    if df_full is None or len(df_full) < 79:
        return {"is_strong_buy": False, "is_strong_sell": False, "Score_visuel": "N/A"}

    last_closed = df_full.iloc[-2]
    scores = {'prix': 0, 'tk': 0, 'kumo': 0, 'chikou': 0}

    # Calcul des scores partiels
    if pd.notna(last_closed["Senkou_A"]) and pd.notna(last_closed["Senkou_B"]):
        if last_closed["Close"] > max(last_closed["Senkou_A"], last_closed["Senkou_B"]): scores['prix'] = 1
        elif last_closed["Close"] < min(last_closed["Senkou_A"], last_closed["Senkou_B"]): scores['prix'] = -1
    
    if pd.notna(last_closed["Tenkan"]) and pd.notna(last_closed["Kijun"]):
        if last_closed["Tenkan"] > last_closed["Kijun"]: scores['tk'] = 1
        elif last_closed["Tenkan"] < last_closed["Kijun"]: scores['tk'] = -1

    if pd.notna(last_closed["Senkou_A"]) and pd.notna(last_closed["Senkou_B"]):
        if last_closed["Senkou_A"] > last_closed["Senkou_B"]: scores['kumo'] = 1
        elif last_closed["Senkou_A"] < last_closed["Senkou_B"]: scores['kumo'] = -1

    if len(df_full) > 27:
        chikou_value = last_closed['Close']
        past_candle = df_full.iloc[-27]
        if pd.notna(chikou_value) and pd.notna(past_candle['High']) and pd.notna(past_candle['Senkou_A']) and pd.notna(past_candle['Senkou_B']):
            if chikou_value > past_candle['High'] and chikou_value > max(past_candle['Senkou_A'], past_candle['Senkou_B']):
                scores['chikou'] = 1
            else:
                scores['chikou'] = -1
    
    final_score = sum(scores.values())
    
    # Définition d'un signal fort selon les critères : score parfait, ou score presque parfait si Chikou est le seul fautif.
    is_strong_buy = (final_score == 4) or (final_score == 3 and scores['chikou'] != 1)
    is_strong_sell = (final_score == -4) or (final_score == -3 and scores['chikou'] != -1)
    
    return {
        "is_strong_buy": is_strong_buy,
        "is_strong_sell": is_strong_sell,
        "Score_visuel": generate_visual_score(final_score)
    }
# --- FIN DE LA SECTION MODIFIÉE (1/2) ---

st.title("🔎 Scanner Ichimoku Pro (M15, H1 & H4)")
st.markdown("Analyse des **signaux alignés** sur plusieurs unités de temps pour des stratégies robustes.")

client = get_oanda_client()

if client:
    st.info("Le scanner recherche les paires dont les signaux Ichimoku sont fortement alignés sur au moins **2 des 3 unités de temps** (M15, H1, H4).")

    pairs_to_scan = [
        "EUR_USD", "GBP_USD", "USD_JPY", "USD_CHF", "USD_CAD", "AUD_USD", "NZD_USD",
        "EUR_GBP", "EUR_JPY", "EUR_CHF", "EUR_CAD", "EUR_AUD", "EUR_NZD",
        "GBP_JPY", "GBP_CHF", "GBP_CAD", "GBP_AUD", "GBP_NZD",
        "CHF_JPY", "CAD_JPY", "AUD_JPY", "NZD_JPY",
        "AUD_CAD", "AUD_CHF", "AUD_NZD", "CAD_CHF", "NZD_CAD", "NZD_CHF",
        "XAU_USD"
    ]

    if st.button("🚀 Lancer le Scan des Signaux Alignés", type="primary"):
        timeframes_to_scan = ["M15", "H1", "H4"]
        # On stocke tous les résultats dans une structure unique pour la synthèse
        all_results = {}

        progress_bar = st.progress(0, text="Lancement de l'analyse multi-temporelle...")
        total_scans = len(pairs_to_scan) * len(timeframes_to_scan)
        scan_count = 0

        for pair in pairs_to_scan:
            all_results[pair] = {}
            for timeframe in timeframes_to_scan:
                scan_count += 1
                progress_bar.progress(scan_count / total_scans, text=f"Analyse de {pair} sur {timeframe}...")

                df_full = get_ohlc_data(client, pair, count=200, granularity=timeframe)
                if df_full is not None and not df_full.empty:
                    df_ichimoku = calculate_ichimoku(df_full.copy())
                    analysis = analyze_ichimoku_status(df_ichimoku)
                    all_results[pair][timeframe] = analysis
        
        progress_bar.empty()

        # --- DÉBUT DE LA SECTION MODIFIÉE (2/2) ---
        # Logique de synthèse pour créer le tableau final.
        
        aligned_signals = []
        for pair, tf_results in all_results.items():
            strong_buy_count = sum(1 for tf in timeframes_to_scan if tf_results.get(tf, {}).get("is_strong_buy"))
            strong_sell_count = sum(1 for tf in timeframes_to_scan if tf_results.get(tf, {}).get("is_strong_sell"))
            
            tendance = None
            if strong_buy_count >= 2:
                tendance = "🟢 Achat Aligné"
            elif strong_sell_count >= 2:
                tendance = "🔴 Vente Alignée"
            
            if tendance:
                signal_row = {"Paire": pair, "Tendance": tendance}
                for tf in timeframes_to_scan:
                    signal_row[f"Score {tf}"] = tf_results.get(tf, {}).get("Score_visuel", "N/A")
                aligned_signals.append(signal_row)

        st.subheader("🚨 Synthèse des Signaux Forts Alignés")

        if aligned_signals:
            results_df = pd.DataFrame(aligned_signals).set_index("Paire")
            st.dataframe(results_df, use_container_width=True)
            st.success(f"Analyse terminée. {len(aligned_signals)} paire(s) avec des signaux forts alignés trouvée(s).")
        else:
            st.info("Aucun signal fort aligné sur au moins 2 unités de temps n'a été trouvé pour cette analyse.")
        # --- FIN DE LA SECTION MODIFIÉE (2/2) ---
else:
    st.error("L'application ne peut pas démarrer. Vérifiez vos secrets OANDA.")
