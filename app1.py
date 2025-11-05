# ==========================================================
# 📊 Tekli Hisse Analiz Aracı (Hızlı + Canlı Veri)
# ==========================================================
import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta

# --- Sayfa Ayarları ---
st.set_page_config(page_title="📊 Tekli Hisse Analiz Aracı", layout="centered")
st.title("📈 Tekli Hisse Analiz Aracı")

# --- Fonksiyonlar ---
@st.cache_data
def get_data(ticker, period="5d", interval="30m"):
    """Canlı verileri Yahoo Finance'tan çeker."""
    data = yf.download(ticker + ".IS", period=period, interval=interval, auto_adjust=True)
    data = data.dropna(subset=["Close"])
    return data

def compute_RSI(data, period=14):
    """RSI hesaplama"""
    delta = data["Close"].diff()
    gain = (delta.where(delta > 0, 0)).rolling(period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(period).mean()
    RS = gain / loss
    RSI = 100 - (100 / (1 + RS))
    return RSI

# --- Hisse Seçimi ---
ticker = st.text_input("Hisse Sembolü (örnek: AKBNK, THYAO):", value="AKBNK")

# --- Veri Getir ---
if st.button("🔍 Analiz Et"):
    try:
        df = get_data(ticker)
        if df.empty:
            st.warning("Veri alınamadı. Hisse kodunu kontrol et.")
        else:
            # RSI Hesapla
            df["RSI"] = compute_RSI(df)

            # Günlük değişim hesapla (canlı)
            son_fiyat = df["Close"].iloc[-1]
            ilk_fiyat = df["Close"].iloc[0]
            gunluk_degisim = ((son_fiyat - ilk_fiyat) / ilk_fiyat) * 100

            # Gösterimler
            st.metric("Anlık Fiyat", f"{son_fiyat:.2f} ₺")
            st.metric("Günlük % Değişim", f"%{gunluk_degisim:.2f}")
            st.metric("RSI (14)", f"{df['RSI'].iloc[-1]:.2f}")

            # --- Grafik ---
            fig = go.Figure()
            fig.add_trace(go.Candlestick(
                x=df.index,
                open=df["Open"], high=df["High"], low=df["Low"], close=df["Close"],
                name="Fiyat"
            ))
            fig.update_layout(
                title=f"{ticker} - Son Günlük Fiyat Hareketi",
                xaxis_rangeslider_visible=False,
                height=500
            )
            st.plotly_chart(fig, use_container_width=True)
    except Exception as e:
        st.error(f"Veri alınamadı: {e}")
