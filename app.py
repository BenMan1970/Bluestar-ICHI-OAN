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

# --- Fonctions Cœur (inchangées) ---

@st.cache_resource(ttl=3600)
def get_oanda_client():
    """Initialise le client API en lisant les secrets Streamlit."""
    try:
        access_token = st.secrets["OANDA_ACCESS_TOKEN"]
        return API(access_token=access_token)
    except (KeyError, AttributeError):
        st.error("Erreur de configuration : Le secret 'OANDA_ACCESS_TOKEN' est introuvable. Veuillez le configurer dans vos secrets Streamlit.")
        return None

@st.cache_data(ttl=300) # Cache de 5 minutes
def get_ohlc_data(_client, pair, count, granularity):
    """Récupère les données OHLC pour une paire et une granularité données."""
    if not _client: return None
    params = {"count": count, "granularity": granularity, "price": "M"}
    r = InstrumentsCandles(instrument=pair, params=params)
    try:
        _client.request(r)
        data = [
            {"Time": c["time"], "Open": float(c["mid"]["o"]), "High": float(c["mid"]["h"]), "Low": float(c["mid"]["l"]), "Close": float(c["mid"]["c"])}
            for c in r.response.get("candles", []) if c.get("complete")
        ]
        if not data: return None
        df = pd.DataFrame(data).set_index(pd.to_datetime(pd.DataFrame(data)['Time'])).drop('Time', axis=1)
        return df
    except V20Error as e:
        st.warning(f"Données non disponibles pour {pair} sur {granularity}. API: {e}")
        return None

def calculate_ichimoku(df):
    """Calcule toutes les composantes d'Ichimoku."""
    df["Tenkan"] = (df["High"].rolling(window=9).max() + df["Low"].rolling(window=9).min()) / 2
    df["Kijun"] = (df["High"].rolling(window=26).max() + df["Low"].rolling(window=26).min()) / 2
    df["Senkou_A"] = ((df["Tenkan"] + df["Kijun"]) / 2).shift(26)
    df["Senkou_B"] = ((df["High"].rolling(window=52).max() + df["Low"].rolling(window=52).min()) / 2).shift(26)
    df["Chikou"] = df["Close"].shift(-26)
    return df

# --- NOUVELLE FONCTION D'ANALYSE DÉTAILLÉE ---

def analyze_ichimoku_status(df):
    """Analyse complète l'état d'Ichimoku et retourne un statut détaillé."""
    if df is None or len(df) < 78:
        return {"Statut": "Données Insuffisantes", "Conditions": {}}

    last = df.iloc[-2]  # Dernière bougie clôturée
    last_chikou = df.iloc[-28] # Bougie de référence pour la Chikou

    conditions = {
        "Prix vs Kumo": "Neutre",
        "Croisement TK": "Neutre",
        "Chikou Libre": "Neutre",
        "Kumo Futur": "Neutre",
    }
    
    # 1. Position du Prix par rapport au Kumo (Nuage)
    if last["Close"] > last["Senkou_A"] and last["Close"] > last["Senkou_B"]: conditions["Prix vs Kumo"] = "✅ Haussier"
    elif last["Close"] < last["Senkou_A"] and last["Close"] < last["Senkou_B"]: conditions["Prix vs Kumo"] = "❌ Baissier"
    
    # 2. Croisement Tenkan-sen / Kijun-sen
    if last["Tenkan"] > last["Kijun"]: conditions["Croisement TK"] = "✅ Haussier"
    elif last["Tenkan"] < last["Kijun"]: conditions["Croisement TK"] = "❌ Baissier"
    
    # 3. Position de la Chikou Span (Lagging Span)
    if last["Chikou"] > last_chikou["High"]: conditions["Chikou Libre"] = "✅ Haussier"
    elif last["Chikou"] < last_chikou["Low"]: conditions["Chikou Libre"] = "❌ Baissier"

    # 4. Couleur du Kumo futur
    if last["Senkou_A"] > last["Senkou_B"]: conditions["Kumo Futur"] = "✅ Haussier"
    elif last["Senkou_A"] < last["Senkou_B"]: conditions["Kumo Futur"] = "❌ Baissier"

    # Détermination du statut global
    is_buy = all(c.startswith("✅") for c in conditions.values())
    is_sell = all(c.startswith("❌") for c in conditions.values())
    
    if is_buy:
        status = "🟢 ACHAT FORT"
    elif is_sell:
        status = "🔴 VENTE FORTE"
    else:
        status = "🟡 Neutre"
        
    return {"Statut": status, "Conditions": conditions, "data": df}


def plot_ichimoku(df, pair, granularity):
    """Crée le graphique Matplotlib."""
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

st.title("🔎 Scanner Ichimoku Pro")
st.markdown("Un tableau de bord pour analyser les conditions Ichimoku sur plusieurs paires et unités de temps.")

client = get_oanda_client()

if client:
    # --- Panneau de configuration ---
    with st.expander("⚙️ Configuration du Scan", expanded=True):
        col1, col2 = st.columns(2)
        with col1:
            timeframe = st.selectbox(
                "Choisissez une unité de temps",
                ("H1", "H4", "D"),
                index=0,
                help="H1=1 Heure, H4=4 Heures, D=Journalier"
            )
        with col2:
            pairs_to_scan = st.multiselect(
                "Choisissez les paires à analyser",
                ["EUR_USD", "GBP_USD", "USD_JPY", "USD_CAD", "AUD_USD", "NZD_USD", "USD_CHF", "EUR_JPY", "GBP_JPY", "XAU_USD"],
                default=["EUR_USD", "GBP_USD", "USD_JPY", "XAU_USD"]
            )

    if st.button("🚀 Lancer le Scan", type="primary"):
        if not pairs_to_scan:
            st.warning("Veuillez sélectionner au moins une paire à analyser.")
        else:
            all_results = []
            progress_bar = st.progress(0, text="Lancement de l'analyse...")
            
            for i, pair in enumerate(pairs_to_scan):
                df = get_ohlc_data(client, pair, count=150, granularity=timeframe)
                if df is not None:
                    df_ichimoku = calculate_ichimoku(df.copy())
                    analysis = analyze_ichimoku_status(df_ichimoku)
                    
                    row = {"Paire": pair, "Statut Global": analysis["Statut"]}
                    row.update(analysis["Conditions"]) # Ajoute les colonnes de conditions
                    all_results.append((row, analysis.get("data")))
                
                progress_bar.progress((i + 1) / len(pairs_to_scan), text=f"Analyse de {pair}...")
            
            progress_bar.empty()

            if all_results:
                # Affichage du tableau de bord des résultats
                st.subheader(f"📊 Tableau de Bord des Résultats ({timeframe})")
                results_df = pd.DataFrame([res[0] for res in all_results])
                st.dataframe(results_df.set_index("Paire"), use_container_width=True)

                # Affichage des graphiques pour les signaux forts
                strong_signals = [res for res in all_results if "FORT" in res[0]["Statut Global"]]
                if strong_signals:
                    st.subheader("📈 Graphiques des Signaux Forts")
                    for result, data in strong_signals:
                        with st.expander(f"Graphique pour {result['Paire']} - {result['Statut Global']}", expanded=True):
                            fig = plot_ichimoku(data, result['Paire'], timeframe)
                            st.pyplot(fig)
                            plt.close(fig)
                else:
                    st.info("Aucun signal d'achat ou de vente fort détecté pour cette analyse.")

            else:
                st.error("Aucune donnée n'a pu être récupérée pour les paires sélectionnées.")
else:
    st.error("L'application ne peut pas démarrer. Vérifiez vos secrets OANDA.")
