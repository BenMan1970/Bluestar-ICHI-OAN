import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.backends.backend_agg import RendererAgg
import io
from fpdf import FPDF
import base64

st.set_page_config(page_title="Bluestar Ichimoku Pro", layout="wide")
_lock = RendererAgg.lock

@st.cache_data
def load_data():
    # Données simulées (à remplacer par votre API ou votre DataFrame réel)
    data = {
        "Paire": ["EUR/USD", "USD/JPY", "GBP/USD", "XAU/USD"],
        "Tendance": ["Buy", "Sell", "Buy", "Sell"],
        "Kijun > Tenkan": [True, False, True, False],
        "Prix > Nuage": [True, False, True, False],
        "Chikou > Prix": [True, False, False, False],
    }
    df = pd.DataFrame(data)
    return df

def get_confluence(row):
    score = sum([row["Kijun > Tenkan"], row["Prix > Nuage"], row["Chikou > Prix"]])
    return score

def plot_ichimoku(pair_name):
    # Simule un graphique Ichimoku avec des courbes aléatoires
    fig, ax = plt.subplots(figsize=(6, 3))
    x = list(range(30))
    ax.plot(x, [i + 5 for i in x], label="Tenkan")
    ax.plot(x, [i + 3 for i in x], label="Kijun")
    ax.plot(x, [i + 4 for i in x], label="Senkou A")
    ax.plot(x, [i + 2 for i in x], label="Senkou B")
    ax.fill_between(x, [i + 4 for i in x], [i + 2 for i in x], color='lightblue', alpha=0.4)
    ax.set_title(f"Ichimoku pour {pair_name}")
    ax.legend()
    st.pyplot(fig)

def export_pdf(df):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    pdf.cell(200, 10, txt="Signaux Bluestar Ichimoku Pro", ln=True, align='C')
    pdf.ln(10)

    # En-têtes
    col_width = pdf.w / 5.5
    pdf.set_font("Arial", style="B")
    for col in df.columns:
        pdf.cell(col_width, 10, col, border=1)
    pdf.ln()

    # Contenu
    pdf.set_font("Arial", style="")
    for _, row in df.iterrows():
        for item in row:
            pdf.cell(col_width, 10, str(item), border=1)
        pdf.ln()

    # Génération du PDF dans la mémoire
    buf = io.BytesIO()
    pdf.output(buf)
    pdf_data = buf.getvalue()
    b64_pdf = base64.b64encode(pdf_data).decode()
    href = f'<a href="data:application/pdf;base64,{b64_pdf}" download="ichimoku_signaux.pdf">📄 Télécharger le PDF</a>'
    st.markdown(href, unsafe_allow_html=True)

def export_png():
    with _lock:
        fig, ax = plt.subplots(figsize=(10, 4))
        ax.axis('off')
        ax.table(cellText=df.values, colLabels=df.columns, loc='center', cellLoc='center')
        buf = io.BytesIO()
        plt.savefig(buf, format="png")
        st.image(buf)
        buf.seek(0)
        b64_img = base64.b64encode(buf.read()).decode()
        href = f'<a href="data:image/png;base64,{b64_img}" download="ichimoku_signaux.png">🖼️ Télécharger le PNG</a>'
        st.markdown(href, unsafe_allow_html=True)

st.title("📊 Bluestar Ichimoku Pro")

with st.spinner("Chargement des données..."):
    df = load_data()
    df["Score"] = df.apply(get_confluence, axis=1)

# Mise en forme
styled_df = df.style.applymap(
    lambda v: "color: green; font-weight: bold" if v == "Buy" else ("color: red; font-weight: bold" if v == "Sell" else "")
    , subset=["Tendance"]
).format(na_rep="-")

st.subheader("🧠 Signaux détectés")
st.dataframe(styled_df, use_container_width=True)

col1, col2 = st.columns([1, 1])
with col1:
    st.markdown("### 📥 Exportation")
    export_pdf(df)
with col2:
    export_png()

st.subheader("📈 Graphiques Ichimoku")
for idx, row in df.iterrows():
    if row["Score"] >= 2:
        plot_ichimoku(row["Paire"])

   
