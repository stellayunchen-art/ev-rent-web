# app.py — 换电站选址租金评估 网页版
# 部署到 Streamlit Community Cloud（免费）

import streamlit as st
import requests
import pandas as pd
from math import radians, sin, cos, sqrt, atan2
from pathlib import Path

# ═══════════════════════════════════════════════
#  页面基础配置
# ═══════════════════════════════════════════════
st.set_page_config(
    page_title="换电站租金评估",
    page_icon="⚡",
    layout="centered",
)

# ═══════════════════════════════════════════════
#  读取 Secrets（本地 .streamlit/secrets.toml；
#  Streamlit Cloud 上在 App Settings → Secrets 填写）
# ═══════════════════════════════════════════════
AMAP_KEY    = st.secrets.get("AMAP_KEY",    "ce2119b87985d25e49cff4c05c6938ff")
COZE_TOKEN       = st.secrets.get("COZE_TOKEN",       "")
COZE_WORKFLOW_ID = st.secrets.get("COZE_WORKFLOW_ID", "7642236438868312079")

HIGHWAY_KEYWORDS = ["高速", "服务区", "收费站"]
BENCH_CSV = Path(__file__).parent / "benchmarks.csv"

# ═══════════════════════════════════════════════
#  工具函数
# ═══════════════════════════════════════════════
def is_highway(name: str) -> bool:
    return any(kw in str(name) for kw in HIGHWAY_KEYWORDS)


def haversine(c1: str, c2: str) -> float:
    try:
        lng1, lat1 = map(float, c1.split(","))
        lng2, lat2 = map(float, c2.split(","))
        R = 6371
        dlat = radians(lat2 - lat1)
        dlng = radians(lng2 - lng1)
        a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlng / 2) ** 2
        return R * 2 * atan2(sqrt(a), sqrt(1 - a))
    except Exception:
        return 99999.0


@st.cache_data(show_spinner=False)
def load_benchmarks() -> pd.DataFrame:
    if not BENCH_CSV.exists():
        return pd.DataFrame()
    return pd.read_csv(BENCH_CSV, dtype=str).fillna("")


def geocode(address: str, city: str):
    try:
        r = requests.get(
            "http://restapi.amap.com/v3/geocode/geo",
            params={"address": address, "city": city, "key": AMAP_KEY, "output": "json"},
            timeout=10,
        ).json()
        if r.get("status") == "1" and r.get("count", "0") != "0":
            return r["geocodes"][0]["location"]
    except Exception:
        pass
    return None


def find_benchmarks(coord: str, city: str, station_name: str, df: pd.DataFrame):
    if df.empty:
        return []
    hw = is_highway(station_name)
    candidates = []
    for _, row in df.iterrows():
        if row["name"] == station_name:
            continue
        if row["city"] != city:
            continue
        if "," not in str(row.get("coord", "")):
            continue
        row_hw = is_highway(str(row["name"]))
        if hw and not row_hw:
            continue
        if not hw and row_hw:
            continue
        d = haversine(coord, row["coord"])
        candidates.append((d, row))
    candidates.sort(key=lambda x: x[0])
    return candidates[:3]


def build_prompt(name, city, district, address, coord, benches) -> str:
    base = "https://restapi.amap.com/v3/staticmap"
    mk   = f"mid,,A:{coord}"
    u13  = f"{base}?location={coord}&zoom=13&size=600*600&markers={mk}&key={AMAP_KEY}"
    u14  = f"{base}?location={coord}&zoom=14&size=600*600&markers={mk}&key={AMAP_KEY}"
    u15  = f"{base}?location={coord}&zoom=15&size=600*600&markers={mk}&key={AMAP_KEY}"

    lines = [
        "请帮我评估以下换电站租金：",
        f"站点名称：{name}",
        f"详细地址：{city}{district}{address}",
        "地图参考：",
        f"zoom13：{u13}",
        f"zoom14：{u14}",
        f"zoom15：{u15}",
    ]

    if benches:
        lines.append("\n参考对标站点（按直线距离排序）：")
        for i, (d_km, row) in enumerate(benches, 1):
            parts = [f"对标{i}：{row['name']}（{round(d_km, 2)}km）"]
            for key, label in [
                ("unit_rent",  "单车位租金"),
                ("bound_rent", "租金边界"),
                ("bc_type",    "商圈类型"),
                ("area_type",  "区域类型"),
                ("road_cond",  "道路条件"),
                ("road_type",  "道路类型"),
            ]:
                v = str(row.get(key, "")).strip()
                if v and v != "nan":
                    parts.append(f"{label}：{v}")
            lines.append(" | ".join(parts))

    return "\n".join(lines)


def format_benchmark_info(benches) -> str:
    """把 Haversine 匹配到的对标站点格式化成文字，传给 Coze 工作流。"""
    if not benches:
        return "（同城市内未找到近距离对标站点，请依赖知识库语义检索）"
    lines = []
    for i, (d_km, row) in enumerate(benches, 1):
        parts = [f"对标{i}：{row['name']}（{round(d_km, 2)}km）"]
        for key, label in [
            ("unit_rent",  "单车位租金"),
            ("bound_rent", "租金边界"),
            ("bc_type",    "商圈类型"),
            ("area_type",  "区域类型"),
            ("road_cond",  "道路条件"),
            ("road_type",  "道路类型"),
        ]:
            v = str(row.get(key, "")).strip()
            if v and v not in ("nan", ""):
                parts.append(f"{label}：{v}")
        lines.append(" | ".join(parts))
    return "\n".join(lines)


def call_workflow(station_name, city, district, address, coord, benches=None) -> str:
    """调用 Coze 工作流 API，同步等待返回结果。"""
    import json as _json
    headers = {"Authorization": f"Bearer {COZE_TOKEN}", "Content-Type": "application/json"}

    benchmark_info = format_benchmark_info(benches or [])

    try:
        resp = requests.post(
            "https://api.coze.cn/v1/workflow/run",
            json={
                "workflow_id": COZE_WORKFLOW_ID,
                "parameters": {
                    "station_name":   station_name,
                    "address":        f"{city}{district}{address}",
                    "city":           city,
                    "district":       district,
                    "coordinates":    coord,
                    "benchmark_info": benchmark_info,
                },
            },
            headers=headers,
            timeout=180,   # 工作流含视觉分析，最多等 3 分钟
        ).json()
    except requests.Timeout:
        return "❌ 超时（180 秒），请稍后重试"
    except Exception as e:
        return f"❌ 请求异常：{e}"

    if resp.get("code") != 0:
        return f"❌ 工作流调用失败（code={resp.get('code')}）：{resp.get('msg', resp)}"

    data = resp.get("data", "")
    # data 可能是 JSON 字符串，也可能直接是文本
    try:
        parsed = _json.loads(data)
        if isinstance(parsed, dict):
            # 尝试常见字段名
            for key in ("output", "result", "answer", "content"):
                if key in parsed:
                    return str(parsed[key])
            return str(parsed)
        return str(parsed)
    except Exception:
        return str(data)


# ═══════════════════════════════════════════════
#  页面主体
# ═══════════════════════════════════════════════
st.title("⚡ 换电站选址租金评估")
st.caption("输入站点信息 → AI 自动读取地图、匹配对标案例 → 输出完整租金评估报告")

# 配置缺失时给出提示
if not COZE_TOKEN:
    st.warning(
        "⚙️ 尚未配置 Coze Token。\n\n"
        "请在 `.streamlit/secrets.toml`（本地）或 Streamlit Cloud 的 App Settings → Secrets 中填写：\n"
        "```\nCOZE_TOKEN       = \"your_token\"\nCOZE_WORKFLOW_ID = \"7642236438868312079\"\n```",
        icon="⚠️",
    )

# ── 输入表单 ──────────────────────────────────
with st.form("eval_form"):
    col1, col2 = st.columns(2)
    with col1:
        f_name = st.text_input("站点名称 *", placeholder="例：广州天河正佳换电站")
        f_city = st.text_input(
            "城市 *",
            placeholder="例：广州",
            help="增城、花都、从化等请填「广州」，否则找不到同城对标站点",
        )
    with col2:
        f_dist = st.text_input("行政区 *", placeholder="例：天河区")
        f_addr = st.text_input("详细地址 *", placeholder="例：天河路385号正佳广场旁")

    submitted = st.form_submit_button("🚀 开始评估", use_container_width=True, type="primary")

# ── 评估流程 ──────────────────────────────────
if submitted:
    if not all([f_name, f_city, f_dist, f_addr]):
        st.error("请填写所有标 * 的字段")
        st.stop()
    if not COZE_TOKEN:
        st.error("请先在 Secrets 中配置 COZE_TOKEN")
        st.stop()

    with st.status("评估进行中…", expanded=True) as status_box:

        # Step 1：Geocode
        st.write("📍 正在获取坐标（高德 API）…")
        coord = geocode(f"{f_dist}{f_addr}", f_city)
        if not coord:
            st.error("❌ 坐标获取失败，请检查城市 / 地址是否填写正确")
            st.stop()
        st.write(f"✅ 坐标：`{coord}`")

        # Step 2：匹配对标站点
        st.write("🔍 正在匹配对标站点（Haversine 直线距离）…")
        df      = load_benchmarks()
        benches = find_benchmarks(coord, f_city, f_name, df)
        if benches:
            for d_km, row in benches:
                st.write(f"  · {row['name']}  —  {round(d_km, 2)} km")
        else:
            st.write("  ⚠️ 同城市内未找到对标站点，将依赖知识库语义检索")

        # Step 3：调用 Coze 工作流
        st.write("🤖 正在调用 Coze 工作流（含地图视觉分析，通常需要 30–90 秒）…")
        result = call_workflow(f_name, f_city, f_dist, f_addr, coord, benches)
        status_box.update(label="✅ 评估完成！", state="complete")

    # ── 显示结果 ──────────────────────────────
    st.divider()
    st.subheader("📋 租金评估报告")
    st.markdown(result)

    st.download_button(
        label="💾 下载报告（.txt）",
        data=f"站点：{f_name}\n地址：{f_city}{f_dist}{f_addr}\n坐标：{coord}\n\n{result}",
        file_name=f"租金评估_{f_name}.txt",
        mime="text/plain",
        use_container_width=True,
    )
