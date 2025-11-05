# ==========================================================
# 🚀 Ertesi Gün Tavan Olasılığı Tahmin Aracı (Canlı + Optimize Edilmiş)
# ==========================================================
import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go

st.set_page_config(page_title="🚀 Tavan Olasılığı Tahmini", layout="centered")
st.title("🚀 Ertesi Gün Tavan Olasılığı Tahmin Aracı")

# --- Fonksiyonlar ---
@st.cache_data
def get_data(ticker):
    """Canlı verileri 15 dakikalık aralıkla getirir."""
    data = yf.download(ticker + ".IS", period="5d", interval="15m", auto_adjust=True)
    return data.dropna(subset=["Close"])

def compute_RSI(data, period=14):
    delta = data["Close"].diff()
    gain = (delta.where(delta > 0, 0)).rolling(period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(period).mean()
    RS = gain / loss
    RSI = 100 - (100 / (1 + RS))
    return RSI

# --- Hisse Seçimi ---
ticker = st.text_input("Hisse Sembolü (örnek: AKBNK, THYAO):", value="AKBNK")

if st.button("🚀 Tavan Olasılığını Hesapla"):
    try:
        df = get_data(ticker)
        if df.empty:
            st.warning("Veri alınamadı. Hisse kodunu kontrol et.")
        else:
            df["RSI"] = compute_RSI(df)

            son_fiyat = df["Close"].iloc[-1]
            ilk_fiyat = df["Close"].iloc[0]
            gunluk_degisim = ((son_fiyat - ilk_fiyat) / ilk_fiyat) * 100

            hacim_artis = df["Volume"].iloc[-1] / df["Volume"].mean() if df["Volume"].mean() > 0 else 1
            rsi_son = df["RSI"].iloc[-1]

            # Basit tahmin algoritması (puanlama)
            skor = 0
            if gunluk_degisim > 6: skor += 2
            if hacim_artis > 1.5: skor += 2
            if rsi_son > 65: skor += 1
            if son_fiyat > df["Close"].rolling(20).mean().iloc[-1]: skor += 1

            olasilik = min(95, skor * 20)

            st.metric("Anlık Fiyat", f"{son_fiyat:.2f} ₺")
            st.metric("Günlük % Değişim", f"%{gunluk_degisim:.2f}")
            st.metric("RSI (14)", f"{rsi_son:.2f}")
            st.metric("Tahmini Tavan Olasılığı", f"%{olasilik}")

            # --- Grafik ---
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=df.index, y=df["Close"], mode="lines", name="Fiyat"))
            fig.update_layout(title=f"{ticker} - 15 Dakikalık Fiyat Grafiği", height=400)
            st.plotly_chart(fig, use_container_width=True)

    except Exception as e:
        st.error(f"Tavan tahmini yapılamadı: {e}")
