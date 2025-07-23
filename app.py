import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import yfinance as yf
from io import BytesIO
from fpdf import FPDF
from PIL import Image
import base64
import numpy as np

st.set_page_config(page_title="Bluestar Ichimoku Pro", layout="wide")

@st.cache_data
def load_data(pair, interval="1h", period="7d"):
    data = yf.download(pair, interval=interval, period=period)
    data.dropna(inplace=True)
    return data

def ichimoku(df):
    high_9 = df['High'].rolling(window=9).max()
    low_9 = df['Low'].rolling(window=9).min()
    tenkan_sen = (high_9 + low_9) / 2

    high_26 = df['High'].rolling(window=26).max()
    low_26 = df['Low'].rolling(window=26).min()
    kijun_sen = (high_26 + low_26) / 2

    senkou_span_a = ((tenkan_sen + kijun_sen) / 2).shift(26)

    high_52 = df['High'].rolling(window=52).max()
    low_52 = df['Low'].rolling(window=52).min()
    senkou_span_b = ((high_52 + low_52) / 2).shift(26)

    chikou_span = df['Close'].shift(-26)

    df['Tenkan'] = tenkan_sen
    df['Kijun'] = kijun_sen
    df['Senkou_A'] = senkou_span_a
    df['Senkou_B'] = senkou_span_b
    df['Chikou'] = chikou_span

    return df

def plot_ichimoku(df, pair):
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(df.index, df['Close'], label='Close', linewidth=1.5)
    ax.plot(df.index, df['Tenkan'], label='Tenkan', linestyle='--')
    ax.plot(df.index, df['Kijun'], label='Kijun', linestyle='--')
    ax.plot(df.index, df['Senkou_A'], label='Senkou A', color='green')
    ax.plot(df.index, df['Senkou_B'], label='Senkou B', color='red')
    ax.fill_between(df.index, df['Senkou_A'], df['Senkou_B'],
                    where=df['Senkou_A'] >= df['Senkou_B'], color='green', alpha=0.2)
    ax.fill_between(df.index, df['Senkou_A'], df['Senkou_B'],
                    where=df['Senkou_A'] < df['Senkou_B'], color='red', alpha=0.2)
    ax.set_title(f"Ichimoku Chart - {pair}")
    ax.legend()
    st.pyplot(fig)

def export_pdf(df):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=10)

    col_width = 40
    row_height = 8

    # Header
    for col in df.columns:
        pdf.cell(col_width, row_height, txt=str(col), border=1)
    pdf.ln()

    # Rows
    for i in range(min(len(df), 20)):
        for col in df.columns:
            pdf.cell(col_width, row_height, txt=str(df.iloc[i][col]), border=1)
        pdf.ln()

    return pdf.output(dest='S').encode('latin-1')

def export_png(table_df):
    fig, ax = plt.subplots(figsize=(10, len(table_df)*0.5))
    ax.axis('off')
    tbl = ax.table(cellText=table_df.values,
                   colLabels=table_df.columns,
                   cellLoc='center',
                   loc='center')
    buf = BytesIO()
    plt.savefig(buf, format="png", bbox_inches='tight')
    plt.close(fig)
    buf.seek(0)
    return buf

# ===================== INTERFACE =====================

st.title("📈 Bluestar Ichimoku Pro")
forex_pairs = ['EURUSD=X', 'GBPUSD=X', 'USDJPY=X', 'AUDUSD=X', 'USDCAD=X', 'USDCHF=X', 'NZDUSD=X', 'XAUUSD=X']
selected_pairs = st.multiselect("Sélectionnez les paires à scanner :", forex_pairs, default=forex_pairs)

data_summary = []

for pair in selected_pairs:
    df = load_data(pair)
    df = ichimoku(df)

    if df['Tenkan'].iloc[-1] > df['Kijun'].iloc[-1] and df['Close'].iloc[-1] > df['Senkou_A'].iloc[-1]:
        signal = "🔥 Signal Fort Achat"
    elif df['Tenkan'].iloc[-1] < df['Kijun'].iloc[-1] and df['Close'].iloc[-1] < df['Senkou_B'].iloc[-1]:
        signal = "❄️ Signal Fort Vente"
    else:
        signal = "⏸️ Neutre"

    data_summary.append({"Pair": pair, "Signal": signal})

df_summary = pd.DataFrame(data_summary)
st.dataframe(df_summary, use_container_width=True)

# Affichage graphique Ichimoku pour chaque signal fort
for i, row in df_summary.iterrows():
    if "Signal Fort" in row["Signal"]:
        st.subheader(f"📊 {row['Pair']} - {row['Signal']}")
        df = load_data(row["Pair"])
        df = ichimoku(df)
        plot_ichimoku(df, row["Pair"])

# 📤 Bouton export PDF
if st.button("📄 Exporter en PDF"):
    pdf_bytes = export_pdf(df_summary)
    b64 = base64.b64encode(pdf_bytes).decode()
    href = f'<a href="data:application/octet-stream;base64,{b64}" download="summary.pdf">📥 Télécharger le PDF</a>'
    st.markdown(href, unsafe_allow_html=True)

# 🖼️ Bouton export PNG
if st.button("🖼️ Exporter en image PNG"):
    img_buf = export_png(df_summary)
    st.image(img_buf, caption="Capture du tableau", use_column_width=True)
    b64 = base64.b64encode(img_buf.read()).decode()
    href = f'<a href="data:image/png;base64,{b64}" download="summary.png">📥 Télécharger l\'image PNG</a>'
    st.markdown(href, unsafe_allow_html=True)

   
