import pandas as pd
import folium
from folium.plugins import HeatMap

# 1. 定義資料來源網址
# A1 類交通事故 (警政署 API)
URL_A1 = "https://opdadm.moi.gov.tw/api/v1/no-auth/resource/api/dataset/02D40248-7CAA-4354-82EA-E27AB8DCAB39/resource/7CE45778-7EF7-4B45-BD69-7BFB6868C0DB/download"

# A2 類交通事故 (警政署開放資料 API)
URL_A2 = "https://opdadm.moi.gov.tw/api/v1/no-auth/resource/api/dataset/266D0D60-4966-4F2A-A80F-A8659ED511E9/resource/7743EB5B-6A59-4785-B4BA-6D29DEDF82CD/download"

# 山坡地/崩塌潛勢/歷史災害資料 (政府 Open Data CSV/API)
URL_SLOPE = "https://data.ardwc.gov.tw/dataset/d883b28b-b83b-4809-a75e-a6167ec50bc5/resource/46487e41-0f81-42cb-bc28-9d4cb058e11a/download/debris.csv" # 範例：土石流/山坡地災害資料點

def load_and_clean_data(url):
    """通用資料讀取與經緯度清理函式"""
    try:
        df = pd.read_csv(url, on_bad_lines='skip')
        lat_col = next((c for c in df.columns if '緯' in c or 'lat' in c.lower()), None)
        lng_col = next((c for c in df.columns if '經' in c or 'lng' in c.lower() or 'lon' in c.lower()), None)
        
        if not lat_col or not lng_col:
            return None, None, None
            
        df[lat_col] = pd.to_numeric(df[lat_col], errors='coerce')
        df[lng_col] = pd.to_numeric(df[lng_col], errors='coerce')
        
        # 剔除空值與極端異常值 (限制在台灣範圍)
        df_clean = df.dropna(subset=[lat_col, lng_col])
        df_clean = df_clean[(df_clean[lat_col] > 21) & (df_clean[lat_col] < 26) & (df_clean[lng_col] > 119) & (df_clean[lng_col] < 123)]
        return df_clean, lat_col, lng_col
    except Exception as e:
        print(f"讀取資料失敗 ({url}): {e}")
        return None, None, None

try:
    print("正在下載並處理各項資料...")
    
    # 初始化地圖 (預設台灣中心)
    m = folium.Map(location=[23.973877, 120.982024], zoom_start=8, tiles="cartodbpositron")

    # --- 1. 處理 A1 類事故圖層 ---
    df_a1, lat_a1, lng_a1 = load_and_clean_data(URL_A1)
    if df_a1 is not None and not df_a1.empty:
        layer_a1 = folium.FeatureGroup(name="🚨 A1 類重大交通事故", show=True)
        heat_a1 = [[row[lat_a1], row[lng_a1]] for _, row in df_a1.iterrows()]
        HeatMap(heat_a1, radius=15, blur=10, gradient={0.4: 'blue', 0.65: 'lime', 1: 'red'}).add_to(layer_a1)
        layer_a1.add_to(m)
        print("A1 類事故圖層建立完成！")

    # --- 2. 處理 A2 類事故圖層 ---
    df_a2, lat_a2, lng_a2 = load_and_clean_data(URL_A2)
    if df_a2 is not None and not df_a2.empty:
        layer_a2 = folium.FeatureGroup(name="⚠️ A2 類受傷交通事故", show=False) # 預設關閉避免地圖太花
        heat_a2 = [[row[lat_a2], row[lng_a2]] for _, row in df_a2.iterrows()]
        HeatMap(heat_a2, radius=12, blur=8, gradient={0.4: 'cyan', 0.65: 'yellow', 1: 'orange'}).add_to(layer_a2)
        layer_a2.add_to(m)
        print("A2 類事故圖層建立完成！")

    # --- 3. 處理山坡地/土石流災害圖層 ---
    df_slope, lat_sp, lng_sp = load_and_clean_data(URL_SLOPE)
    if df_slope is not None and not df_slope.empty:
        layer_slope = folium.FeatureGroup(name="⛰️ 山坡地/土石流潛勢點", show=False)
        heat_slope = [[row[lat_sp], row[lng_sp]] for _, row in df_slope.iterrows()]
        HeatMap(heat_slope, radius=18, blur=12, gradient={0.4: 'purple', 0.8: 'brown', 1: 'darkred'}).add_to(layer_slope)
        layer_slope.add_to(m)
        print("山坡地災害圖層建立完成！")

    # --- 4. 加入圖層控制開關 ---
    folium.LayerControl(collapsed=False).add_to(m) # collapsed=False 讓開關選單保持展開狀態

    # 5. 儲存網頁
    m.save("index.html")
    print("成功更新包含多圖層開關的 index.html！")

except Exception as e:
    print(f"Error executing script: {e}")
    raise e
