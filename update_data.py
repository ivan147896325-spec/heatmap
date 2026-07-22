import pandas as pd
import folium
from folium.plugins import HeatMap

# 1. 抓取開放資料 CSV (選用穩定且包含經緯度的 Open Data)
url = "https://raw.githubusercontent.com/kiang/NPA_TMA/master/data/2026/202601.csv"

try:
    df = pd.read_csv(url)
    print("欄位列表：", df.columns.tolist()) # 方便在 Actions 日誌中查看欄位名稱

    # 自動偵測經緯度欄位名稱 (防呆機制)
    lat_col = next((c for c in df.columns if '緯' in c or 'lat' in c.lower()), None)
    lng_col = next((c for c in df.columns if '經' in c or 'lng' in c.lower() or 'lon' in c.lower()), None)
    addr_col = next((c for c in df.columns if '地點' in c or '地址' in c or 'address' in c.lower()), None)

    if not lat_col or not lng_col:
        raise ValueError("找不到經緯度欄位！請檢查資料來源格式。")

    # 2. 資料篩選 (若有地點欄位則篩選桃園，若無則取前 1000 筆測試)
    if addr_col:
        df_filtered = df[df[addr_col].astype(str).str.contains('桃園', na=False)].copy()
    else:
        df_filtered = df.copy()

    # 清理並確保經緯度為數值型態
    df_filtered[lat_col] = pd.to_numeric(df_filtered[lat_col], errors='coerce')
    df_filtered[lng_col] = pd.to_numeric(df_filtered[lng_col], errors='coerce')
    df_filtered = df_filtered.dropna(subset=[lat_col, lng_col])

    # 儲存篩選後的 CSV
    df_filtered.to_csv("filtered_accidents.csv", index=False)

    # 3. 生成熱力圖 HTML
    # 如果篩選後有資料，地圖中心定位在第一筆資料；若無資料則定位在桃園
    if not df_filtered.empty:
        center_lat = df_filtered[lat_col].mean()
        center_lng = df_filtered[lng_col].mean()
    else:
        center_lat, center_lng = 24.958, 121.297

    m = folium.Map(location=[center_lat, center_lng], zoom_start=12, tiles="cartodbpositron")
    heat_data = [[row[lat_col], row[lng_col]] for _, row in df_filtered.iterrows()]
    
    HeatMap(heat_data, radius=18, blur=12).add_to(m)
    m.save("index.html")
    print("Successfully updated index.html")

except Exception as e:
    print(f"Error executing script: {e}")
    # 拋出異常讓 GitHub Actions 知道跑失敗，方便除錯
    raise e
