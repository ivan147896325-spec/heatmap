import pandas as pd
import folium
from folium.plugins import HeatMap

# 1. 抓取警政署或開源開放資料 CSV
url = "https://raw.githubusercontent.com/kiang/NPA_TMA/master/data/2026/202601.csv" # 範例來源
try:
    df = pd.read_csv(url)
    
    # 2. 資料篩選（以桃園市為例，避開全台資料過大問題）
    # 請依實際欄位名稱調整，例如 '發生地點' 或 'address'
    df_filtered = df[df['發生地點'].str.contains('桃園', na=False)].copy()
    
    # 清理無效座標
    df_filtered = df_filtered.dropna(subset=['緯度', '經度'])
    
    # 儲存篩選後的 CSV
    df_filtered.to_csv("filtered_accidents.csv", index=False)
    
    # 3. 生成熱力圖 HTML
    m = folium.Map(location=[24.958, 121.297], zoom_start=13, tiles="cartodbpositron")
    heat_data = [[row['緯度'], row['經度']] for _, row in df_filtered.iterrows()]
    HeatMap(heat_data, radius=18, blur=12).add_to(m)
    
    m.save("index.html")
    print("Successfully updated index.html")
except Exception as e:
    print(f"Error: {e}")
