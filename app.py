import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib
from oandapyV20 import API
from oandapyV20.exceptions import V20Error
from oandapyV20.endpoints.instruments import InstrumentsCandles

# Utiliser le backend "Agg" pour la compatibilité avec les serveurs sans interface graphique (Streamlit Cloud)
matplotlib.use("Agg")

# --- Configuration et Initialisation ---
st.set_page_config(page_title="Scan Ichimoku", layout="wide")
st.title("🔍 Scan Ichimoku sur Paires de Devises")
st.markdown("Analyse des signaux Ichimoku forts sur plusieurs paires de devises via l'API OANDA.")

# --- Fonctions ---

@st.cache_data(ttl=600) # Mettre en cache les données pendant 10 minutes
def get_oanda_client():
    """Initialise et retourne le client API OANDA."""
    try:
        access_token = st.secrets["oanda"]["api_key"]
        # L'environnement est 'practice' ou 'live'
        environment = st.secrets["oanda"].get("environment", "practice")
        client = API(access_token=access_token, environment=environment)
        return client
    except (KeyError, V20Error) as e:
        st.error(f"Erreur d'authentification ou de configuration OANDA. Vérifiez vos secrets.toml. Détails: {e}")
        return None

@st.cache_data(ttl=600) # Mettre en cache les données pendant 10 minutes
def get_ohlc(_client, pair, count=150, granularity="H1"):
    """Récupère les données OHLC pour une paire donnée."""
    if not _client:
        return None
        
    params = {"count": count, "granularity": granularity, "price": "M"}
    r = InstrumentsCandles(instrument=pair, params=params)
    try:
        _client.request(r)
        data = []
        for candle in r.response["candles"]:
            if candle['complete']:
                data.append({
                    "Time": candle["time"],
                    "Open": float(candle["mid"]["o"]),
                    "High": float(candle["mid"]["h"]),
                    "Low": float(candle["mid"]["l"]),
                    "Close": float(candle["mid"]["c"])
                })
        df = pd.DataFrame(data)
        df["Time"] = pd.to_datetime(df["Time"])
        return df.set_index("Time")
    except V20Error as e:
        st.warning(f"Impossible de récupérer les données pour {pair}. Erreur API: {e}")
        return None

def calculate_ichimoku(df):
    """Calcule les indicateurs Ichimoku."""
    # Tenkan-sen (Ligne de Conversion)
    df["Tenkan"] = (df["High"].rolling(window=9).max() + df["Low"].rolling(window=9).min()) / 2
    # Kijun-sen (Ligne de Base)
    df["Kijun"] = (df["High"].rolling(window=26).max() + df["Low"].rolling(window=26).min()) / 2
    # Senkou Span A (Portée Principale A)
    df["Senkou_A"] = ((df["Tenkan"] + df["Kijun"]) / 2).shift(26)
    # Senkou Span B (Portée Principale B)
    df["Senkou_B"] = ((df["High"].rolling(window=52).max() + df["Low"].rolling(window=52).min()) / 2).shift(26)
    # Chikou Span (Portée Décalée)
    df["Chikou"] = df["Close"].shift(-26)
    return df

def check_strong_buy_signal(df):
    """Vérifie un signal d'achat Ichimoku fort sur la dernière bougie clôturée."""
    if len(df) < 80: # Assez de données pour que tous les indicateurs soient calculés
        return False

    last = df.iloc[-2] # On utilise l'avant-dernière ligne (dernière bougie clôturée)
    
    # Conditions pour un signal d'achat fort
    is_tenkan_above_kijun = last["Tenkan"] > last["Kijun"]
    is_price_above_kumo = last["Close"] > last["Senkou_A"] and last["Close"] > last["Senkou_B"]
    is_chikou_above_price = df['Chikou'].iloc[-28] > df['Close'].iloc[-28] # Chikou comparé au prix d'il y a 26 périodes
    is_kumo_bullish = last["Senkou_A"] > last["Senkou_B"]
    
    return all([is_tenkan_above_kijun, is_price_above_kumo, is_chikou_above_price, is_kumo_bullish])

def plot_ichimoku(df, pair):
    """Crée un graphique Matplotlib pour Ichimoku."""
    fig, ax = plt.subplots(figsize=(12, 7))
    
    ax.plot(df.index, df["Close"], label="Prix de Clôture", color="black", linewidth=1.5)
    ax.plot(df.index, df["Tenkan"], label="Tenkan-sen", color="blue", linewidth=1)
    ax.plot(df.index, df["Kijun"], label="Kijun-sen", color="red", linewidth=1)
    ax.plot(df.index, df["Chikou"], label="Chikou Span", color="purple", linewidth=1, linestyle='--')
    
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

# --- Interface Principale ---

client = get_oanda_client()

if client:
    pairs = [
        "EUR_USD", "GBP_USD", "USD_JPY", "USD_CAD", "AUD_USD", 
        "NZD_USD", "USD_CHF", "EUR_JPY", "GBP_JPY", "XAU_USD" # Or
    ]
    
    strong_signals = []
    
    with st.spinner("Analyse des paires en cours... Veuillez patienter."):
        for pair in pairs:
            df = get_ohlc(client, pair)
            if df is not None and not df.empty:
                df_ichimoku = calculate_ichimoku(df)
                if check_strong_buy_signal(df_ichimoku):
                    strong_signals.append((pair, df_ichimoku))

    if strong_signals:
        st.subheader(f"📈 {len(strong_signals)} Paire(s) avec Signal d'Achat Ichimoku Fort Détecté")
        
        results_df = pd.DataFrame([pair for pair, _ in strong_signals], columns=["Paires avec signal"])
        
        col1, col2 = st.columns([1, 3])
        with col1:
            st.dataframe(results_df)
            st.download_button(
                label="📥 Télécharger la liste en CSV",
                data=results_df.to_csv(index=False).encode('utf-8'),
                file_name='signaux_ichimoku.csv',
                mime='text/csv',
            )
        with col2:
            st.info("Les graphiques ci-dessous montrent les détails pour chaque paire détectée.")

        st.divider()

        for pair, df in strong_signals:
            st.markdown(f"### Analyse détaillée pour : {pair}")
            fig = plot_ichimoku(df, pair)
            st.pyplot(fig)
            plt.close(fig) # Important pour libérer la mémoire

    else:
        st.success("✅ Aucun signal d'achat fort détecté pour le moment parmi les paires analysées.")
else:
    st.warning("L'application ne peut pas démarrer sans une connexion valide à l'API OANDA.")
