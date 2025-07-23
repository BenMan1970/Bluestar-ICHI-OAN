import streamlit as st
import pandas as pd
import pandas_ta as ta
from oandapyV20 import API
import oandapyV20.endpoints.instruments as instruments
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
import time

# --- Configuration et Constantes ---
st.set_page_config(layout="wide", page_title="BlueStar Scanner", page_icon="🚀")

# Seuils pour l'analyse technique
TK_SPREAD_THRESHOLD = 0.05  # Seuil pour croisement "énergique" (en % du prix)
KUMO_DISTANCE_THRESHOLD = 0.1  # Distance minimale du prix par rapport au Kumo (en %)
MIN_CANDLES_ICHIMOKU = 52  # Minimum de bougies pour calculer Ichimoku

INSTRUMENTS_TO_SCAN = [
    "EUR_USD", "GBP_USD", "USD_JPY", "USD_CHF", "USD_CAD", "AUD_USD", "NZD_USD",
    "EUR_JPY", "GBP_JPY", "XAU_USD", "US30_USD", "NAS100_USD", "SPX500_USD"
]

TIMEFRAME_LABELS = {
    "H1": "1H", "H4": "4H", "D": "1D", "W": "1W", "M": "1M"
}

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

# --- Fonctions améliorées ---
@st.cache_data(ttl=60)
def fetch_candles(instrument, timeframe, count=200):
    """Récupère les données de bougies avec gestion d'erreurs améliorée"""
    params = {"count": count, "granularity": timeframe}
    try:
        r = instruments.InstrumentsCandles(instrument=instrument, params=params)
        api.request(r)
        
        if not r.response.get('candles'):
            return None
            
        data = []
        for candle in r.response['candles']:
            if not candle.get('complete', True):  # Ignorer les bougies incomplètes
                continue
                
            time = pd.to_datetime(candle['time'])
            o, h, l, c = (
                float(candle['mid']['o']), 
                float(candle['mid']['h']), 
                float(candle['mid']['l']), 
                float(candle['mid']['c'])
            )
            data.append([time, o, h, l, c])
        
        if len(data) < MIN_CANDLES_ICHIMOKU:
            return None
            
        df = pd.DataFrame(data, columns=['time', 'open', 'high', 'low', 'close'])
        df.set_index('time', inplace=True)
        return df
        
    except Exception as e:
        st.error(f"Erreur lors de la récupération des données pour {instrument} ({timeframe}): {e}")
        return None

@st.cache_data(ttl=300)  # Cache plus long pour les calculs Ichimoku
def calculate_ichimoku(df):
    """Calcule les indicateurs Ichimoku avec gestion d'erreurs"""
    if df is None or len(df) < MIN_CANDLES_ICHIMOKU:
        return None
    
    try:
        df_copy = df.copy()
        df_copy.ta.ichimoku(append=True)
        df_copy.rename(columns={
            "ITS_9": "tenkan", 
            "IKS_26": "kijun", 
            "ISA_9": "senkou_a", 
            "ISB_26": "senkou_b", 
            "ICS_26": "chikou"
        }, inplace=True)
        return df_copy
    except Exception as e:
        st.error(f"Erreur lors du calcul Ichimoku: {e}")
        return None

def get_ichimoku_trend(df):
    """Détermine la tendance Ichimoku avec logique améliorée"""
    if df is None or len(df) < MIN_CANDLES_ICHIMOKU:
        return "Indisponible"
    
    df_ichimoku = calculate_ichimoku(df)
    if df_ichimoku is None:
        return "Indisponible"
    
    last = df_ichimoku.iloc[-1]
    if pd.isna(last['senkou_a']) or pd.isna(last['senkou_b']):
        return "Indisponible"
    
    kumo_top = max(last['senkou_a'], last['senkou_b'])
    kumo_bottom = min(last['senkou_a'], last['senkou_b'])
    
    # Logique de tendance améliorée
    if last['close'] > kumo_top and last['tenkan'] > last['kijun']:
        return "Haussier"
    elif last['close'] < kumo_bottom and last['tenkan'] < last['kijun']:
        return "Baissier"
    else:
        return "Neutre"

def is_valid_signal(signal_type, last_candle):
    """Valide un signal selon les critères Ichimoku stricts"""
    kumo_top = max(last_candle['senkou_a'], last_candle['senkou_b'])
    kumo_bottom = min(last_candle['senkou_a'], last_candle['senkou_b'])
    
    if signal_type == "Haussier":
        price_above_kumo = last_candle['close'] > kumo_top
        tenkan_above_kumo = last_candle['tenkan'] > kumo_top
        kumo_bullish = last_candle['senkou_a'] > last_candle['senkou_b']
        
        return price_above_kumo and tenkan_above_kumo and kumo_bullish
    
    elif signal_type == "Baissier":
        price_below_kumo = last_candle['close'] < kumo_bottom
        tenkan_below_kumo = last_candle['tenkan'] < kumo_bottom
        kumo_bearish = last_candle['senkou_a'] < last_candle['senkou_b']
        
        return price_below_kumo and tenkan_below_kumo and kumo_bearish
    
    return False

def calculate_signal_strength(signal_type, last, previous):
    """Calcule la force du signal avec critères améliorés"""
    score = 1  # Signal de base
    
    # 1. Force du croisement (momentum)
    tk_momentum = abs(last['tenkan'] - last['kijun']) - abs(previous['tenkan'] - previous['kijun'])
    if tk_momentum > 0:
        score += 1
    
    # 2. Position du Chikou Span
    kumo_top = max(last['senkou_a'], last['senkou_b'])
    kumo_bottom = min(last['senkou_a'], last['senkou_b'])
    
    if not pd.isna(last['chikou']):
        if signal_type == "Haussier" and last['chikou'] > kumo_top:
            score += 1
        elif signal_type == "Baissier" and last['chikou'] < kumo_bottom:
            score += 1
    
    # 3. Distance du prix par rapport au Kumo
    if signal_type == "Haussier":
        distance = (last['close'] - kumo_top) / last['close'] * 100
        if distance > KUMO_DISTANCE_THRESHOLD:
            score += 1
    else:
        distance = (kumo_bottom - last['close']) / last['close'] * 100
        if distance > KUMO_DISTANCE_THRESHOLD:
            score += 1
    
    # 4. Élan du croisement TK
    spread = abs(last['tenkan'] - last['kijun'])
    if (spread / last['close']) * 100 > TK_SPREAD_THRESHOLD:
        score += 1
    
    return min(score, 5)  # Limite à 5 étoiles maximum

def get_signal_strength_display(score):
    """Affiche la force du signal avec des étoiles"""
    if score >= 5:
        return "★★★★★ Excellent"
    elif score >= 4:
        return "★★★★☆ Très Fort"
    elif score >= 3:
        return "★★★☆☆ Fort"
    elif score >= 2:
        return "★★☆☆☆ Moyen"
    else:
        return "★☆☆☆☆ Faible"

def analyze_signal_with_double_confirmation(instrument, main_tf, conf_tf1, conf_tf2):
    """Analyse un signal avec double confirmation MTF - Version améliorée"""
    df_main = fetch_candles(instrument, main_tf)
    if df_main is None:
        return None

    df_ichimoku = calculate_ichimoku(df_main)
    if df_ichimoku is None:
        return None
    
    # Utilisation des dernières bougies complètes
    last = df_ichimoku.iloc[-1]
    previous = df_ichimoku.iloc[-2]
    
    # Vérification des données nécessaires
    required_cols = ['tenkan', 'kijun', 'senkou_a', 'senkou_b', 'chikou']
    if any(pd.isna(last[col]) for col in required_cols[:4]):  # Chikou peut être NaN
        return None

    # Détection du croisement TK
    signal_type = None
    if last['tenkan'] > last['kijun'] and previous['tenkan'] <= previous['kijun']:
        signal_type = "Haussier"
    elif last['tenkan'] < last['kijun'] and previous['tenkan'] >= previous['kijun']:
        signal_type = "Baissier"
    
    if not signal_type:
        return None

    # Validation du signal selon les critères Ichimoku
    if not is_valid_signal(signal_type, last):
        return None
    
    # Calcul de la force du signal
    strength_score = calculate_signal_strength(signal_type, last, previous)
    
    # Double confirmation MTF
    trend1 = get_ichimoku_trend(fetch_candles(instrument, conf_tf1))
    trend2 = get_ichimoku_trend(fetch_candles(instrument, conf_tf2))
    
    # Le signal doit être confirmé par les deux timeframes supérieurs
    if signal_type == trend1 and signal_type == trend2:
        return {
            "Force": get_signal_strength_display(strength_score),
            "Score": strength_score,
            "Actif": instrument,
            "Signal": f"✅ {signal_type}",
            f"Conf. {TIMEFRAME_LABELS.get(conf_tf1, conf_tf1)}": f"👍 {trend1}",
            f"Conf. {TIMEFRAME_LABELS.get(conf_tf2, conf_tf2)}": f"👍 {trend2}",
            "Prix": f"{last['close']:.5f}",
            "Heure (UTC)": last.name.strftime('%Y-%m-%d %H:%M')
        }
    
    return None

def scan_instruments_parallel(instruments_list, main_tf, conf_tf1, conf_tf2):
    """Scan parallèle des instruments pour améliorer les performances"""
    signals = []
    
    with ThreadPoolExecutor(max_workers=5) as executor:
        future_to_instrument = {
            executor.submit(analyze_signal_with_double_confirmation, inst, main_tf, conf_tf1, conf_tf2): inst 
            for inst in instruments_list
        }
        
        for future in as_completed(future_to_instrument):
            instrument = future_to_instrument[future]
            try:
                result = future.result(timeout=30)  # Timeout de 30 secondes
                if result:
                    signals.append(result)
            except Exception as e:
                st.warning(f"Erreur lors de l'analyse de {instrument}: {e}")
    
    return signals

# --- Interface Streamlit améliorée ---
st.title("🚀 BlueStar - Scanner Ichimoku à Double Confirmation")
st.markdown("*Scanner avancé avec filtrage multi-timeframe et scoring intelligent*")

# Sidebar pour la configuration
with st.sidebar:
    st.header("⚙️ Configuration")
    
    # Sélection d'instruments personnalisée
    selected_instruments = st.multiselect(
        "Sélectionner les actifs à scanner:",
        INSTRUMENTS_TO_SCAN,
        default=INSTRUMENTS_TO_SCAN,
        help="Choisissez les instruments à analyser"
    )
    
    # Seuils personnalisables
    st.subheader("Paramètres avancés")
    tk_threshold = st.slider("Seuil croisement TK (%)", 0.01, 0.20, TK_SPREAD_THRESHOLD, 0.01)
    kumo_threshold = st.slider("Distance Kumo (%)", 0.05, 0.50, KUMO_DISTANCE_THRESHOLD, 0.05)
    
    # Mise à jour des constantes globales
    TK_SPREAD_THRESHOLD = tk_threshold
    KUMO_DISTANCE_THRESHOLD = kumo_threshold

# État de l'application
if 'scan_complete' not in st.session_state:
    st.session_state.scan_complete = False
    st.session_state.results_h4 = pd.DataFrame()
    st.session_state.results_h1 = pd.DataFrame()
    st.session_state.last_scan_time = None

# Métriques en temps réel
col1, col2, col3, col4 = st.columns(4)

if st.session_state.scan_complete:
    with col1:
        st.metric("Signaux H4", len(st.session_state.results_h4))
    with col2:
        st.metric("Signaux H1", len(st.session_state.results_h1))
    with col3:
        total_signals = len(st.session_state.results_h4) + len(st.session_state.results_h1)
        st.metric("Total Signaux", total_signals)
    with col4:
        if st.session_state.last_scan_time:
            st.metric("Dernier Scan", st.session_state.last_scan_time.strftime("%H:%M:%S"))

# Bouton de scan principal
if st.button("🔍 Lancer le Scan Complet (H4 & H1)", type="primary", use_container_width=True):
    if not selected_instruments:
        st.error("Veuillez sélectionner au moins un instrument à scanner.")
        st.stop()
    
    st.session_state.scan_complete = True
    st.session_state.last_scan_time = pd.Timestamp.now()
    
    # Barre de progression
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    with st.spinner("🔄 Analyse complète en cours..."):
        # Scan H4 avec confirmation D1 & W1
        status_text.text("Analyse des signaux H4...")
        progress_bar.progress(25)
        signals_h4 = scan_instruments_parallel(selected_instruments, "H4", "D", "W")
        
        # Scan H1 avec confirmation H4 & D1
        status_text.text("Analyse des signaux H1...")
        progress_bar.progress(75)
        signals_h1 = scan_instruments_parallel(selected_instruments, "H1", "H4", "D")
        
        progress_bar.progress(100)
        status_text.text("✅ Analyse terminée!")
        
        # Sauvegarde des résultats
        st.session_state.results_h4 = pd.DataFrame(signals_h4)
        st.session_state.results_h1 = pd.DataFrame(signals_h1)
        
        # Trier par force du signal
        if not st.session_state.results_h4.empty:
            st.session_state.results_h4 = st.session_state.results_h4.sort_values('Score', ascending=False)
        if not st.session_state.results_h1.empty:
            st.session_state.results_h1 = st.session_state.results_h1.sort_values('Score', ascending=False)
    
    # Nettoyage de l'interface
    time.sleep(1)
    progress_bar.empty()
    status_text.empty()

# Affichage des résultats
if st.session_state.scan_complete:
    st.markdown("---")
    
    # Onglets pour organiser les résultats
    tab1, tab2 = st.tabs(["📊 Signaux H4", "⚡ Signaux H1"])
    
    with tab1:
        st.subheader("🎯 Signaux H4 (Confirmés par D1 & W1)")
        if st.session_state.results_h4.empty:
            st.info("🔍 Aucun signal H4 avec double confirmation trouvé.")
        else:
            # Affichage avec style
            df_display = st.session_state.results_h4.drop('Score', axis=1)  # Masquer le score numérique
            st.dataframe(
                df_display,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Force": st.column_config.TextColumn("Force", width="medium"),
                    "Signal": st.column_config.TextColumn("Signal", width="small"),
                    "Prix": st.column_config.NumberColumn("Prix", format="%.5f")
                }
            )
            
            # Statistiques
            if len(st.session_state.results_h4) > 0:
                strong_signals = st.session_state.results_h4[st.session_state.results_h4['Score'] >= 3]
                st.success(f"🌟 {len(strong_signals)} signal(s) fort(s) détecté(s) sur H4")
    
    with tab2:
        st.subheader("⚡ Signaux H1 (Confirmés par H4 & D1)")
        if st.session_state.results_h1.empty:
            st.info("🔍 Aucun signal H1 avec double confirmation trouvé.")
        else:
            # Affichage avec style
            df_display = st.session_state.results_h1.drop('Score', axis=1)  # Masquer le score numérique
            st.dataframe(
                df_display,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Force": st.column_config.TextColumn("Force", width="medium"),
                    "Signal": st.column_config.TextColumn("Signal", width="small"),
                    "Prix": st.column_config.NumberColumn("Prix", format="%.5f")
                }
            )
            
            # Statistiques
            if len(st.session_state.results_h1) > 0:
                strong_signals = st.session_state.results_h1[st.session_state.results_h1['Score'] >= 3]
                st.success(f"🌟 {len(strong_signals)} signal(s) fort(s) détecté(s) sur H1")

# Footer avec informations
st.markdown("---")
st.markdown("""
<div style='text-align: center; color: #666;'>
    <small>
    🚀 BlueStar Scanner v2.0 | 
    Filtrage Ichimoku avancé avec double confirmation MTF | 
    Données OANDA en temps réel
    </small>
</div>
""", unsafe_allow_html=True)
   
