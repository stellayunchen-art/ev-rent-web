# app.py — 换电站选址租金评估 网页版
# 部署到 Streamlit Community Cloud（免费）

import re
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
#  读取 Secrets
# ═══════════════════════════════════════════════
AMAP_KEY         = st.secrets.get("AMAP_KEY",         "ce2119b87985d25e49cff4c05c6938ff")
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


def geocode(address: str):
    """
    输入完整地址，返回 (coord, city, district)。
    高德 geocode 响应里自带 city / district，无需用户手填。
    失败时返回 (None, None, None)。
    """
    try:
        r = requests.get(
            "http://restapi.amap.com/v3/geocode/geo",
            params={"address": address, "key": AMAP_KEY, "output": "json"},
            timeout=10,
        ).json()
        if r.get("status") == "1" and r.get("count", "0") != "0":
            geo  = r["geocodes"][0]
            coord = geo["location"]
            # 高德返回 "深圳市" / "广州市"，去掉"市"以匹配 benchmarks.csv 中的城市名
            city_raw = str(geo.get("city", "") or geo.get("province", ""))
            city     = re.sub(r"[市省]$", "", city_raw)
            district = str(geo.get("district", ""))
            return coord, city, district
    except Exception:
        pass
    return None, None, None


def find_nearby_transit(coord: str) -> str:
    """
    用高德关键词周边搜索，找坐标2km内的城轨/地铁/高铁/城际站。
    结果用于给 Coze 提供准确的 POI 距离，防止视觉分析误判为远端地标。
    返回格式化文字，失败时返回空字符串。
    """
    keywords = "地铁站|城轨站|高铁站|城际站|轻轨站|火车站"
    # 名称必须含以下词之一，排除"地铁XX站出口""地铁停车场"等干扰项
    NAME_MUST_CONTAIN = ["地铁", "城轨", "高铁", "城际", "轻轨", "火车站"]
    EXCLUDE = ["出口", "停车", "公交", "换乘中心"]
    try:
        r = requests.get(
            "https://restapi.amap.com/v3/place/around",
            params={
                "location": coord,
                "keywords": keywords,
                "radius":   2000,
                "sortrule": "distance",
                "offset":   5,
                "page":     1,
                "key":      AMAP_KEY,
                "output":   "json",
            },
            timeout=10,
        ).json()
        pois = r.get("pois") or []
        def name_main(name: str) -> str:
            return re.sub(r'[（(][^）)]*[）)]', '', name).strip()

        pois = [p for p in pois
                if any(kw in name_main(str(p.get("name", ""))) for kw in NAME_MUST_CONTAIN)
                and not any(kw in str(p.get("name", "")) for kw in EXCLUDE)]
        if not pois:
            return ""
        lines = []
        for poi in pois[:3]:
            name = str(poi.get("name", "")).strip()
            dist = poi.get("distance", "")
            dist_str = f"{dist}m" if dist else "距离未知"
            lines.append(f"{name}（{dist_str}）")
        return "【周边交通枢纽（高德自动检索，2km内）】\n" + "\n".join(lines)
    except Exception:
        return ""


def find_nearby_industrial(coord: str) -> str:
    """
    用高德关键词周边搜索，找坐标2km内的工业园/产业园/科技园。
    结果拼入 benchmark_info，供 Coze LLM2 正确标注工业地标距离。
    """
    keywords = "产业园|工业园|工业区|科技园|工业城|产业城|创新中心|研发中心"
    NAME_MUST_CONTAIN = [
        "产业园", "工业园", "工业区", "科技园", "工业城", "产业城",
        "创新中心", "研发中心", "产业基地", "工业基地",
    ]
    EXCLUDE = ["停车", "公寓", "宿舍", "社区", "小区"]
    try:
        r = requests.get(
            "https://restapi.amap.com/v3/place/around",
            params={
                "location": coord,
                "keywords": keywords,
                "radius":   2000,
                "sortrule": "distance",
                "offset":   8,
                "page":     1,
                "key":      AMAP_KEY,
                "output":   "json",
            },
            timeout=10,
        ).json()
        pois = r.get("pois") or []
        def name_main(name: str) -> str:
            return re.sub(r'[（(][^）)]*[）)]', '', name).strip()

        pois = [p for p in pois
                if any(kw in name_main(str(p.get("name", ""))) for kw in NAME_MUST_CONTAIN)
                and not any(kw in str(p.get("name", "")) for kw in EXCLUDE)]
        if not pois:
            return ""
        lines = []
        for poi in pois[:5]:
            name = str(poi.get("name", "")).strip()
            dist = poi.get("distance", "")
            dist_str = f"{dist}m" if dist else "距离未知"
            lines.append(f"{name}（{dist_str}）")
        return "【周边工业园/产业园（高德自动检索，2km内）】\n" + "\n".join(lines)
    except Exception:
        return ""


def find_nearby_commercial(coord: str) -> str:
    """
    用高德关键词周边搜索，找坐标1.5km内的大型商业设施。
    搜索名称含「购物广场/商场/购物中心/文化广场/万家福/大润发/沃尔玛/永辉/嘉荣」的地点。
    返回格式化文字，失败时返回空字符串。
    """
    # 搜索关键词（让 API 在附近区域内搜）
    keywords = "购物广场|购物中心|文化广场|万家福|大润发|沃尔玛|永辉|嘉荣|华润万家|家乐福|天虹|步步高|万达|吾悦|宝龙"
    # 返回结果中，POI 名称必须包含以下词之一，才算真正的大型商业设施
    NAME_MUST_CONTAIN = [
        "购物广场", "购物中心", "文化广场", "商业广场", "商业中心",
        "万家福", "大润发", "沃尔玛", "永辉", "嘉荣",
        "华润万家", "家乐福", "天虹", "步步高",
        "万达广场", "吾悦广场", "宝龙广场",
    ]
    # 排除明显的非商业设施
    EXCLUDE = ["停车场", "停车楼", "社区", "小区", "便民", "农贸", "菜市"]
    try:
        r = requests.get(
            "https://restapi.amap.com/v3/place/around",
            params={
                "location": coord,
                "keywords": keywords,
                "radius":   2000,
                "sortrule": "distance",
                "offset":   10,
                "page":     1,
                "key":      AMAP_KEY,
                "output":   "json",
            },
            timeout=10,
        ).json()
        pois = r.get("pois") or []
        # 只保留【名称主体】含大型商业关键词的结果
        # 先去掉括号内容（括号内通常是"XX购物广场店"这类位置说明），再做匹配
        def name_main(name: str) -> str:
            import re
            return re.sub(r'[（(][^）)]*[）)]', '', name).strip()

        pois = [p for p in pois
                if any(kw in name_main(str(p.get("name", ""))) for kw in NAME_MUST_CONTAIN)
                and not any(kw in str(p.get("name", "")) for kw in EXCLUDE)]
        if not pois:
            return ""
        lines = []
        for poi in pois[:5]:
            name = str(poi.get("name", "")).strip()
            dist = poi.get("distance", "")
            dist_str = f"{dist}m" if dist else "距离未知"
            lines.append(f"{name}（{dist_str}）")
        return "【周边大型商业/文化设施（高德自动检索，1.5km内）】\n" + "\n".join(lines)
    except Exception:
        return ""


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
        if d < 0.1:   # 100 米内视为同一站点，跳过
            continue
        candidates.append((d, row))
    candidates.sort(key=lambda x: x[0])
    return candidates[:3]


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
    nearby_transit = find_nearby_transit(coord)
    if nearby_transit:
        benchmark_info = benchmark_info + "\n\n" + nearby_transit
    nearby_industrial = find_nearby_industrial(coord)
    if nearby_industrial:
        benchmark_info = benchmark_info + "\n\n" + nearby_industrial
    nearby_commercial = find_nearby_commercial(coord)
    if nearby_commercial:
        benchmark_info = benchmark_info + "\n\n" + nearby_commercial
    try:
        resp = requests.post(
            "https://api.coze.cn/v1/workflow/run",
            json={
                "workflow_id": COZE_WORKFLOW_ID,
                "parameters": {
                    "station_name":   station_name,
                    "address":        address,
                    "city":           city,
                    "district":       district,
                    "coordinates":    coord,
                    "benchmark_info": benchmark_info,
                },
            },
            headers=headers,
            timeout=300,
        ).json()
    except requests.Timeout:
        return "❌ 超时（300 秒），请稍后重试"
    except Exception as e:
        return f"❌ 请求异常：{e}"

    if resp.get("code") != 0:
        return f"❌ 工作流调用失败（code={resp.get('code')}）：{resp.get('msg', resp)}"

    data = resp.get("data", "")
    try:
        parsed = _json.loads(data)
        if isinstance(parsed, dict):
            for key in ("output", "result", "answer", "content"):
                if key in parsed:
                    return str(parsed[key])
            return str(parsed)
        return str(parsed)
    except Exception:
        return str(data)


def extract_key_numbers(result: str):
    """
    从报告 markdown 中提取：目标单车位租金、谈判起点报价。
    返回 (target_rent, opening_price)，提取失败时返回 None。
    """
    target_rent   = None
    opening_price = None

    for pattern in [
        r"建议目标单车位租金[^：:\d]*[：:][^\d]*(\d+)\s*元",
        r"目标单车位租金[^：:\d]*[：:][^\d]*(\d+)\s*元",
        r"目标租金[^：:\d]*[：:][^\d]*(\d+)\s*元",
    ]:
        m = re.search(pattern, result)
        if m:
            target_rent = m.group(1)
            break

    for pattern in [
        r"谈判起点价[^0-9]*(\d+)\s*元",
        r"起点[报价]*[^：:\d]*[：:][^\d]*(\d+)\s*元",
        r"起点[^0-9]{0,10}(\d+)\s*元",
    ]:
        m = re.search(pattern, result)
        if m:
            opening_price = m.group(1)
            break

    return target_rent, opening_price


# ═══════════════════════════════════════════════
#  页面主体
# ═══════════════════════════════════════════════
st.title("⚡ 换电站选址租金评估")
st.caption("输入站点信息 → AI 自动读取地图、匹配对标案例 → 输出完整租金评估报告")

if not COZE_TOKEN:
    st.warning(
        "⚙️ 尚未配置 Coze Token。\n\n"
        "请在 `.streamlit/secrets.toml`（本地）或 Streamlit Cloud 的 App Settings → Secrets 中填写：\n"
        "```\nCOZE_TOKEN       = \"your_token\"\nCOZE_WORKFLOW_ID = \"7642236438868312079\"\n```",
        icon="⚠️",
    )

# ── 输入表单（简化为 2 个字段）──────────────────
with st.form("eval_form"):
    f_name = st.text_input(
        "站点名称 *",
        placeholder="例：广州天河正佳换电站",
    )
    f_addr = st.text_input(
        "完整地址 *",
        placeholder="例：广东省广州市天河区天河路385号正佳广场旁",
        help="请包含省市区信息，系统将自动解析城市和行政区，无需单独填写",
    )
    submitted = st.form_submit_button("🚀 开始评估", use_container_width=True, type="primary")

# ── 评估流程 ──────────────────────────────────
if submitted:
    if not all([f_name, f_addr]):
        st.error("请填写站点名称和完整地址")
        st.stop()
    if not COZE_TOKEN:
        st.error("请先在 Secrets 中配置 COZE_TOKEN")
        st.stop()

    with st.status("评估进行中…", expanded=True) as status_box:

        # Step 1：Geocode（同时解析 city / district）
        st.write("📍 正在获取坐标（高德 API）…")
        coord, city, district = geocode(f_addr)
        if not coord:
            st.error("❌ 坐标获取失败，请检查地址是否填写正确（建议包含省市区）")
            st.stop()
        st.write(f"✅ 坐标：`{coord}`  |  城市：`{city}`  |  行政区：`{district}`")

        # Step 2：匹配对标站点
        st.write("🔍 正在匹配对标站点（Haversine 直线距离）…")
        df      = load_benchmarks()
        benches = find_benchmarks(coord, city, f_name, df)
        if benches:
            for d_km, row in benches:
                st.write(f"  · {row['name']}  —  {round(d_km, 2)} km")
        else:
            st.write("  ⚠️ 同城市内未找到对标站点，将依赖知识库语义检索")

        # Step 2.5：查周边交通枢纽 + 大型商业设施
        st.write("🚉 正在查询周边交通枢纽（高德 2km 搜索）…")
        nearby_tr = find_nearby_transit(coord)
        if nearby_tr:
            for line in nearby_tr.split("\n")[1:]:
                if line.strip():
                    st.write(f"  · {line.strip()}")
        else:
            st.write("  · 2km 内未检索到城轨/地铁/高铁站")

        st.write("🏭 正在查询周边工业园/产业园（高德 2km 搜索）…")
        nearby_ind = find_nearby_industrial(coord)
        if nearby_ind:
            for line in nearby_ind.split("\n")[1:]:
                if line.strip():
                    st.write(f"  · {line.strip()}")
        else:
            st.write("  · 2km 内未检索到工业园/产业园")

        st.write("🏬 正在查询周边大型商业设施（高德 2km 关键词搜索）…")
        nearby = find_nearby_commercial(coord)
        if nearby:
            for line in nearby.split("\n")[1:]:   # 跳过标题行
                if line.strip():
                    st.write(f"  · {line.strip()}")
        else:
            st.write("  · 1.5km 内未检索到大型商业/文化设施")

        # Step 3：调用 Coze 工作流
        st.write("🤖 正在调用 Coze 工作流（含地图视觉分析，通常需要 30–90 秒）…")
        result = call_workflow(f_name, city, district, f_addr, coord, benches)
        status_box.update(label="✅ 评估完成！", state="complete")

    # ── 双视图展示 ────────────────────────────
    st.divider()
    tab_finance, tab_biz = st.tabs(["📊 财务BP 完整报告", "💼 商务同事视图"])

    # ── 财务BP 视图 ───────────────────────────
    with tab_finance:
        st.subheader("📋 租金评估报告")
        # Markdown 单换行=空格，需在行尾加两个空格才能强制换行
        # 章节标题前额外插入 --- 分隔线
        SECTION_EMOJIS = ("📍", "📚", "💡", "💰", "🤝", "🔥")
        formatted_lines = []
        for line in result.splitlines():
            stripped = line.lstrip()
            if any(stripped.startswith(e) for e in SECTION_EMOJIS) and formatted_lines:
                formatted_lines.append("")
                formatted_lines.append("---")
                formatted_lines.append("")
            # 非空行末尾加两个空格，强制 Markdown 保留换行
            formatted_lines.append(line + ("  " if stripped else ""))
        st.markdown("\n".join(formatted_lines))
        with st.expander("📋 一键复制纯文本"):
            st.code(result, language=None)
        st.download_button(
            label="💾 下载报告（.txt）",
            data=f"站点：{f_name}\n地址：{f_addr}\n坐标：{coord}\n城市：{city}  行政区：{district}\n\n{result}",
            file_name=f"租金评估_{f_name}.txt",
            mime="text/plain",
            use_container_width=True,
        )

    # ── 商务同事 视图 ─────────────────────────
    with tab_biz:
        target_rent, opening_price = extract_key_numbers(result)

        # 1. 站点确认
        st.markdown("#### ✅ 站点确认")
        st.markdown(f"**站点名称：** {f_name}")
        st.markdown(f"**地址：** {f_addr}")
        st.markdown(f"**城市 / 行政区：** {city} · {district}")

        st.divider()

        # 2. 周边参考站点（距离 + 单车位租金，不显示边界）
        st.markdown("#### 📍 周边参考站点")
        if benches:
            table_rows = []
            for d_km, row in benches:
                unit_rent = str(row.get("unit_rent", "")).strip()
                try:
                    unit_rent_display = f"{round(float(unit_rent))} 元/月"
                except (ValueError, TypeError):
                    unit_rent_display = "—"
                table_rows.append({
                    "站点名称":   row["name"],
                    "直线距离":   f"{round(d_km, 2)} km",
                    "单车位租金": unit_rent_display if unit_rent and unit_rent != "nan" else "—",
                })
            st.table(pd.DataFrame(table_rows))
        else:
            st.info("同城市内未找到近距离参考站点")

        st.divider()

        # 3. 目标单车位租金
        st.markdown("#### 🎯 目标单车位租金")
        if target_rent:
            st.metric(label="AI 建议成交价", value=f"{target_rent} 元/车位/月")
        else:
            st.warning("未能自动提取，请查看「财务BP 完整报告」标签页")

        st.divider()

        # 4. 谈判策略
        st.markdown("#### 🤝 谈判策略")
        if opening_price:
            st.markdown(f"**起点报价：** {opening_price} 元/车位/月")
        else:
            st.warning("未能自动提取，请查看「财务BP 完整报告」标签页")
