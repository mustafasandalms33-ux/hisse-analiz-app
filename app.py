import streamlit as st
import yfinance as yf
import datetime
import pandas as pd
import plotly.graph_objects as go
import os
import requests
from bs4 import BeautifulSoup

# --- Sayfa ayarları ---
st.set_page_config(page_title="Hisse Senedi Analiz Aracı", layout="centered")
st.title("📊 Hisse Senedi Analiz Aracı + Teknik Göstergeler + Toplu Alım Bölgesi + Tahmini Yön")

# --- Favori hisseler dosyası ---
FAV_FILE = "favori_hisseler.csv"
if not os.path.exists(FAV_FILE):
    pd.DataFrame(columns=["Hisse"]).to_csv(FAV_FILE, index=False)

if "favoriler" not in st.session_state:
    if os.path.exists(FAV_FILE):
        st.session_state["favoriler"] = pd.read_csv(FAV_FILE)["Hisse"].tolist()
    else:
        st.session_state["favoriler"] = []

# --- Kullanıcı girdileri ---
hisse_kodu = st.text_input("Hisse Kodu", value="EREGL")
start_date = st.date_input("Başlangıç Tarihi", datetime.date(2024, 1, 1))
end_date = st.date_input("Bitiş Tarihi", datetime.date.today())

st.subheader("Hedef Yüzdeleri (%)")
hedef1_yuzde = st.slider("Kısa vadeli hedef (%)", 5, 50, 8)
hedef2_yuzde = st.slider("Orta vadeli hedef (%)", 5, 50, 15)
hedef3_yuzde = st.slider("Uzun vadeli hedef (%)", 5, 50, 20)

st.subheader("Grafik Zaman Dilimi")
zaman_dilimi = st.selectbox("Zaman Dilimi Seç", ["1 Günlük", "1 Haftalık", "1 Aylık"])

# --- Ticker oluştur ---
def get_ticker(symbol):
    return symbol.upper() + ".IS" if not symbol.endswith(".IS") else symbol.upper()

# --- Veri çekme ---
@st.cache_data
def get_data(ticker, start, end, interval):
    # Veri çekilirken 'auto_adjust=True' kullanarak nan sorununu azaltırız
    data = yf.download(ticker, start=start, end=end, interval=interval, auto_adjust=True)
    # Eksik verileri temizle
    data = data.dropna(subset=['Close', 'Volume'])
    return data

# --- RSI hesaplama ---
def compute_RSI(data, period=14):
    # NaN değerlerini temizleme
    data = data.dropna(subset=['Close'])
    if len(data) < period:
        return pd.Series([float('nan')] * len(data), index=data.index)
        
    delta = data['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(period).mean()
    RS = gain / loss
    RSI = 100 - (100 / (1 + RS))
    return RSI

# --- Hedef analizi ---
def hedef_analizi(ticker, yuzdeler, data=None):
    try:
        stock = yf.Ticker(ticker)
        # Hissede işlem yoksa lastPrice NaN dönebilir.
        fiyat = stock.fast_info.get('lastPrice')
        zirve = stock.fast_info.get('yearHigh')
        dip = stock.fast_info.get('yearLow')

        if fiyat is None or zirve is None or dip is None:
            return None # Veri eksikse analizi yapma

        hedef1 = fiyat * (1 + yuzdeler[0]/100)
        hedef2 = fiyat * (1 + yuzdeler[1]/100)
        hedef3 = fiyat * (1 + yuzdeler[2]/100)
        destek = zirve * 0.95

        # Eğer data gönderildiyse daha doğru direnç hesapla
        if data is not None and not data.empty:
            direnç_kisa = data['Close'].rolling(20).max().iloc[-1]
            direnç_orta = data['Close'].rolling(50).max().iloc[-1]
        else:
            direnç_kisa = zirve * 1.02  # fallback
            direnç_orta = zirve * 1.05  # fallback

        direnç_uzun = zirve

        trend = "📈 Yükseliş trendi" if fiyat > destek else "⚠️ Zayıflama riski"

        return {
            "fiyat": fiyat,
            "zirve": zirve,
            "dip": dip,
            "hedef1": hedef1,
            "hedef2": hedef2,
            "hedef3": hedef3,
            "destek": destek,
            "direnc_kisa": direnç_kisa,
            "direnc_orta": direnç_orta,
            "direnc_uzun": direnç_uzun,
            "trend": trend
        }
    except:
        return None

def tahmini_olasilik(data):
    # Gelen veriyi temizle
    if 'Close' not in data.columns:
        return 50, 50, 0, 0, 0
    data = data.dropna(subset=['Close', 'RSI14'])
    if data.empty or len(data) < 60:
        return 50, 50, 0, 0, 0

    # Son 60 gün yükseliş yüzdesi
    son_60 = data.tail(60)
    yuzde_yukselis = (son_60['Close'].diff() > 0).sum() / len(son_60) * 100

    # EMA sinyali
    ema10_series = data['Close'].ewm(span=10, adjust=False).mean().dropna()
    close_last = data['Close'].iloc[-1]
    EMA_bonus = 10 if not ema10_series.empty and close_last > ema10_series.iloc[-1] else 0

    # RSI sinyali
    rsi_series = data['RSI14'].dropna()
    rsi = rsi_series.iloc[-1] if not rsi_series.empty else 50
    RSI_bonus = 5 if rsi < 30 else 0

    # Hacim sinyali
    Hacim_bonus = 0
    if 'Volume' in data.columns and not data['Volume'].dropna().empty:
        vol_avg = data['Volume'].tail(5).mean()
        if not pd.isna(vol_avg):
            Hacim_bonus = 5 if data['Volume'].iloc[-1] > vol_avg else 0

    P_tahmin = yuzde_yukselis + EMA_bonus + RSI_bonus + Hacim_bonus
    return P_tahmin, yuzde_yukselis, EMA_bonus, RSI_bonus, Hacim_bonus

# --- Tekli analiz yorum ---
def otomatik_yorum(hedefler, data):
    # RSI ve MA'lar için NaN kontrolü
    data = data.dropna(subset=["RSI14", "MA20", "MA50"])
    if data.empty:
        st.error("RSI ve Hareketli Ortalama hesaplaması için yeterli veri yok.")
        return
        
    son_rsi = data["RSI14"].iloc[-1]
    ma20 = data["MA20"].iloc[-1]
    ma50 = data["MA50"].iloc[-1]

    P_tahmin, P_tarihce, EMA_bonus, RSI_bonus, Hacim_bonus = tahmini_olasilik(data)
    
    # Tahmini yön açıklaması
    if P_tahmin > 70:
        tahmin = f"🔮 Yükseliş olasılığı yüksek ({P_tahmin:.1f}%)"
    elif P_tahmin > 55:
        tahmin = f"🔮 Hafif Yükseliş beklenebilir ({P_tahmin:.1f}%)"
    elif P_tahmin < 30:
        tahmin = f"🔮 Düşüş olasılığı yüksek ({P_tahmin:.1f}%)"
    else:
        tahmin = f"🔮 Nötr/Belirsiz ({P_tahmin:.1f}%)"

    # 📌 Yorum çıktısı
    yorum = f"""
### 📌 Güncel Fiyat: {hedefler['fiyat']:.2f} ₺
**Genel Trend:** {hedefler['trend']}
**Tahmini Yön (Ertesi Gün):** {tahmin}
- RSI: {son_rsi:.1f}
- MA20: {ma20:.2f} | MA50: {ma50:.2f}

### 🎯 Hedef Fiyatlar:
- Hedef1: {hedefler['hedef1']:.2f} ₺
- Hedef2: {hedefler['hedef2']:.2f} ₺
- Hedef3: {hedefler['hedef3']:.2f} ₺

### 🛡️ Destek / Direnç Seviyeleri:
- **Destek:** {hedefler['destek']:.2f} ₺
- **Kısa Vadeli Direnç (20G):** {hedefler['direnc_kisa']:.2f} ₺
- **Orta Vadeli Direnç (50G):** {hedefler['direnc_orta']:.2f} ₺
- **Uzun Vadeli Direnç (Yıllık Zirve):** {hedefler['direnc_uzun']:.2f} ₺
"""
    st.markdown(yorum)

# --- Tekli hisse analizi ---
if st.button("Analiz Et"):
    ticker = get_ticker(hisse_kodu)
    interval = "1d" if zaman_dilimi=="1 Günlük" else "1wk" if zaman_dilimi=="1 Haftalık" else "1mo"
    data = get_data(ticker, start_date, end_date, interval)
    if not data.empty and len(data) >= 50: # En az 50 günlük veri kontrolü
        data["MA20"] = data["Close"].rolling(20).mean()
        data["MA50"] = data["Close"].rolling(50).mean()
        data["RSI14"] = compute_RSI(data)
        hedefler = hedef_analizi(ticker, [hedef1_yuzde, hedef2_yuzde, hedef3_yuzde], data)
        if hedefler is not None:
            otomatik_yorum(hedefler, data)
        else:
            st.error("Hisse temel verileri (fiyat, zirve/dip) çekilemedi.")
    else:
        st.error("Analiz için yeterli (en az 50 günlük) Close/Volume verisi çekilemedi.")


# --- Toplu Hisseler Analizi ---
st.subheader("📋 Toplu Hisseler Alım Bölgesi ve Tahmini Yön")

BIST30 = ["AKBNK", "ARCLK", "ASELS", "BIMAS", "DOHOL", "EKGYO", "EREGL", "FROTO",
    "GWIND", "GUBRF", "SAHOL", "HEKTS", "KCHOL", "KOZAL", "KOZAA", "MAVI",
    "OYAKC", "PGSUS", "PETKM", "SISE", "SODA", "TAVHL", "THYAO", "TTKOM",
    "TUPRS", "ISCTR", "TCELL", "TTRAK", "ULKER", "VAKBN"]
# ... (Diğer BIST listeleri aynı kalır)
BIST50 = ["AKBNK", "ARCLK", "ASELS", "BIMAS", "DOHOL", "EKGYO", "EREGL", "FROTO",
    "GWIND", "GUBRF", "SAHOL", "HEKTS", "KCHOL", "KOZAL", "KOZAA", "MAVI",
    "OYAKC", "PGSUS", "PETKM", "SISE", "SODA", "TAVHL", "THYAO", "TTKOM",
    "TUPRS", "ISCTR", "TCELL", "TTRAK", "ULKER", "VAKBN", "AKSA", "AKSGY",
    "ANHYT", "ARCLK", "AYDEM", "BJKAS", "DENGE", "ENJSA", "FROTO", "GSDHO",
    "HALKB", "ISGYO", "KRDMD", "MAVI", "ORMA", "OZKGY", "PGSUS", "SNGYO",
    "TATEN", "TAVHL"]
BIST100 = ["AKBNK", "ARCLK", "ASELS", "BIMAS", "DOHOL", "EKGYO", "EREGL", "FROTO","GWIND", "GUBRF", "SAHOL", "HEKTS", "KCHOL", "KOZAL", "KOZAA", "MAVI",
           "OYAKC", "PGSUS", "PETKM", "SISE", "SODA", "TAVHL", "THYAO", "TTKOM","TUPRS", "ISCTR", "TCELL", "TTRAK", "ULKER", "VAKBN", "AKSA", "AKSGY",
           "ANHYT", "AYDEM", "BJKAS", "DENGE", "ENJSA", "GSDHO", "HALKB", "ISGYO","KRDMD", "ORMA", "OZKGY", "SNGYO", "TATEN", "AKGRT", "ADEL", "AFYON",
           "AGHOL", "AKFGY", "AKMGY", "ALARK", "ALGYO", "ANACM", "ANHYT", "ASELS","BEYAZ", "BOSSA", "BRISA", "BUNY", "CCOLA", "CEMAS", "CIMSA", "CLEBI",
           "CRFSA", "DEVA", "DOAS", "EGEEN", "ENKAI", "ESEN", "ETILR", "GARAN","GLYHO", "GOZDE", "GRNYO", "GSRAY", "HEKTS", "HLGYO", "HURGZ", "IPEKE",
           "ISDMR", "ISCTR", "IZMDC", "JANTS", "KCHOL", "KORDS", "KRONT", "KUL","MAVI", "MGROS", "MPARK", "NTHOL", "NUHCM", "ORGL", "PRKME", "SASA",
           "SELEC", "SISE", "SKBNK", "SNGYO", "SODASN", "SRV", "TAVHL", "TAVHL","TOASO", "TRGYO", "TRKCM", "TSKB", "TTKOM", "TUKAS", "TUPRS", "VAKBN",
           "VESTL", "YATAS", "YKBNK", "ZOREN"]
toplu_listeler = {"BIST30": BIST30, "BIST50": BIST50, "BIST100": BIST100}

def temizle_hisseler(BIST30, BIST50, BIST100):
    BIST50_temiz = [h for h in BIST50 if h not in BIST30]
    BIST100_temiz = [h for h in BIST100 if h not in BIST30 and h not in BIST50_temiz]
    return BIST30, BIST50_temiz, BIST100_temiz

BIST30, BIST50, BIST100 = temizle_hisseler(BIST30, BIST50, BIST100)
toplu_listeler = {"BIST30": BIST30, "BIST50": BIST50, "BIST100": BIST100}

secilen_borsa = st.multiselect("Borsa Seç", options=list(toplu_listeler.keys()), default=list(toplu_listeler.keys()))

@st.cache_data
def fetch_data_all(tickers):
    tickers_is = [t + ".IS" for t in tickers]
    # Sadece Kapanış ve Hacim çekiyoruz
    data = yf.download(tickers_is, period="3mo", auto_adjust=True)
    return data

def toplu_alim_ve_hedef(hisseler_dict, hedef_yuzdeleri=[8,15,20]):
    tum_hisseler = [h for b in hisseler_dict for h in hisseler_dict[b]]
    df_all = fetch_data_all(tum_hisseler)
    
    sonuc_list = []
    for borsa, hisseler in hisseler_dict.items():
        if borsa not in secilen_borsa:
            continue
        for h in hisseler:
            ticker_name = h + ".IS"
            try:
                hisse_data = pd.DataFrame({
                    "Close": df_all["Close"][ticker_name],
                    "Volume": df_all["Volume"][ticker_name]
                }).dropna() # Nan olan satırları temizle

                if len(hisse_data) < 50: # MA ve RSI için yeterli veri kontrolü
                    continue

                fiyat = hisse_data["Close"].iloc[-1]
                ma20 = hisse_data["Close"].rolling(20).mean().iloc[-1]
                ma50 = hisse_data["Close"].rolling(50).mean().iloc[-1]
                
                # RSI hesapla ve NaN'leri temizle
                hisse_data["RSI14"] = compute_RSI(hisse_data)
                hisse_data = hisse_data.dropna(subset=['RSI14'])
                
                if hisse_data.empty:
                    continue

                rsi = hisse_data["RSI14"].iloc[-1]

                hedefler = hedef_analizi(get_ticker(h), hedef_yuzdeleri)
                if hedefler is None:
                    continue

                # Tahmini olasılık
                P_tahmin, _, _, _, _ = tahmini_olasilik(hisse_data)

                # Alım bölgesi kontrolü
                if rsi < 30 or ma20 > ma50:
                    if P_tahmin > 70:
                        tahmin = f"🚀 Yüksek Yükseliş ({P_tahmin:.1f}%)"
                    elif P_tahmin > 55:
                        tahmin = f"📈 Hafif Yükseliş ({P_tahmin:.1f}%)"
                    else:
                        tahmin = f"⚠️ Nötr ({P_tahmin:.1f}%)"

                    sonuc_list.append({
                        "Hisse": h,
                        "Borsa": borsa,
                        "Fiyat": f"{fiyat:.2f}",
                        "MA20": f"{ma20:.2f}",
                        "MA50": f"{ma50:.2f}",
                        "RSI14": f"{rsi:.1f}",
                        "Hedef1": f"{hedefler['hedef1']:.2f}",
                        "Hedef2": f"{hedefler['hedef2']:.2f}",
                        "Hedef3": f"{hedefler['hedef3']:.2f}",
                        "Durum": "Alım Bölgesi ✅",
                        "Tahmini_Yon": tahmin
                    })

            except Exception as e:
                # print(f"Toplu alım hatası {h}: {e}")
                continue

    sonuc_df = pd.DataFrame(sonuc_list)
    return sonuc_df.sort_values(by="RSI14", key=lambda x: pd.to_numeric(x.str.replace(',', '.'), errors='coerce'))

def highlight_row(row):
    if "Alım Bölgesi" in row["Durum"]:
        return ["background-color: lightgreen"]*len(row)
    else:
        return ["background-color: white"]*len(row)

if st.button("Toplu Alım ve Hedef Fiyatları Kontrol Et"):
    df_sonuc = toplu_alim_ve_hedef(toplu_listeler)
    if not df_sonuc.empty:
        st.dataframe(df_sonuc.style.apply(highlight_row, axis=1))
    else:
        st.info("📌 Şu anda alım bölgesinde hisseler yok.")


# --- Otomatik Güncellenen Toplu Tarama Paneli ---
st.subheader("🚀 Otomatik Güncellenen Toplu Tarama - BIST100/50/30")

@st.cache_data
def otomatik_toplu_tarama(hisseler_dict):
    tum_hisseler = [h for b in hisseler_dict for h in hisseler_dict[b]]
    tickers_is = [h + ".IS" for h in tum_hisseler]
    
    # Close ve Volume verilerini çekiyoruz
    df_all = yf.download(tickers_is, period="3mo", auto_adjust=True)
    
    sonuc_list = []
    for borsa, hisseler in hisseler_dict.items():
        for h in hisseler:
            ticker_name = h + ".IS"
            try:
                data = pd.DataFrame({
                    "Close": df_all["Close"][ticker_name],
                    "Volume": df_all["Volume"][ticker_name]
                }).dropna() # NaN'leri temizle

                if len(data) < 50: # Yeterli veri kontrolü
                    continue

                data['RSI14'] = compute_RSI(data)
                data = data.dropna(subset=['RSI14'])
                
                if data.empty:
                    continue

                # Tahmini olasılık
                P_tahmin, _, _, _, _ = tahmini_olasilik(data)
                fiyat = data['Close'].iloc[-1]
                ma20 = data['Close'].rolling(20).mean().iloc[-1]
                ma50 = data['Close'].rolling(50).mean().iloc[-1]

                durum = "Alım Bölgesi ✅" if data['RSI14'].iloc[-1]<30 or ma20>ma50 else "Normal"
                sonuc_list.append({
                    "Hisse": h,
                    "Borsa": borsa,
                    "Fiyat": f"{fiyat:.2f}",
                    "MA20": f"{ma20:.2f}",
                    "MA50": f"{ma50:.2f}",
                    "RSI14": f"{data['RSI14'].iloc[-1]:.1f}",
                    "Tahmini_Yuzde": f"{P_tahmin:.1f}",
                    "Durum": durum
                })
            except Exception as e:
                continue

    df_sonuc = pd.DataFrame(sonuc_list)
    df_sonuc['Tahmini_Yuzde'] = pd.to_numeric(df_sonuc['Tahmini_Yuzde'], errors='coerce')
    df_sonuc = df_sonuc.sort_values(by="Tahmini_Yuzde", ascending=False)
    return df_sonuc

def highlight_alim(row):
    if "Alım" in row["Durum"]:
        return ["background-color: lightgreen"]*len(row)
    return [""]*len(row)

# Sayfa açıldığında otomatik tarama
st.info("📌 Otomatik tarama çalışıyor, lütfen bekleyin...")
df_otomatik = otomatik_toplu_tarama(toplu_listeler)
if not df_otomatik.empty:
    st.dataframe(df_otomatik.style.apply(highlight_alim, axis=1))
else:
    st.info("📌 Şu anda alım bölgesinde hisseler yok.")
    
# --- Tavan İhtimali Tahmin Aracı ---
st.title("🚀 Ertesi Gün Tavan Olasılığı Tahmin Aracı (BIST30/50/100 + Yıldız Pazar)")

# --- Tavan Skoru Hesaplama ---
def tavan_skoru(data):
    # RSI hesaplamadan önce 'Close' sütununda NaN olan satırları at
    data = data.dropna(subset=['Close', 'Volume']) 
    
    # Yeterli veri yoksa (en az 2 gün) NaN dön
    if len(data) < 50: # Ortalama ve RSI için yeterli veri
        return 0, float('nan'), float('nan'), float('nan'), float('nan')
        
    data["RSI14"] = compute_RSI(data)
    
    # RSI hesaplandıktan sonra NaN içeren ilk satırları at
    data = data.dropna(subset=['RSI14'])
    
    # Tekrar kontrol
    if data.empty or len(data) < 2:
         return 0, float('nan'), float('nan'), float('nan'), float('nan')

    # En son geçerli değerleri al
    close = data["Close"].iloc[-1]
    prev_close = data["Close"].iloc[-2] # Dünkü kapanış
    hacim = data["Volume"].iloc[-1]
    
    # Ort Hacim: Son 10 günün ortalamasını alırken
    ort_hacim = data["Volume"].tail(10).mean()

    # Hesaplamalar
    fiyat_degisim = (close - prev_close) / prev_close * 100
    rsi = data["RSI14"].iloc[-1]

    # ... (Skor hesaplaması aynı kalır)
    skor = 0
    if fiyat_degisim > 7:
        skor += 30
    if hacim > ort_hacim * 1.5:
        skor += 25
    if rsi > 50:
        skor += 15
    if close > data["Close"].rolling(20).mean().iloc[-1]:
        skor += 15
    if close > data["Close"].rolling(50).mean().iloc[-1]:
        skor += 15

    return skor, fiyat_degisim, rsi, hacim, ort_hacim

# --- Hisse Listeleri ---
# ... (Hisse listeleri aynı kalır)
MENKUL_HISSELER = ["A1CAP","A1YEN","ACSEL","ADEL","ADESE","ADGYO","AEFES","AFYON","AGESA","AGHOL",
    "AGROT","AGYO","AHGAZ","AHSGY","AKBNK","AKCNS","AKENR","AKFGY","AKFIS","AKFYE",
    "AKGRT","AKMGY","AKSA","AKSEN","AKSGY","AKSUE","AKYHO","ALARK","ALBRK","ALCAR",
    "ALCTL","ALFAS","ALGYO","ALKA","ALKIM","ALKLC","ALTNY","ALVES","ANELE","ANGEN",
    "ANHYT","ANSGR","APBDL","APLIB","APMDL","APX30","ARASE","ARCLK","ARDYZ","ARENA",
    "ARMGD","ARSAN","ARTMS","ARZUM","ASELS","ASGYO","ASTOR","ASUZU","ATAGY","ATAKP",
    "ATATP","ATEKS","ATLAS","ATSYH","AVGYO","AVHOL","AVOD","AVPGY","AVTUR","AYCES",
    "AYDEM","AYEN","AYES","AYGAZ","AZTEK","BAGFS","BAHKM","BAKAB","BALAT","BALSU",
    "BANVT","BARMA","BASCM","BASGZ","BAYRK","BEGYO","BERA","BESLR","BEYAZ","BFREN",
    "BIENY","BIGCH","BIGEN","BIMAS","BINBN","BINHO","BIOEN","BIZIM","BJKAS","BLCYT",
    "BLUME","BMSCH","BMSTL","BNTAS","BOBET","BORLS","BORSK","BOSSA","BRISA","BRKO",
    "BRKSN","BRKVY","BRLSM","BRMEN","BRSAN","BRYAT","BSOKE","BTCIM","BUCIM","BULGS",
    "BURCE","BURVA","BVSAN","BYDNR","CANTE","CASA","CATES","CCOLA","CELHA","CEMAS",
    "CEMTS","CEMZY","CEOEM","CGCAM","CIMSA","CLEBI","CMBTN","CMENT","CONSE","COSMO",
    "CRDFA","CRFSA","CUSAN","CVKMD","CWENE","DAGI","DAPGM","DARDL","DCTTR","DENGE",
    "DERHL","DERIM","DESA","DESPC","DEVA","DGATE","DGGYO","DGNMO","DIRIT","DITAS",
    "DMRGD","DMSAS","DNISI","DOAS","DOBUR","DOCO","DOFER","DOFRB","DOGUB","DOHOL",
    "DOKTA","DSTKF","DUNYH","DURDO","DURKN","DYOBY","DZGYO","EBEBK","ECILC","ECZYT",
    "EDATA","EDIP","EFORC","EGEEN","EGEGY","EGEPO","EGGUB","EGPRO","EGSER","EKGYO",
    "EKIZ","EKOS","EKSUN","ELITE","EMKEL","EMNIS","ENDAE","ENERY","ENJSA","ENKAI",
    "ENSRI","ENTRA","EPLAS","ERBOS","ERCB","EREGL","ERSU","ESCAR","ESCOM","ESEN",
    "ETILR","ETYAT","EUHOL","EUKYO","EUPWR","EUREN","EUYO","EYGYO","FADE","FENER",
    "FLAP","FMIZP","FONET","FORMT","FORTE","FRIGO","FROTO","FZLGY","GARAN","GARFA",
    "GEDIK","GEDZA","GENIL","GENTS","GEREL","GESAN","GIPTA","GLBMD","GLCVY","GLDTR",
    "GLRMK","GLRYH","GLYHO","GMSTR","GMTAS","GOKNR","GOLTS","GOODY","GOZDE","GRNYO",
    "GRSEL","GRTHO","GSDDE","GSDHO","GSRAY","GUBRF","GUNDG","GWIND","GZNMI","HALKB",
    "HALKS","HATEK","HATSN","HDFGS","HEDEF","HEKTS","HKTM","HLGYO","HOROZ","HRKET",
    "HTTBT","HUBVC","HUNER","HURGZ","ICBCT","ICUGS","IDGYO","IEYHO","IHAAS","IHEVA",
    "IHGZT","IHLAS","IHLGM","IHYAY","IMASM","INDES","INFO","INGRM","INTEK","INTEM",
    "INVEO","INVES","IPEKE","ISATR","ISBIR","ISBTR","ISCTR","ISDMR","ISFIN","ISGLK",
    "ISGSY","ISGYO","ISIST","ISKPL","ISKUR","ISMEN","ISSEN","ISYAT","IZENR","IZFAS",
    "IZINV","IZMDC","JANTS","KAPLM","KAREL","KARSN","KARTN","KATMR","KAYSE","KBORU",
    "KCAER","KCHOL","KENT","KERVN","KFEIN","KGYO","KIMMR","KLGYO","KLKIM","KLMSN",
    "KLNMA","KLRHO","KLSER","KLSYN","KLYPV","KMPUR","KNFRT","KOCMT","KONKA","KONTR",
    "KONYA","KOPOL","KORDS","KOTON","KOZAA","KOZAL","KRDMA","KRDMB","KRDMD","KRGYO",
    "KRONT","KRPLS","KRSTL","KRTEK","KRVGD","KSTUR","KTLEV","KTSKR","KUTPO","KUVVA",
    "KUYAS","KZBGY","KZGYO","LIDER","LIDFA","LILAK","LINK","LKMNH","LMKDC","LOGO",
    "LRSHO","LUKSK","LYDHO","LYDYE","MAALT","MACKO","MAGEN","MAKIM","MAKTK","MANAS",
    "MARBL","MARKA","MARMR","MARTI","MAVI","MEDTR","MEGAP","MEGMT","MEKAG","MEPET",
    "MERCN","MERIT","MERKO","METRO","MGROS","MHRGY","MIATK","MMCAS","MNDRS","MNDTR",
    "MOBTL","MOGAN","MOPAS","MPARK","MRGYO","MRSHL","MSGYO","MTRKS","MTRYO","MZHLD",
    "NATEN","NETAS","NIBAS","NTGAZ","NTHOL","NUGYO","NUHCM","OBAMS","OBASE","ODAS",
    "ODINE","OFSYM","ONCSM","ONRYT","OPK30","OPT25","OPTGY","OPTLR","OPX30","ORCAY",
    "ORGE","ORMA","OSMEN","OSTIM","OTKAR","OTTO","OYAKC","OYAYO","OYLUM","OYYAT",
    "OZATD","OZGYO","OZKGY","OZRDN","OZSUB","OZYSR","PAGYO","PAMEL","PAPIL","PARSN",
    "PASEU","PATEK","PCILT","PEKGY","PENGD","PENTA","PETKM","PETUN","PGSUS","PINSU",
    "PKART","PKENT","PLTUR","PNLSN","PNSUT","POLHO","POLTK","PRDGS","PRKAB","PRKME",
    "PRZMA","PSDTC","PSGYO","QNBFK","QNBTR","QTEMZ","QUAGR","RALYH","RAYSG","REEDR",
    "RGYAS","RNPOL","RODRG","RTALB","RUBNS","RUZYE","RYGYO","RYSAS","SAFKR","SAHOL",
    "SAMAT","SANEL","SANFM","SANKO","SARKY","SASA","SAYAS","SDTTR","SEGMN","SEGYO",
    "SEKFK","SEKUR","SELEC","SELVA","SERNT","SEYKM","SILVR","SISE","SKBNK","SKTAS",
    "SKYLP","SKYMD","SMART","SMRTG","SMRVA","SNGYO","SNICA","SNKRN","SNPAM","SODSN",
    "SOKE","SOKM","SONME","SRVGY","SUMAS","SUNTK","SURGY","SUWEN","TABGD","TARKM",
    "TATEN","TATGD","TAVHL","TBORG","TCELL","TCKRC","TDGYO","TEHOL","TEKTU","TERA",
    "TEZOL","TGSAS","THYAO","TKFEN","TKNSA","TLMAN","TMPOL","TMSN","TNZTP","TOASO",
    "TRCAS","TRGYO","TRHOL","TRILC","TSGYO","TSKB","TSPOR","TTKOM","TTRAK","TUCLK",
    "TUKAS","TUPRS","TUREX","TURGG","TURSG","UFUK","ULAS","ULKER","ULUFA","ULUSE",
    "ULUUN","UNLU","USAK","USDTR","VAKBN","VAKFN","VAKKO","VANGD","VBTYZ","VERTU",
    "VERUS","VESBE","VESTL","VKFYO","VKGYO","VKING","VRGYO","VSNMD","X030S","X100S",
    "XBANA","XBANK","XBLSM","XELKT","XFINK","XGIDA","XGMYO","XHARZ","XHOLD","XILTM",
    "XINSA","XKAGT","XKMYA","XKOBI","XKURY","XMADN","XMANA","XMESY","XSADA","XSANK",
    "XSANT","XSBAL","XSBUR","XSDNZ","XSGRT","XSIST","XSIZM","XSKAY","XSKOC","XSKON",
    "XSPOR","XSTKR","XTAST","XTCRT","XTEKS","XTM25","XTMTU","XTRZM","XTUMY","XU030",
    "XU050","XU100","XUHIZ","XULAS","XUMAL","XUSIN","XUSRD","XUTEK","XUTUM","XYLDZ",
    "XYORT"]
BIST100 = BIST50 + MENKUL_HISSELER


YILDIZ_PAZAR = ["ASGYO","SASA","HEKTS","KONTR","GWIND","GESAN","BIOEN","NTHOL",
                "PENTA","KMPUR","SMRTG","ENJSA","ESEN","ALARK","SISE","KRDMD",
                "AKFGY","YKBNK","VESTL","TUPRS","EREGL","THYAO","AKBNK","GARAN"]

borsalar = {"BIST30": BIST30, "BIST50": BIST50, "BIST100": BIST100, "Yıldız Pazar": YILDIZ_PAZAR}
secilen = st.selectbox("Endeks Seç (Tavan Olasılığı)", list(borsalar.keys()))

# --- Verileri Çek & Hesapla ---
tickers = [h + ".IS" for h in borsalar[secilen]]
df_all = yf.download(tickers, period="6mo", auto_adjust=True) # auto_adjust ekledik
sonuclar = []
for h in borsalar[secilen]:
    ticker_name = h + ".IS"
    try:
        # Veri çekme ve NaN temizleme
        data = pd.DataFrame({
            "Close": df_all["Close"][ticker_name],
            "Volume": df_all["Volume"][ticker_name]
        }).dropna()
        
        # tavan_skoru'nu çağır
        skor, degisim, rsi, hacim, ort_hacim = tavan_skoru(data)

        # Eğer tavan_skoru NaN döndürdüyse, bu hisseyi atla
        if pd.isna(degisim) or pd.isna(rsi):
            continue 
            
        sonuclar.append({
            "Hisse": h,
            "Günlük % Değişim": f"{degisim:.2f}%",
            "RSI14": f"{rsi:.1f}",
            "Hacim (M)": f"{hacim/1e6:.2f}",
            "Ort Hacim (M)": f"{ort_hacim/1e6:.2f}",
            "Tavan Skoru": skor,
            "Tahmin": "🚀 Tavan ihtimali yüksek" if skor >= 70 else "⚠️ Normal"
        })
    except Exception as e:
        continue

df_sonuc = pd.DataFrame(sonuclar).sort_values(by="Tavan Skoru", ascending=False)
st.dataframe(df_sonuc)
