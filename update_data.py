import pandas as pd
import folium
from folium.plugins import HeatMap
import requests
import io
import zipfile
import gzip

# 1. API 網址 (包含主要與備用來源)
URL_A1 = "https://opdadm.moi.gov.tw/api/v1/no-auth/resource/api/dataset/02D40248-7CAA-4354-82EA-E27AB8DCAB39/resource/7CE45778-7EF7-4B45-BD69-7BFB6868C0DB/download"

# A2 事故 API (加入多元解壓保護)
URL_A2 = "https://opdadm.moi.gov.tw/api/v1/no-auth/resource/api/dataset/266D0D60-4966-4F2A-A80F-A8659ED511E9/resource/7743EB5B-6A59-4785-B4BA-6D29DEDF82CD/download"

# 山坡地/土石流警戒 API (使用農業部政府開放資料穩定備用節點)
URL_SLOPE = "https://data.moi.gov.tw/MoiOD/System/DownloadFile.aspx?DATA=B75BA704-B091-4D2A-B980-EB141C44F35E"


def fetch_data(url, tag=""):
    try:
        print(f"[{tag}] 開始下載資料: {url}")
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        res = requests.get(url, headers=headers, timeout=60, verify=False)
        res.raise_for_status()

        content = res.content
        df = None

        # 1. 嘗試 Zip 解壓
        if content[:4] == b'PK\x03\x04':
            print(f"[{tag}] 偵測到 ZIP 檔，解壓中...")
            with zipfile.ZipFile(io.BytesIO(content)) as z:
                csv_files = [f for f in z.namelist() if f.endswith('.csv')]
                if csv_files:
                    df = pd.read_csv(z.open(csv_files[0]), on_bad_lines='skip', encoding='utf-8-sig', low_memory=False)

        # 2. 嘗試 Gzip 解壓
        if df is None and content[:2] == b'\x1f\x8b':
            print(f"[{tag}] 偵測到 GZIP 檔，解壓中...")
            with gzip.GzipFile(fileobj=io.BytesIO(content)) as gz:
                df = pd.read_csv(gz, on_bad_lines='skip', encoding='utf-8-sig', low_memory=False)

        # 3. 一般 CSV 讀取
        if df is None:
            df = pd.read_csv(io.BytesIO(content), on_bad_lines='skip', encoding='utf-8-sig', low_memory=False)

        print(f"[{tag}] 成功讀取 {len(df)} 筆原始資料")

        # 自動尋找經緯度欄位 (適應不同官方 API 的命名習慣)
        lat_col = next((c for c in df.columns if any(k in c.lower() for k in ['緯', 'lat', 'y', 'y座標'])), None)
        lng_col = next((c for c in df.columns if any(k in c.lower() for k in ['經', 'lng', 'lon', 'x', 'x座標'])), None)

        if not lat_col or not lng_col:
            print(f"[{tag}] ⚠️ 未找到經緯度欄位，現有欄位: {list(df.columns)[:6]}")
            return None

        df[lat_col] = pd.to_numeric(df[lat_col], errors='coerce')
        df[lng_col] = pd.to_numeric(df[lng_col], errors='coerce')

        df_clean = df.dropna(subset=[lat_col, lng_col])
        # 篩選台灣本島經緯度範圍
        df_clean = df_clean[(df_clean[lat_col] > 21) & (df_clean[lat_col] < 26) & 
                            (df_clean[lng_col] > 119) & (df_clean[lng_col] < 123)]

        print(f"[{tag}] 經緯度解析完畢，有效點數：{len(df_clean)}")
        return [[row[lat_col], row[lng_col]] for _, row in df_clean.iterrows()]

    except Exception as e:
        print(f"[{tag}] ❌ 抓取或解析失敗: {e}")
        return None


# --- 地圖初始化 ---
m = folium.Map(location=[23.973877, 120.982024], zoom_start=8, tiles="cartodbpositron", control_scale=True)

# 1. A1 事故
pts_a1 = fetch_data(URL_A1, "A1事故")
if pts_a1:
    fg1 = folium.FeatureGroup(name="🚨 A1 類重大交通事故 (死亡)", show=True)
    HeatMap(pts_a1, radius=15, blur=10).add_to(fg1)
    fg1.add_to(m)

# 2. A2 事故
pts_a2 = fetch_data(URL_A2, "A2事故")
if pts_a2:
    fg2 = folium.FeatureGroup(name="⚠️ A2 類交通事故 (受傷)", show=False)
    HeatMap(pts_a2, radius=10, blur=8, gradient={0.4: 'cyan', 0.65: 'yellow', 1: 'orange'}).add_to(fg2)
    fg2.add_to(m)

# 3. 山坡地 / 土石流警戒點
pts_slope = fetch_data(URL_SLOPE, "山坡地警戒")
if pts_slope:
    fg3 = folium.FeatureGroup(name="⛰️ 土石流及坡地災害警戒區", show=False)
    HeatMap(pts_slope, radius=18, blur=12, gradient={0.4: 'purple', 0.8: 'brown', 1: 'darkred'}).add_to(fg3)
    fg3.add_to(m)

# 4. 畫面中央 1~3km 固定範圍圈 (CSS Overlay)
css_overlay = """
<style>
.center-crosshair {
    position: absolute; top: 50%; left: 50%;
    transform: translate(-50%, -50%);
    pointer-events: none; z-index: 1000;
    display: flex; justify-content: center; align-items: center;
}
.crosshair-dot { width: 8px; height: 8px; background-color: red; border-radius: 50%; border: 1px solid black; position: absolute; }
.circle-1km { width: 120px; height: 120px; border: 2px dashed red; border-radius: 50%; position: absolute; background: rgba(255, 0, 0, 0.05); }
.circle-2km { width: 240px; height: 240px; border: 1.5px dashed blue; border-radius: 50%; position: absolute; }
.circle-3km { width: 360px; height: 360px; border: 1px dashed green; border-radius: 50%; position: absolute; }
</style>

<div id="center-scope" class="center-crosshair" style="display: none;">
    <div class="circle-3km"></div><div class="circle-2km"></div><div class="circle-1km"></div><div class="crosshair-dot"></div>
</div>

<script>
document.addEventListener('DOMContentLoaded', function() {
    setInterval(function() {
        var labels = document.querySelectorAll('label');
        labels.forEach(function(label) {
            if (label.innerText.includes('畫面中央')) {
                var checkbox = label.querySelector('input');
                var scope = document.getElementById('center-scope');
                if (checkbox && scope) {
                    scope.style.display = checkbox.checked ? 'flex' : 'none';
                }
            }
        });
    }, 500);
});
</script>
"""

fg_scope = folium.FeatureGroup(name="🎯 畫面中央 1~3km 固定範圍圈", show=False)
fg_scope.add_to(m)

m.get_root().html.add_child(folium.Element(css_overlay))
folium.LayerControl(collapsed=False).add_to(m)

m.save("index.html")
print("地圖更新全數完成！")
