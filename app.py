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
/* 主标题横幅（浅色卡片+图标徽章+流程胶囊） */
.hero-banner {
    background: linear-gradient(180deg, #ffffff 0%, #f4f8fe 100%);
    border: 1px solid #e3eaf6;
    border-radius: 16px;
    padding: 22px 26px;
    margin-bottom: 6px;
    box-shadow: 0 2px 10px rgba(26,43,74,0.06);
    display: flex;
    align-items: center;
    gap: 18px;
}
.hero-icon {
    width: 58px; height: 58px; flex-shrink: 0;
    background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%);
    border-radius: 15px;
    display: flex; align-items: center; justify-content: center;
    font-size: 30px;
    box-shadow: 0 4px 12px rgba(30,60,114,0.35);
}
.hero-banner h1 {
    margin: 0;
    font-size: 1.6rem;
    font-weight: 800;
    color: #1a2b4a;
    letter-spacing: 1px;
}
.hero-steps {
    margin-top: 9px;
    display: flex; align-items: center; gap: 7px; flex-wrap: wrap;
}
.hero-steps span.step {
    background: #eef3fb;
    color: #44536f;
    border-radius: 999px;
    padding: 3px 12px;
    font-size: 0.78rem;
}
.hero-steps span.arrow { color: #b0bdd4; font-size: 0.8rem; }
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
/* 板块间距：带边框容器之间留出明显空隙 */
div[data-testid="stVerticalBlockBorderWrapper"] { margin-bottom: 18px; }
div[data-testid="stVerticalBlockBorderWrapper"] > div { padding: 6px 4px; }
/* iframe组件与下方内容留距 */
iframe { margin-bottom: 4px; }
</style>
""", unsafe_allow_html=True)

# ═══════════════════════════════════════════════
#  登录门禁（账号=手机号，密码由管理员在Secrets中分配）
#  Secrets中无[users]配置时不启用登录（本地调试友好）
# ═══════════════════════════════════════════════
USERS = st.secrets.get("users", {})
if USERS and not st.session_state.get("auth_user"):
    st.markdown("""
<div class="hero-banner" style="justify-content:center">
  <div class="hero-icon">⚡</div>
  <div>
    <h1>换电站选址租金评估</h1>
    <div class="hero-steps"><span class="step">🔒 内部系统 · 请登录后使用</span></div>
  </div>
</div>
""", unsafe_allow_html=True)
    _, _mid, _ = st.columns([1, 2, 1])
    with _mid:
        with st.form("login_form"):
            _phone = st.text_input("📱 手机号", placeholder="请输入手机号")
            _pwd   = st.text_input("🔑 密码", type="password", placeholder="请输入密码")
            _login = st.form_submit_button("登 录", use_container_width=True, type="primary")
        if _login:
            import hmac as _hmac
            _real = USERS.get(_phone.strip())
            if _real and _hmac.compare_digest(str(_real), _pwd):
                st.session_state.auth_user = _phone.strip()
                st.rerun()
            else:
                st.error("手机号或密码错误。如需开通权限，请联系财务BP")
        st.caption("账号权限由财务BP统一管理")
    st.stop()

if USERS:
    # 登录信息显示在右上角小气泡，不占版面
    _, _user_col = st.columns([3.2, 1])
    with _user_col:
        with st.popover(f"👤 {st.session_state.auth_user}", use_container_width=True):
            if st.button("退出登录", use_container_width=True):
                st.session_state.auth_user = None
                st.rerun()

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
    """2km内商场/购物中心，结果传给 Coze 补充地图盲区。
    双查询合并：商场分类码060100 + 商业关键词，均以"POI官方类型含'商场'"过滤，
    不会混入餐馆/店铺（官方类型≠商户自报类型）。
    旧的名称白名单方案会漏掉永旺梦乐城等不含"广场/中心"字样的大型商场。"""
    seen, results = set(), []
    for extra in [
        {"types": "060100"},   # 商场大类（购物中心/普通商场）
        {"keywords": "购物中心|购物广场|商业广场|文化广场|天地|万达广场|吾悦广场|印象城|大悦城|万象城|万象汇|梦乐城|环宇城|天街"},
    ]:
        params = {
            "location": coord, "radius": 2000, "sortrule": "distance",
            "offset": 20, "page": 1, "key": AMAP_KEY, "output": "json",
        }
        params.update(extra)
        try:
            r = requests.get("https://restapi.amap.com/v3/place/around",
                             params=params, timeout=10).json()
        except Exception:
            continue
        for p in (r.get("pois") or []):
            name  = str(p.get("name", "")).strip()
            ptype = str(p.get("type", ""))
            if "商场" not in ptype:   # 高德官方类型过滤，排除餐饮/零售小店
                continue
            if name in seen:
                continue
            seen.add(name)
            subtype = ptype.split("|")[0].split(";")[-1]
            try:
                dist = int(p.get("distance") or 0)
            except (ValueError, TypeError):
                dist = 0
            results.append((dist, f"{name}（{dist}m，{subtype}）"))
    if not results:
        return ""
    results.sort()
    lines = [t for _, t in results[:5]]
    return "【周边商场/购物中心（高德自动检索，2km内）】\n" + "\n".join(lines)


def find_benchmarks(coord: str, city: str, station_name: str, df: pd.DataFrame):
    if df.empty:
        return []
    hw = is_highway(station_name)
    candidates = []
    for _, row in df.iterrows():
        if row["name"] == station_name:
            continue
        # 不限制同城市/同行政区：交界处站点按纯直线距离匹配（如白云-南海交界）
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
            ("audit_date", "内审日期"),
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
    # 租金数字高亮（红色加粗），支持区间如"900-1300元/车位/月"
    stripped = re.sub(
        r"(?<!\*)(\d[\d,\.]*(?:\s*[-–~—]\s*\d[\d,\.]*)?)\s*(元/车位/月|元/月|元)(?!\*)",
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

    # 关键结论已在顶部卡片/图表呈现，报告全部折叠作为备查详情
    # 💡规律归纳同质化、🔥热力值暂不需要；📍站点定位已在地图区、💰租金建议已在价格卡+锚点推理展示
    EXPANDED_SECTIONS = ()
    HIDDEN_SECTIONS = ("💡", "🔥", "📍", "💰")
    for sec in sections:
        title = sec[0].strip()
        if any(title.startswith(e) for e in HIDDEN_SECTIONS):
            continue
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


def get_section_lines(result: str, emoji: str):
    """提取报告中某个模块（如📍）的内容行（不含标题行）。"""
    SECTION_EMOJIS = ("📍", "📚", "💡", "💰", "🤝", "🔥")
    out, started = [], False
    for line in result.splitlines():
        s = line.lstrip()
        if any(s.startswith(e) for e in SECTION_EMOJIS):
            if s.startswith(emoji):
                started = True
                continue
            elif started:
                break
        elif started:
            out.append(line)
    return out


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
  <div class="hero-icon">⚡</div>
  <div>
    <h1>换电站选址租金评估</h1>
    <div class="hero-steps">
      <span class="step">📝 输入站点信息</span><span class="arrow">→</span>
      <span class="step">🤖 AI读图 · 匹配对标案例</span><span class="arrow">→</span>
      <span class="step">📊 输出租金评估报告</span>
    </div>
  </div>
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
    st.session_state.eval_pois    = {"🚉 交通枢纽": nearby_tr, "🏭 工业园/产业园": nearby_ind, "🏬 大型商业设施": nearby}

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
            # 行政区土地租金标准范围（从报告文本提取）
            _range_m = re.search(r"租金标准[^\d]{0,15}(\d+)\s*[-–~至—]\s*(\d+)", result)
            _range_str = f"{_range_m.group(1)} – {_range_m.group(2)}" if _range_m else "—"
            # 价格主卡：目标租金居中最大，其余价格自上而下递减
            _t = _target if _target else "—"
            _o = _opening if _opening else "—"
            _b = _boundary if _boundary else "—"
            st.markdown(
                f"""
<div style="background:linear-gradient(135deg,#1e3c72 0%,#2a5298 100%);
     border-radius:16px;padding:30px 24px 20px;text-align:center;
     color:#ffffff;margin-bottom:10px">
  <div style="font-size:0.95rem;color:rgba(255,255,255,0.85)">🎯 建议目标单车位租金</div>
  <div style="font-size:3.2rem;font-weight:800;line-height:1.2;letter-spacing:1px">¥{_t}</div>
  <div style="font-size:0.85rem;color:rgba(255,255,255,0.7)">元 / 车位 / 月</div>
  <div style="margin-top:16px;font-size:1.05rem;color:rgba(255,255,255,0.95)">
    🤝 谈判起点价&nbsp;<b style="font-size:1.25rem">¥{_o}</b>
  </div>
  <div style="margin-top:14px;padding-top:12px;border-top:1px solid rgba(255,255,255,0.25);
       font-size:0.92rem;color:rgba(255,255,255,0.85)">
    💰 租金边界（上限）<b>¥{_b}</b>
  </div>
  <div style="margin-top:8px;font-size:0.85rem;color:rgba(255,255,255,0.65)">
    🏛️ 行政区租金标准 {_range_str} 元/车位/月
  </div>
</div>
""",
                unsafe_allow_html=True,
            )
            # 边界锚点+推理依据小字摘要（定价的核心依据）
            _anchor = re.search(r"边界锚点[：:]\s*([^\n。；]+)", result)
            if _anchor:
                st.caption(f"⚓ 边界锚点：{_anchor.group(1).strip()}")
            _br = re.search(r"边界推理依据[：:]\s*([^\n]+)", result)
            if _br:
                st.caption(f"💰 边界推理依据：{_br.group(1).strip()}")
            _tr = re.search(r"目标价推理依据[：:]\s*([^\n]+)", result)
            if _tr:
                st.caption(f"🎯 目标价推理依据：{_tr.group(1).strip()}")

        # ── 站点周边：静态地图 + 站点定位描述（上图下文）──
        _pois = st.session_state.get("eval_pois") or {}

        def _poi_items(text):
            return [l.strip() for l in (text or "").split("\n")[1:] if l.strip()]

        if coord:
            with st.container(border=True):
                st.markdown("##### 🗺️ 站点周边与定位")
                # 关键特征高亮条：区域性质描述（商圈类型）· 道路描述+通达结论（仿领导版）
                _bc_val = _rd_val = _bc_rs = _rd_rs = ""
                _last_lbl = None
                for _l in get_section_lines(result, "📍"):
                    _s = _l.strip()
                    _m = re.match(r"^商圈类型[：:]\s*(.+)$", _s)
                    if _m:
                        _bc_val, _last_lbl = _m.group(1).strip(), "bc"
                        continue
                    _m = re.match(r"^道路条件[：:]\s*(.+)$", _s)
                    if _m:
                        _rd_val, _last_lbl = _m.group(1).strip(), "rd"
                        continue
                    _m = re.match(r"^依据[：:]\s*(.+)$", _s)
                    if _m and _last_lbl == "bc":
                        _bc_rs = _m.group(1).strip()
                    elif _m and _last_lbl == "rd":
                        _rd_rs = _m.group(1).strip()
                if _bc_val or _rd_val:
                    _bc_first = re.split(r"[，。；,;]", _bc_rs)[0] if _bc_rs else ""
                    _rd_first = re.split(r"[，。；,;]", _rd_rs)[0] if _rd_rs else ""
                    _left  = f"{_bc_first}（{_bc_val}）" if _bc_first else _bc_val
                    _right = f"{_rd_first}，{_rd_val}" if _rd_first else _rd_val
                    _feat = " · ".join(x for x in (_left, _right) if x)
                    st.markdown(
                        f"<div style='background:#e8f1fd;border:1px solid #c9defb;border-radius:10px;"
                        f"padding:9px 16px;color:#1857b8;font-size:0.95rem;font-weight:600;"
                        f"margin-bottom:12px'>🟢 {_feat}</div>",
                        unsafe_allow_html=True,
                    )
                render_static_maps(coord)
                _loc_html = []
                # AI站点定位：结论值加粗，依据为灰色小字引用样式
                for _raw in get_section_lines(result, "📍"):
                    _s = _raw.strip()
                    if not _s:
                        continue
                    _m = re.match(r"^(商圈类型|道路条件)[：:]\s*(.+)$", _s)
                    if _m:
                        _loc_html.append(
                            f"<div style='margin-top:14px;color:#44536f'>{_m.group(1)}："
                            f"<b style='font-size:1.08rem;color:#1a2b4a'>{_m.group(2)}</b></div>"
                        )
                        continue
                    _m = re.match(r"^依据[：:]\s*(.+)$", _s)
                    if _m:
                        _loc_html.append(
                            f"<div style='margin-top:5px;padding-left:12px;border-left:3px solid #dbe4f3;"
                            f"color:#6b7a94;font-size:0.88rem;line-height:1.8'>{_m.group(1)}</div>"
                        )
                        continue
                    _m = re.match(r"^地段价值[：:]\s*(.+)$", _s)
                    if _m:
                        _loc_html.append(
                            f"<div style='margin-top:14px;color:#44536f'>地段价值："
                            f"<b style='color:#1a2b4a'>{_m.group(1)}</b></div>"
                        )
                        continue
                    _loc_html.append(f"<div style='margin-top:6px;color:#31333F;line-height:1.9'>{_s}</div>")
                if _loc_html:
                    st.markdown("".join(_loc_html), unsafe_allow_html=True)

        # ── 周边设施统计（紧凑横向条：3类服务器端 + 住宅小区浏览器端）──
        if any(_pois.values()) or coord:
            _chips_srv = ""
            _details_srv = ""
            for _lbl, _text in _pois.items():
                _items = _poi_items(_text)
                _chips_srv += (
                    f"<div style='flex:1;background:linear-gradient(180deg,#f8faff,#eef3fb);"
                    f"border:1px solid #dbe4f3;border-radius:10px;padding:8px 6px;text-align:center'>"
                    f"<div style='color:#5b6b8c;font-size:12.5px'>{_lbl}</div>"
                    f"<div style='font-size:1.5rem;font-weight:700;color:#1a2b4a'>{len(_items)} 个</div></div>"
                )
                _details_srv += f"<b>{_lbl}</b>：{'、'.join(_items) if _items else '2km内未检索到'}<br>"
            _strip_html = f"""
<div style="font-family:-apple-system,'PingFang SC','Source Sans Pro',sans-serif">
  <div style="display:flex;gap:10px">
    {_chips_srv}
    <div style="flex:1;background:linear-gradient(180deg,#f8faff,#eef3fb);border:1px solid #dbe4f3;
         border-radius:10px;padding:8px 6px;text-align:center">
      <div style="color:#5b6b8c;font-size:12.5px">🏘️ 住宅小区</div>
      <div id="cnt" style="font-size:1.5rem;font-weight:700;color:#1a2b4a">…</div>
    </div>
  </div>
  <div style="margin-top:10px;font-size:12.5px;color:#808495;line-height:1.9;
       max-height:130px;overflow-y:auto;background:#fafbfe;border:1px solid #eef2f9;
       border-radius:8px;padding:8px 12px">
    {_details_srv}<span id="resdetail"><b>🏘️ 住宅小区</b>：检索中…</span>
  </div>
</div>
<script>
async function load() {{
  const KEY = "{AMAP_KEY}";
  const coord = "{coord}";
  let all = [];
  for (let page = 1; page <= 3; page++) {{
    const r = await fetch("https://restapi.amap.com/v3/place/around?location=" + coord +
      "&types=120302&radius=2000&offset=25&page=" + page +
      "&sortrule=distance&output=json&key=" + KEY);
    const j = await r.json();
    if (!j.pois || !j.pois.length) break;
    all = all.concat(j.pois);
    if (j.pois.length < 25) break;
  }}
  const seen = new Set();
  const items = all.filter(p => {{
    if (seen.has(p.name)) return false;
    seen.add(p.name); return true;
  }});
  document.getElementById("cnt").innerHTML = items.length + " 个";
  document.getElementById("resdetail").innerHTML = "<b>🏘️ 住宅小区</b>：" +
    (items.length ? items.slice(0, 30).map(p => p.name + "（" + p.distance + "m）").join("、") +
      (items.length > 30 ? " …等共" + items.length + "个" : "") : "2km内未检索到");
}}
load().catch(e => {{
  document.getElementById("cnt").innerHTML = "—";
  document.getElementById("resdetail").innerHTML = "<b>🏘️ 住宅小区</b>：检索失败";
}});
</script>
"""
            import streamlit.components.v1 as components
            components.html(_strip_html, height=245, scrolling=True)
            st.caption("📡 周边设施统计：2km范围，明细列表可上下滚动查看完整名单")

        # 对标案例对比（表格+柱状图，数据来自benchmarks匹配，非LLM文本）
        if benches:
            with st.container(border=True):
                st.markdown("##### 📊 对标案例对比")

                def _num(v):
                    try:
                        return round(float(str(v).replace(",", "")))
                    except (ValueError, TypeError):
                        return None

                def _audit_display(v):
                    """内审日期展示：2025年6月及以前为早期建站，成交租金不具参考性"""
                    s = str(v or "").strip()[:10]
                    if not s or s in ("nan", "None"):
                        return "—"
                    return f"{s} ⚠️早期" if s <= "2025-06-30" else s

                rows_ = []
                for d_km, brow in benches:
                    rows_.append({
                        "站点": brow["name"],
                        "距离(km)": round(d_km, 2),
                        "内审日期": _audit_display(brow.get("audit_date")),
                        "商圈类型": str(brow.get("bc_type", "") or "—"),
                        "道路条件": str(brow.get("road_cond", "") or "—"),
                        "成交租金(元)": _num(brow.get("unit_rent")),
                        "租金边界(元)": _num(brow.get("bound_rent")),
                    })
                # 末行加入本站建议（商圈/道路取AI评估结果），方便与对标直接比较
                if _target or _boundary:
                    _bc_m   = re.search(r"商圈类型[：:]\s*([^\n，,。；;（(]+)", result)
                    _road_m = re.search(r"道路条件[：:]\s*([^\n，,。；;（(]+)", result)
                    rows_.append({
                        "站点": "★ 本站建议",
                        "距离(km)": None,
                        "内审日期": "—",
                        "商圈类型": _bc_m.group(1).strip() if _bc_m else "—",
                        "道路条件": _road_m.group(1).strip() if _road_m else "—",
                        "成交租金(元)": int(_target) if _target else None,
                        "租金边界(元)": int(_boundary) if _boundary else None,
                    })
                _df_show = pd.DataFrame(rows_)
                _df_show["距离(km)"] = _df_show["距离(km)"].apply(lambda v: f"{v:.2f}" if isinstance(v, (int, float)) and v is not None else "—")
                st.dataframe(_df_show, hide_index=True, use_container_width=True)
                st.caption("⚠️早期 = 2025年上半年及以前过会，早期建站未严格管控租金，成交租金不具参考性，仅边界可参考")

        st.subheader("📋 评估报告详情")
        st.caption("站点定位已在上方地图区展示，以下为参考案例与租金建议的完整推理，点击各节展开查看")
        render_report_sections(result)
        # 组装完整纯文本：站点信息 + 关键价格 + 对标案例 + AI报告
        _full_lines = [
            f"站点：{f_name}",
            f"地址：{f_addr}",
            f"坐标：{coord}",
            f"城市：{city}  行政区：{district}",
        ]
        # 按模块拆分报告：💰租金建议提前，其余作为AI评估报告，避免重复
        _SECTION_E = ("📍", "📚", "💡", "💰", "🤝", "🔥")
        _secs, _cur = [], []
        for _line in result.splitlines():
            _s = _line.lstrip()
            if any(_s.startswith(_e) for _e in _SECTION_E) and _cur:
                _secs.append(_cur)
                _cur = []
            _cur.append(_line)
        if _cur:
            _secs.append(_cur)
        _money_sec = next((sec for sec in _secs if sec[0].lstrip().startswith("💰")), None)
        _rest_txt  = "\n".join("\n".join(sec) for sec in _secs if not sec[0].lstrip().startswith("💰"))

        if _money_sec:
            _full_lines += ["", "【租金建议】"] + [l for l in _money_sec[1:] if l.strip()]
        elif any([_boundary, _target, _opening]):
            _full_lines += ["", "【租金建议】"]
            _rm = re.search(r"租金标准[^\d]{0,15}(\d+)\s*[-–~至—]\s*(\d+)", result)
            if _rm:
                _full_lines.append(f"行政区租金标准：{_rm.group(1)}-{_rm.group(2)}元/车位/月")
            if _boundary:
                _full_lines.append(f"建议租金边界：{_boundary}元/车位/月")
            if _target:
                _full_lines.append(f"目标租金：{_target}元/车位/月")
            if _opening:
                _full_lines.append(f"谈判起点价：{_opening}元/车位/月")
        if _rest_txt.strip():
            _full_lines += ["", "【AI评估报告】", _rest_txt]
        if benches:
            _full_lines += ["", "【对标案例】"]
            for _i, (_d, _b) in enumerate(benches, 1):
                _ad = str(_b.get("audit_date", "") or "").strip()[:10]
                _early = "（⚠️早期，成交租金不参考）" if _ad and _ad <= "2025-06-30" else ""
                _full_lines.append(
                    f"{_i}. {_b['name']}｜距离{_d:.2f}km｜内审{_ad or '—'}{_early}｜"
                    f"{_b.get('bc_type', '') or '—'}｜{_b.get('road_cond', '') or '—'}｜"
                    f"成交{_b.get('unit_rent', '') or '—'}元｜边界{_b.get('bound_rent', '') or '—'}元"
                )
        full_text = "\n".join(_full_lines)

        with st.expander("📋 一键复制纯文本"):
            st.code(full_text, language=None)
        st.download_button(
            label="💾 下载报告（.txt）",
            data=full_text,
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
