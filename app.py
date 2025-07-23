import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib
from oandapyV20 import API
from oandapyV20.exceptions import V20Error
from oandapyV20.endpoints.instruments import InstrumentsCandles

# --- Configuration de la page ---
matplotlib.use("Agg")
st.set_page_config(page_title="Scanner Ichimoku Pro", layout="wide")

# --- Fonctions Cœur ---

@st.cache_resource(ttl=3600)
def get_oanda_client():
    """Initialise le client API en lisant les secrets Streamlit."""
    try:
        access_token = st.secrets["OANDA_ACCESS_TOKEN"]
        return API(access_token=access_token)
    except (KeyError, AttributeError):
        st.error("Erreur de configuration : Le secret 'OANDA_ACCESS_TOKEN' est introuvable.")
        return None

@st.cache_data(ttl=300)
def get_ohlc_data(_client, pair, count, granularity):
    """Récupère les données OHLC."""
    if not _client: return None
    params = {"count": count, "granularity": granularity, "price": "M"}
    r = InstrumentsCandles(instrument=pair, params=params)
    try:
        _client.request(r)
        data = [{"Time": c["time"], "Open": float(c["mid"]["o"]), "High": float(c["mid"]["h"]), "Low": float(c["mid"]["l"]), "Close": float(c["mid"]["c"])} for c in r.response.get("candles", []) if c.get("complete")]
        if not data: return None
        df = pd.DataFrame(data)
        df["Time"] = pd.to_datetime(df["Time"])
        return df.set_index("Time")
    except V20Error:
        return None

def calculate_ichimoku(df):
    """Calcule toutes les composantes d'Ichimoku."""
    df["Tenkan"] = (df["High"].rolling(window=9).max() + df["Low"].rolling(window=9).min()) / 2
    df["Kijun"] = (df["High"].rolling(window=26).max() + df["Low"].rolling(window=26).min()) / 2
    df["Senkou_A"] = ((df["Tenkan"] + df["Kijun"]) / 2).shift(26)
    df["Senkou_B"] = ((df["High"].rolling(window=52).max() + df["Low"].rolling(window=52).min()) / 2).shift(26)
    df["Chikou"] = df["Close"].shift(-26)
    return df

def find_last_tk_cross(df):
    """Trouve la date du dernier croisement Tenkan/Kijun."""
    is_bullish = df['Tenkan'] > df['Kijun']
    # Un croisement se produit lorsque l'état change par rapport à la bougie précédente
    crosses = is_bullish.ne(is_bullish.shift(1))
    if crosses.any():
        return crosses[crosses].index[-1]
    return pd.NaT # Retourne "Not a Time" si aucun croisement n'est trouvé

def analyze_ichimoku_status(df):
    """Analyse complète l'état d'Ichimoku et retourne un statut détaillé."""
    if df is None or len(df) < 78:
        return {"Statut": "Données Insuffisantes", "Conditions": {}, "cross_time": pd.NaT}

    last = df.iloc[-2]
    last_chikou = df.iloc[-28]
    cross_time = find_last_tk_cross(df)

    conditions = {"Prix vs Kumo": "Neutre", "Croisement TK": "Neutre", "Chikou Libre": "Neutre", "Kumo Futur": "Neutre"}
    
    if last["Close"] > last["Senkou_A"] and last["Close"] > last["Senkou_B"]: conditions["Prix vs Kumo"] = "✅ Haussier"
    elif last["Close"] < last["Senkou_A"] and last["Close"] < last["Senkou_B"]: conditions["Prix vs Kumo"] = "❌ Baissier"
    
    if last["Tenkan"] > last["Kijun"]: conditions["Croisement TK"] = "✅ Haussier"
    elif last["Tenkan"] < last["Kijun"]: conditions["Croisement TK"] = "❌ Baissier"
    
    if last["Chikou"] > last_chikou["High"]: conditions["Chikou Libre"] = "✅ Haussier"
    elif last["Chikou"] < last_chikou["Low"]: conditions["Chikou Libre"] = "❌ Baissier"

    if last["Senkou_A"] > last["Senkou_B"]: conditions["Kumo Futur"] = "✅ Haussier"
    elif last["Senkou_A"] < last["Senkou_B"]: conditions["Kumo Futur"] = "❌ Baissier"

    is_buy = all(c.startswith("✅") for c in conditions.values())
    is_sell = all(c.startswith("❌") for c in conditions.values())
    
    status = "🟡 Neutre"
    if is_buy: status = "🟢 ACHAT FORT"
    elif is_sell: status = "🔴 VENTE FORTE"
        
    return {"Statut": status, "Conditions": conditions, "data": df, "cross_time": cross_time}

def plot_ichimoku(df, pair, granularity):
    """Crée le graphique Matplotlib."""
    fig, ax = plt.subplots(figsize=(12, 7))
    ax.plot(df.index, df["Close"], label="Prix", color="black", lw=1.5)
    # ... (code de tracé identique, pas besoin de le répéter ici)
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
        pairs_to_scan = st.multiselect(
            "Choisissez les paires à analyser",
            ["EUR_USD", "GBP_USD", "USD_JPY", "USD_CAD", "AUD_USD", "NZD_USD", "USD_CHF", "EUR_JPY", "GBP_JPY", "XAU_USD"],
            default=["EUR_USD", "GBP_USD", "USD_JPY", "XAU_USD", "AUD_USD"]
        )

    if st.button("🚀 Lancer le Scan (H1 & H4)", type="primary"):
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
                    
                    df = get_ohlc_data(client, pair, count=200, granularity=timeframe) # 200 pour avoir assez de données pour le croisement
                    if df is not None:
                        df_ichimoku = calculate_ichimoku(df.copy())
                        analysis = analyze_ichimoku_status(df_ichimoku)
                        
                        row = {"Paire": pair, "Statut Global": analysis["Statut"]}
                        row.update(analysis["Conditions"])
                        row["cross_time_obj"] = analysis["cross_time"] # Pour la comparaison
                        
                        all_results_by_tf[timeframe].append((row, analysis.get("data")))
                        if pd.notna(analysis["cross_time"]):
                            all_cross_times.append(analysis["cross_time"])

            progress_bar.empty()
            
            most_recent_cross_time = max(all_cross_times) if all_cross_times else pd.NaT

            for timeframe, results in all_results_by_tf.items():
                st.subheader(f"📊 Tableau de Bord des Résultats ({timeframe})")
                if results:
                    # Préparation des données pour l'affichage
                    display_data = []
                    for row_data, _ in results:
                        cross_time = row_data["cross_time_obj"]
                        
                        # Formatage de l'heure du croisement
                        if pd.notna(cross_time):
                            time_str = cross_time.strftime("%Y-%m-%d %H:%M")
                            if cross_time == most_recent_cross_time:
                                time_str += " ⭐" # Ajout de l'étoile
                        else:
                            time_str = "N/A"
                        
                        row_data["Dernier Croisement TK"] = time_str
                        del row_data["cross_time_obj"] # Nettoyage avant affichage
                        display_data.append(row_data)

                    results_df = pd.DataFrame(display_data).set_index("Paire")
                    st.dataframe(results_df, use_container_width=True)

                    # Affichage des graphiques pour les signaux forts
                    strong_signals = [res for res in results if "FORT" in res[0]["Statut Global"]]
                    if strong_signals:
                        st.markdown(f"**Graphiques des signaux forts détectés sur {timeframe} :**")
                        for result, data in strong_signals:
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
