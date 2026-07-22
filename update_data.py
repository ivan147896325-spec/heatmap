import pandas as pd
import folium
from folium.plugins import HeatMap

# 1. 直接對接政府資料開放平臺 API (警政署即時 A1 類交通事故 CSV)
url = "https://opdadm.moi.gov.tw/api/v1/no-auth/resource/api/dataset/02D40248-7CAA-4354-82EA-E27AB8DCAB39/resource/7CE45778-7EF7-4B45-BD69-7BFB6868C0DB/download"

try:
    print("正在下載政府開放資料 API...")
    df = pd.read_csv(url)
    print("成功讀取資料！資料總筆數：", len(df))
    print("欄位列表：", df.columns.tolist())

    # 2. 確定欄位名稱（根據警政署標準欄位：'經度'、'緯度'、'發生地點'）
    lat_col = '緯度' if '緯度' in df.columns else next((c for c in df.columns if '緯' in c or 'lat' in c.lower()), None)
    lng_col = '經度' if '經度' in df.columns else next((c for c in df.columns if '經' in c or 'lng' in c.lower() or 'lon' in c.lower()), None)
    addr_col = '發生地點' if '發生地點' in df.columns else next((c for c in df.columns if '地點' in c or '地址' in c), None)

    if not lat_col or not lng_col:
        raise ValueError("資料集中未找到經緯度欄位！")

    # 3. 轉為數值並清理無效座標
    df[lat_col] = pd.to_numeric(df[lat_col], errors='coerce')
    df[lng_col] = pd.to_numeric(df[lng_col], errors='coerce')
    
    # 剔除經緯度為 NaN 或異常值 (例如 0,0 點)
    df_clean = df.dropna(subset=[lat_col, lng_col])
    df_clean = df_clean[(df_clean[lat_col] > 21) & (df_clean[lat_col] < 26) & (df_clean[lng_col] > 119) & (df_clean[lng_col] < 123)]

    # 4. 可選：地點篩選（若想限定桃園市可解除下方註解，否則預設呈現全台事故）
    # if addr_col:
    #     df_clean = df_clean[df_clean[addr_col].astype(str).str.contains('桃園', na=False)]

    print(f"清理後有效定位資料筆數：{len(df_clean)}")

    # 5. 儲存備份 CSV 檔
    df_clean.to_csv("filtered_accidents.csv", index=False)

    # 6. 計算地圖中心點並繪製熱力圖
    if not df_clean.empty:
        center_lat = df_clean[lat_col].mean()
        center_lng = df_clean[lng_col].mean()
    else:
        center_lat, center_lng = 23.973877, 120.982024 # 台灣中心

    m = folium.Map(location=[center_lat, center_lng], zoom_start=8, tiles="cartodbpositron")
    heat_data = [[row[lat_col], row[lng_col]] for _, row in df_clean.iterrows()]
    
    HeatMap(heat_data, radius=15, blur=10).add_to(m)
    
    # 存成 index.html (GitHub Pages 預設會讀取的首頁)
    m.save("index.html")
    print("成功生成 index.html 網頁！")

except Exception as e:
    print(f"Error executing script: {e}")
    raise e
