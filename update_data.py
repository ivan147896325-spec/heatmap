import pandas as pd
import folium
from folium.plugins import HeatMap
from datetime import datetime, timedelta

# 1. 官方開放資料 API 網址設定
# A1 類事故 API (dataset/12818)
URL_A1 = "https://opdadm.moi.gov.tw/api/v1/no-auth/resource/api/dataset/02D40248-7CAA-4354-82EA-E27AB8DCAB39/resource/7CE45778-7EF7-4B45-BD69-7BFB6868C0DB/download"

# A2 類事故 API (dataset/13139)
URL_A2 = "https://opdadm.moi.gov.tw/api/v1/no-auth/resource/api/dataset/266D0D60-4966-4F2A-A80F-A8659ED511E9/resource/7743EB5B-6A59-4785-B4BA-6D29DEDF82CD/download"

# 農業部農村水保署 - 土石流/山坡地警戒點 CSV API
URL_SLOPE = "https://data.ardwc.gov.tw/dataset/d883b28b-b83b-4809-a75e-a6167ec50bc5/resource/46487e41-0f81-42cb-bc28-9d4cb058e11a/download/debris.csv"


def process_traffic_data(url, name_tag="事故"):
    """讀取交通事故資料，並精準過濾出『最新 3 個月』(90天) 的資料筆數"""
    try:
        print(f"正在抓取 {name_tag} 資料...")
        df = pd.read_csv(url, on_bad_lines='skip', encoding='utf-8-sig', low_memory=False)
        
        # 自動尋找經緯度欄位
        lat_col = next((c for c in df.columns if '緯' in c or 'lat' in c.lower()), None)
        lng_col = next((c for c in df.columns if '經' in c or 'lng' in c.lower() or 'lon' in c.lower()), None)
        
        if not lat_col or not lng_col:
            print(f"[{name_tag}] 警告：找不到經緯度欄位，現有欄位: {df.columns.tolist()}")
            return None
            
        df[lat_col] = pd.to_numeric(df[lat_col], errors='coerce')
        df[lng_col] = pd.to_numeric(df[lng_col], errors='coerce')
        
        # 清理無效座標並鎖定台灣本島範圍
        df_clean = df.dropna(subset=[lat_col, lng_col]).copy()
        df_clean = df_clean[(df_clean[lat_col] > 21) & (df_clean[lat_col] < 26) & 
                            (df_clean[lng_col] > 119) & (df_clean[lng_col] < 123)]
        
        # 尋找日期欄位並篩選「最近 3 個月」
        date_col = next((c for c in df.columns if '日期' in c or 'date' in c.lower()), None)
        if date_col:
            def parse_taiwan_date(d):
                try:
                    s = str(int(float(d)))
                    if len(s) == 7: # 民國年 (如 1130101)
                        return datetime(int(s[:3]) + 1911, int(s[3:5]), int(s[5:7]))
                    elif len(s) == 8: # 西元年 (如 20240101)
                        return datetime.strptime(s, "%Y%m%d")
                except:
                    return None
                return None

            df_clean['parsed_date'] = df_clean[date_col].apply(parse_taiwan_date)
            max_date = df_clean['parsed_date'].max()
            
            if pd.notnull(max_date):
                cutoff_date = max_date - timedelta(days=90)
                df_clean = df_clean[df_clean['parsed_date'] >= cutoff_date]
                print(f"[{name_tag}] 已篩選近 3 個月資料 ({cutoff_date.strftime('%Y-%m-%d')} ~ {max_date.strftime('%Y-%m-%d')})，共 {len(df_clean)} 筆")

        return [[row[lat_col], row[lng_col]] for _, row in df_clean.iterrows()]
    except Exception as e:
        print(f"[{name_tag}] 讀取失敗: {e}")
        return None


def process_slope_data(url):
    """讀取山坡地/土石流潛勢資料"""
    try:
        print("正在抓取山坡地/土石流資料...")
        df = pd.read_csv(url, on_bad_lines='skip', encoding='utf-8-sig')
        
        lat_col = next((c for c in df.columns if '緯' in c or 'lat' in c.lower()), None)
        lng_col = next((c for c in df.columns if '經' in c or 'lng' in c.lower() or 'lon' in c.lower()), None)
        
        if lat_col and lng_col:
            df[lat_col] = pd.to_numeric(df[lat_col], errors='coerce')
            df[lng_col] = pd.to_numeric(df[lng_col], errors='coerce')
            df_clean = df.dropna(subset=[lat_col, lng_col])
            df_clean = df_clean[(df_clean[lat_col] > 21) & (df_clean[lat_col] < 26) & 
                                (df_clean[lng_col] > 119) & (df_clean[lng_col] < 123)]
            print(f"[山坡地] 成功讀取 {len(df_clean)} 筆警戒點資料")
            return [[row[lat_col], row[lng_col]] for _, row in df_clean.iterrows()]
        else:
            print(f"[山坡地] CSV 檔案中未發現直接的經緯度欄位: {df.columns.tolist()}")
            return None
    except Exception as e:
        print(f"[山坡地] 讀取失敗: {e}")
        return None


# --- 開始構建地圖 ---
m = folium.Map(location=[23.973877, 120.982024], zoom_start=8, tiles="cartodbpositron")

# 1. A1 事故圖層 (最新 3 個月)
heat_a1 = process_traffic_data(URL_A1, name_tag="A1 事故")
if heat_a1:
    fg_a1 = folium.FeatureGroup(name="🚨 A1 類重大交通事故 (最新3個月)", show=True)
    HeatMap(heat_a1, radius=15, blur=10, gradient={0.4: 'blue', 0.65: 'lime', 1: 'red'}).add_to(fg_a1)
    fg_a1.add_to(m)

# 2. A2 事故圖層 (最新 3 個月全量)
heat_a2 = process_traffic_data(URL_A2, name_tag="A2 事故")
if heat_a2:
    fg_a2 = folium.FeatureGroup(name="⚠️ A2 類交通事故 (最新3個月)", show=False)
    HeatMap(heat_a2, radius=10, blur=8, gradient={0.4: 'cyan', 0.65: 'yellow', 1: 'orange'}).add_to(fg_a2)
    fg_a2.add_to(m)

# 3. 山坡地/土石流潛勢點圖層
heat_slope = process_slope_data(URL_SLOPE)
if heat_slope:
    fg_slope = folium.FeatureGroup(name="⛰️ 土石流/山坡地警戒潛勢點", show=False)
    HeatMap(heat_slope, radius=18, blur=12, gradient={0.4: 'purple', 0.8: 'brown', 1: 'darkred'}).add_to(fg_slope)
    fg_slope.add_to(m)

# 啟用右上角控制開關 (選單預設保持展開)
folium.LayerControl(collapsed=False).add_to(m)

# 儲存為 HTML 檔
m.save("index.html")
print("成功更新全量 index.html！")
