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
# 水保署土石流潛勢溪流警告標誌/警戒 JSON 端點
URL_SLOPE = "https://data.ardswc.gov.tw/api/v1/DebrisWarning"

def fetch_data(url, tag="", filter_recent_months=False, drop_dups=True, is_json=False):
    try:
        print(f"[{tag}] 開始下載資料...")
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        session = requests.Session()
        res = session.get(url, headers=headers, timeout=60, verify=False, allow_redirects=True)
        res.raise_for_status()

        df = None

        if is_json:
            data = res.json()
            if isinstance(data, dict) and 'data' in data:
                df = pd.DataFrame(data['data'])
            elif isinstance(data, list):
                df = pd.DataFrame(data)
        else:
            content = res.content

            # Zip 檔解壓處理 (借鏡 Kiang 邏輯)
            if content[:4] == b'PK\x03\x04':
                print(f"[{tag}] 進行 ZIP 解壓...")
                with zipfile.ZipFile(io.BytesIO(content)) as z:
                    dfs = []
                    for info in z.infolist():
                        # 檔名只取最後一截，避免目錄名稱干擾
                        filename_only = info.filename.split('/')[-1]
                        
                        # 🔒 關鍵三重防護：
                        # 1. 絕非資料夾 (!info.is_dir())
                        # 2. 檔案大小大於 10 KB (排除 1KB 的 file.csv, manifest.csv, schema-file.csv)
                        # 3. 檔名包含 NPA_ 且副檔名為 .csv
                        if not info.is_dir() and info.file_size > 10 * 1024 and filename_only.lower().endswith('.csv') and 'NPA_' in filename_only:
                            try:
                                print(f"[{tag}] 成功抓取主資料檔: {filename_only} ({info.file_size / 1024:.1f} KB)")
                                temp_df = pd.read_csv(z.open(info.filename), on_bad_lines='skip', encoding='utf-8-sig', dtype=str)
                                if len(temp_df) > 0:
                                    dfs.append(temp_df)
                            except Exception as parse_err:
                                print(f"[{tag}] ⚠️ 跳過異常子檔案 {info.filename}: {parse_err}")
                        else:
                            if not info.is_dir() and filename_only.lower().endswith('.csv'):
                                print(f"[{tag}] 🙈 忽略小於10KB的中繼/雜訊檔: {filename_only} ({info.file_size} Bytes)")

                    if dfs:
                        df = pd.concat(dfs, ignore_index=True)
                        print(f"[{tag}] 成功併檔 {len(dfs)} 個有效資料集，總計 {len(df)} 筆原始資料")

            # Gzip 檔解壓
            if df is None and content[:2] == b'\x1f\x8b':
                with gzip.GzipFile(fileobj=io.BytesIO(content)) as gz:
                    df = pd.read_csv(gz, on_bad_lines='skip', encoding='utf-8-sig', dtype=str)

            # 一般 CSV 讀取
            if df is None:
                df = pd.read_csv(io.BytesIO(content), on_bad_lines='skip', encoding='utf-8-sig', dtype=str)

        if df is None or len(df) == 0:
            print(f"[{tag}] ⚠️ 資料讀取為空")
            return None

        # 精準鎖定欄位名稱
        lat_col = next((c for c in df.columns if str(c).strip() in ['緯度', 'Lat', 'lat', 'Y', 'y']), None)
        lng_col = next((c for c in df.columns if str(c).strip() in ['經度', 'Lng', 'lng', 'Lon', 'lon', 'X', 'x']), None)
        date_col = next((c for c in df.columns if str(c).strip() in ['發生日期', '日期', 'Date']), None)

        # 備援模糊搜尋
        if not lat_col: lat_col = next((c for c in df.columns if any(k in str(c) for k in ['緯', 'lat', 'Y'])), None)
        if not lng_col: lng_col = next((c for c in df.columns if any(k in str(c) for k in ['經', 'lng', 'lon', 'X'])), None)
        if not date_col: date_col = next((c for c in df.columns if '日' in str(c)), None)

        print(f"[{tag}] 欄位對應 -> 緯度: [{lat_col}], 經度: [{lng_col}], 日期: [{date_col}]")

        if not lat_col or not lng_col:
            print(f"[{tag}] ❌ 找不到經緯度欄位")
            return None

        # --- 時間過濾 ---
        if filter_recent_months is True and date_col is not None:
            now = datetime.now()
            cutoff_date = now - timedelta(days=90)
            
            def parse_8digit_date(val):
                try:
                    s = str(val).strip()
                    if len(s) >= 8:
                        return datetime(int(s[:4]), int(s[4:6]), int(s[6:8]))
                except:
                    return None
                return None

            df['parsed_dt'] = df[date_col].apply(parse_8digit_date)
            valid_cnt = df['parsed_dt'].notnull().sum()

            if valid_cnt > 0:
                df = df[df['parsed_dt'] >= cutoff_date]
                print(f"[{tag}] 進行 90 天時間篩選，剩餘 {len(df)} 筆")
        else:
            print(f"[{tag}] 🔒 不進行時間篩選，保留全量資料")

        # 轉數字與座標區域清潔
        df[lat_col] = pd.to_numeric(df[lat_col], errors='coerce')
        df[lng_col] = pd.to_numeric(df[lng_col], errors='coerce')

        df_clean = df.dropna(subset=[lat_col, lng_col])
        df_clean = df_clean[(df_clean[lat_col] > 21) & (df_clean[lat_col] < 26) & 
                            (df_clean[lng_col] > 119) & (df_clean[lng_col] < 123)]

        if drop_dups:
            df_clean = df_clean.drop_duplicates(subset=[lat_col, lng_col])
            print(f"[{tag}] 執行重複點位清理，最終繪圖點數：{len(df_clean)}")
        else:
            print(f"[{tag}] 🚨 不執行去重，完整繪製所有點數：{len(df_clean)}")

        return df_clean[[lat_col, lng_col]].values.tolist()

    except Exception as e:
        print(f"[{tag}] ❌ 處理失敗: {e}")
        return None

# --- 地圖初始化 ---
m = folium.Map(location=[23.973877, 120.982024], zoom_start=8, tiles="cartodbpositron", control_scale=True)

# 🔒 1. A1 事故 (鎖定：全抓、不篩選時間、不執行去重)
pts_a1 = fetch_data(URL_A1, "A1事故", filter_recent_months=False, drop_dups=False)
if pts_a1:
    fg1 = folium.FeatureGroup(name="🚨 A1 類重大交通事故 (全歷史資料)", show=True)
    HeatMap(pts_a1, radius=15, blur=10).add_to(fg1)
    fg1.add_to(m)

# 2. A2 事故 (近3個月，加強容量過濾與 NPA_ 鎖定)
pts_a2 = fetch_data(URL_A2, "A2事故", filter_recent_months=True, drop_dups=True)
if pts_a2:
    fg2 = folium.FeatureGroup(name="⚠️ A2 類交通事故 (近3個月)", show=False)
    HeatMap(pts_a2, radius=10, blur=8, gradient={0.4: 'cyan', 0.65: 'yellow', 1: 'orange'}).add_to(fg2)
    fg2.add_to(m)

# 3. 山坡地警戒點
pts_slope = fetch_data(URL_SLOPE, "山坡地警戒", filter_recent_months=False, drop_dups=True, is_json=True)
if pts_slope:
    fg3 = folium.FeatureGroup(name="⛰️ 土石流及坡地災害警戒區", show=False)
    HeatMap(pts_slope, radius=18, blur=12, gradient={0.4: 'purple', 0.8: 'brown', 1: 'darkred'}).add_to(fg3)
    fg3.add_to(m)

# --- 4. 動態 Leaflet 地理同心圓圈 ---
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
print("更新完成！")
