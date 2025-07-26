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

    if last_bullish and (not last_bearish or last_bullish > last_bearish):
        return last_bullish
    elif last_bearish and (not last_bullish or last_bearish > last_bullish):
        return last_bearish
    else:
        return pd.NaT

def generate_visual_score(score):
    if score > 0:
        return '🔵' * score
    elif score < 0:
        return '🔴' * abs(score)
    elif score == 0:
        return '⚪'
    return "N/A"

def analyze_ichimoku_status(df_full):
    if df_full is None or len(df_full) < 79:
        conditions = {
            "1. Prix / Nuage": "N/A", "2. Tenkan / Kijun": "N/A",
            "3. Kumo Futur": "N/A", "4. Chikou": "N/A"
        }
        return {"Score": "N/A", "Statut": "Données Insuffisantes", "Conditions": conditions, "cross_time": pd.NaT}

    cross_time = find_last_tk_cross_info(df_full)
    last_closed = df_full.iloc[-2]
    score = 0
    conditions = {}

    # 1. Prix par rapport au nuage
    if pd.notna(last_closed["Senkou_A"]) and pd.notna(last_closed["Senkou_B"]):
        kumo_high = max(last_closed["Senkou_A"], last_closed["Senkou_B"])
        kumo_low = min(last_closed["Senkou_A"], last_closed["Senkou_B"])
        if last_closed["Close"] > kumo_high:
            score += 1
            conditions["1. Prix / Nuage"] = "✅ Au-dessus"
        elif last_closed["Close"] < kumo_low:
            score -= 1
            conditions["1. Prix / Nuage"] = "🔴 En dessous"
        else:
            conditions["1. Prix / Nuage"] = "🟡 Neutre (dedans)"
    else:
        conditions["1. Prix / Nuage"] = "N/A"

    # 2. Tenkan / Kijun
    if pd.notna(last_closed["Tenkan"]) and pd.notna(last_closed["Kijun"]):
        if last_closed["Tenkan"] > last_closed["Kijun"]:
            score += 1
            conditions["2. Tenkan / Kijun"] = "✅ Haussier"
        elif last_closed["Tenkan"] < last_closed["Kijun"]:
            score -= 1
            conditions["2. Tenkan / Kijun"] = "🔴 Baissier"
        else:
            conditions["2. Tenkan / Kijun"] = "🟡 Neutre"
    else:
        conditions["2. Tenkan / Kijun"] = "N/A"

    # 3. Kumo futur
    if pd.notna(last_closed["Senkou_A"]) and pd.notna(last_closed["Senkou_B"]):
        if last_closed["Senkou_A"] > last_closed["Senkou_B"]:
            score += 1
            conditions["3. Kumo Futur"] = "✅ Vert"
        elif last_closed["Senkou_A"] < last_closed["Senkou_B"]:
            score -= 1
            conditions["3. Kumo Futur"] = "🔴 Rouge"
        else:
            conditions["3. Kumo Futur"] = "🟡 Plat"
    else:
        conditions["3. Kumo Futur"] = "N/A"

    # 4. Chikou
    if len(df_full) > 27:
        chikou_value = last_closed['Close']
        past_candle = df_full.iloc[-27]
        if pd.notna(chikou_value) and pd.notna(past_candle['High']) and pd.notna(past_candle['Senkou_A']) and pd.notna(past_candle['Senkou_B']):
            past_price_high = past_candle['High']
            past_kumo_high = max(past_candle['Senkou_A'], past_candle['Senkou_B'])
            if chikou_value > past_price_high and chikou_value > past_kumo_high:
                score += 1
                conditions["4. Chikou"] = "✅ Libre (Haut)"
            else:
                score -= 1
                conditions["4. Chikou"] = "🔴 Bloqué/Bas"
        else:
            conditions["4. Chikou"] = "N/A"
    else:
        conditions["4. Chikou"] = "N/A"

    if score == 4: status = "🟢 ACHAT FORT"
    elif score > 0: status = f"✅ Haussier"
    elif score == -4: status = "🔴 VENTE FORTE"
    elif score < 0: status = f"🔴 Baissier"
    else: status = "🟡 Neutre"
    
    visual_score = generate_visual_score(score)

    return {"Score": visual_score, "Statut": status, "Conditions": conditions, "cross_time": cross_time}

st.title("🔎 Scanner Ichimoku Pro (M15, H1 & H4)")
st.markdown("Analyse simultanée des conditions Ichimoku sur les unités de temps M15, H1 et H4.")

client = get_oanda_client()

if client:
    with st.expander("⚙️ Configuration du Scan", expanded=False):
        col1, col2 = st.columns(2)
        with col2:
            timezone_options = {
                "GMT+1": "Etc/GMT-1",
                "Paris / Berlin (GMT+2)": "Europe/Paris",
                "Londres (GMT+1 / BST)": "Europe/London",
                "New York (GMT-4 / EDT)": "America/New_York",
                "Tokyo (GMT+9)": "Asia/Tokyo",
                "UTC (Temps Universel)": "UTC"
            }
            selected_friendly_name = st.selectbox("Choisissez votre fuseau horaire", options=list(timezone_options.keys()), index=0)
            selected_timezone = timezone_options[selected_friendly_name]

    pairs_to_scan = [
        "EUR_USD", "GBP_USD", "USD_JPY", "USD_CHF", "USD_CAD", "AUD_USD", "NZD_USD",
        "EUR_GBP", "EUR_JPY", "EUR_CHF", "EUR_CAD", "EUR_AUD", "EUR_NZD",
        "GBP_JPY", "GBP_CHF", "GBP_CAD", "GBP_AUD", "GBP_NZD",
        "CHF_JPY", "CAD_JPY", "AUD_JPY", "NZD_JPY",
        "AUD_CAD", "AUD_CHF", "AUD_NZD", "CAD_CHF", "NZD_CAD", "NZD_CHF",
        "XAU_USD"
    ]

    if st.button("🚀 Lancer le Scan (M15, H1 & H4)", type="primary"):
        timeframes_to_scan = ["M15", "H1", "H4"]
        all_results_by_tf = {tf: [] for tf in timeframes_to_scan}
        all_cross_times = []

        progress_bar = st.progress(0, text="Lancement de l'analyse multi-temporelle...")
        total_scans = len(pairs_to_scan) * len(timeframes_to_scan)
        scan_count = 0

        for timeframe in timeframes_to_scan:
            for pair in pairs_to_scan:
                scan_count += 1
                progress_bar.progress(scan_count / total_scans, text=f"Analyse de {pair} sur {timeframe}...")

                df_full = get_ohlc_data(client, pair, count=200, granularity=timeframe)
                if df_full is not None and not df_full.empty:
                    df_ichimoku = calculate_ichimoku(df_full.copy())
                    analysis = analyze_ichimoku_status(df_ichimoku)
                    
                    row = {
                        "Paire": pair,
                        "Tendance": analysis["Statut"],
                        "Score": analysis["Score"],
                    }
                    row.update(analysis["Conditions"])
                    
                    row["cross_time_obj"] = analysis["cross_time"]
                    all_results_by_tf[timeframe].append(row)
                    if pd.notna(analysis["cross_time"]):
                        all_cross_times.append(analysis["cross_time"])

        progress_bar.empty()
        most_recent_cross_time = max(all_cross_times) if all_cross_times else pd.NaT

        for timeframe, results in all_results_by_tf.items():
            st.subheader(f"📊 Tableau de Bord des Résultats ({timeframe})")
            if results:
                display_data = []
                for row_data in results:
                    cross_time = row_data["cross_time_obj"]
                    if pd.notna(cross_time):
                        localized_time = cross_time.tz_convert(selected_timezone)
                        time_str = localized_time.strftime("%Y-%m-%d %H:%M")
                        if cross_time == most_recent_cross_time:
                            time_str += " ⭐"
                    else:
                        time_str = "N/A"
                    row_data["Dernier Croisement TK"] = time_str
                    del row_data["cross_time_obj"]
                    display_data.append(row_data)

                results_df = pd.DataFrame(display_data)
                
                cols_order = ["Tendance", "Score", "1. Prix / Nuage", "2. Tenkan / Kijun", 
                              "3. Kumo Futur", "4. Chikou", "Dernier Croisement TK"]
                
                final_cols = [col for col in cols_order if col in results_df.columns]
                results_df = results_df.set_index("Paire")[final_cols]
                
                results_df['is_starred'] = results_df['Dernier Croisement TK'].str.contains("⭐", na=False)
                results_df['sort_time'] = pd.to_datetime(results_df['Dernier Croisement TK'].str.replace(" ⭐", "", regex=False), errors='coerce')
                results_df = results_df.sort_values(by=['is_starred', 'sort_time'], ascending=[False, False])
                results_df = results_df.drop(columns=['sort_time', 'is_starred'])

                st.dataframe(results_df, use_container_width=True, height=600)
            else:
                st.warning(f"Aucune donnée n'a pu être récupérée pour l'unité de temps {timeframe} ou aucun croisement n'a été trouvé.")
else:
    st.error("L'application ne peut pas démarrer. Vérifiez vos secrets OANDA.")
