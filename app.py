import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib
import pytz
import numpy as np  # Ajout de la bibliothèque NumPy pour les calculs
from oandapyV20 import API
from oandapyV20.exceptions import V20Error
from oandapyV20.endpoints.instruments import InstrumentsCandles

# --- Configuration de la page ---
matplotlib.use("Agg")
st.set_page_config(page_title="Scanner Ichimoku Pro", layout="wide")

# --- Fonctions Cœur ---

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

# --- NOUVELLE FONCTION DE DÉTECTION DE CROISEMENT (ROBUSTE) ---
def find_last_tk_cross_info(df):
    """
    Trouve l'heure et la direction du dernier croisement Tenkan/Kijun
    en utilisant une méthode mathématique fiable.
    """
    # 1. Calculer la position relative de Tenkan par rapport à Kijun
    #    +1.0 si Tenkan > Kijun, -1.0 si Tenkan < Kijun
    df['tk_position'] = np.sign(df['Tenkan'] - df['Kijun'])
    
    # 2. Un croisement se produit là où la différence de position entre une bougie et la précédente n'est pas nulle
    df['tk_cross'] = df['tk_position'].diff()
    
    # 3. Trouver la dernière fois où un croisement s'est produit
    cross_events = df[df['tk_cross'] != 0]
    
    if not cross_events.empty:
        last_cross_time = cross_events.index[-1]
        
        # 4. Déterminer la direction en regardant la position APRÈS le croisement
        #    Si tk_cross est > 0 (ex: passe de -1 à +1), c'est un croisement haussier
        #    Si tk_cross est < 0 (ex: passe de +1 à -1), c'est un croisement baissier
        last_cross_event = cross_events.iloc[-1]
        
        if last_cross_event['tk_cross'] > 0:
            direction = "✅ Haussier"
        elif last_cross_event['tk_cross'] < 0:
            direction = "❌ Baissier"
        else:
            direction = "Neutre" # Cas improbable
            
        return last_cross_time, direction
        
    return pd.NaT, "Neutre"


def analyze_ichimoku_status(df):
    if df is None or len(df) < 79:
        return {"Statut": "Données Insuffisantes", "Conditions": {}, "cross_time": pd.NaT}

    cross_time, cross_direction = find_last_tk_cross_info(df)

    last_closed = df.iloc[-2]
    chikou_ref_closed = df.iloc[-28]

    conditions = {"Prix vs Kumo": "Neutre", "Croisement TK": cross_direction, "Chikou Libre": "Neutre", "Kumo Futur": "Neutre"}
    
    if last_closed["Close"] > last_closed["Senkou_A"] and last_closed["Close"] > last_closed["Senkou_B"]: conditions["Prix vs Kumo"] = "✅ Haussier"
    elif last_closed["Close"] < last_closed["Senkou_A"] and last_closed["Close"] < last_closed["Senkou_B"]: conditions["Prix vs Kumo"] = "❌ Baissier"
    if last_closed["Chikou"] > chikou_ref_closed["High"]: conditions["Chikou Libre"] = "✅ Haussier"
    elif last_closed["Chikou"] < chikou_ref_closed["Low"]: conditions["Chikou Libre"] = "❌ Baissier"
    if last_closed["Senkou_A"] > last_closed["Senkou_B"]: conditions["Kumo Futur"] = "✅ Haussier"
    elif last_closed["Senkou_A"] < last_closed["Senkou_B"]: conditions["Kumo Futur"] = "❌ Baissier"

    is_buy = all(c.startswith("✅") for c in conditions.values())
    is_sell = all(c.startswith("❌") for c in conditions.values())
    
    status = "🟡 Neutre"
    if is_buy: status = "🟢 ACHAT FORT"
    elif is_sell: status = "🔴 VENTE FORTE"
        
    return {"Statut": status, "Conditions": conditions, "data": df, "cross_time": cross_time}

def plot_ichimoku(df, pair, granularity):
    # Identique à avant
    fig, ax = plt.subplots(figsize=(12, 7))
    ax.plot(df.index, df["Close"], label="Prix", color="black", lw=1.5)
    ax.plot(df.index, df["Tenkan"], label="Tenkan", color="blue", lw=1)
    ax.plot(df.index, df["Kijun"], label="Kijun", color="red", lw=1)
    ax.plot(df.index, df["Chikou"], label="Chikou", color="purple", lw=1.2, ls='--')
    ax.fill_between(df.index, df["Senkou_A"], df["Senkou_B"], where=df["Senkou_A"] >= df["Senkou_B"], color='lightgreen', alpha=0.4, label="Kumo Haussier")
    ax.fill_between(df.index, df["Senkou_A"], df["Senkou_B"], where=df["Senkou_A"] < df["Senkou_B"], color='lightcoral', alpha=0.4, label="Kumo Baissier")
    ax.set_title(f"Ichimoku pour {pair} ({granularity})", fontsize=16)
    ax.legend()
    ax.grid(True, linestyle='--', alpha=0.6)
    plt.tight_layout()
    return fig

# --- INTERFACE UTILISATEUR STREAMLIT ---

st.title("🔎 Scanner Ichimoku Pro (H1 & H4)")
st.markdown("Analyse simultanée des conditions Ichimoku sur les unités de temps H1 et H4.")

client = get_oanda_client()

if client:
    with st.expander("⚙️ Configuration du Scan", expanded=True):
        col1, col2 = st.columns(2)
        with col1:
            pairs_to_scan = st.multiselect(
                "Choisissez les paires à analyser",
                ["EUR_USD", "GBP_USD", "USD_JPY", "USD_CAD", "AUD_USD", "NZD_USD", "USD_CHF", "EUR_JPY", "GBP_JPY", "XAU_USD"],
                default=["EUR_USD", "GBP_USD", "USD_JPY", "XAU_USD", "AUD_USD"]
            )
        with col2:
            timezone_options = {
                "GMT+1": "Etc/GMT-1",
                "Paris / Berlin (GMT+2)": "Europe/Paris",
                "Londres (GMT+1 / BST)": "Europe/London",
                "New York (GMT-4 / EDT)": "America/New_York",
                "Tokyo (GMT+9)": "Asia/Tokyo",
                "UTC (Temps Universel)": "UTC"
            }
            friendly_names = list(timezone_options.keys())
            default_index = friendly_names.index("GMT+1")

            selected_friendly_name = st.selectbox(
                "Choisissez votre fuseau horaire",
                options=friendly_names,
                index=default_index,
                help="Les heures des croisements seront affichées dans ce fuseau horaire."
            )
            selected_timezone = timezone_options[selected_friendly_name]

    if st.button("🚀 Lancer le Scan (H1 & H4)", type="primary"):
        # Le reste du code est identique et correct
        if not pairs_to_scan:
            st.warning("Veuillez sélectionner au moins une paire.")
        else:
            timeframes_to_scan = ["H1", "H4"]
            all_results_by_tf = {tf: [] for tf in timeframes_to_scan}
            all_cross_times = []

            progress_bar = st.progress(0, text="Lancement de l'analyse multi-temporelle...")
            total_scans = len(pairs_to_scan) * len(timeframes_to_scan)
            scan_count = 0

            for timeframe in timeframes_to_scan:
                for pair in pairs_to_scan:
                    scan_count += 1
                    progress_bar.progress(scan_count / total_scans, text=f"Analyse de {pair} sur {timeframe}...")
                    
                    df = get_ohlc_data(client, pair, count=200, granularity=timeframe)
                    if df is not None:
                        df_ichimoku = calculate_ichimoku(df.copy())
                        analysis = analyze_ichimoku_status(df_ichimoku)
                        
                        row = {"Paire": pair, "Statut Global": analysis["Statut"]}
                        row.update(analysis["Conditions"])
                        row["cross_time_obj"] = analysis["cross_time"]
                        
                        all_results_by_tf[timeframe].append((row, analysis.get("data")))
                        if pd.notna(analysis["cross_time"]):
                            all_cross_times.append(analysis["cross_time"])

            progress_bar.empty()
            
            most_recent_cross_time = max(all_cross_times) if all_cross_times else pd.NaT

            for timeframe, results in all_results_by_tf.items():
                st.subheader(f"📊 Tableau de Bord des Résultats ({timeframe})")
                if results:
                    display_data = []
                    for row_data, _ in results:
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

                    results_df = pd.DataFrame(display_data).set_index("Paire")
                    
                    results_df['is_starred'] = results_df['Dernier Croisement TK'].str.contains("⭐", na=False)
                    results_df['sort_time'] = pd.to_datetime(results_df['Dernier Croisement TK'].str.replace(" ⭐", "", regex=False), errors='coerce')
                    results_df = results_df.sort_values(by=['is_starred', 'sort_time'], ascending=[False, False])
                    results_df = results_df.drop(columns=['sort_time', 'is_starred'])
                    
                    st.dataframe(results_df, use_container_width=True)

                    strong_signals = [res for res in results if "FORT" in res[0]["Statut Global"]]
                    if strong_signals:
                        st.markdown(f"**Graphiques des signaux forts détectés sur {timeframe} :**")
                        for result, data in strong_signals:
                            if "FORT" in result["Statut Global"]:
                                with st.expander(f"Graphique pour {result['Paire']} - {result['Statut Global']}", expanded=True):
                                    fig = plot_ichimoku(data, result['Paire'], timeframe)
                                    st.pyplot(fig)
                                    plt.close(fig)
                    else:
                        st.info(f"Aucun signal fort détecté sur {timeframe} pour cette analyse.")
                else:
                    st.warning(f"Aucune donnée n'a pu être récupérée pour l'unité de temps {timeframe}.")
else:
    st.error("L'application ne peut pas démarrer. Vérifiez vos secrets OANDA.")
