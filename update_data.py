import pandas as pd
import folium
from folium.plugins import HeatMap
import requests
import io
import zipfile

# 1. 官方 API 網址設定
URL_A1 = "https://opdadm.moi.gov.tw/api/v1/no-auth/resource/api/dataset/02D40248-7CAA-4354-82EA-E27AB8DCAB39/resource/7CE45778-7EF7-4B45-BD69-7BFB6868C0DB/download"
URL_A2 = "https://opdadm.moi.gov.tw/api/v1/no-auth/resource/api/dataset/266D0D60-4966-4F2A-A80F-A8659ED511E9/resource/7743EB5B-6A59-4785-B4BA-6D29DEDF82CD/download"
URL_SLOPE = "https://data.ardwc.gov.tw/dataset/d883b28b-b83b-4809-a75e-a6167ec50bc5/resource/46487e41-0f81-42cb-bc28-9d4cb058e11a/download/debris.csv"


def fetch_data(url, tag=""):
    try:
        print(f"[{tag}] 開始下載資料...")
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=60)
        response.raise_for_status()

        # 自動判斷並解壓縮 ZIP 檔 (針對 A2 大資料包)
        if response.content[:4] == b'PK\x03\x04':
            print(f"[{tag}] 偵測到 ZIP 壓縮檔，自動解壓中...")
            with zipfile.ZipFile(io.BytesIO(response.content)) as z:
                csv_name = next(f for f in z.namelist() if f.endswith('.csv'))
                df = pd.read_csv(z.open(csv_name), on_bad_lines='skip', encoding='utf-8-sig', low_memory=False)
        else:
            df = pd.read_csv(io.BytesIO(response.content), on_bad_lines='skip', encoding='utf-8-sig', low_memory=False)

        print(f"[{tag}] 成功讀取 {len(df)} 筆原始資料")

        # 自動尋找經緯度欄位
        lat_col = next((c for c in df.columns if any(k in c.lower() for k in ['緯', 'lat', 'y'])), None)
        lng_col = next((c for c in df.columns if any(k in c.lower() for k in ['經', 'lng', 'lon', 'x'])), None)

        if not lat_col or not lng_col:
            print(f"[{tag}] ⚠️ 未找到經緯度欄位: {list(df.columns)[:5]}")
            return None

        df[lat_col] = pd.to_numeric(df[lat_col], errors='coerce')
        df[lng_col] = pd.to_numeric(df[lng_col], errors='coerce')

        df_clean = df.dropna(subset=[lat_col, lng_col])
        df_clean = df_clean[(df_clean[lat_col] > 21) & (df_clean[lat_col] < 26) & 
                            (df_clean[lng_col] > 119) & (df_clean[lng_col] < 123)]

        print(f"[{tag}] 解析完成，有效點數：{len(df_clean)}")
        return [[row[lat_col], row[lng_col]] for _, row in df_clean.iterrows()]

    except Exception as e:
        print(f"[{tag}] ❌ 讀取失敗: {e}")
        return None


# --- 2. 建立地圖 ---
m = folium.Map(location=[23.973877, 120.982024], zoom_start=8, tiles="cartodbpositron", control_scale=True)

# A1 重大事故
pts_a1 = fetch_data(URL_A1, "A1事故")
if pts_a1:
    fg1 = folium.FeatureGroup(name="🚨 A1 類重大交通事故 (死亡)", show=True)
    HeatMap(pts_a1, radius=15, blur=10).add_to(fg1)
    fg1.add_to(m)

# A2 交通事故 (自動解壓)
pts_a2 = fetch_data(URL_A2, "A2事故")
if pts_a2:
    fg2 = folium.FeatureGroup(name="⚠️ A2 類交通事故 (受傷)", show=False)
    HeatMap(pts_a2, radius=10, blur=8, gradient={0.4: 'cyan', 0.65: 'yellow', 1: 'orange'}).add_to(fg2)
    fg2.add_to(m)

# 山坡地警戒點
pts_slope = fetch_data(URL_SLOPE, "山坡地警戒")
if pts_slope:
    fg3 = folium.FeatureGroup(name="⛰️ 土石流及坡地災害警戒點", show=False)
    HeatMap(pts_slope, radius=18, blur=12, gradient={0.4: 'purple', 0.8: 'brown', 1: 'darkred'}).add_to(fg3)
    fg3.add_to(m)

# --- 3. 畫面中央 1~3km 動態範圍圈圖層 ---
fg_circles = folium.FeatureGroup(name="🎯 畫面中央 1~3km 固定範圍圈", show=False)
fg_circles.add_to(m)

# 安全注入綁定 Leaflet 實體的 JavaScript
center_js = """
<script>
window.addEventListener('load', function() {
    // 自動取得 Folium 產生的地圖變數
    var mapObj = None;
    for (var key in window) {
        if (key.startsWith('map_') && window[key] instanceof L.Map) {
            mapObj = window[key];
            break;
        }
    }
    
    if (!mapObj) return;

    // 尋找中央圖層 FeatureGroup
    var circleGroup = L.layerGroup().addTo(mapObj);
    
    var c1 = L.circle(mapObj.getCenter(), {radius: 1000, color: 'red', weight: 2, fill: true, fillOpacity: 0.08, interactive: false});
    var c2 = L.circle(mapObj.getCenter(), {radius: 2000, color: 'blue', weight: 1.5, fill: false, interactive: false});
    var c3 = L.circle(mapObj.getCenter(), {radius: 3000, color: 'green', weight: 1.2, fill: false, interactive: false});
    var crosshair = L.circleMarker(mapObj.getCenter(), {radius: 4, color: 'black', fillColor: 'red', fillOpacity: 1, interactive: false});

    circleGroup.addLayer(c1);
    circleGroup.addLayer(c2);
    circleGroup.addLayer(c3);
    circleGroup.addLayer(crosshair);

    function updateCenter() {
        var center = mapObj.getCenter();
        c1.setLatLng(center);
        c2.setLatLng(center);
        c3.setLatLng(center);
        crosshair.setLatLng(center);
    }

    mapObj.on('move', updateCenter);
    mapObj.on('zoomend', updateCenter);
});
</script>
"""
m.get_root().html.add_child(folium.Element(center_js))

# 選單控制
folium.LayerControl(collapsed=False).add_to(m)

# 儲存網頁
m.save("index.html")
print("地圖與圓圈修復完成！")
