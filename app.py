# app.py — 换电站选址租金评估 网页版
# 部署到 Streamlit Community Cloud（免费）

import re
import streamlit as st
import requests
import pandas as pd
import numpy as np
from math import radians, sin, cos, sqrt, atan2
from pathlib import Path

# ═══════════════════════════════════════════════
#  页面基础配置
# ═══════════════════════════════════════════════
st.set_page_config(
    page_title="换电站租金评估",
    page_icon="⚡",
    layout="wide",
)

# ── 全局样式 ──────────────────────────────────
# 设计方向（2026-07-15）：克制留白风格——去渐变、去重阴影，改用细边框(1px hairline)+
# 大留白+单一强调色，参考的是"少即是多"的现代SaaS工具（Linear/Notion一类），而不是
# 常见的"企业蓝渐变卡片"套路。全站统一走 --app-* 这套变量，不再零散写十六进制色值。
st.markdown("""
<style>
:root {
    --app-page-bg: #f5f6f8;
    --app-bg: #ffffff;
    --app-surface: #fafbfc;
    --app-border: #e6e8ec;
    --app-border-strong: #d5d9e0;
    --app-text: #16181d;
    --app-text-secondary: #6b7280;
    --app-text-muted: #9aa0ab;
    --app-accent: #1f3a5f;
    --app-accent-soft: #eef2f7;
    --app-danger: #c1372f;
    --app-danger-soft: #fdecea;
    --app-radius: 10px;
}
/* 页面本身用极浅灰底，白色卡片才能在上面显出"浮起来"的层次——
   之前卡片和页面背景同为纯白，只靠1px边框分隔，视觉上显得单薄。 */
[data-testid="stAppViewContainer"] { background: var(--app-page-bg); }
section[data-testid="stSidebar"] { background: var(--app-bg); }
/* 宽屏但限制最大宽度，避免超宽显示器上内容被拉得过散 */
.block-container { max-width: 1320px; padding-top: 2rem; }
html, body, [class*="css"] {
    font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", "Helvetica Neue", Arial, sans-serif;
}
/* 主标题横幅：白底细边框，不用渐变/阴影 */
.hero-banner {
    background: var(--app-bg);
    border: 1px solid var(--app-border);
    border-radius: 14px;
    padding: 20px 26px;
    margin-bottom: 6px;
    display: flex;
    align-items: center;
    gap: 16px;
}
.hero-icon {
    width: 46px; height: 46px; flex-shrink: 0;
    background: var(--app-accent-soft);
    border-radius: 12px;
    display: flex; align-items: center; justify-content: center;
    font-size: 22px;
}
.hero-banner h1 {
    margin: 0;
    font-size: 1.4rem;
    font-weight: 700;
    color: var(--app-text);
    letter-spacing: 0.3px;
}
.hero-steps {
    margin-top: 8px;
    display: flex; align-items: center; gap: 6px; flex-wrap: wrap;
}
.hero-steps span.step {
    border: 1px solid var(--app-border);
    color: var(--app-text-secondary);
    border-radius: 999px;
    padding: 2px 11px;
    font-size: 0.76rem;
}
.hero-steps span.arrow { color: var(--app-text-muted); font-size: 0.8rem; }
/* 指标卡片：去渐变，细边框 */
div[data-testid="stMetric"] {
    background: var(--app-surface);
    border: 1px solid var(--app-border);
    border-radius: var(--app-radius);
    padding: 12px 16px;
}
div[data-testid="stMetric"] label { color: var(--app-text-secondary); }
/* 报告分节卡片内的标题行 */
.section-title {
    font-size: 1.02rem;
    font-weight: 600;
    margin-bottom: 2px;
    color: var(--app-text);
}
/* 表格圆角 */
div[data-testid="stTable"] table { border-radius: var(--app-radius); overflow: hidden; }
/* 按钮：细边框风格，去圆润阴影 */
.stButton > button, .stDownloadButton > button, .stFormSubmitButton > button {
    border-radius: var(--app-radius);
    border: 1px solid var(--app-border-strong);
    box-shadow: none;
}
/* 带边框容器（st.container(border=True)）：白底+细边框，在浅灰页面背景上"浮起来" */
div[data-testid="stVerticalBlockBorderWrapper"] {
    margin-bottom: 16px;
    background: var(--app-bg) !important;
    border-color: var(--app-border) !important;
    border-radius: 12px !important;
    box-shadow: none !important;
}
div[data-testid="stVerticalBlockBorderWrapper"] > div { padding: 4px 2px; }
/* dataframe/表格同样给白底，避免和灰页面背景融在一起 */
div[data-testid="stDataFrame"] { background: var(--app-bg); border-radius: var(--app-radius); overflow: hidden; }
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
            _login = st.form_submit_button("登 录", width="stretch", type="primary")
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
        with st.popover(f"👤 {st.session_state.auth_user}", width="stretch"):
            if st.button("退出登录", width="stretch"):
                st.session_state.auth_user = None
                st.rerun()

# ═══════════════════════════════════════════════
#  读取 Secrets
# ═══════════════════════════════════════════════
AMAP_KEY         = st.secrets.get("AMAP_KEY",         "ce2119b87985d25e49cff4c05c6938ff")
COZE_TOKEN       = st.secrets.get("COZE_TOKEN",       "")
COZE_WORKFLOW_ID = st.secrets.get("COZE_WORKFLOW_ID", "7642236438868312079")
# 评估历史台账（2026-07-26新增）：GitHub PAT需要"Contents: Read and write"权限，
# 建议用fine-grained token只授权ev-rent-web这一个仓库。未配置时台账功能静默跳过，不影响主流程。
GITHUB_TOKEN     = st.secrets.get("GITHUB_TOKEN",     "")
GITHUB_REPO      = st.secrets.get("GITHUB_REPO",      "stellayunchen-art/ev-rent-web")

HIGHWAY_KEYWORDS = ["高速", "服务区", "收费站"]
BENCH_CSV = Path(__file__).parent / "benchmarks.csv"
RENT_STANDARD_CSV = Path(__file__).parent / "rent_standard.csv"
RENT_MODEL_PATH   = Path(__file__).parent / "rent_model.joblib"
FEATURES_CSV      = Path(__file__).parent / "station_features.csv"

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


@st.cache_data(show_spinner=False, ttl=300)
def load_rent_standard() -> dict:
    """加载行政区租金标准表，返回 {(city, district): (low, high)}。
    city/district 需与geocode返回的格式一致（city不带"市"字）。"""
    if not RENT_STANDARD_CSV.exists():
        return {}
    df = pd.read_csv(RENT_STANDARD_CSV, encoding="utf-8-sig")
    return {
        (str(r["city"]).strip(), str(r["district"]).strip()): (int(r["low"]), int(r["high"]))
        for _, r in df.iterrows()
    }


def lookup_rent_standard(city: str, district: str):
    """查行政区标准范围 (low, high)；查不到返回 None。"""
    table = load_rent_standard()
    city_clean = str(city).replace("市", "").strip()
    return table.get((city_clean, str(district).strip()))


@st.cache_resource(show_spinner=False)
def load_rent_model():
    """加载训练好的Ridge回归模型（joblib格式，含pipeline+use_log标记）。加载失败返回None。"""
    if not RENT_MODEL_PATH.exists():
        return None
    try:
        import joblib
        return joblib.load(RENT_MODEL_PATH)
    except Exception:
        return None


def model_stats_note() -> str:
    """模型样本数+MAPE的展示文案，从joblib bundle动态读取（而不是写死数字），
    这样每次重训模型后不用满屋子改字符串，数字自动跟着rent_model.joblib走。
    ⚠️ 2026-07-19起MAPE改为5折交叉验证均值（比单次切分更稳，同一份数据单次切分
    实测能在10%~16%间波动），mape_holdout_std存在时一并显示±标准差，让人一眼
    看出这个数字有多可信，而不是误以为是精确值。"""
    bundle = load_rent_model()
    if not bundle:
        return "统计模型不可用"
    n = bundle.get("n_samples", "—")
    mape = bundle.get("mape_holdout")
    mape_std = bundle.get("mape_holdout_std")
    if isinstance(mape, (int, float)):
        mape_str = f"{mape:.2f}%"
        if isinstance(mape_std, (int, float)):
            mape_str += f"±{mape_std:.2f}%"
    else:
        mape_str = "—"
    return f"{n}个历史场地训练 · MAPE {mape_str}"


@st.cache_data(show_spinner=False, ttl=3600)
def district_sample_count(city: str, district: str) -> int:
    """该城市-行政区在训练集（station_features.csv）中的样本数，用于置信度评估。"""
    if not FEATURES_CSV.exists():
        return 0
    df = pd.read_csv(FEATURES_CSV, encoding="utf-8-sig")
    city_clean = str(city).replace("市", "").strip()
    return int(((df["city"].astype(str).str.strip() == city_clean) &
                (df["district"].astype(str).str.strip() == str(district).strip())).sum())


def assess_confidence(city, district, transit_count, industrial_count, mall_count, benches):
    """确定性置信度评估（规则算分，非AI判断）。
    返回 (等级'高'/'中'/'低', 原因列表, 人工审核建议列表)。"""
    flags_low, flags_mid = [], []

    # 1. 训练样本覆盖：该行政区历史样本太少 → 模型对此区外推，可信度降
    n_samples = district_sample_count(city, district)
    if n_samples < 3:
        flags_low.append(f"该行政区训练样本仅 {n_samples} 个（<3），模型属外推预测")
    elif n_samples < 10:
        flags_mid.append(f"该行政区训练样本 {n_samples} 个（<10），覆盖偏薄")

    # 2. POI稀疏度：周边设施极少 → 特征信号弱（借鉴领导工具的判断）
    poi_total = transit_count + industrial_count + mall_count
    if poi_total < 2:
        flags_low.append(f"POI 极度稀疏（交通+工业园+商场共 {poi_total} 个 < 2）")
    elif poi_total < 5:
        flags_mid.append(f"POI 较稀疏（交通+工业园+商场共 {poi_total} 个 < 5）")

    # 3. 对标距离：最近对标站点太远 → 无近距离市场参照
    if benches:
        nearest = min(d for d, _ in benches)
        if nearest > 8:
            flags_low.append(f"最近对标站点 {nearest:.1f}km（>8km），无近距离市场参照")
        elif nearest > 5:
            flags_mid.append(f"最近对标站点 {nearest:.1f}km（>5km），参照距离偏远")
    else:
        flags_low.append("未找到任何对标站点")

    if flags_low:
        level = "低"
    elif len(flags_mid) >= 2:
        level = "中"
    elif flags_mid:
        level = "中"
    else:
        level = "高"

    advice = []
    if level == "低":
        advice = [
            "联系周边 2-3 个已签约场地的商务同事，了解实际成交参考",
            "重点确认场地类型（工业园/城中村/专用站）是否属于特殊品类",
            "参考同城市同类站点均值作为保底谈判目标",
        ]
    elif level == "中":
        advice = ["建议结合报告下方对标案例表格人工复核一遍数字再对外报价"]
    return level, flags_low + flags_mid, advice


def _current_audit_num() -> float:
    """今天对应的连续时间数值（年+月/12），必须与 train_rent_model.py 的
    current_audit_num() 算法完全一致，否则预测值和训练时的时间基准对不上。"""
    from datetime import date
    today = date.today()
    return today.year + (today.month - 1) / 12


def _model_feature_row(city, district, transit_count, industrial_count, mall_count, hub_counts):
    """组装喂给模型的一行特征DataFrame。hub_counts为{hub_*:数量}，缺失的hub补0。
    predict_target_rent和explain_prediction共用，保证两处特征完全一致。"""
    import pandas as _pd
    city_clean = str(city).replace("市", "").strip()
    hc = hub_counts or {}
    return _pd.DataFrame([{
        "city_district": f"{city_clean}-{district}",
        "transit_count": transit_count,
        "industrial_count": industrial_count,
        "mall_count": mall_count,
        "audit_num": _current_audit_num(),
        "hub_highway": int(hc.get("hub_highway", 0)),
        "hub_railway": int(hc.get("hub_railway", 0)),
        "hub_coach": int(hc.get("hub_coach", 0)),
        "hub_airport": int(hc.get("hub_airport", 0)),
    }])


def _derive_boundary(std_low, std_high, bench_rows):
    """边界上限：以周边对标案例的边界为基准，再用行政区标准上下限硬性封顶。
    ⚠️ 不再无脑取行政区标准上限——那会在对标案例边界普遍偏低时（如工业区周边案例
    边界700-850，但行政区标准上限1000）把边界顶到不合理的高位（用户实测黄埔云埔工业区案例）。
    取法：对标案例边界的最大值（多个近距离案例支持的最高水平），封顶到行政区标准上限、
    不低于标准下限。早期/特批案例的边界仍可参考（成交价不参考、边界可参考，符合既有规则）。
    无任何对标案例边界可用时，退回行政区标准上限（老逻辑兜底）。"""
    bounds = []
    for _d_km, row in (bench_rows or []):
        try:
            b = float(str(row.get("bound_rent", "")).replace(",", "").strip())
            if b > 0:
                bounds.append(b)
        except (ValueError, TypeError):
            continue
    if not bounds:
        return std_high
    derived = max(bounds)
    # 封顶到行政区标准上限、不低于下限，取整到10元
    derived = min(std_high, max(std_low, derived))
    return round(derived / 10) * 10


def predict_target_rent(city: str, district: str, transit_count: int, industrial_count: int, mall_count: int, hub_counts: dict = None, bench_rows=None):
    """用Ridge回归模型预测目标单车位租金，并按行政区标准范围夹取。
    模型基于历史场地训练（城市+行政区 + 2km内交通枢纽/工业园/商场数量 + 内审时间趋势
    + 高速/高铁站/汽车站/机场固定半径数量），刻意不含AI视觉分类特征，可在调用Coze前独立完成预测。
    ⚠️ 预测时代入"当前时点"（audit_num=今天），模型据此从历史时间趋势系数自动
    折算出当前行情价，效果类似领导工具的"×0.85时间折扣"，但系数由数据回归得出、
    不是人工拍定，且对任意行政区自适应生效。
    边界上限由周边对标案例边界推导（_derive_boundary），不再无脑取行政区标准上限。
    返回 (目标租金, 边界上限, 谈判起点价)，任一环节数据缺失则返回 (None, None, None)。"""
    bundle = load_rent_model()
    std = lookup_rent_standard(city, district)
    if bundle is None or std is None:
        return None, None, None

    row = _model_feature_row(city, district, transit_count, industrial_count, mall_count, hub_counts)
    try:
        pred = bundle["pipeline"].predict(row)[0]
        raw_target = float(np.exp(pred)) if bundle["use_log"] else float(pred)
    except Exception:
        return None, None, None

    low, high = std
    # 边界=周边对标案例边界的最高水平，封顶到行政区标准上限（不再无脑=标准上限）
    boundary = _derive_boundary(low, high, bench_rows)
    # 目标价夹取在[标准下限, 边界×95%]——刻意不允许目标=边界，保留谈判空间
    target_cap = max(low, round(boundary * 0.95 / 10) * 10)
    target = max(low, min(target_cap, round(raw_target / 10) * 10))
    opening = max(low, round(target * 0.9 / 10) * 10)  # 起点价=目标价的90%，同样不低于标准下限
    return target, boundary, opening


def predict_price_range(city: str, district: str, transit_count: int, industrial_count: int, mall_count: int, hub_counts: dict = None):
    """预测区间（保守/中性/进取三档，2026-07-26新增）：用train_rent_model.py训练的
    分位数回归模型（10%/50%/90%分位），代替单点数字给出一个价格带。
    ⚠️ 这是对predict_target_rent()的补充展示，不替代它——目标价/边界/起点价那套硬性
    业务规则（边界按对标案例推导+95%谈判空间保护）已经过反复打磨，分位数回归只是
    原始统计意义上的价格分布，不做那些业务规则夹取，仅供参考"这个价大概率的浮动范围"。
    K折校准检验：conservative目标10%分位实际覆盖10.6%、aggressive目标90%分位实际
    覆盖89.6%，分位数交叉率仅0.2%，可信。
    返回 (保守价, 中性价, 进取价)，模型不可用/未训练分位数模型时返回 (None, None, None)。"""
    bundle = load_rent_model()
    if bundle is None or not bundle.get("quantile_pipelines"):
        return None, None, None
    row = _model_feature_row(city, district, transit_count, industrial_count, mall_count, hub_counts)
    try:
        qp = bundle["quantile_pipelines"]
        conservative = float(np.exp(qp["conservative"].predict(row)[0]))
        neutral      = float(np.exp(qp["neutral"].predict(row)[0]))
        aggressive   = float(np.exp(qp["aggressive"].predict(row)[0]))
    except Exception:
        return None, None, None
    # 防止极小概率的分位数交叉导致展示乱序（训练时K折已验证交叉率仅0.2%，这里兜底排序）
    conservative, neutral, aggressive = sorted([conservative, neutral, aggressive])
    return (round(conservative / 10) * 10, round(neutral / 10) * 10, round(aggressive / 10) * 10)


def explain_prediction(city: str, district: str, transit_count: int, industrial_count: int, mall_count: int, hub_counts: dict = None):
    """把Ridge回归模型的预测拆解成"行政区基准 × 各特征调整系数"的可读分项，
    回答"这个数字是怎么算出来的"，而不是只吐一个黑箱数字。
    数学原理：log(rent) = intercept + Σ(特征值 × 系数)，两边取exp后拆成连乘：
    rent = exp(intercept) × Π exp(特征贡献)，每一项exp(贡献)就是该特征对最终价格的乘数因子，
    可以直接读成"+12%"这种人话。返回None表示模型不可用或预测失败。"""
    bundle = load_rent_model()
    if bundle is None or not bundle.get("use_log"):
        return None  # 线性目标模型的贡献是可加的元，不是乘数，暂不支持拆解（当前部署模型固定用log目标）
    try:
        pipe = bundle["pipeline"]
        pre = pipe.named_steps["pre"]
        ridge = pipe.named_steps["ridge"]
        _hc = hub_counts or {}
        row = _model_feature_row(city, district, transit_count, industrial_count, mall_count, hub_counts)
        X_trans = pre.transform(row)
        if hasattr(X_trans, "toarray"):
            X_trans = X_trans.toarray()
        contributions = X_trans[0] * ridge.coef_
        feature_names = pre.get_feature_names_out()
    except Exception:
        return None

    LABELS = [
        ("cat__city_district_", lambda: f"📍 {district}行政区基准"),
        ("num__transit_count", lambda: f"🚇 轨道交通2km（{transit_count}个）"),
        ("num__industrial_count", lambda: f"🏭 工业园（{industrial_count}个）"),
        ("num__mall_count", lambda: f"🏬 商业设施（{mall_count}个）"),
        ("num__audit_num", lambda: "📅 内审时间趋势"),
        ("num__hub_railway", lambda: f"🚄 高铁/火车站5km（{int(_hc.get('hub_railway', 0))}个）"),
        ("num__hub_highway", lambda: f"🛣️ 高速出入口3km（{int(_hc.get('hub_highway', 0))}个）"),
        ("num__hub_coach", lambda: f"🚌 长途汽车站3km（{int(_hc.get('hub_coach', 0))}个）"),
        ("num__hub_airport", lambda: f"✈️ 机场15km（{int(_hc.get('hub_airport', 0))}个）"),
    ]
    baseline = float(np.exp(ridge.intercept_))
    parts = []
    for name, contrib in zip(feature_names, contributions):
        if abs(contrib) < 1e-6:
            continue
        label = next((make() for prefix, make in LABELS if name.startswith(prefix)), name)
        parts.append({"label": label, "factor": float(np.exp(contrib)), "pct": float((np.exp(contrib) - 1) * 100)})
    return {"baseline": baseline, "parts": parts}


@st.cache_data(show_spinner=False, ttl=3600)
def load_district_rent_history(city: str, district: str) -> pd.DataFrame:
    """该行政区历史成交价随时间的数据点（内审日期+单车位租金），用于趋势图。
    数据来自station_features.csv（和训练模型同一份数据），不是另起炉灶查数据库。"""
    if not FEATURES_CSV.exists():
        return pd.DataFrame()
    df = pd.read_csv(FEATURES_CSV, encoding="utf-8-sig")
    city_clean = str(city).replace("市", "").strip()
    df = df[
        (df["city"].astype(str).str.replace("市", "", regex=False).str.strip() == city_clean)
        & (df["district"].astype(str).str.strip() == str(district).strip())
    ]
    df = df.dropna(subset=["audit_date", "unit_rent"]).copy()
    df["audit_date"] = pd.to_datetime(df["audit_date"], errors="coerce")
    df = df.dropna(subset=["audit_date"])
    return df[["audit_date", "unit_rent", "name"]].sort_values("audit_date")


# ── 回测校准（2026-07-26新增）：向老板证明模型可信度的证据，不是黑箱吐数字 ──
_BT_CATEGORICAL = ["city_district"]
_BT_NUMERIC = ["transit_count", "industrial_count", "mall_count", "audit_num",
               "hub_highway", "hub_railway", "hub_coach", "hub_airport"]


def _bt_audit_to_num(date_str):
    """必须和train_rent_model.py的audit_to_num()算法完全一致，否则回测口径就和
    训练时不一样了。"""
    m = re.match(r"(\d{4})-(\d{2})", str(date_str or ""))
    if not m:
        return None
    year, month = int(m.group(1)), int(m.group(2))
    return year + (month - 1) / 12


@st.cache_data(show_spinner="正在跑5折交叉验证回测（约需10-20秒）…", ttl=3600)
def run_backtest():
    """对576个历史场地做5折交叉验证的样本外预测（out-of-fold）：每个站点被预测时，
    用的都是不包含它自己的那4折训练出来的模型，避免"用自己训练自己"这种自欺欺人的
    评估方式。返回逐站点的(实际成交价, 模型会预测多少, 误差%)，用于画散点图+误差分布，
    是比单个MAPE数字更直观的"这个模型到底准不准"的证据。"""
    from sklearn.compose import ColumnTransformer
    from sklearn.linear_model import RidgeCV
    from sklearn.model_selection import KFold
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import OneHotEncoder, StandardScaler

    if not FEATURES_CSV.exists():
        return pd.DataFrame()
    df = pd.read_csv(FEATURES_CSV, encoding="utf-8-sig")
    df = df.dropna(subset=["unit_rent"])
    df = df[df["unit_rent"] > 0]
    df["city_district"] = df["city"].astype(str) + "-" + df["district"].astype(str)
    df["audit_num"] = df["audit_date"].apply(_bt_audit_to_num)
    df = df.dropna(subset=["audit_num"]).reset_index(drop=True)

    X = df[_BT_CATEGORICAL + _BT_NUMERIC]
    y_log = np.log(df["unit_rent"].values)
    y_true = df["unit_rent"].values

    kf = KFold(n_splits=5, shuffle=True, random_state=42)
    pred = np.zeros(len(df))
    for tr_idx, te_idx in kf.split(X):
        pre = ColumnTransformer([
            ("cat", OneHotEncoder(handle_unknown="ignore"), _BT_CATEGORICAL),
            ("num", StandardScaler(), _BT_NUMERIC),
        ])
        pipe = Pipeline([("pre", pre), ("ridge", RidgeCV(alphas=np.logspace(-2, 3, 40)))])
        pipe.fit(X.iloc[tr_idx], y_log[tr_idx])
        pred[te_idx] = np.exp(pipe.predict(X.iloc[te_idx]))

    result = df[["name", "city", "district", "audit_date"]].copy()
    result["实际成交价"] = y_true.round(0)
    result["模型预测价"] = pred.round(0)
    result["误差%"] = ((pred - y_true) / y_true * 100).round(1)
    return result


def render_backtest_page():
    """回测校准页面：预测vs实际散点图 + 误差分布，向老板证明模型可信度的直观证据。"""
    bt = run_backtest()
    if bt.empty:
        st.info("暂无历史训练数据，无法回测")
        return

    st.markdown("##### 📐 模型回测校准")
    st.caption(
        "对576个历史场地做5折交叉验证样本外预测——每个站点被预测时，模型完全没见过它，"
        "更接近真实的「新站点评估」场景，不是用自己训练自己的自欺欺人评估。"
    )

    n = len(bt)
    within_10 = (bt["误差%"].abs() <= 10).sum()
    within_20 = (bt["误差%"].abs() <= 20).sum()
    mape_val = bt["误差%"].abs().mean()
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("样本数", f"{n}")
    c2.metric("平均绝对误差", f"{mape_val:.1f}%")
    c3.metric("误差≤10%占比", f"{within_10/n*100:.0f}%")
    c4.metric("误差≤20%占比", f"{within_20/n*100:.0f}%")

    import altair as alt
    max_v = max(bt["实际成交价"].max(), bt["模型预测价"].max()) * 1.05
    scatter = alt.Chart(bt).mark_circle(size=50, opacity=0.5, color="#1f3a5f").encode(
        x=alt.X("实际成交价:Q", title="实际成交价（元/月）", scale=alt.Scale(domain=[0, max_v])),
        y=alt.Y("模型预测价:Q", title="模型预测价（元/月）", scale=alt.Scale(domain=[0, max_v])),
        tooltip=["name:N", "city:N", "district:N", "实际成交价:Q", "模型预测价:Q", "误差%:Q"],
    )
    diagonal = alt.Chart(pd.DataFrame({"x": [0, max_v], "y": [0, max_v]})).mark_line(
        color="#c1372f", strokeDash=[5, 5]
    ).encode(x="x:Q", y="y:Q")
    st.altair_chart((scatter + diagonal).properties(height=380), use_container_width=True)
    st.caption("红色虚线=完美预测（预测值=实际值）；点越贴近虚线，模型越准。散点整体分布反映的是真实预测能力，不是挑好看的案例展示")

    with st.expander("查看误差最大的10个站点（供排查数据质量或模型盲区）"):
        worst = bt.reindex(bt["误差%"].abs().sort_values(ascending=False).index).head(10)
        st.dataframe(worst, hide_index=True, width="stretch")


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


def find_nearby_transit(coord: str):
    """2km内地铁/城轨/高铁/城际/轻轨/火车站。返回 (展示用文本, 完整数量)——
    完整数量与build_station_features.py的count_transit同口径，用于回归模型特征，
    不受展示截断（只显示前3个）影响。
    ⚠️ 用高德官方typecode过滤（150200火车站+150500地铁站），不用名称关键词判断：
    实测名称判断法有两个反向bug——①真站点名称格式为"民治(地铁站)"，"地铁站"三字
    在括号里，会被_name_main()去掉后导致名称检测失效、真站点被漏掉；②"雅好花园酒店
    深圳龙华地铁站店"这类商户名称本身就含"地铁站"三字，会被误判为真地铁站纳入统计。
    typecode是高德官方分类，不受商户自报名称影响，一次性解决两个问题。"""
    try:
        r = requests.get(
            "https://restapi.amap.com/v3/place/around",
            params={"location": coord, "types": "150200|150500", "radius": 2000,
                    "sortrule": "distance", "offset": 20, "page": 1,
                    "key": AMAP_KEY, "output": "json"},
            timeout=10,
        ).json()
        pois = [p for p in (r.get("pois") or []) if str(p.get("typecode", "")) in ("150200", "150500")]
        if not pois:
            return "", 0
        lines = [f"{p.get('name', '').strip()}（{p.get('distance', '')}m）" for p in pois[:3]]
        text = "【周边交通枢纽（高德自动检索，2km内）】\n" + "\n".join(lines)
        return text, len(pois)
    except Exception:
        return "", 0


def find_nearby_industrial(coord: str):
    """2km内工业园/产业园。返回 (展示用文本, 完整数量)，同上原则。"""
    keywords = "产业园|工业园|工业区|科技园|工业城|产业城|创新中心|研发中心"
    NAME_MUST_CONTAIN = [
        "产业园", "工业园", "工业区", "科技园", "工业城", "产业城",
        "创新中心", "研发中心", "产业基地", "工业基地",
    ]
    try:
        r = requests.get(
            "https://restapi.amap.com/v3/place/around",
            params={"location": coord, "keywords": keywords, "radius": 2000,
                    "sortrule": "distance", "offset": 20, "page": 1,
                    "key": AMAP_KEY, "output": "json"},
            timeout=10,
        ).json()
        pois = r.get("pois") or []
        pois = [p for p in pois
                if _kw_at_end(_name_main(str(p.get("name", ""))), NAME_MUST_CONTAIN)
                and "-" not in _name_main(str(p.get("name", "")))]
        if not pois:
            return "", 0
        lines = [f"{p.get('name', '').strip()}（{p.get('distance', '')}m）" for p in pois[:5]]
        text = "【周边工业园/产业园（高德自动检索，2km内）】\n" + "\n".join(lines)
        return text, len(pois)
    except Exception:
        return "", 0



def find_nearby_commercial(coord: str):
    """2km内商场/购物中心。返回 (展示用文本, 完整数量)，同上原则。
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
        return "", 0
    results.sort()
    lines = [t for _, t in results[:5]]
    text = "【周边商场/购物中心（高德自动检索，2km内）】\n" + "\n".join(lines)
    return text, len(results)


def find_charging_stations(coord: str):
    """2km内充电站数量+最近距离（高德typecode=011100，展示用，不进模型特征）。"""
    try:
        r = requests.get(
            "https://restapi.amap.com/v3/place/around",
            params={"location": coord, "types": "011100", "radius": 2000,
                    "sortrule": "distance", "offset": 1, "page": 1,
                    "key": AMAP_KEY, "output": "json"},
            timeout=10,
        ).json()
        count = int(r.get("count") or 0)
        pois = r.get("pois") or []
        nearest = int(pois[0].get("distance") or 0) if pois else None
        return count, nearest
    except Exception:
        return 0, None


# ⚠️ 交通枢纽固定半径规格——必须与 build_station_features.py 的 HUB_SPECS 完全一致
# （key/关键词/半径一字不差），否则训练特征和实时预测特征口径不一致，模型收到错位数据。
# (特征名key, 展示标签, 关键词, 半径米)
HUB_SPECS = [
    ("hub_highway", "🛣️ 高速出入口", "高速公路出入口", 3000),
    ("hub_railway", "🚄 高铁/火车站", "火车站|高铁站", 5000),
    ("hub_coach",   "🚌 长途汽车站", "长途汽车站|客运站", 3000),
    ("hub_airport", "✈️ 机场",       "机场",           15000),
]


def find_transit_hubs_extended(coord: str):
    """交通枢纽固定半径搜索。返回 list[(key, 标签, 半径, 数量, 最近距离)]。
    数量既用于页面展示，也作为模型特征（2026-07-15起高铁火车站等纳入回归模型）。"""
    results = []
    for key, label, kw, radius in HUB_SPECS:
        try:
            r = requests.get(
                "https://restapi.amap.com/v3/place/around",
                params={"location": coord, "keywords": kw, "radius": radius,
                        "sortrule": "distance", "offset": 1, "page": 1,
                        "key": AMAP_KEY, "output": "json"},
                timeout=10,
            ).json()
            count = int(r.get("count") or 0)
            pois = r.get("pois") or []
            nearest = int(pois[0].get("distance") or 0) if pois else None
        except Exception:
            count, nearest = 0, None
        results.append((key, label, radius, count, nearest))
    return results


def hub_counts_from_results(transit_hubs) -> dict:
    """从 find_transit_hubs_extended 的返回里抽出 {特征名: 数量}，喂给模型。"""
    return {key: count for key, _label, _radius, count, _near in (transit_hubs or [])}


def find_nearby_roads(coord: str):
    """regeo逆地理编码：返回 (街道名, [(道路名, 方位, 距离m), ...最近3条])。
    ⚠️ 高德不提供道路等级（此前已验证），故只展示名称/方位/距离，不按名称猜等级
    （"XX大道"未必是主干道——领导工具按名称标注等级的做法有误判风险，不学）。"""
    try:
        r = requests.get(
            "https://restapi.amap.com/v3/geocode/regeo",
            params={"location": coord, "key": AMAP_KEY, "extensions": "all", "output": "json"},
            timeout=10,
        ).json()
        rc = r.get("regeocode") or {}
        township = str((rc.get("addressComponent") or {}).get("township") or "")
        roads = []
        for rd in (rc.get("roads") or []):
            try:
                roads.append((str(rd.get("name", "")), str(rd.get("direction", "")), float(rd.get("distance", 0))))
            except (ValueError, TypeError):
                continue
        roads.sort(key=lambda x: x[2])
        return township, roads[:5]
    except Exception:
        return "", []


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


INDUSTRIAL_KEYWORDS = ["工业区", "工业园", "产业园", "城中村", "物流", "厂房", "五金", "制造", "仓储"]


def find_industrial_supplement(coord: str, city: str, station_name: str,
                                existing_names: set, df: pd.DataFrame, need: int = 2):
    """当最近的对标站点普遍偏远（无法就近参考）时，
    在全市范围按 area_type 关键词补充同类型（工业区/城中村主导）站点，
    不受距离限制——让 AI 有真实同类案例可归纳，而非套用固定公式。"""
    if df.empty:
        return []
    candidates = []
    for _, row in df.iterrows():
        name = row["name"]
        if name == station_name or name in existing_names:
            continue
        if row.get("city") != city:
            continue
        if is_highway(name):
            continue
        if "," not in str(row.get("coord", "")):
            continue
        try:
            if float(str(row.get("bound_rent", "")).replace(",", "") or 0) <= 0:
                continue
        except (ValueError, TypeError):
            continue
        area_text = str(row.get("area_type", "")) + str(row.get("bc_type", ""))
        if not any(kw in area_text for kw in INDUSTRIAL_KEYWORDS):
            continue
        d = haversine(coord, row["coord"])
        if d < 0.1:
            continue
        candidates.append((d, row))
    candidates.sort(key=lambda x: x[0])
    return candidates[:need]


def _bound(row):
    try:
        return float(str(row.get("bound_rent", "")).replace(",", ""))
    except (ValueError, TypeError):
        return None


def detect_dominant_cluster(benches, supplement):
    """比较最近对标站点与全市同类型补充案例的边界水平：
    若补充案例中有≥2个边界明显低于最近对标站点（<85%），判定为更能代表当前真实定价的主导集群，
    返回一句可直接写入benchmark_info的系统提示，明确建议AI改用该集群中最合适的案例作为锚点。
    这是为了避免AI单纯因为"距离最近"而默认选用价格明显偏高的孤立案例。"""
    near_bounds = [b for _, r in benches if (b := _bound(r)) is not None]
    if not near_bounds or not supplement:
        return None
    near_median = sorted(near_bounds)[len(near_bounds) // 2]

    low_supp = [(d, r) for d, r in supplement if (b := _bound(r)) is not None and b < near_median * 0.85]
    if len(low_supp) < 2:
        return None

    low_supp.sort(key=lambda x: x[0])  # 低价集群里选距离最近的一个作为推荐锚点
    best_d, best_row = low_supp[0]
    best_bound = _bound(best_row)
    low_values = sorted(_bound(r) for _, r in low_supp)

    return (
        f"⚠️系统提示：距离最近的对标站点边界集中在约{round(near_median)}元，"
        f"但全市同类型补充案例中有{len(low_supp)}个边界明显更低（约{low_values[0]:.0f}-{low_values[-1]:.0f}元），"
        f"距离虽较远但业态更贴近本站点。建议以【{best_row['name']}】（{best_d:.2f}km，边界{best_bound:.0f}元）"
        f"作为边界判定的主要参考锚点，而非以上方最近对标站点为锚点——"
        f"多个一致的同类型案例比单个距离更近但价格明显偏高的案例更能代表当前真实定价水平。"
    )


def format_benchmark_info(benches, supplement=None) -> str:
    """把 Haversine 匹配到的对标站点格式化成文字，传给 Coze 工作流。
    supplement：当最近对标站点普遍偏远时，全市范围补充的同类型（工业区/城中村）站点，
    是与最近对标站点同等有效的真实数据，供AI综合归纳、判断合理锚点。"""
    if not benches:
        return "（同城市内未找到近距离对标站点，请依赖知识库语义检索）"

    def _fmt(i, d_km, row, tag=""):
        parts = [f"对标{i}{tag}：{row['name']}（{round(d_km, 2)}km）"]
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
        return " | ".join(parts)

    lines = [_fmt(i, d_km, row) for i, (d_km, row) in enumerate(benches, 1)]
    if supplement:
        lines.append("")
        lines.append("【全市同类型补充案例（工业区/城中村主导，距离较远但业态相似，与最近对标站点同等有效，供综合判断锚点）】")
        for j, (d_km, row) in enumerate(supplement, 1):
            lines.append(_fmt(j, d_km, row, tag="(同类型)"))
        note = detect_dominant_cluster(benches, supplement)
        if note:
            lines.append("")
            lines.append(note)
    return "\n".join(lines)


def static_map_urls(coord: str):
    """生成 3km/2km/1km 三张高德静态地图URL（与Coze工作流代码节点一致）。
    zoom+图片尺寸组合精确控制图幅（广东纬度约23°）：
    zoom=15@682px≈3km见方、zoom=15@455px≈2km见方、zoom=16@455px≈1km见方。"""
    coord = str(coord).replace(" ", "").strip()  # 空格会导致高德返回JSON错误
    base = "https://restapi.amap.com/v3/staticmap"
    marker = f"mid,,A:{coord}"
    specs = [
        ("3km", 15, "682*682"),
        ("2km", 15, "455*455"),
        ("1km", 16, "455*455"),
    ]
    return [
        (label, f"{base}?location={coord}&zoom={z}&size={s}&markers={marker}&key={AMAP_KEY}")
        for label, z, s in specs
    ]


def render_static_maps(coord: str):
    """标签页大图展示站点周边地图。
    ⚠️ 这是给人看的展示图，与传给Coze视觉分析的三张固定图幅（static_map_urls）是两套，互不影响：
    AI用的图幅必须精确（3/2/1km，距离推断依赖它），展示图则追求清晰放大（高zoom+大像素）。"""
    coord = str(coord).replace(" ", "").strip()
    base = "https://restapi.amap.com/v3/staticmap"
    marker = f"mid,,A:{coord}"
    # 展示图规格（广东纬度约23°）：zoom=16@910px宽≈2km、zoom=17≈1km、zoom=15≈4km
    display_specs = [
        ("🏘️ 周边环境（约2km）", 16),
        ("🔍 紧邻街区（约1km）", 17),
        ("🗺️ 片区格局（约4km）", 15),
    ]
    tabs = st.tabs([label for label, _ in display_specs])
    for tab, (label, z) in zip(tabs, display_specs):
        with tab:
            url = f"{base}?location={coord}&zoom={z}&size=910*568&markers={marker}&key={AMAP_KEY}"
            st.image(url, width="stretch")
    st.caption("📍 红色标记为站点位置 · 切换标签查看不同范围（评估AI使用的是另一套精确图幅地图，不受此处显示影响）")


def render_rent_trend_chart(city: str, district: str):
    """该行政区历史成交价随内审时间变化的散点+趋势线，让"统计模型判断的时间趋势"
    可视化给人看，而不是只在算法内部生效。领导工具的×0.85折扣是人工拍的固定系数，
    看不出数据支撑；这张图直接把576条训练数据里这个行政区的真实走势画出来。"""
    hist = load_district_rent_history(city, district)
    if len(hist) < 3:
        st.caption(f"📉 {district}历史样本不足3个，暂不显示趋势图")
        return
    import altair as alt
    base = alt.Chart(hist).encode(
        x=alt.X("audit_date:T", title="内审日期"),
        y=alt.Y("unit_rent:Q", title="单车位租金（元/月）", scale=alt.Scale(zero=False)),
    )
    points = base.mark_circle(size=70, opacity=0.6, color="#1f3a5f").encode(
        tooltip=[alt.Tooltip("name:N", title="站点"), alt.Tooltip("audit_date:T", title="内审日期"), alt.Tooltip("unit_rent:Q", title="租金")]
    )
    trend = base.transform_regression("audit_date", "unit_rent", method="linear").mark_line(color="#c1372f", strokeWidth=2)
    st.altair_chart((points + trend).properties(height=200), use_container_width=True)
    st.caption(f"📉 {district}历史{len(hist)}个场地成交价，红线为时间趋势拟合——模型预测时会参考这条趋势自动折算当前行情价")


def render_price_explainability(explain: dict):
    """把统计模型预测拆解成"行政区基准 × 各特征调整系数"的分项列表，
    回答"这个数字是怎么算出来的"，而不是只吐一个数字让人凭空相信。"""
    if not explain or not explain.get("parts"):
        return
    rows_html = (
        f"<div style='display:flex;justify-content:space-between;padding:6px 2px;"
        f"border-bottom:1px solid var(--app-border);font-size:0.88rem'>"
        f"<span style='color:var(--app-text-secondary)'>行政区基准价（该行政区历史均值水平）</span>"
        f"<span style='color:var(--app-text);font-weight:600'>¥{explain['baseline']:.0f}</span></div>"
    )
    for p in explain["parts"]:
        arrow = "↑" if p["pct"] >= 0 else "↓"
        sign = "+" if p["pct"] >= 0 else ""
        rows_html += (
            f"<div style='display:flex;justify-content:space-between;padding:6px 2px;"
            f"border-bottom:1px solid var(--app-border);font-size:0.88rem'>"
            f"<span style='color:var(--app-text-secondary)'>{p['label']}</span>"
            f"<span style='color:var(--app-text)'>{arrow} {sign}{p['pct']:.1f}%</span></div>"
        )
    st.markdown(rows_html, unsafe_allow_html=True)
    st.caption("以上为模型系数拆解（未经边界夹取前的原始预测过程），最终目标价见上方价格卡（已按行政区标准夹取留出谈判空间）")


def render_price_range(price_range):
    """预测区间：保守/中性/进取三档（2026-07-26新增），代替单点数字更适合谈判场景——
    保守价是"大概率能拿下的价"，进取价是"运气好能冲到的价"。纯参考展示，不影响
    上方价格卡的目标/边界/起点价（那套有对标案例+行政区标准的硬性业务规则约束）。"""
    if not price_range or not all(price_range):
        return
    conservative, neutral, aggressive = price_range
    st.markdown(
        f"""
<div style="display:flex;gap:10px;margin-bottom:6px">
  <div style="flex:1;background:var(--app-surface);border:1px solid var(--app-border);border-radius:10px;padding:10px 14px;text-align:center">
    <div style="font-size:0.78rem;color:var(--app-text-muted)">保守</div>
    <div style="font-size:1.2rem;font-weight:600;color:var(--app-text)">¥{conservative:.0f}</div>
  </div>
  <div style="flex:1;background:var(--app-accent-soft);border:1px solid var(--app-border);border-radius:10px;padding:10px 14px;text-align:center">
    <div style="font-size:0.78rem;color:var(--app-accent)">中性</div>
    <div style="font-size:1.2rem;font-weight:700;color:var(--app-accent)">¥{neutral:.0f}</div>
  </div>
  <div style="flex:1;background:var(--app-surface);border:1px solid var(--app-border);border-radius:10px;padding:10px 14px;text-align:center">
    <div style="font-size:0.78rem;color:var(--app-text-muted)">进取</div>
    <div style="font-size:1.2rem;font-weight:600;color:var(--app-text)">¥{aggressive:.0f}</div>
  </div>
</div>
""",
        unsafe_allow_html=True,
    )
    st.caption("统计模型分位数回归给出的价格分布区间（10%/50%/90%分位，纯参考），不参与上方价格卡的业务规则计算")


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
    # 📚参考案例已在上方"对标案例对比"表格+下方"一键复制纯文本"里展示过，此处不再重复渲染
    HIDDEN_SECTIONS = ("💡", "🔥", "📍", "💰", "📚")
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


def run_batch_prediction(name: str, address: str) -> dict:
    """批量评估单行：geocode+POI+统计模型三价，不调用Coze（视觉分析+LLM报告太慢，
    批量场景要的是快速拿到一批数字做初筛，不是逐个出完整报告）。
    返回一行结果字典，任一环节失败时对应字段留空，不中断整批。"""
    row = {"站点名称": name or "—", "地址": address, "城市": "", "行政区": "",
           "谈判起点": None, "建议目标": None, "边界上限": None, "置信度": "", "备注": ""}
    if not address:
        row["备注"] = "地址为空，已跳过"
        return row
    coord, city, district = geocode(address)
    if not coord:
        row["备注"] = "定位失败"
        return row
    row["城市"], row["行政区"] = city, district
    if not row["站点名称"] or row["站点名称"] == "—":
        row["站点名称"] = re.split(r"[，,]", address.strip())[-1].strip()[:20] or "未命名站点"

    _, transit_count = find_nearby_transit(coord)
    _, industrial_count = find_nearby_industrial(coord)
    _, mall_count = find_nearby_commercial(coord)
    hub_counts = hub_counts_from_results(find_transit_hubs_extended(coord))
    # 先取对标案例（边界推导要用），再预测
    df = load_benchmarks()
    benches = find_benchmarks(coord, city, row["站点名称"], df)
    target, boundary, opening = predict_target_rent(city, district, transit_count, industrial_count, mall_count, hub_counts, bench_rows=benches)
    if target is None:
        row["备注"] = "该行政区无租金标准数据，模型无法预测"
        return row

    conf_level, conf_reasons, _ = assess_confidence(city, district, transit_count, industrial_count, mall_count, benches)
    row.update({
        "谈判起点": opening, "建议目标": round(target), "边界上限": boundary,
        "置信度": conf_level, "备注": "；".join(conf_reasons) if conf_level == "低" else "",
    })
    return row


# ── 评估历史台账（2026-07-26新增）────────────────────
# Streamlit Community Cloud的文件系统是临时的，重启/重新部署会清空本地写入，
# 不能像本地脚本那样简单追加CSV。改用GitHub Contents API直接读写仓库里的
# eval_history.csv——复用项目里benchmarks.csv/rent_standard.csv那套"改CSV→git commit→
# Streamlit Cloud自动拉取"的既有模式，不引入新的外部服务/依赖。
EVAL_HISTORY_PATH = "eval_history.csv"  # 仓库根目录（即coze网页版/目录）下的路径
EVAL_HISTORY_FIELDS = [
    "timestamp", "name", "city", "district", "address", "coord",
    "target", "boundary", "opening",
    "price_conservative", "price_neutral", "price_aggressive", "confidence",
]


def log_evaluation_to_github(record: dict):
    """把一条评估记录追加写入GitHub仓库里的eval_history.csv并提交。
    ⚠️ 失败（未配置Token/网络问题/并发冲突）时静默跳过，绝不能因为记台账失败
    影响主评估流程——这是锦上添花的功能，不是关键路径。"""
    if not GITHUB_TOKEN:
        return False, "未配置GITHUB_TOKEN，跳过台账记录"
    import base64
    import csv
    import io

    api_base = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{EVAL_HISTORY_PATH}"
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
    }
    try:
        r = requests.get(api_base, headers=headers, timeout=10)
        if r.status_code == 200:
            data = r.json()
            sha = data["sha"]
            existing = base64.b64decode(data["content"]).decode("utf-8-sig")
        elif r.status_code == 404:
            sha = None
            existing = ""
        else:
            return False, f"读取eval_history.csv失败：HTTP {r.status_code}"

        buf = io.StringIO()
        buf.write(existing)  # 文件不存在时existing=""，什么都不写
        if not existing.strip():
            csv.DictWriter(buf, fieldnames=EVAL_HISTORY_FIELDS).writeheader()
        elif not existing.endswith("\n"):
            buf.write("\n")  # 确保上次内容结尾有换行，避免新行和上一行粘在一起
        csv.DictWriter(buf, fieldnames=EVAL_HISTORY_FIELDS).writerow(record)
        new_content = buf.getvalue()

        payload = {
            "message": f"log evaluation: {record.get('name', '')}",
            "content": base64.b64encode(new_content.encode("utf-8")).decode("ascii"),
        }
        if sha:
            payload["sha"] = sha
        r2 = requests.put(api_base, headers=headers, json=payload, timeout=10)
        if r2.status_code in (200, 201):
            return True, "已记录"
        return False, f"写入失败：HTTP {r2.status_code} {r2.text[:200]}"
    except Exception as e:
        return False, f"台账记录异常：{e}"


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

# ── 输入表单（侧边栏：左侧输入、右侧展示，减少上下滚动）──
with st.sidebar:
    eval_mode = st.radio("评估模式", ["单站评估", "批量评估", "模型回测"], horizontal=True, label_visibility="collapsed")
    submitted = False
    batch_submitted = False
    f_name = f_addr = f_coord = ""
    batch_text = ""

    if eval_mode == "单站评估":
        st.markdown("### ⚡ 站点信息输入")
        with st.form("eval_form"):
            f_name = st.text_input(
                "站点名称（选填）",
                placeholder="不填则用地址自动生成，例：广州天河正佳换电站",
            )
            f_addr = st.text_area(
                "完整地址 *",
                placeholder="例：广东省广州市天河区天河路385号正佳广场旁",
                help="请包含省市区信息，系统将自动解析城市和行政区，无需单独填写",
                height=80,
            )
            f_coord = st.text_input(
                "坐标（选填）",
                placeholder="例：113.935068,22.677748",
                help="高德定位不准时手动填入。从钉图易点击站点位置获取坐标，格式：经度,纬度（中英文逗号均可）。填入后将覆盖高德自动定位。",
            )
            submitted = st.form_submit_button("🚀 开始评估", width="stretch", type="primary")
    elif eval_mode == "批量评估":
        st.markdown("### 📦 批量站点输入")
        with st.form("batch_form"):
            batch_text = st.text_area(
                "每行一个站点，格式：站点名称,完整地址（名称可留空）",
                placeholder="龙华民治站,广东省深圳市龙华区民治大道88号\n,广东省广州市天河区天河路385号正佳广场旁",
                height=220,
                help="快速拿到一批候选点的目标价/边界/起点价，仅跑统计模型，不生成AI报告和地图分析（速度快很多）",
            )
            batch_submitted = st.form_submit_button("🚀 开始批量评估", width="stretch", type="primary")
        st.caption(
            "⚠️ 价格数字不受影响：目标价/边界/起点价本来就是统计模型算的，和AI视觉分析无关。"
            "批量模式只是跳过「AI看地图写商圈说明文字」这一步（这步慢，1-2分钟一个站），"
            "适合快速初筛多个候选点；需要完整文字报告时切回单站评估逐个跑"
        )
    else:
        st.markdown("### 📐 模型回测")
        st.caption("对576个历史场地做5折交叉验证样本外预测，看模型预测vs实际成交的吻合程度——不需要输入，切到这个模式直接看右侧结果")
    st.caption(f"📊 统计模型：{model_stats_note()}")

# ── Session State 初始化 ──────────────────────
if "eval_result" not in st.session_state:
    st.session_state.eval_result = None   # 评估报告文本
    st.session_state.eval_meta   = {}     # 站点名/地址/坐标/城市/行政区
    st.session_state.eval_benches = []    # 对标站点列表
    st.session_state.eval_supplement = [] # 全市同类型补充案例
if "batch_results" not in st.session_state:
    st.session_state.batch_results = None

# ── 批量评估流程（跑统计模型三价，不调用Coze）──
if batch_submitted:
    _lines = [l.strip() for l in batch_text.splitlines() if l.strip()]
    if not _lines:
        st.error("请至少粘贴一行站点信息")
        st.stop()
    _rows = []
    _progress = st.progress(0.0, text="批量评估中…")
    for _i, _line in enumerate(_lines, 1):
        _parts = _line.split(",", 1) if "," in _line else ["", _line]
        _bname, _baddr = _parts[0].strip(), _parts[-1].strip()
        _rows.append(run_batch_prediction(_bname, _baddr))
        _progress.progress(_i / len(_lines), text=f"批量评估中…（{_i}/{len(_lines)}）")
    _progress.empty()
    st.session_state.batch_results = _rows

# ── 评估流程 ──────────────────────────────────
if submitted:
    if not f_addr:
        st.error("请填写完整地址")
        st.stop()
    if not f_name:
        # 未填站点名称时，用地址最后一段自动生成一个可读名称
        f_name = re.split(r"[，,]", f_addr.strip())[-1].strip()[:20] or "未命名站点"
    if not COZE_TOKEN:
        st.error("请先在 Secrets 中配置 COZE_TOKEN")
        st.stop()

    with st.status("评估进行中…", expanded=False) as status_box:

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
        nearby_tr, transit_count = find_nearby_transit(coord)
        if nearby_tr:
            for line in nearby_tr.split("\n")[1:]:
                if line.strip():
                    st.write(f"  · {line.strip()}")
        else:
            st.write("  · 2km 内未检索到城轨/地铁/高铁站")

        st.write("🏭 正在查询周边工业园/产业园（高德 2km 搜索）…")
        nearby_ind, industrial_count = find_nearby_industrial(coord)
        if nearby_ind:
            for line in nearby_ind.split("\n")[1:]:
                if line.strip():
                    st.write(f"  · {line.strip()}")
        else:
            st.write("  · 2km 内未检索到工业园/产业园")

        st.write("🏬 正在查询周边大型商业设施（高德 2km 关键词搜索）…")
        nearby, mall_count = find_nearby_commercial(coord)
        if nearby:
            for line in nearby.split("\n")[1:]:   # 跳过标题行
                if line.strip():
                    st.write(f"  · {line.strip()}")
        else:
            st.write("  · 1.5km 内未检索到大型商业/文化设施")

        # Step 2.6：最近对标站点普遍偏远 + 周边工业多商业少 → 全市补充同类型（工业区/城中村）站点
        # 让AI有真实同类案例可归纳，而非在无相关数据时硬套公式
        supplement = []
        if benches and min(d for d, _ in benches) > 3.0:
            st.write("🏗️ 附近对标站点较远，正在全市范围补充同类型（工业区/城中村）站点…")
            existing_names = {row["name"] for _, row in benches}
            # 需要足够数量才能覆盖不同价格片区（如近处高价corridor + 远一点的低价工业带），
            # 让AI有完整图景可比较归纳，而非只看到与最近3个同质的高价案例
            supplement = find_industrial_supplement(coord, city, f_name, existing_names, df, need=6)
            for d_km, row in supplement:
                st.write(f"  · {row['name']}（同类型补充） — {round(d_km, 2)} km")

        # Step 2.65：充电站 + 交通枢纽固定半径搜索
        # ⚠️ 必须在Step 2.7模型预测之前算好——高铁/火车站等4类枢纽数量现在是模型特征。
        # 充电站仍只用于展示，不进模型。
        charging_count, charging_nearest = find_charging_stations(coord)
        transit_hubs = find_transit_hubs_extended(coord)
        hub_counts = hub_counts_from_results(transit_hubs)

        # Step 2.7：Ridge回归模型预测目标租金
        # 在调用Coze之前完成，边界=周边对标案例边界的最高水平（封顶行政区标准上限），
        # 目标=模型预测夹取在标准范围内，起点价=目标的90%——三个数字全部由Python确定性算出，
        # 作为既定事实传给Coze，LLM不再自行判断锚点/打折，只负责写支撑这些数字的说明文字。
        st.write(f"📈 正在用统计模型预测目标租金（{model_stats_note()}）…")
        model_target, model_boundary, model_opening = predict_target_rent(
            city, district, transit_count, industrial_count, mall_count, hub_counts,
            bench_rows=(benches or supplement),
        )
        if model_target:
            st.write(f"  · 模型预测目标租金：{model_target:.0f} 元 ｜ 边界：{model_boundary} 元 ｜ 起点价：{model_opening:.0f} 元")
        else:
            st.write("  ⚠️ 未找到该行政区的租金标准或模型不可用，将退回由AI自行判断数字")
        # 预测区间（保守/中性/进取，纯参考，不参与Coze/边界业务规则）
        price_conservative, price_neutral, price_aggressive = predict_price_range(
            city, district, transit_count, industrial_count, mall_count, hub_counts
        )

        # Step 2.75：周边路网（regeo最近道路，展示用）
        township, nearby_roads = find_nearby_roads(coord)

        # Step 2.8：置信度评估（确定性规则：训练样本覆盖 + POI密度 + 对标距离）
        conf_level, conf_reasons, conf_advice = assess_confidence(
            city, district, transit_count, industrial_count, mall_count, benches
        )
        st.write(f"🎚️ 评估置信度：{conf_level}" + (f"（{'；'.join(conf_reasons)}）" if conf_reasons else ""))

        # Step 3：调用 Coze 工作流（流式优先，失败回退非流式）
        # 复用上面已查询的POI结果，避免重复请求高德API
        benchmark_info = format_benchmark_info(benches or [], supplement)
        for extra in (nearby_tr, nearby_ind, nearby):
            if extra:
                benchmark_info = benchmark_info + "\n\n" + extra
        if model_target:
            benchmark_info += (
                f"\n\n【系统统计模型预测（最高优先级，覆盖以下所有对标案例的数字推断）】\n"
                f"基于{model_stats_note()}的Ridge回归模型（城市/行政区+2km内交通枢纽/工业园/商场数量特征）预测：\n"
                f"建议单车位租金边界：{model_boundary}元/车位/月（=本行政区标准上限，硬性规则）\n"
                f"建议目标单车位租金：{model_target:.0f}元/车位/月（模型预测值，已夹取在行政区标准范围内）\n"
                f"谈判起点价：{model_opening:.0f}元/车位/月（目标价的90%）\n"
                f"请直接采用以上三个数字，不得自行调整或重新计算；"
                f"以上方对标案例和本站点特征为依据，说明这些数字为何合理即可。"
            )

        st.write("🤖 正在调用 Coze 工作流（报告将实时逐字显示）…")
        stream_placeholder = st.empty()
        result = call_workflow_stream(f_name, city, district, f_addr, coord, benchmark_info, stream_placeholder)
        if result is None:
            st.write("  ⚠️ 流式接口不可用，切换为普通模式（通常需要 30–90 秒）…")
            result = call_workflow(f_name, city, district, f_addr, coord, benchmark_info)
        stream_placeholder.empty()

        # Step 4：记台账（失败不影响评估结果，只是锦上添花，见log_evaluation_to_github注释）
        if model_target:
            from datetime import datetime as _dt
            _ok, _msg = log_evaluation_to_github({
                "timestamp": _dt.now().strftime("%Y-%m-%d %H:%M:%S"),
                "name": f_name, "city": city, "district": district,
                "address": f_addr, "coord": coord,
                "target": round(model_target), "boundary": model_boundary, "opening": round(model_opening),
                "price_conservative": price_conservative or "", "price_neutral": price_neutral or "",
                "price_aggressive": price_aggressive or "", "confidence": conf_level,
            })
            st.write(f"📒 评估台账：{_msg}")

        # 完成后折叠过程日志（可点开审计），页面直接呈现结果
        status_box.update(label="✅ 评估完成（点击展开查看评估过程日志）", state="complete", expanded=False)

    # 保存结果到 session_state，防止标签页切换/重渲染时结果丢失
    st.session_state.eval_result  = result
    st.session_state.eval_meta    = {"name": f_name, "addr": f_addr, "coord": coord, "city": city, "district": district}
    st.session_state.eval_benches = benches
    st.session_state.eval_supplement = supplement
    st.session_state.eval_pois    = {"🚉 交通枢纽": nearby_tr, "🏭 工业园/产业园": nearby_ind, "🏬 大型商业设施": nearby}
    st.session_state.eval_model   = {
        "target": model_target, "boundary": model_boundary, "opening": model_opening,
        "transit_count": transit_count, "industrial_count": industrial_count, "mall_count": mall_count,
        "hub_counts": hub_counts,
        "price_range": (price_conservative, price_neutral, price_aggressive),
    }
    st.session_state.eval_confidence = {"level": conf_level, "reasons": conf_reasons, "advice": conf_advice}
    st.session_state.eval_roads = {"township": township, "roads": nearby_roads}
    st.session_state.eval_transit_hubs = {
        "charging": (charging_count, charging_nearest),
        "hubs": transit_hubs,
        "transit_count": transit_count,
    }

# ── 批量评估结果展示 ──────────────────────────
if eval_mode == "批量评估" and st.session_state.batch_results:
    st.divider()
    _bdf = pd.DataFrame(st.session_state.batch_results)
    st.markdown(f"##### 📦 批量评估结果（{len(_bdf)}个站点）")
    st.dataframe(
        _bdf, hide_index=True, width="stretch",
        column_config={
            "谈判起点": st.column_config.NumberColumn(format="¥%d"),
            "建议目标": st.column_config.NumberColumn(format="¥%d"),
            "边界上限": st.column_config.NumberColumn(format="¥%d"),
        },
    )
    st.download_button(
        "💾 下载结果（.csv）",
        data=_bdf.to_csv(index=False).encode("utf-8-sig"),
        file_name="批量租金评估结果.csv",
        mime="text/csv",
    )
    st.caption("以上价格数字和单站评估同源、同样可信（都是统计模型算的，不依赖AI视觉分析）；缺的只是AI写的商圈说明文字和地图分析，需要完整文字报告时切回「单站评估」逐个跑")

# ── 模型回测页面 ──────────────────────────────
if eval_mode == "模型回测":
    st.divider()
    render_backtest_page()

# ── 财务BP视图 / 商务同事视图 共用的渲染组件 ───────────────
# 抽成函数，让两个视图都能复用同一套站点头/价格卡/周边定位卡，改一处两处都变，不再各写一份。
def poi_items(text):
    return [l.strip() for l in (text or "").split("\n")[1:] if l.strip()]


def render_site_header(f_name, city, district, township, f_addr, coord):
    """场地信息头条：站点名 + 城市·行政区·街道 + 高德识别地址 + 坐标。"""
    st.markdown(
        f"""
<div style="display:flex;align-items:baseline;gap:18px;flex-wrap:wrap;margin:2px 0 2px">
  <span style="font-size:1.2rem;font-weight:600;color:var(--app-text)">📍 {f_name or '—'}</span>
  <span style="font-size:1rem;font-weight:500;color:var(--app-text-secondary)">{city} · {district}{('·' + township) if township else ''}</span>
</div>
<div style="color:var(--app-text-muted);font-size:0.85rem;margin-bottom:12px">
  高德识别地址：{f_addr}　|　坐标：{coord}
</div>
""",
        unsafe_allow_html=True,
    )


def compute_price_numbers(result, city, district):
    """算出价格卡要用的三价+标准范围+数据来源。无价格时返回None。
    ⚠️ std_missing=True 表示rent_standard.csv里查不到这个(city,district)组合——
    这种情况下predict_target_rent会直接返回None，导致三个价格全部退回AI在报告文字里
    自由判断的数字（不受统计模型约束，可信度低很多）。常见原因：地名用字不一致
    （如"寮步镇"在标准表里被错打成"察步镇"）或该行政区确实还没收录标准。"""
    model_nums = st.session_state.get("eval_model") or {}
    if model_nums.get("target"):
        boundary = str(int(model_nums["boundary"]))
        target   = str(int(round(model_nums["target"])))
        opening  = str(int(round(model_nums["opening"])))
    else:
        boundary = extract_boundary(result)
        target, opening = extract_key_numbers(result)
    if not any([boundary, target, opening]):
        return None
    std = lookup_rent_standard(city, district)
    std_missing = std is None
    if std:
        range_str = f"{std[0]} – {std[1]}"
    else:
        rm = re.search(r"租金标准[^\d]{0,15}(\d+)\s*[-–~至—]\s*(\d+)", result)
        range_str = f"{rm.group(1)} – {rm.group(2)}" if rm else "—"
    src_note = (f"统计模型计算 · {model_stats_note()}" if model_nums.get("target") else "AI评估提取")
    return {"model_nums": model_nums, "target": target, "opening": opening,
            "boundary": boundary, "range_str": range_str, "src_note": src_note,
            "std_missing": std_missing, "city": city, "district": district}


def render_price_hero(nums, show_boundary=True, show_footer=True):
    """价格主卡：谈判起点 / 建议目标（居中放大深色块）/ 边界上限 + 标准范围 + 数据来源。
    show_boundary=False 隐藏"边界上限"卡（商务同事视图不给看边界，防止对外泄露定价上限）；
    show_footer=False 隐藏底部"行政区标准范围 + 模型来源"那行（同样对商务同事隐藏）。"""
    _t = nums["target"] or "—"
    _o = nums["opening"] or "—"
    _b = nums["boundary"] or "—"
    _boundary_card = (
        f"""    <div style="background:var(--app-bg);border:1px solid var(--app-border);border-radius:12px;padding:12px 22px">
      <div style="font-size:0.8rem;color:var(--app-text-muted)">💰 边界上限</div>
      <div style="font-size:1.6rem;font-weight:600;line-height:1.3;color:var(--app-text)">¥{_b}</div>
    </div>"""
        if show_boundary else ""
    )
    _footer = (
        f"""  <div style="margin-top:16px;padding-top:10px;border-top:1px solid var(--app-border-strong);
       font-size:0.8rem;color:var(--app-text-muted)">
    🏛️ 行政区租金标准 {nums['range_str']} 元/车位/月　·　📈 {nums['src_note']}
  </div>"""
        if show_footer else ""
    )
    st.markdown(
        f"""
<div style="background:var(--app-accent-soft);border:1px solid var(--app-border);
     border-radius:14px;padding:22px 24px 14px;text-align:center;margin-bottom:10px">
  <div style="font-size:0.9rem;color:var(--app-text-secondary);margin-bottom:16px">综合建议租金（首年价，元/车位/月）</div>
  <div style="display:flex;justify-content:center;align-items:center;gap:24px">
    <div style="background:var(--app-bg);border:1px solid var(--app-border);border-radius:12px;padding:12px 22px">
      <div style="font-size:0.8rem;color:var(--app-text-muted)">🤝 谈判起点</div>
      <div style="font-size:1.6rem;font-weight:600;line-height:1.3;color:var(--app-text)">¥{_o}</div>
    </div>
    <div style="background:var(--app-accent);border-radius:14px;padding:14px 32px">
      <div style="font-size:0.85rem;color:#c9d8ea;font-weight:600">🎯 建议目标</div>
      <div style="font-size:2.6rem;font-weight:700;line-height:1.15;letter-spacing:0.3px;color:#ffffff">¥{_t}</div>
    </div>
{_boundary_card}
  </div>
{_footer}
</div>
""",
        unsafe_allow_html=True,
    )


def render_location_card(result, coord):
    """站点周边与定位卡：左侧静态地图标签页 + 右侧AI定位分析（商圈/道路/地段+周边路网）。"""
    if not coord:
        return
    with st.container(border=True):
        st.markdown("##### 🗺️ 站点周边与定位")
        # 关键特征高亮条：区域性质描述（商圈类型）· 道路描述+通达结论
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
                f"<div style='background:var(--app-accent-soft);border:1px solid var(--app-border);border-radius:10px;"
                f"padding:9px 16px;color:var(--app-accent);font-size:0.95rem;font-weight:600;"
                f"margin-bottom:12px'>{_feat}</div>",
                unsafe_allow_html=True,
            )
        # 左图右文布局：左侧地图标签页，右侧AI定位分析
        _col_map, _col_txt = st.columns([1.1, 1], gap="medium")
        with _col_map:
            render_static_maps(coord)
        with _col_txt:
            _loc_html = []
            _LABEL_COLORS = {"商圈类型": "#3b6fd1", "道路条件": "#d98c22", "地段价值": "#2b9e6f"}

            def _sec_open(label, value, value_size="1.15rem", value_bold=True):
                w = "700" if value_bold else "400"
                c = _LABEL_COLORS.get(label, "#9aa7bd")
                return (
                    f"<div style='margin-bottom:20px;padding-left:11px;border-left:3px solid {c}'>"
                    f"<div style='font-size:0.78rem;color:{c};letter-spacing:2px;font-weight:700;margin-bottom:3px'>{label}</div>"
                    f"<div style='font-size:{value_size};font-weight:{w};color:var(--app-text);line-height:1.75'>{value}</div>"
                )

            _blocks = []
            for _raw in get_section_lines(result, "📍"):
                _s = _raw.strip()
                if not _s:
                    continue
                _m = re.match(r"^(商圈类型|道路条件)[：:]\s*(.+)$", _s)
                if _m:
                    _blocks.append({"label": _m.group(1), "value": _m.group(2), "reason": ""})
                    continue
                _m = re.match(r"^依据[：:]\s*(.+)$", _s)
                if _m and _blocks:
                    _blocks[-1]["reason"] = _m.group(1)
                    continue
                _m = re.match(r"^地段价值[：:]\s*(.+)$", _s)
                if _m:
                    _blocks.append({"label": "地段价值", "value": _m.group(1), "reason": "", "plain": True})
                    continue

            for _b in _blocks:
                _plain = _b.get("plain")
                _loc_html.append(_sec_open(
                    _b["label"], _b["value"],
                    value_size="0.95rem" if _plain else "1.15rem",
                    value_bold=not _plain,
                ))
                if _b["reason"]:
                    _loc_html.append(
                        f"<div style='margin-top:7px;color:var(--app-text-muted);font-size:0.85rem;line-height:1.9'>{_b['reason']}</div>"
                    )
                _loc_html.append("</div>")

            # 周边路网：胶囊标签（regeo最近道路，只列名称/方位/距离，不猜等级）
            _roads = (st.session_state.get("eval_roads") or {}).get("roads") or []
            if _roads:
                _pills = "".join(
                    f"<span style='background:#f2f6fd;border:1px solid #e3eaf6;border-radius:999px;"
                    f"padding:4px 13px;font-size:0.82rem;color:var(--app-text-secondary);display:inline-block;"
                    f"margin:0 8px 8px 0;white-space:nowrap'>"
                    f"<b style='color:var(--app-text)'>{n}</b>　{d}侧 · 约{dist:.0f}m</span>"
                    for n, d, dist in _roads
                )
                _loc_html.append(
                    f"<div style='padding-top:14px;border-top:1px dashed #dbe4f3;"
                    f"padding-left:11px;border-left:3px solid #8b5cf6'>"
                    f"<div style='font-size:0.78rem;color:#8b5cf6;letter-spacing:2px;font-weight:700;margin-bottom:8px'>周边路网</div>"
                    f"{_pills}</div>"
                )
            if _loc_html:
                st.markdown("".join(_loc_html), unsafe_allow_html=True)


# ── 双视图展示（从 session_state 读取，刷新不丢失）────
if eval_mode == "单站评估" and st.session_state.eval_result:
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
        # 场地信息头条（复用共享组件）
        _township = (st.session_state.get("eval_roads") or {}).get("township", "")
        render_site_header(f_name, city, district, _township, f_addr, coord)

        # 关键数字：统计模型优先，模型不可用时回退AI文字提取（compute_price_numbers内部处理）
        _model_nums = st.session_state.get("eval_model") or {}
        _price = compute_price_numbers(result, city, district)
        _target   = _price["target"] if _price else ""
        _opening  = _price["opening"] if _price else ""
        _boundary = _price["boundary"] if _price else ""
        if _price:
            if _price.get("std_missing"):
                # 行政区标准查不到 → 统计模型被整体跳过，三个价格全部退回AI在报告文字里
                # 自由判断的数字，可信度远低于模型计算。常见原因：rent_standard.csv里的
                # 地名用字和geocode返回的不一致（如"寮步镇"曾被误录成"察步镇"），也可能是
                # 该行政区确实还没收录标准。必须显眼提示，不能只在脚注小字里悄悄写"AI评估提取"。
                st.markdown(
                    f"<div style='background:var(--app-danger-soft);border-left:3px solid var(--app-danger);"
                    f"border-radius:8px;padding:12px 16px;margin-bottom:10px;font-size:0.88rem;color:var(--app-text-secondary)'>"
                    f"<b style='color:var(--app-danger)'>⚠️ 未在行政区标准表中查到「{_price['city']} · {_price['district']}」</b><br>"
                    f"以下三个价格均为AI在报告文字里自由判断，<b>未经统计模型计算</b>，可信度低很多。"
                    f"请检查 rent_standard.csv 里该行政区的地名写法是否与本站一致（常见问题：形近字打错、"
                    f"街道/镇后缀不一致），或该行政区是否尚未收录标准。</div>",
                    unsafe_allow_html=True,
                )
            render_price_hero(_price)
            # 置信度徽章 + 低置信度警示（确定性规则评估，借鉴领导工具设计）
            _conf = st.session_state.get("eval_confidence") or {}
            _lv = _conf.get("level")
            if _lv:
                _badge_tints = {
                    "高": ("#1c7a4a", "#e6f4ec"),
                    "中": ("#946200", "#fdf1dc"),
                    "低": ("#c1372f", "#fbe4e2"),
                }
                _badge_color, _badge_bg = _badge_tints[_lv]
                st.markdown(
                    f"<div style='text-align:center;margin:4px 0 8px'><span style='color:{_badge_color};"
                    f"background:{_badge_bg};padding:4px 16px;border-radius:999px;"
                    f"font-size:0.85rem;font-weight:600'>"
                    f"{'✅' if _lv=='高' else '⚠️'} {_lv}置信度</span></div>",
                    unsafe_allow_html=True,
                )
                if _lv == "低":
                    _reason_html = "".join(f"<div>• {r}</div>" for r in _conf.get("reasons", []))
                    _advice_html = "".join(f"<div>• {a}</div>" for a in _conf.get("advice", []))
                    st.markdown(
                        f"<div style='background:var(--app-danger-soft);border-left:3px solid var(--app-danger);border-radius:8px;"
                        f"padding:14px 18px;margin-bottom:10px;font-size:0.9rem;color:var(--app-text-secondary);line-height:1.9'>"
                        f"<div style='color:var(--app-danger);font-weight:600;margin-bottom:6px'>⚠️ 低置信度 — 建议人工审核</div>"
                        f"{_reason_html}"
                        f"<div style='font-weight:700;margin-top:8px'>人工审核建议：</div>{_advice_html}</div>",
                        unsafe_allow_html=True,
                    )
                elif _lv == "中" and _conf.get("reasons"):
                    st.caption("⚠️ " + "；".join(_conf["reasons"]) + "。" + "；".join(_conf.get("advice", [])))

            if _model_nums.get("target"):
                st.caption(f"📈 以上边界/目标/起点价由统计模型计算（{model_stats_note()}），下方为AI针对此数字的定性说明")
            else:
                # 模型不可用时的旧路径：边界锚点+推理依据从AI报告文字提取
                _anchor = re.search(r"边界锚点[：:]\s*([^\n。；]+)", result)
                if _anchor:
                    st.caption(f"⚓ 边界锚点：{_anchor.group(1).strip()}")
            _br = re.search(r"边界推理依据[：:]\s*([^\n]+)", result)
            if _br:
                st.caption(f"💰 边界推理依据：{_br.group(1).strip()}")
            _tr = re.search(r"目标价推理依据[：:]\s*([^\n]+)", result)
            if _tr:
                st.caption(f"🎯 目标价推理依据：{_tr.group(1).strip()}")

            # 这个价格是怎么算出来的：趋势图+模型系数拆解，默认折叠（不打断决策区的简洁），
            # 但比黑箱吐一个数字更能让人信服——领导工具的×0.85折扣看不出这层依据
            if _model_nums.get("target"):
                with st.expander("📈 这个价格是怎么算出来的"):
                    render_price_range(_model_nums.get("price_range"))
                    _ec1, _ec2 = st.columns([1.1, 1], gap="medium")
                    with _ec1:
                        st.markdown("**行政区历史租金趋势**")
                        render_rent_trend_chart(city, district)
                    with _ec2:
                        st.markdown("**模型系数拆解**")
                        _explain = explain_prediction(
                            city, district,
                            _model_nums.get("transit_count", 0),
                            _model_nums.get("industrial_count", 0),
                            _model_nums.get("mall_count", 0),
                            _model_nums.get("hub_counts", {}),
                        )
                        render_price_explainability(_explain)

        # ── 站点周边与定位（复用共享组件）──
        _pois = st.session_state.get("eval_pois") or {}
        _poi_items = poi_items  # 兼容下方详细分析里对_poi_items的引用
        render_location_card(result, coord)

        # ── 详细分析：周边设施(左) + 交通与充电枢纽(右) + 对标案例(下) + AI报告(折叠) ──
        # 不再用tab切来切去，改为并排+纵排一屏铺开，一眼看全
        st.markdown("##### 🔍 详细分析")
        _first_dist_re = re.compile(r"（(\d+)m")
        _facility_col, _transit_col = st.columns([1.5, 1], gap="medium")
        with _facility_col:
            # ── 周边设施统计（紧凑横向条：3类服务器端 + 住宅小区浏览器端）──
            if any(_pois.values()) or coord:
                _chips_srv = ""
                _details_srv = ""
                _first_dist_re = re.compile(r"（(\d+)m")
                for _lbl, _text in _pois.items():
                    if _lbl == "🚉 交通枢纽":
                        continue  # 交通枢纽已合并进下方"交通与充电枢纽"面板，此处不重复展示
                    _items = _poi_items(_text)
                    # 最近距离（明细第一条括号里的距离）
                    _near = ""
                    if _items:
                        _dm = _first_dist_re.search(_items[0])
                        _near = f"最近 {_dm.group(1)}m" if _dm else ""
                    _chips_srv += (
                        f"<div style='background:#ffffff;border:1px solid #e6e8ec;border-radius:10px;"
                        f"padding:12px 8px 10px;text-align:center'>"
                        f"<div style='color:#6b7280;font-size:12px;letter-spacing:1px'>{_lbl}</div>"
                        f"<div style='font-size:1.5rem;font-weight:600;color:#1f3a5f;line-height:1.4'>{len(_items)}"
                        f"<span style='font-size:0.8rem;font-weight:400;color:#9aa0ab'> 个</span></div>"
                        f"<div style='color:#9aa0ab;font-size:11px'>{_near or '&nbsp;'}</div></div>"
                    )
                    _details_srv += f"<b>{_lbl}</b>：{'、'.join(_items) if _items else '2km内未检索到'}<br>"
                # 浏览器端补充统计的类别（仿领导工具的"环境构成"，但仅做展示参考，不参与区域类型判断）
                _browser_cats_html = ""
                for _i, (_emoji_lbl,) in enumerate([("🏘️ 住宅小区",), ("🏢 写字楼",), ("🏫 中小学",), ("🏥 医院",), ("🌳 公园广场",)]):
                    _browser_cats_html += (
                        f"<div style='background:#ffffff;border:1px solid #e6e8ec;border-radius:10px;"
                        f"padding:12px 8px 10px;text-align:center'>"
                        f"<div style='color:#6b7280;font-size:12px;letter-spacing:1px'>{_emoji_lbl}</div>"
                        f"<div id='cnt{_i}' style='font-size:1.5rem;font-weight:600;color:#1f3a5f;line-height:1.4'>…</div>"
                        f"<div id='near{_i}' style='color:#9aa0ab;font-size:11px'>&nbsp;</div></div>"
                    )
                _strip_html = f"""
    <div style="font-family:-apple-system,'PingFang SC','Source Sans Pro',sans-serif">
      <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:10px">
        {_chips_srv}
        {_browser_cats_html}
      </div>
      <div style="margin-top:10px;font-size:12.5px;color:#808495;line-height:1.9;
           max-height:130px;overflow-y:auto;background:#fafbfe;border:1px solid #eef2f9;
           border-radius:8px;padding:8px 12px">
        {_details_srv}<span id="resdetail"><b>🏘️ 住宅小区</b>：检索中…</span>
      </div>
    </div>
    <script>
    const KEY = "{AMAP_KEY}";
    const coord = "{coord}";
    // 浏览器端统计类别（国内网络直连高德，绕过海外服务器限制）
    // count字段=2km内总数；nearest取距离排序第一条
    const CATS = [
      ["120302", 0, true],            // 住宅小区（额外拉明细清单）
      ["120201", 1, false],           // 写字楼
      ["141202|141203", 2, false],    // 中小学
      ["090100", 3, false],           // 综合医院
      ["110101|110105", 4, false],    // 公园广场
    ];
    async function loadCat(types, idx, wantDetail) {{
      const r = await fetch("https://restapi.amap.com/v3/place/around?location=" + coord +
        "&types=" + encodeURIComponent(types) + "&radius=2000&offset=25&page=1" +
        "&sortrule=distance&output=json&key=" + KEY);
      const j = await r.json();
      const total = parseInt(j.count || "0");
      const pois = j.pois || [];
      document.getElementById("cnt" + idx).innerHTML = total +
        "<span style='font-size:0.8rem;font-weight:400;color:#9aa7bd'> 个</span>";
      if (pois.length) {{
        document.getElementById("near" + idx).innerHTML = "最近 " + pois[0].distance + "m";
      }} else {{
        document.getElementById("near" + idx).innerHTML = "范围内无";
      }}
      if (wantDetail) {{
        const seen = new Set();
        const items = pois.filter(p => {{
          if (seen.has(p.name)) return false;
          seen.add(p.name); return true;
        }});
        document.getElementById("resdetail").innerHTML = "<b>🏘️ 住宅小区</b>：" +
          (items.length ? items.slice(0, 25).map(p => p.name + "（" + p.distance + "m）").join("、") +
            (total > items.length ? " …等共" + total + "个" : "") : "2km内未检索到") +
          "<span style='color:#b0bdd4'>（注：可能含公寓/宿舍，仅供参考，不作为区域类型判断依据）</span>";
      }}
    }}
    Promise.allSettled(CATS.map(c => loadCat(c[0], c[1], c[2]))).catch(() => {{}});
    </script>
    """
                import streamlit.components.v1 as components
                with st.container(border=True):
                    st.markdown("##### 📡 周边设施统计")
                    components.html(_strip_html, height=300, scrolling=True)
                    st.caption("2km范围 · 前三类服务器端检索并传给AI，后五类浏览器端实时检索（仅展示参考，不参与区域类型判断——住宅类POI常混入宿舍公寓）")

        with _transit_col:
            # ── 交通与充电枢纽（合并面板：2km地铁/高铁/城轨明细 + 充电站 + 固定半径补充搜索，仿领导工具）──
            _th = st.session_state.get("eval_transit_hubs") or {}
            if _th:
                with st.container(border=True):
                    st.markdown("##### 🚉 交通与充电枢纽")
                    _chg_count, _chg_nearest = _th.get("charging", (0, None))
                    _transit_items = _poi_items(_pois.get("🚉 交通枢纽", ""))
                    _transit_near = ""
                    if _transit_items:
                        _dm = _first_dist_re.search(_transit_items[0])
                        _transit_near = f"最近 {_dm.group(1)}m" if _dm else ""
                    _c1, _c2 = st.columns(2)
                    _c1.metric("🚇 地铁/高铁/城轨（2km，进AI评估）", f"{_th.get('transit_count', 0)} 个",
                               _transit_near or "范围内无")
                    _c2.metric("⚡ 充电站（2km）", f"{_chg_count} 个",
                               f"最近 {_chg_nearest}m" if _chg_nearest else "范围内无")
                    if _transit_items:
                        st.markdown(
                            f"<div style='font-size:0.85rem;color:#5c6b85;padding:2px 2px 10px'>"
                            f"{'、'.join(_transit_items)}</div>",
                            unsafe_allow_html=True,
                        )
                    st.caption(
                        "以下高速出入口/高铁火车站/长途汽车站/机场（更大固定半径）**均已作为模型特征参与租金预测**——"
                        "高铁/火车站等对网约车热力、区域通达性有实际影响。可在上方"
                        "「这个价格是怎么算出来的」里看到各枢纽对价格的具体贡献。"
                    )
                    for _key, _label, _radius, _count, _nearest in _th.get("hubs", []):
                        _rk = int(_radius / 1000)
                        _detail = f"最近 {_nearest}m" if _nearest else "范围内无"
                        st.markdown(
                            f"<div style='display:flex;justify-content:space-between;padding:5px 2px;"
                            f"border-bottom:1px solid #f0f3f8;font-size:0.9rem'>"
                            f"<span style='color:var(--app-text-secondary)'>{_label}（{_rk}km内）</span>"
                            f"<span><b style='color:var(--app-text)'>{_count} 个</b>"
                            f"<span style='color:#9aa7bd;margin-left:10px'>{_detail}</span></span></div>",
                            unsafe_allow_html=True,
                        )

        # ── 对标案例（整幅展示在设施/交通两列下方，不再放进tab）──
        with st.container():
            # 对标案例对比（表格+柱状图，数据来自benchmarks匹配，非LLM文本）
            _supp_for_tab = st.session_state.get("eval_supplement") or []
            if benches or _supp_for_tab:
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

                    def _parse_similarity_notes(text: str) -> dict:
                        """从📚参考案例文本中解析每个站点的"相似/差异"说明。"""
                        notes = {}
                        lines = get_section_lines(text, "📚")
                        cur_name = None
                        for l in lines:
                            s = l.strip()
                            if not s:
                                continue
                            m = re.match(r"^\d*\.?\s*([^（(]+)[（(]", s)
                            if m and "相似" not in s and "差异" not in s:
                                cur_name = m.group(1).strip()
                            elif s.startswith("相似") and cur_name:
                                notes[cur_name] = s.split("：", 1)[-1].split(":", 1)[-1].strip()
                                cur_name = None
                        return notes

                    _sim_notes = _parse_similarity_notes(result)

                    rows_ = []
                    for d_km, brow in benches:
                        rows_.append({
                            "来源": "🎯最近对标",
                            "站点": brow["name"],
                            "行政区": str(brow.get("district", "") or "—"),
                            "距离(km)": round(d_km, 2),
                            "内审日期": _audit_display(brow.get("audit_date")),
                            "商圈类型": str(brow.get("bc_type", "") or "—"),
                            "道路条件": str(brow.get("road_cond", "") or "—"),
                            "成交租金(元)": _num(brow.get("unit_rent")),
                            "租金边界(元)": _num(brow.get("bound_rent")),
                            "相似/差异": _sim_notes.get(brow["name"], "—"),
                        })
                    # 全市同类型补充案例（工业区/城中村主导，距离较远，仅供归纳参考）
                    for d_km, brow in (st.session_state.get("eval_supplement") or []):
                        rows_.append({
                            "来源": "🏭全市补充",
                            "站点": brow["name"],
                            "行政区": str(brow.get("district", "") or "—"),
                            "距离(km)": round(d_km, 2),
                            "内审日期": _audit_display(brow.get("audit_date")),
                            "商圈类型": str(brow.get("bc_type", "") or "—"),
                            "道路条件": str(brow.get("road_cond", "") or "—"),
                            "成交租金(元)": _num(brow.get("unit_rent")),
                            "租金边界(元)": _num(brow.get("bound_rent")),
                            "相似/差异": "（全市同类型补充，AI未逐一分析）",
                        })
                    # 末行加入本站建议（商圈/道路取AI评估结果），方便与对标直接比较
                    if _target or _boundary:
                        _bc_m   = re.search(r"商圈类型[：:]\s*([^\n，,。；;（(]+)", result)
                        _road_m = re.search(r"道路条件[：:]\s*([^\n，,。；;（(]+)", result)
                        rows_.append({
                            "来源": "",
                            "站点": "★ 本站建议",
                            "行政区": district or "—",
                            "距离(km)": None,
                            "内审日期": "—",
                            "商圈类型": _bc_m.group(1).strip() if _bc_m else "—",
                            "道路条件": _road_m.group(1).strip() if _road_m else "—",
                            "成交租金(元)": int(_target) if _target else None,
                            "租金边界(元)": int(_boundary) if _boundary else None,
                            "相似/差异": "",
                        })
                    _df_show = pd.DataFrame(rows_)
                    _df_show["距离(km)"] = _df_show["距离(km)"].apply(lambda v: f"{v:.2f}" if isinstance(v, (int, float)) and v is not None else "—")
                    st.dataframe(
                        _df_show, hide_index=True, width="stretch",
                        column_config={
                            "来源":       st.column_config.TextColumn(width="small"),
                            "行政区":     st.column_config.TextColumn(width="small"),
                            "距离(km)":   st.column_config.TextColumn(width="small"),
                            "成交租金(元)": st.column_config.NumberColumn(format="¥%d"),
                            "租金边界(元)": st.column_config.NumberColumn(format="¥%d"),
                            "相似/差异":  st.column_config.TextColumn(width="large"),
                        },
                    )
                    st.caption("⚠️早期 = 2025年上半年及以前过会，早期建站未严格管控租金，成交租金不具参考性，仅边界可参考")
            else:
                st.info(
                    "该区域历史签约站点稀少，未匹配到近距离对标案例。\n\n"
                    "价格建议已由统计模型基于行政区基准+周边POI特征给出（见上方价格卡与「这个价格是怎么算出来的」），"
                    "但缺少实际成交案例佐证，建议参考左侧「低置信度」提示做人工审核。"
                )

        # ── AI评估报告：放最下面，默认折叠。用checkbox而非expander——因为报告内部
        # render_report_sections每节都用了st.expander，Streamlit不允许expander套expander。
        st.markdown("##### 📋 AI 评估报告")
        if st.checkbox("展开完整评估报告（参考案例完整推理 · 一键复制 · 下载）", value=False):
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
            _supp = st.session_state.get("eval_supplement") or []
            if _supp:
                _full_lines += ["", "【全市同类型补充案例（工业区/城中村主导，仅供归纳参考）】"]
                for _i, (_d, _b) in enumerate(_supp, 1):
                    _ad = str(_b.get("audit_date", "") or "").strip()[:10]
                    _early = "（⚠️早期，成交租金不参考）" if _ad and _ad <= "2025-06-30" else ""
                    _full_lines.append(
                        f"{_i}. {_b['name']}｜距离{_d:.2f}km｜内审{_ad or '—'}{_early}｜"
                        f"{_b.get('bc_type', '') or '—'}｜{_b.get('road_cond', '') or '—'}｜"
                        f"成交{_b.get('unit_rent', '') or '—'}元｜边界{_b.get('bound_rent', '') or '—'}元"
                    )
            full_text = "\n".join(_full_lines)

            # ⚠️ 不能用嵌套expander（Streamlit禁止expander套expander，会运行时报错），
            # 此处已在外层"AI评估报告"expander内，改用普通标题+code块展示纯文本。
            st.markdown("**📋 一键复制纯文本**")
            st.code(full_text, language=None)
            st.download_button(
                label="💾 下载报告（.txt）",
                data=full_text,
                file_name=f"租金评估_{f_name}.txt",
                mime="text/plain",
                width="stretch",
            )

    # ── 商务同事 视图 ─────────────────────────
    # 与财务视图共用站点头/价格卡/周边定位卡（不显示置信度拆解和详细分析tab，保持简洁），
    # 底部保留周边参考站点表（成交租金口径）。
    with tab_biz:
        _township_b = (st.session_state.get("eval_roads") or {}).get("township", "")
        render_site_header(f_name, city, district, _township_b, f_addr, coord)

        _price_b = compute_price_numbers(result, city, district)
        if _price_b:
            # 商务同事视图：隐藏边界上限 + 底部行政区标准/模型来源（对外不泄露定价上限和内部依据）
            render_price_hero(_price_b, show_boundary=False, show_footer=False)
        else:
            st.info("暂无价格数据，请查看「财务BP 完整报告」标签页")

        # 站点周边与定位（地图 + 商圈/道路/地段 + 周边路网）
        render_location_card(result, coord)

        # 周边参考站点（距离 + 成交租金，不显示边界；商务同事只需知道邻站实际成交多少）
        with st.container(border=True):
            st.markdown("##### 📍 周边参考站点")
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
                        "成交租金": unit_rent_display if unit_rent and unit_rent != "nan" else "—",
                    })
                st.table(pd.DataFrame(table_rows))
            else:
                st.info("同城市内未找到近距离参考站点")
