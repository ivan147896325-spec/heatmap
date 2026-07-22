import pandas as pd
import folium
from folium.plugins import HeatMap
from datetime import datetime, timedelta

# 1. 官方 API 網址設定
# A1 類事故 API (dataset/12818)
URL_A1 = "https://opdadm.moi.gov.tw/api/v1/no-auth/resource/api/dataset/02D40248-7CAA-4354-82EA-E27AB8DCAB39/resource/7CE45778-7EF7-4B45-BD69-7BFB6868C0DB/download"

# A2 類事故 API (dataset/13139)
URL_A2 = "https://opdadm.moi.gov.tw/api/v1/no-auth/resource/api/dataset/266D0D60-4966-4F2A-A80F-A8659ED511E9/resource/7743EB5B-6A59-4785-B4BA-6D29DEDF82CD/download"

# 山坡地/土石流潛勢溪流與災害點 API (農業部農村水保署官方開放資料)
URL_SLOPE = "https://data.ardwc.gov.tw/dataset/d883b28b-b83b-4809-a75e-a6167ec50bc5/resource/46487e41-0f81-42cb-bc28-9d4cb058e11a/download/debris.csv"


def process_traffic_data(url, months=3):
    """讀取交通事故資料並過濾出『最新 3 個月』的事故筆數"""
    try:
        print(f"正在抓取並處理事故資料: {url}")
        df = pd.read_csv(url, on_bad_lines='skip', encoding='utf-8-sig', low_memory=False)
        
        # 尋找經緯度欄位
        lat_col = next((c for c in df.columns if '緯' in c or 'lat' in c.lower()), None)
        lng_col = next((c for c in df.columns if '經' in c or 'lng' in c.lower() or 'lon' in c.lower()), None)
        
        if not lat_col or not lng_col:
            print(f"警告：找不到經緯度欄位 {df.columns.tolist()}")
            return None
            
        df[lat_col] = pd.to_numeric(df[lat_col], errors='coerce')
        df[lng_col] = pd.to_numeric(df[lng_col], errors='coerce')
        
        # 剔除座標異常
        df_clean = df.dropna(subset=[lat_col, lng_col]).copy()
        df_clean = df_clean[(df_clean[lat_col] > 21) & (df_clean[lat_col] < 26) & 
                            (df_clean[lng_col] > 119) & (df_clean[lng_col] < 123)]
        
        # 日期處理與『最新 3 個月』篩選
        # 警政署格式常見欄位：發生日期/發生年月日 (如 1130101 或 2024-01-01)
        date_col = next((c for c in df.columns if '日期' in c or 'date' in c.lower()), None)
        
        if date_col:
            def parse_taiwan_date(d):
                try:
                    s = str(int(float(d)))
                    if len(s) == 7: # 1130101 民國年
                        year = int(s[:3]) + 1911
                        month = int(s[3:5])
                        day = int(s[5:7])
                        return datetime(year, month, day)
                    elif len(s) == 8: # 20240101 西元年
                        return datetime.strptime(s, "%Y%m%d")
                except:
                    return None
                return None

            df_clean['parsed_date'] = df_clean[date_col].apply(parse_taiwan_date)
            
            # 以資料集內最新的日期往前推 90 天
            max_date = df_clean['parsed_date'].max()
            if pd.notnull(max_date):
                cutoff_date = max_date - timedelta(days=90)
                df_clean = df_clean[df_clean['parsed_date'] >= cutoff_date]
                print(f"篩選範圍: {cutoff_date.strftime('%Y-%m-%d')} 至 {max_date.strftime('%Y-%m-%d')}，共 {len(df_clean)} 筆事故")

        return [[row[lat_col], row[lng_col]] for _, row in df_clean.iterrows()]
    except Exception as e:
        print(f"讀取事故資料失敗: {e}")
        return None


def process_slope_data(url):
    """讀取山坡地/土石流潛勢資料"""
    try:
        print(f"正在抓取山坡地資料: {url}")
        df = pd.read_csv(url, on_bad_lines='skip', encoding='utf-8-sig')
        
        lat_col = next((c for c in df.columns if '緯' in c or 'lat' in c.lower()), None)
        lng_col = next((c for c in df.columns if '經' in c or 'lng' in c.lower() or 'lon' in c.lower()), None)
        
        if lat_col and lng_col:
            df[lat_col] = pd.to_numeric(df[lat_col], errors='coerce')
            df[lng_col] = pd.to_numeric(df[lng_col], errors='coerce')
            df_clean = df.dropna(subset=[lat_col, lng_col])
            df_clean = df_clean[(df_clean[lat_col] > 21) & (df_clean[lat_col] < 26) & 
                                (df_clean[lng_col] > 119) & (df_clean[lng_col] < 123)]
            return [[row[lat_col], row[lng_col]] for _, row in df_clean.iterrows()]
        else:
            print("山坡地資料檔中無直接經緯度欄位，嘗試解析區域中心點...")
            return None
    except Exception as e:
        print(f"讀取山坡地資料失敗: {e}")
        return None


# --- 開始構建地圖 ---
m = folium.Map(location=[23.973877, 120.982024], zoom_start=8, tiles="cartodbpositron")

# 1. A1 事故圖層 (最新 3 個月)
heat_a1 = process_traffic_data(URL_A1, months=3)
if heat_a1:
    layer_a1 = folium.FeatureGroup(name="🚨 A1 類重大交通事故 (最新3個月)", show=True)
    HeatMap(heat_a1, radius=15, blur=10, gradient={0.4: 'blue', 0.65: 'lime', 1: 'red'}).add_to(layer_a1)
    layer_a1.add_to(m)

# 2. A2 事故圖層 (最新 3 個月)
heat_a2 = process_traffic_data(URL_A2, months=3)
if heat_a2:
    layer_a2 = folium.FeatureGroup(name="⚠️ A2 類交通事故 (最新3個月)", show=True)
    HeatMap(heat_a2, radius=10, blur=8, gradient={0.4: 'cyan', 0.65: 'yellow', 1: 'orange'}).add_to(layer_a2)
    layer_a2.add_to(m)

# 3. 山坡地/土石流潛勢點圖層
heat_slope = process_slope_data(URL_SLOPE)
if heat_slope:
    layer_slope = folium.FeatureGroup(name="⛰️ 山坡地/土石流警戒潛勢點", show=False)
    HeatMap(heat_slope, radius=18, blur=12, gradient={0.4: 'purple', 0.8: 'brown', 1: 'darkred'}).add_to(layer_slope)
    layer_slope.add_to(m)

# 啟用開關控制選單
folium.LayerControl(collapsed=False).add_to(m)

# 儲存
m.save("index.html")
print("成功更新『最新 3 個月全量資料』與多圖層 index.html！")
