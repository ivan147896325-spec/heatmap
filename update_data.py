import pandas as pd
import folium
from folium.plugins import HeatMap
from datetime import datetime, timedelta

# 1. 官方 API 網址設定
URL_A1 = "https://opdadm.moi.gov.tw/api/v1/no-auth/resource/api/dataset/02D40248-7CAA-4354-82EA-E27AB8DCAB39/resource/7CE45778-7EF7-4B45-BD69-7BFB6868C0DB/download"
URL_A2 = "https://opdadm.moi.gov.tw/api/v1/no-auth/resource/api/dataset/266D0D60-4966-4F2A-A80F-A8659ED511E9/resource/7743EB5B-6A59-4785-B4BA-6D29DEDF82CD/download"
URL_SLOPE = "https://data.ardwc.gov.tw/dataset/d883b28b-b83b-4809-a75e-a6167ec50bc5/resource/46487e41-0f81-42cb-bc28-9d4cb058e11a/download/debris.csv"


def process_data(url, name_tag="資料", filter_recent_months=True):
    try:
        print(f"正在抓取 [{name_tag}]...")
        df = pd.read_csv(url, on_bad_lines='skip', encoding='utf-8-sig', low_memory=False)
        
        lat_col = next((c for c in df.columns if '緯' in c or 'lat' in c.lower()), None)
        lng_col = next((c for c in df.columns if '經' in c or 'lng' in c.lower() or 'lon' in c.lower()), None)
        
        if not lat_col or not lng_col:
            print(f"[{name_tag}] ⚠️ 未找到經緯度欄位")
            return None
            
        df[lat_col] = pd.to_numeric(df[lat_col], errors='coerce')
        df[lng_col] = pd.to_numeric(df[lng_col], errors='coerce')
        
        df_clean = df.dropna(subset=[lat_col, lng_col]).copy()
        df_clean = df_clean[(df_clean[lat_col] > 21) & (df_clean[lat_col] < 26) & 
                            (df_clean[lng_col] > 119) & (df_clean[lng_col] < 123)]
        
        if filter_recent_months:
            date_col = next((c for c in df.columns if '日期' in c or 'date' in c.lower()), None)
            if date_col:
                def parse_taiwan_date(d):
                    try:
                        s = str(int(float(d)))
                        if len(s) == 7:
                            return datetime(int(s[:3]) + 1911, int(s[3:5]), int(s[5:7]))
                        elif len(s) == 8:
                            return datetime.strptime(s, "%Y%m%d")
                    except:
                        return None
                    return None

                df_clean['parsed_date'] = df_clean[date_col].apply(parse_taiwan_date)
                max_date = df_clean['parsed_date'].max()
                
                if pd.notnull(max_date):
                    cutoff_date = max_date - timedelta(days=90)
                    df_filtered = df_clean[df_clean['parsed_date'] >= cutoff_date]
                    if not df_filtered.empty:
                        df_clean = df_filtered
        
        print(f"[{name_tag}] 成功處理：{len(df_clean)} 筆")
        return [[row[lat_col], row[lng_col]] for _, row in df_clean.iterrows()]

    except Exception as e:
        print(f"[{name_tag}] 處理失敗: {e}")
        return None


# --- 開始建立地圖 ---
center_loc = [23.973877, 120.982024]
m = folium.Map(
    location=center_loc, 
    zoom_start=8, 
    tiles="cartodbpositron",
    control_scale=True
)

# 1. A1 事故圖層
heat_a1 = process_data(URL_A1, name_tag="A1事故", filter_recent_months=True)
if heat_a1:
    fg_a1 = folium.FeatureGroup(name="🚨 A1 類重大交通事故 (最新3個月)", show=True)
    HeatMap(heat_a1, radius=15, blur=10, gradient={0.4: 'blue', 0.65: 'lime', 1: 'red'}).add_to(fg_a1)
    fg_a1.add_to(m)

# 2. A2 事故圖層
heat_a2 = process_data(URL_A2, name_tag="A2事故", filter_recent_months=True)
if heat_a2:
    fg_a2 = folium.FeatureGroup(name="⚠️ A2 類交通事故 (最新3個月)", show=False)
    HeatMap(heat_a2, radius=10, blur=8, gradient={0.4: 'cyan', 0.65: 'yellow', 1: 'orange'}).add_to(fg_a2)
    fg_a2.add_to(m)

# 3. 山坡地警戒圖層
heat_slope = process_data(URL_SLOPE, name_tag="山坡地警戒", filter_recent_months=False)
if heat_slope:
    fg_slope = folium.FeatureGroup(name="⛰️ 土石流/山坡地警戒點", show=False)
    HeatMap(heat_slope, radius=18, blur=12, gradient={0.4: 'purple', 0.8: 'brown', 1: 'darkred'}).add_to(fg_slope)
    fg_slope.add_to(m)

# 4. 畫面中央 1km / 2km / 3km 固定範圍圈圖層 (預設隱藏，可由右上角開啟)
fg_center_circles = folium.FeatureGroup(name="🎯 畫面中央 1~3km 固定範圍圈", show=False)
fg_center_circles.add_to(m)

# 注入動態追蹤畫面中央點的 JavaScript
center_js = """
<script>
document.addEventListener('DOMContentLoaded', function() {
    var c1 = L.circle(map.getCenter(), {radius: 1000, color: 'red', weight: 2, fill: true, fillOpacity: 0.08, interactive: false});
    var c2 = L.circle(map.getCenter(), {radius: 2000, color: 'blue', weight: 1.5, fill: false, interactive: false});
    var c3 = L.circle(map.getCenter(), {radius: 3000, color: 'green', weight: 1.2, fill: false, interactive: false});
    
    // 中央小十字標記
    var crosshair = L.circleMarker(map.getCenter(), {radius: 4, color: 'black', fillColor: 'red', fillOpacity: 1, interactive: false});

    // 取得圖層物件綁定
    var circleGroup = null;
    map.eachLayer(function(layer) {
        if (layer.options && layer.options.name && layer.options.name.includes("畫面中央")) {
            circleGroup = layer;
        }
    });

    if (circleGroup) {
        circleGroup.addLayer(c1);
        circleGroup.addLayer(c2);
        circleGroup.addLayer(c3);
        circleGroup.addLayer(crosshair);
    }

    // 地圖平移或縮放時，同步更新圓心位置
    function updateCenterCircles() {
        var center = map.getCenter();
        c1.setLatLng(center);
        c2.setLatLng(center);
        c3.setLatLng(center);
        crosshair.setLatLng(center);
    }

    map.on('move', updateCenterCircles);
});
</script>
"""
m.get_root().html.add_child(folium.Element(center_js))

# 右上角開關選單
folium.LayerControl(collapsed=False).add_to(m)

# 儲存
m.save("index.html")
print("成功生成畫面中央固定 1~3km 範圍圈圖層！")
