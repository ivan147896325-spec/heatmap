import pandas as pd
import folium
from folium.plugins import HeatMap
import requests
import io
import zipfile
import gzip
from datetime import datetime, timedelta

# 1. 官方 API 網址
URL_A1 = "https://opdadm.moi.gov.tw/api/v1/no-auth/resource/api/dataset/02D40248-7CAA-4354-82EA-E27AB8DCAB39/resource/7CE45778-7EF7-4B45-BD69-7BFB6868C0DB/download"
URL_A2 = "https://opdadm.moi.gov.tw/api/v1/no-auth/resource/api/dataset/266D0D60-4966-4F2A-A80F-A8659ED511E9/resource/7743EB5B-6A59-4785-B4BA-6D29DEDF82CD/download"
URL_SLOPE = "https://data.ardswc.gov.tw/api/v1/DebrisWarning"

def fetch_data(url, tag="", filter_recent_months=False, is_json=False):
    try:
        print(f"[{tag}] 開始下載資料...")
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': '*/*',
            'Connection': 'keep-alive'
        }
        
        session = requests.Session()
        res = session.get(url, headers=headers, timeout=60, verify=False, allow_redirects=True)
        res.raise_for_status()

        df = None

        if is_json:
            data = res.json()
            if isinstance(data, dict) and 'data' in data:
                df = pd.DataFrame(data['data'])
            else:
                df = pd.DataFrame(data)
        else:
            content = res.content
            # 1. Zip 檔解壓 (瞄準 NPA 開頭的所有主檔並合併)
            if content[:4] == b'PK\x03\x04':
                print(f"[{tag}] 進行 ZIP 解壓...")
                with zipfile.ZipFile(io.BytesIO(content)) as z:
                    # 抓出所有 NPA 開頭且為 CSV 的檔案
                    npa_files = [f for f in z.namelist() if f.upper().startswith('NPA') and f.lower().endswith('.csv')]
                    
                    if npa_files:
                        dfs = []
                        for file_name in npa_files:
                            print(f"[{tag}] 讀取主檔案: {file_name}")
                            temp_df = pd.read_csv(z.open(file_name), on_bad_lines='skip', encoding='utf-8-sig', low_memory=False)
                            dfs.append(temp_df)
                        
                        # 全部 NPA 檔案合併
                        df = pd.concat(dfs, ignore_index=True)
                        print(f"[{tag}] 已成功合併 {len(npa_files)} 個 NPA 資料檔")
                    else:
                        # 備案：萬一沒有 NPA 前綴，避開小檔案（容量 > 100KB 的檔）
                        main_files = [f for f in z.namelist() if f.lower().endswith('.csv') and z.getinfo(f).file_size > 100 * 1024]
                        if main_files:
                            dfs = [pd.read_csv(z.open(f), on_bad_lines='skip', encoding='utf-8-sig', low_memory=False) for f in main_files]
                            df = pd.concat(dfs, ignore_index=True)

            # 2. Gzip 檔解壓
            if df is None and content[:2] == b'\x1f\x8b':
                print(f"[{tag}] 進行 GZIP 解壓...")
                with gzip.GzipFile(fileobj=io.BytesIO(content)) as gz:
                    df = pd.read_csv(gz, on_bad_lines='skip', encoding='utf-8-sig', low_memory=False)

            # 3. 一般 CSV 讀取
            if df is None:
                df = pd.read_csv(io.BytesIO(content), on_bad_lines='skip', encoding='utf-8-sig', low_memory=False)

        if df is None or len(df) == 0:
            print(f"[{tag}] ⚠️ 無法解析內容或資料為空")
            return None

        print(f"[{tag}] 成功讀取總計 {len(df)} 筆原始資料")

        # 自動尋找經緯度與日期欄位
        lat_col = next((c for c in df.columns if any(k in str(c).lower() for k in ['緯', 'lat', 'y', 'latitude'])), None)
        lng_col = next((c for c in df.columns if any(k in str(c).lower() for k in ['經', 'lng', 'lon', 'x', 'longitude'])), None)
        date_col = next((c for c in df.columns if any(k in str(c).lower() for k in ['日', 'date', '時間'])), None)

        if not lat_col or not lng_col:
            print(f"[{tag}] ⚠️ 未找到經緯度欄位")
            return None

        # --- 現實時間近 3 個月 (90天) 動態過濾 ---
        if filter_recent_months and date_col:
            now = datetime.now()
            cutoff_date = now - timedelta(days=90)
            print(f"[{tag}] 執行時間比對，基準點：{now.strftime('%Y-%m-%d')}，過濾 {cutoff_date.strftime('%Y-%m-%d')} 至今資料...")

            def parse_date(val):
                try:
                    s = str(val).strip().split(' ')[0].replace('-', '').replace('/', '')
                    if len(s) == 7: # 民國年 1150501
                        year = int(s[:3]) + 1911
                        month = int(s[3:5])
                        day = int(s[5:7])
                        return datetime(year, month, day)
                    elif len(s) >= 8: # 西元年 20260501
                        return datetime(int(s[:4]), int(s[4:6]), int(s[6:8]))
                except:
                    return None
                return None

            df['parsed_dt'] = df[date_col].apply(parse_date)
            df = df[df['parsed_dt'] >= cutoff_date]
            print(f"[{tag}] 近3個月時間過濾完成，剩餘 {len(df)} 筆資料")

        df[lat_col] = pd.to_numeric(df[lat_col], errors='coerce')
        df[lng_col] = pd.to_numeric(df[lng_col], errors='coerce')

        df_clean = df.dropna(subset=[lat_col, lng_col])
        df_clean = df_clean[(df_clean[lat_col] > 21) & (df_clean[lat_col] < 26) & 
                            (df_clean[lng_col] > 119) & (df_clean[lng_col] < 123)]

        print(f"[{tag}] 解析完成，有效繪圖點數：{len(df_clean)}")
        return [[row[lat_col], row[lng_col]] for _, row in df_clean.iterrows()]

    except Exception as e:
        print(f"[{tag}] ❌ 處理失敗: {e}")
        return None

# --- 地圖初始化 ---
m = folium.Map(location=[23.973877, 120.982024], zoom_start=8, tiles="cartodbpositron", control_scale=True)

# 1. A1 事故 (近3個月)
pts_a1 = fetch_data(URL_A1, "A1事故", filter_recent_months=True)
if pts_a1:
    fg1 = folium.FeatureGroup(name="🚨 A1 類重大交通事故 (近3個月)", show=True)
    HeatMap(pts_a1, radius=15, blur=10).add_to(fg1)
    fg1.add_to(m)

# 2. A2 事故 (近3個月，全數抓取 NPA 開頭主檔並合併)
pts_a2 = fetch_data(URL_A2, "A2事故", filter_recent_months=True)
if pts_a2:
    fg2 = folium.FeatureGroup(name="⚠️ A2 類交通事故 (近3個月)", show=False)
    HeatMap(pts_a2, radius=10, blur=8, gradient={0.4: 'cyan', 0.65: 'yellow', 1: 'orange'}).add_to(fg2)
    fg2.add_to(m)

# 3. 山坡地警戒點
pts_slope = fetch_data(URL_SLOPE, "山坡地警戒", filter_recent_months=False, is_json=True)
if pts_slope:
    fg3 = folium.FeatureGroup(name="⛰️ 土石流及坡地災害警戒區", show=False)
    HeatMap(pts_slope, radius=18, blur=12, gradient={0.4: 'purple', 0.8: 'brown', 1: 'darkred'}).add_to(fg3)
    fg3.add_to(m)

# --- 4. 真實 Leaflet 地理同心圓圈 ---
real_geo_js = """
<script>
window.addEventListener('load', function() {
    var mapInst = null;
    for (var l in window) {
        if (window[l] instanceof L.Map) {
            mapInst = window[l];
            break;
        }
    }

    if (mapInst) {
        var circleGroup = L.layerGroup();

        var c1 = L.circle(mapInst.getCenter(), {radius: 1000, color: 'red', weight: 2, fill: true, fillOpacity: 0.08, interactive: false});
        var c2 = L.circle(mapInst.getCenter(), {radius: 2000, color: 'blue', weight: 1.5, fill: false, interactive: false});
        var c3 = L.circle(mapInst.getCenter(), {radius: 3000, color: 'green', weight: 1.2, fill: false, interactive: false});
        var centerDot = L.circleMarker(mapInst.getCenter(), {radius: 4, color: 'black', fillColor: 'red', fillOpacity: 1, interactive: false});

        circleGroup.addLayer(c1);
        circleGroup.addLayer(c2);
        circleGroup.addLayer(c3);
        circleGroup.addLayer(centerDot);

        function updateGeoCircles() {
            var center = mapInst.getCenter();
            c1.setLatLng(center);
            c2.setLatLng(center);
            c3.setLatLng(center);
            centerDot.setLatLng(center);
        }

        mapInst.on('move', updateGeoCircles);

        setInterval(function() {
            var labels = document.querySelectorAll('label');
            labels.forEach(function(label) {
                if (label.innerText.includes('畫面中央')) {
                    var checkbox = label.querySelector('input');
                    if (checkbox) {
                        if (checkbox.checked && !mapInst.hasLayer(circleGroup)) {
                            mapInst.addLayer(circleGroup);
                        } else if (!checkbox.checked && mapInst.hasLayer(circleGroup)) {
                            mapInst.removeLayer(circleGroup);
                        }
                    }
                }
            });
        }, 400);
    }
});
</script>
"""

fg_scope = folium.FeatureGroup(name="🎯 畫面中央 1~3km 固定範圍圈", show=False)
fg_scope.add_to(m)

m.get_root().html.add_child(folium.Element(real_geo_js))
folium.LayerControl(collapsed=False).add_to(m)

m.save("index.html")
print("更新完成！現在會將所有 NPA 開頭的事故 CSV 全部合併處理！")
