import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib
import base64
from io import BytesIO
from oandapyV20 import API
from oandapyV20.endpoints.instruments import InstrumentsCandles
from datetime import datetime, timedelta

# Utiliser Agg backend pour éviter les erreurs dans Streamlit Cloud
matplotlib.use("Agg")

# Authentification OANDA
access_token = st.secrets["oanda_api_key"]
client = API(access_token=access_token)
account_id = st.secrets["oanda_account_id"]

# Fonctions utiles pour récupérer les données et calculer Ichimoku
def get_ohlc(pair, count=120, granularity="H1"):
    params = {
        "count": count,
        "granularity": granularity,
        "price": "M"
    }
    r = InstrumentsCandles(instrument=pair, params=params)
    client.request(r)
    ohlc = []
    for candle in r.response["candles"]:
        ohlc.append({
            "Time": candle["time"],
            "Open": float(candle["mid"]["o"]),
            "High": float(candle["mid"]["h"]),
            "Low": float(candle["mid"]["l"]),
            "Close": float(candle["mid"]["c"])
        })
    df = pd.DataFrame(ohlc)
    df["Time"] = pd.to_datetime(df["Time"])
    return df.set_index("Time")

def ichimoku(df):
    df["Tenkan"] = (df["High"].rolling(window=9).max() + df["Low"].rolling(window=9).min()) / 2
    df["Kijun"] = (df["High"].rolling(window=26).max() + df["Low"].rolling(window=26).min()) / 2
    df["Senkou_A"] = ((df["Tenkan"] + df["Kijun"]) / 2).shift(26)
    df["Senkou_B"] = ((df["High"].rolling(window=52).max() + df["Low"].rolling(window=52).min()) / 2).shift(26)
    df["Chikou"] = df["Close"].shift(-26)
    return df

def check_strong_signal(df):
    if len(df) < 80 or df[["Tenkan", "Kijun", "Close", "Senkou_A"]].isnull().iloc[-1].any():
        return False
    return (
        df["Tenkan"].iloc[-1] > df["Kijun"].iloc[-1] and
        df["Close"].iloc[-1] > df["Senkou_A"].iloc[-1]
    )

def plot_ichimoku(df, pair):
    plt.figure(figsize=(10, 5))
    plt.plot(df.index, df["Close"], label="Close", color="black")
    plt.plot(df.index, df["Tenkan"], label="Tenkan", color="blue")
    plt.plot(df.index, df["Kijun"], label="Kijun", color="red")
    plt.plot(df.index, df["Senkou_A"], label="Senkou A", color="green")
    plt.plot(df.index, df["Senkou_B"], label="Senkou B", color="orange")
    plt.fill_between(df.index, df["Senkou_A"], df["Senkou_B"], where=(df["Senkou_A"] >= df["Senkou_B"]), color='lightgreen', alpha=0.4)
    plt.fill_between(df.index, df["Senkou_A"], df["Senkou_B"], where=(df["Senkou_A"] < df["Senkou_B"]), color='lightcoral', alpha=0.4)
    plt.title(f"Ichimoku - {pair}")
    plt.legend()
    plt.tight_layout()
    return plt

def export_table_as_image(df):
    fig, ax = plt.subplots(figsize=(10, 2 + len(df) * 0.25))
    ax.axis("off")
    tbl = ax.table(cellText=df.values, colLabels=df.columns, loc='center', cellLoc='center')
    tbl.auto_set_font_size(False)
    tbl.set_fontsize(10)
    tbl.scale(1.2, 1.2)
    buf = BytesIO()
    fig.savefig(buf, format="png")
    st.image(buf)
    return buf

def export_pdf(buf):
    b64 = base64.b64encode(buf.getvalue()).decode()
    href = f'<a href="data:application/pdf;base64,{b64}" download="scan_result.pdf">📄 Télécharger le PDF</a>'
    st.markdown(href, unsafe_allow_html=True)

# Interface principale Streamlit
st.title("🔍 Scan Ichimoku avec OANDA")

pairs = ["EUR_USD", "GBP_USD", "USD_JPY", "USD_CAD", "AUD_USD", "NZD_USD", "XAU_USD"]
strong_signals = []

for pair in pairs:
    df = get_ohlc(pair)
    df = ichimoku(df)
    if check_strong_signal(df):
        strong_signals.append((pair, df))

if strong_signals:
    st.subheader("📈 Paires avec signal Ichimoku fort")
    results = pd.DataFrame([pair for pair, _ in strong_signals], columns=["Paires"])
    st.dataframe(results)

    # Boutons export
    img_buf = export_table_as_image(results)
    export_pdf(img_buf)

    # Graphiques Ichimoku
    for pair, df in strong_signals:
        st.markdown(f"### {pair}")
        fig = plot_ichimoku(df, pair)
        st.pyplot(fig)
else:
    st.info("Aucun signal fort détecté parmi les paires analysées.")

