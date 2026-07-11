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

# ── 全局样式 ──────────────────────────────────
st.markdown("""
<style>
/* 主标题横幅 */
.hero-banner {
    background: linear-gradient(135deg, #1a2980 0%, #26d0ce 100%);
    border-radius: 14px;
    padding: 26px 30px 22px 30px;
    margin-bottom: 6px;
    color: #ffffff;
}
.hero-banner h1 {
    margin: 0;
    font-size: 1.75rem;
    font-weight: 700;
    color: #ffffff;
    letter-spacing: 1px;
}
.hero-banner p {
    margin: 8px 0 0 0;
    font-size: 0.92rem;
    color: rgba(255,255,255,0.85);
}
/* 指标卡片 */
div[data-testid="stMetric"] {
    background: linear-gradient(180deg, #f8faff 0%, #eef3fb 100%);
    border: 1px solid #dbe4f3;
    border-radius: 12px;
    padding: 14px 16px;
}
div[data-testid="stMetric"] label { color: #5b6b8c; }
/* 报告分节卡片内的标题行 */
.section-title {
    font-size: 1.02rem;
    font-weight: 700;
    margin-bottom: 2px;
}
/* 表格圆角 */
div[data-testid="stTable"] table { border-radius: 10px; overflow: hidden; }
/* 按钮圆角 */
.stButton > button, .stDownloadButton > button, .stFormSubmitButton > button { border-radius: 10px; }
</style>
""", unsafe_allow_html=True)

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


@st.cache_data(show_spinner=False, ttl=300)
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


def _name_main(name: str) -> str:
    """去掉括号内的位置说明，返回名称主体。"""
    return re.sub(r'[（(][^）)]*[）)]', '', name).strip()


def _kw_at_end(name_m: str, keywords: list) -> bool:
    """关键词必须出现在名称末尾（后面最多跟1个字符，如A/B区编号），过滤"工业区五期仓库"类噪音。"""
    for kw in keywords:
        idx = name_m.find(kw)
        if idx == -1:
            continue
        after = name_m[idx + len(kw):]
        if len(after) <= 1:   # 末尾或仅跟单字区编号
            return True
    return False


def find_nearby_transit(coord: str) -> str:
    """2km内城轨/地铁/高铁/城际站，结果传给 Coze 防止误判距离。"""
    keywords = "地铁站|城轨站|高铁站|城际站|轻轨站|火车站"
    NAME_MUST_CONTAIN = ["地铁", "城轨", "高铁", "城际", "轻轨", "火车站"]
    EXCLUDE = ["出口", "停车", "公交", "换乘中心"]
    try:
        r = requests.get(
            "https://restapi.amap.com/v3/place/around",
            params={"location": coord, "keywords": keywords, "radius": 2000,
                    "sortrule": "distance", "offset": 5, "page": 1,
                    "key": AMAP_KEY, "output": "json"},
            timeout=10,
        ).json()
        pois = r.get("pois") or []
        pois = [p for p in pois
                if any(kw in _name_main(str(p.get("name", ""))) for kw in NAME_MUST_CONTAIN)
                and "-" not in _name_main(str(p.get("name", "")))
                and not any(kw in str(p.get("name", "")) for kw in EXCLUDE)]
        if not pois:
            return ""
        lines = [f"{p.get('name', '').strip()}（{p.get('distance', '')}m）" for p in pois[:3]]
        return "【周边交通枢纽（高德自动检索，2km内）】\n" + "\n".join(lines)
    except Exception:
        return ""


def find_nearby_industrial(coord: str) -> str:
    """2km内工业园/产业园，结果传给 Coze 防止误判距离。"""
    keywords = "产业园|工业园|工业区|科技园|工业城|产业城|创新中心|研发中心"
    NAME_MUST_CONTAIN = [
        "产业园", "工业园", "工业区", "科技园", "工业城", "产业城",
        "创新中心", "研发中心", "产业基地", "工业基地",
    ]
    try:
        r = requests.get(
            "https://restapi.amap.com/v3/place/around",
            params={"location": coord, "keywords": keywords, "radius": 2000,
                    "sortrule": "distance", "offset": 8, "page": 1,
                    "key": AMAP_KEY, "output": "json"},
            timeout=10,
        ).json()
        pois = r.get("pois") or []
        pois = [p for p in pois
                if _kw_at_end(_name_main(str(p.get("name", ""))), NAME_MUST_CONTAIN)
                and "-" not in _name_main(str(p.get("name", "")))]
        if not pois:
            return ""
        lines = [f"{p.get('name', '').strip()}（{p.get('distance', '')}m）" for p in pois[:5]]
        return "【周边工业园/产业园（高德自动检索，2km内）】\n" + "\n".join(lines)
    except Exception:
        return ""



def find_nearby_commercial(coord: str) -> str:
    """2km内大型商业/文化设施，结果传给 Coze 补充地图盲区。"""
    keywords = "购物广场|购物中心|文化广场|万家福|大润发|沃尔玛|永辉|嘉荣|华润万家|家乐福|天虹|步步高|万达|吾悦|宝龙"
    NAME_MUST_CONTAIN = [
        "购物广场", "购物中心", "文化广场", "商业广场", "商业中心",
        "万家福", "大润发", "沃尔玛", "永辉", "嘉荣",
        "华润万家", "家乐福", "天虹", "步步高",
        "万达广场", "吾悦广场", "宝龙广场",
    ]
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
        # 关键词须出现在名称末尾，且名称主体不含连字符（过滤子地点噪音）
        pois = [p for p in pois
                if _kw_at_end(_name_main(str(p.get("name", ""))), NAME_MUST_CONTAIN)
                and "-" not in _name_main(str(p.get("name", "")))]
        if not pois:
            return ""
        lines = [f"{p.get('name', '').strip()}（{p.get('distance', '')}m）" for p in pois[:5]]
        return "【周边大型商业/文化设施（高德自动检索，2km内）】\n" + "\n".join(lines)
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
        # 普通站点跳过租金边界为0/空的候选（边界0会把新站边界锚死在0）
        if not hw:
            try:
                if float(str(row.get("bound_rent", "")).replace(",", "") or 0) <= 0:
                    continue
            except (ValueError, TypeError):
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
            if v and v not in ("nan", "", "0", "0.0"):
                parts.append(f"{label}：{v}")
        lines.append(" | ".join(parts))
    return "\n".join(lines)


def static_map_urls(coord: str):
    """生成 zoom13/14/15 三张高德静态地图URL（与Coze工作流代码节点一致）。"""
    coord = str(coord).replace(" ", "").strip()  # 空格会导致高德返回JSON错误
    base = "https://restapi.amap.com/v3/staticmap"
    marker = f"mid,,A:{coord}"
    return [
        (z, f"{base}?location={coord}&zoom={z}&size=500*400&markers={marker}&key={AMAP_KEY}")
        for z in (13, 14, 15)
    ]


def render_static_maps(coord: str):
    """三列并排展示站点周边静态地图。"""
    cols = st.columns(3)
    captions = {13: "zoom=13 · 城市格局", 14: "zoom=14 · 周边业态", 15: "zoom=15 · 紧邻环境"}
    for col, (z, url) in zip(cols, static_map_urls(coord)):
        with col:
            st.image(url, caption=captions[z], use_container_width=True)


def format_report(result: str) -> str:
    """把报告文本格式化为适合 st.markdown 的形式（分节分隔线+强制换行）。"""
    SECTION_EMOJIS = ("📍", "📚", "💡", "💰", "🤝", "🔥")
    formatted_lines = []
    for line in result.splitlines():
        stripped = line.lstrip()
        if any(stripped.startswith(e) for e in SECTION_EMOJIS) and formatted_lines:
            formatted_lines.append("")
            formatted_lines.append("---")
            formatted_lines.append("")
        formatted_lines.append(line + ("  " if stripped else ""))
    return "\n".join(formatted_lines)


def _extract_output(data) -> str:
    """从工作流返回的 data 字段提取 output 文本。"""
    import json as _json
    try:
        parsed = _json.loads(data) if isinstance(data, str) else data
        if isinstance(parsed, dict):
            for key in ("output", "result", "answer", "content"):
                if key in parsed:
                    return str(parsed[key])
            return str(parsed)
        return str(parsed)
    except Exception:
        return str(data)


def call_workflow_stream(station_name, city, district, address, coord, benchmark_info, placeholder):
    """流式调用 Coze 工作流，边接收边渲染到 placeholder。
    成功返回完整文本；流式接口异常时返回 None（由调用方回退到非流式）。"""
    import json as _json
    headers = {"Authorization": f"Bearer {COZE_TOKEN}", "Content-Type": "application/json"}
    try:
        resp = requests.post(
            "https://api.coze.cn/v1/workflow/stream_run",
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
            stream=True,
        )
        if resp.status_code != 200:
            return None

        full  = ""
        event = None
        for raw in resp.iter_lines(decode_unicode=True):
            if raw is None or raw == "":
                continue
            if raw.startswith("event:"):
                event = raw.split(":", 1)[1].strip()
            elif raw.startswith("data:"):
                data_str = raw.split(":", 1)[1].strip()
                if event == "Message":
                    try:
                        d = _json.loads(data_str)
                        content = d.get("content", "")
                        if content:
                            full += content
                            placeholder.markdown(format_report(_extract_output(full) if full.lstrip().startswith("{") else full) + " ▌")
                    except Exception:
                        pass
                elif event == "Error":
                    return None
                elif event == "Done":
                    break
        if not full:
            return None
        # 内容可能是 {"output": "..."} 的JSON，也可能是纯文本
        return _extract_output(full) if full.lstrip().startswith("{") else full
    except Exception:
        return None


def call_workflow(station_name, city, district, address, coord, benchmark_info) -> str:
    """调用 Coze 工作流 API，同步等待返回结果（非流式，作为回退）。"""
    import json as _json
    headers = {"Authorization": f"Bearer {COZE_TOKEN}", "Content-Type": "application/json"}
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

    return _extract_output(resp.get("data", ""))


CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩"
# 单次正则替换（长标签在前，避免"推理依据"被"依据"二次替换）
BOLD_LABEL_RE = re.compile(r"(推理依据|综合依据|相似点|差异点|谈判起点价|最高报价|合同年限|依据)：")


def _beautify_line(line: str) -> str:
    """单行排版增强：子标题加粗、案例名加粗、关键标签加粗、租金数字高亮。"""
    stripped = line.strip()
    if not stripped:
        return ""
    # ①②③ 子标题：圈号+短标题部分加粗
    m = re.match(rf"^([{CIRCLED}])\s*(.*)$", stripped)
    if m:
        rest = m.group(2)
        if "：" in rest:
            head, tail = rest.split("：", 1)
            stripped = f"**{m.group(1)} {head}：** {tail}"
        else:
            stripped = f"**{m.group(1)} {rest}**"
    # 参考案例编号行：站点名称加粗
    m = re.match(r"^(\d+\.\s*)([^：:，,；;]{2,30})(.*)$", stripped)
    if m and ("站" in m.group(2) or "距离" in m.group(3)[:20]):
        stripped = f"{m.group(1)}**{m.group(2)}**{m.group(3)}"
    # 关键标签加粗（单次替换）
    stripped = BOLD_LABEL_RE.sub(r"**\1：** ", stripped)
    # 租金数字高亮（红色加粗）
    stripped = re.sub(
        r"(?<!\*)(\d[\d,\.]*)\s*(元/车位/月|元/月|元)(?!\*)",
        r"<span style='color:#d6336c;font-weight:700'>\1\2</span>",
        stripped,
    )
    return stripped


def render_report_sections(result: str):
    """把报告按六个模块拆分，每个模块渲染为一张带边框的卡片，内容做排版增强。"""
    SECTION_EMOJIS = ("📍", "📚", "💡", "💰", "🤝", "🔥")
    # 圈号子标题若挤在同一行，先强制分行
    result = re.sub(rf"(?<!\n)\s*([{CIRCLED}])", r"\n\1", result)

    sections = []
    current = []
    for line in result.splitlines():
        stripped = line.lstrip()
        if any(stripped.startswith(e) for e in SECTION_EMOJIS) and current:
            sections.append(current)
            current = []
        current.append(line)
    if current:
        sections.append(current)

    # 默认只展开核心章节，其余折叠，减少视觉压力
    EXPANDED_SECTIONS = ("💰", "🤝")
    for sec in sections:
        title = sec[0].strip()
        body_lines = [_beautify_line(l) for l in sec[1:]]
        # 子标题（**①…）前插入空行形成独立段落，
        # 否则会被前面的markdown列表吸收成缩进内容
        parts = []
        for l in body_lines:
            if not l:
                continue
            if re.match(rf"^\*\*[{CIRCLED}]", l):
                parts.append("")
            parts.append(l + "  ")
        body = "\n".join(parts)
        expanded = any(title.startswith(e) for e in EXPANDED_SECTIONS)
        with st.expander(title, expanded=expanded):
            if body.strip():
                st.markdown(body, unsafe_allow_html=True)


def extract_boundary(result: str):
    """从报告中提取建议单车位租金边界，失败返回 None。"""
    for pattern in [
        r"建议单车位租金边界[^：:\d]*[：:][^\d]*(\d+)\s*元",
        r"租金边界[^：:\d]*[：:][^\d]*(\d+)\s*元",
    ]:
        m = re.search(pattern, result)
        if m:
            return m.group(1)
    return None


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
st.markdown("""
<div class="hero-banner">
  <h1>⚡ 换电站选址租金评估</h1>
  <p>输入站点信息 → AI 自动读取地图、匹配对标案例 → 输出完整租金评估报告</p>
</div>
""", unsafe_allow_html=True)

if not COZE_TOKEN:
    st.warning(
        "⚙️ 尚未配置 Coze Token。\n\n"
        "请在 `.streamlit/secrets.toml`（本地）或 Streamlit Cloud 的 App Settings → Secrets 中填写：\n"
        "```\nCOZE_TOKEN       = \"your_token\"\nCOZE_WORKFLOW_ID = \"7642236438868312079\"\n```",
        icon="⚠️",
    )

# ── 输入表单 ──────────────────────────────────
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
    f_coord = st.text_input(
        "坐标（选填，高德定位不准时手动填入）",
        placeholder="例：113.935068,22.677748",
        help="从钉图易点击站点位置获取坐标，格式：经度,纬度（中英文逗号均可）。填入后将覆盖高德自动定位。",
    )
    submitted = st.form_submit_button("🚀 开始评估", use_container_width=True, type="primary")

# ── Session State 初始化 ──────────────────────
if "eval_result" not in st.session_state:
    st.session_state.eval_result = None   # 评估报告文本
    st.session_state.eval_meta   = {}     # 站点名/地址/坐标/城市/行政区
    st.session_state.eval_benches = []    # 对标站点列表

# ── 评估流程 ──────────────────────────────────
if submitted:
    if not all([f_name, f_addr]):
        st.error("请填写站点名称和完整地址")
        st.stop()
    if not COZE_TOKEN:
        st.error("请先在 Secrets 中配置 COZE_TOKEN")
        st.stop()

    with st.status("评估进行中…", expanded=True) as status_box:

        # Step 1：坐标（手动输入优先，否则 Geocode）
        # 兼容中文逗号「，」
        # 兼容中文逗号和空格（"113.93, 22.54" → "113.93,22.54"），空格会导致高德静态地图报错
        _fc = f_coord.strip().replace("，", ",").replace(" ", "") if f_coord else ""
        manual_coord = _fc if _fc and "," in _fc else None

        if manual_coord:
            st.write("📍 使用手动输入坐标，正在解析城市信息…")
            # 用 regeo 从坐标反查城市/行政区
            try:
                rg = requests.get(
                    "https://restapi.amap.com/v3/geocode/regeo",
                    params={"location": manual_coord, "key": AMAP_KEY, "output": "json"},
                    timeout=10,
                ).json()
                addr_comp = (rg.get("regeocode") or {}).get("addressComponent") or {}
                city_raw  = str(addr_comp.get("city") or addr_comp.get("province") or "")
                city      = re.sub(r"[市省]$", "", city_raw)
                district  = str(addr_comp.get("district") or "")
                coord     = manual_coord
            except Exception:
                coord, city, district = geocode(f_addr)
            st.write(f"✅ 坐标（手动）：`{coord}`  |  城市：`{city}`  |  行政区：`{district}`")
        else:
            st.write("📍 正在获取坐标（高德 API）…")
            coord, city, district = geocode(f_addr)
            if not coord:
                st.error("❌ 坐标获取失败，请检查地址是否填写正确（建议包含省市区）")
                st.stop()
            st.write(f"✅ 坐标：`{coord}`  |  城市：`{city}`  |  行政区：`{district}`")

        # 站点周边静态地图（立即展示，评估进行时可先人工查看周边环境）
        st.write("🗺️ 站点周边静态地图：")
        render_static_maps(coord)

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

        # Step 3：调用 Coze 工作流（流式优先，失败回退非流式）
        # 复用上面已查询的POI结果，避免重复请求高德API
        benchmark_info = format_benchmark_info(benches or [])
        for extra in (nearby_tr, nearby_ind, nearby):
            if extra:
                benchmark_info = benchmark_info + "\n\n" + extra

        st.write("🤖 正在调用 Coze 工作流（报告将实时逐字显示）…")
        stream_placeholder = st.empty()
        result = call_workflow_stream(f_name, city, district, f_addr, coord, benchmark_info, stream_placeholder)
        if result is None:
            st.write("  ⚠️ 流式接口不可用，切换为普通模式（通常需要 30–90 秒）…")
            result = call_workflow(f_name, city, district, f_addr, coord, benchmark_info)
        stream_placeholder.empty()
        status_box.update(label="✅ 评估完成！", state="complete")

    # 保存结果到 session_state，防止标签页切换/重渲染时结果丢失
    st.session_state.eval_result  = result
    st.session_state.eval_meta    = {"name": f_name, "addr": f_addr, "coord": coord, "city": city, "district": district}
    st.session_state.eval_benches = benches

# ── 双视图展示（从 session_state 读取，刷新不丢失）────
if st.session_state.eval_result:
    result   = st.session_state.eval_result
    _meta    = st.session_state.eval_meta
    f_name   = _meta.get("name", "")
    f_addr   = _meta.get("addr", "")
    coord    = _meta.get("coord", "")
    city     = _meta.get("city", "")
    district = _meta.get("district", "")
    benches  = st.session_state.eval_benches

    st.divider()
    tab_finance, tab_biz = st.tabs(["📊 财务BP 完整报告", "💼 商务同事视图"])

    # ── 财务BP 视图 ───────────────────────────
    with tab_finance:
        # 关键数字一览
        _boundary = extract_boundary(result)
        _target, _opening = extract_key_numbers(result)
        if any([_boundary, _target, _opening]):
            c1, c2, c3 = st.columns(3)
            c1.metric("💰 租金边界（上限）", f"{_boundary} 元" if _boundary else "—")
            c2.metric("🎯 目标租金", f"{_target} 元" if _target else "—")
            c3.metric("🤝 谈判起点价", f"{_opening} 元" if _opening else "—")

        if coord:
            with st.expander("🗺️ 站点周边静态地图（zoom 13/14/15）", expanded=True):
                render_static_maps(coord)
        st.subheader("📋 租金评估报告")
        render_report_sections(result)
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
        with st.container(border=True):
            st.markdown("#### ✅ 站点确认")
            st.markdown(f"**站点名称：** {f_name}")
            st.markdown(f"**地址：** {f_addr}")
            st.markdown(f"**城市 / 行政区：** {city} · {district}")

        # 2. 周边参考站点（距离 + 单车位租金，不显示边界）
        with st.container(border=True):
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

        # 3. 核心数字
        c1, c2 = st.columns(2)
        c1.metric("🎯 AI 建议成交价", f"{target_rent} 元/车位/月" if target_rent else "—")
        c2.metric("🤝 谈判起点报价", f"{opening_price} 元/车位/月" if opening_price else "—")
        if not target_rent or not opening_price:
            st.caption("部分数字未能自动提取，请查看「财务BP 完整报告」标签页")
