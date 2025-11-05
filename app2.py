# ==========================================================
# 📊 Toplu Hisse Analiz Aracı (Hızlı + Optimize Edilmiş)
# ==========================================================
import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime

st.set_page_config(page_title="📊 Toplu Hisse Analizi", layout="centered")
st.title("📊 Toplu Hisse Analiz Aracı")

# --- Fonksiyonlar ---
@st.cache_data
def get_single_data(ticker):
    """Canlı verilerden fiyat ve günlük % değişim döndürür."""
    data = yf.download(ticker + ".IS", period="2d", interval="1h", auto_adjust=True)
    if data.empty:
        return None
    first = data["Close"].iloc[0]
    last = data["Close"].iloc[-1]
    degisim = ((last - first) / first) * 100
    return {"Hisse": ticker, "Fiyat": round(last, 2), "Değişim(%)": round(degisim, 2)}

# --- Hisse Listesi Girişi ---
st.write("İncelenecek hisseleri aralarına virgül koyarak yaz (örnek: AKBNK, THYAO, EREGL)")
hisse_listesi = st.text_input("Hisseler:", value="AKBNK, THYAO, EREGL")

# --- Taramayı Başlat ---
if st.button("🚀 Taramayı Başlat"):
    hisseler = [h.strip().upper() for h in hisse_listesi.split(",") if h.strip()]
    sonuc_listesi = []
    progress = st.progress(0)

    for i, h in enumerate(hisseler):
        data = get_single_data(h)
        if data:
            sonuc_listesi.append(data)
        progress.progress((i + 1) / len(hisseler))

    if sonuc_listesi:
        df = pd.DataFrame(sonuc_listesi)
        df = df.sort_values("Değişim(%)", ascending=False)
        st.dataframe(df, use_container_width=True)
    else:
        st.warning("Hiçbir veriye ulaşılamadı.")
