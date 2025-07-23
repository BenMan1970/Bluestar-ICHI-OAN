import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib
from oandapyV20 import API
from oandapyV20.exceptions import V20Error
from oandapyV20.endpoints.instruments import InstrumentsCandles

# Configuration de la page et du backend Matplotlib
matplotlib.use("Agg")  # Indispensable pour Streamlit Cloud
st.set_page_config(page_title="Scan Ichimoku", layout="wide")

# --- Fonctions de l'application ---

@st.cache_resource(ttl=3600) # Met en cache le client API pendant 1 heure
def get_oanda_client():
    """Initialise et retourne le client API OANDA en lisant les secrets."""
    try:
        # Structure recommandée pour les secrets Streamlit
        access_token = st.secrets["oanda"]["api_key"]
        environment = st.secrets["oanda"].get("environment", "practice") # 'practice' par défaut
        return API(access_token=access_token, environment=environment)
    except (KeyError, AttributeError):
        st.error("Erreur de configuration des secrets OANDA. Assurez-vous que votre fichier secrets.toml contient une section [oanda] avec une 'api_key'.")
        return None

@st.cache_data(ttl=600) # Met en cache les données d'une paire pendant 10 minutes
def get_ohlc_data(_client, pair, count=150, granularity="H1"):
    """Récupère les données OHLC complètes pour une paire via l'API OANDA."""
    if not _client:
        return None
        
    params = {"count": count, "granularity": granularity, "price": "M"}
    r = InstrumentsCandles(instrument=pair, params=params)
    
    try:
        _client.request(r)
        data = [
            {
                "Time": candle["time"],
                "Open": float(candle["mid"]["o"]),
                "High": float(candle["mid"]["h"]),
                "Low": float(candle["mid"]["l"]),
                "Close": float(candle["mid"]["c"]),
            }
            for candle in r.response.get("candles", []) if candle.get("complete")
        ]
        
        if not data:
            return None

        df = pd.DataFrame(data)
        df["Time"] = pd.to_datetime(df["Time"])
        return df.set_index("Time")
    except V20Error as e:
        st.warning(f"Impossible de récupérer les données pour {pair}. Erreur API : {e}")
        return None

def calculate_ichimoku(df):
    """Calcule et ajoute les composantes Ichimoku à un DataFrame."""
    df["Tenkan"] = (df["High"].rolling(window=9).max() + df["Low"].rolling(window=9).min()) / 2
    df["Kijun"] = (df["High"].rolling(window=26).max() + df["Low"].rolling(window=26).min()) / 2
    df["Senkou_A"] = ((df["Tenkan"] + df["Kijun"]) / 2).shift(26)
    df["Senkou_B"] = ((df["High"].rolling(window=52).max() + df["Low"].rolling(window=52).min()) / 2).shift(26)
    df["Chikou"] = df["Close"].shift(-26)
    return df

def check_strong_buy_signal(df):
    """Vérifie un signal d'achat Ichimoku fort sur la dernière bougie clôturée."""
    if len(df) < 78:  # Nécessaire pour le calcul de Chikou (52 + 26)
        return False

    # Analyse sur la dernière bougie clôturée (avant-dernière ligne)
    last_candle = df.iloc[-2]
    
    # Prix de référence pour la Chikou Span (il y a 26 périodes)
    chikou_price_ref = df['Close'].iloc[-28]
    
    # Conditions pour un signal d'achat fort
    is_tenkan_above_kijun = last_candle["Tenkan"] > last_candle["Kijun"]
    is_price_above_kumo = last_candle["Close"] > last_candle["Senkou_A"] and last_candle["Close"] > last_candle["Senkou_B"]
    is_chikou_above_price = last_candle['Chikou'] > chikou_price_ref
    is_kumo_bullish = last_candle["Senkou_A"] > last_candle["Senkou_B"]
    
    # Toutes les conditions doivent être réunies
    return all([is_tenkan_above_kijun, is_price_above_kumo, is_chikou_above_price, is_kumo_bullish])

def plot_ichimoku(df, pair):
    """Crée un graphique Matplotlib pour l'indicateur Ichimoku."""
    fig, ax = plt.subplots(figsize=(12, 7))
    
    ax.plot(df.index, df["Close"], label="Prix de Clôture", color="black", linewidth=1.5)
    ax.plot(df.index, df["Tenkan"], label="Tenkan-sen", color="blue", linewidth=1)
    ax.plot(df.index, df["Kijun"], label="Kijun-sen", color="red", linewidth=1)
    ax.plot(df.index, df["Chikou"], label="Chikou Span", color="purple", linewidth=1.2, linestyle='--')
    
    ax.fill_between(df.index, df["Senkou_A"], df["Senkou_B"], 
                    where=df["Senkou_A"] >= df["Senkou_B"], color='lightgreen', alpha=0.4, label="Kumo haussier")
    ax.fill_between(df.index, df["Senkou_A"], df["Senkou_B"], 
                    where=df["Senkou_A"] < df["Senkou_B"], color='lightcoral', alpha=0.4, label="Kumo baissier")

    ax.set_title(f"Graphique Ichimoku pour {pair}", fontsize=16)
    ax.set_ylabel("Prix")
    ax.legend()
    ax.grid(True, linestyle='--', alpha=0.6)
    plt.tight_layout()
    return fig

# --- Interface Principale Streamlit ---

st.title("🔍 Scan de Signaux Ichimoku Forts")
st.markdown("Cette application analyse plusieurs paires de devises pour détecter des signaux d'achat Ichimoku robustes en temps quasi réel.")

client = get_oanda_client()

if client:
    pairs_to_scan = [
        "EUR_USD", "GBP_USD", "USD_JPY", "USD_CAD", "AUD_USD", 
        "NZD_USD", "USD_CHF", "EUR_JPY", "GBP_JPY", "XAU_USD" # Or
    ]
    
    strong_signal_pairs = []
    
    with st.spinner(f"Analyse de {len(pairs_to_scan)} paires en cours..."):
        for pair in pairs_to_scan:
            df = get_ohlc_data(client, pair)
            if df is not None and not df.empty:
                df_ichimoku = calculate_ichimoku(df.copy())
                if check_strong_buy_signal(df_ichimoku):
                    strong_signal_pairs.append((pair, df_ichimoku))

    if strong_signal_pairs:
        st.success(f"**{len(strong_signal_pairs)} paire(s) avec un signal d'achat fort détecté !**")
        
        results_df = pd.DataFrame([pair for pair, _ in strong_signal_pairs], columns=["Paires avec signal"])
        st.dataframe(results_df)

        st.download_button(
            label="📥 Télécharger la liste en CSV",
            data=results_df.to_csv(index=False).encode('utf-8'),
            file_name='signaux_ichimoku.csv',
            mime='text/csv',
        )
        st.divider()

        for pair, df in strong_signal_pairs:
            with st.expander(f"Voir le graphique pour {pair}", expanded=True):
                fig = plot_ichimoku(df, pair)
                st.pyplot(fig)
                plt.close(fig) # Libère la mémoire après l'affichage

    else:
        st.info("Aucun signal d'achat fort détecté pour le moment parmi les paires analysées.")

else:
    st.warning("L'application n'a pas pu démarrer. Veuillez vérifier la configuration de vos secrets OANDA.")
