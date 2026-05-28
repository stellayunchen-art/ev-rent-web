# export_benchmarks.py
# ============================================================
# 作用：把 Excel 知识库导出成 benchmarks.csv，供 Streamlit 网页版使用
# 运行环境：MacBook（本地）
# 运行时机：每次有新站点过会后，重新跑一次，然后把 benchmarks.csv 提交到 GitHub
# ============================================================

import openpyxl
import csv
from pathlib import Path

# ─── 修改这里 ──────────────────────────────────────────────
INPUT_FILE = Path("/Users/stellachan/Documents/AI  Application/AI租金自动评估/换电站选址租金知识库_租金评估结果AI自动化更新.xlsx")
OUTPUT_CSV = Path(__file__).parent / "benchmarks.csv"   # 输出到 coze网页版/ 目录
SHEET_NAME = "案例知识库"
# ───────────────────────────────────────────────────────────

# 列索引（1-based，与 update_new_stations_v2.py 保持一致）
C_NAME  = 2   # B 站点名称
C_CITY  = 6   # F 城市
C_COORD = 9   # I 坐标
C_BC    = 10  # J 商圈类型
C_AREA  = 11  # K 区域类型
C_ROADC = 12  # L 道路条件
C_ROADT = 13  # M 道路类型
# N=14 场地类型（跳过）
C_UNIT  = 15  # O 单车位租金
C_BOUND = 16  # P 单车位租金边界
DATA_START = 2

FIELDS = ["name", "city", "coord", "bc_type", "area_type", "road_cond", "road_type", "unit_rent", "bound_rent"]


def safe(v) -> str:
    if v is None:
        return ""
    s = str(v).strip()
    return "" if s in ("#N/A", "None", "nan") else s


def main():
    if not INPUT_FILE.exists():
        print(f"❌ 找不到文件：{INPUT_FILE}")
        print("请确认 Excel 路径是否正确")
        return

    print(f"加载 Excel：{INPUT_FILE.name}")
    wb = openpyxl.load_workbook(INPUT_FILE, data_only=True)

    if SHEET_NAME not in wb.sheetnames:
        print(f"❌ 找不到 Sheet「{SHEET_NAME}」，当前 Sheet 列表：{wb.sheetnames}")
        return

    ws = wb[SHEET_NAME]
    for m in list(ws.merged_cells.ranges):
        ws.unmerge_cells(str(m))

    rows = []
    skipped = 0
    for r in range(DATA_START, ws.max_row + 1):
        name  = safe(ws.cell(r, C_NAME).value)
        coord = safe(ws.cell(r, C_COORD).value)

        # 跳过：无名称 / 坐标为空 / 待评估（新增未过会站点不作为对标）
        if not name or "," not in coord:
            skipped += 1
            continue

        rows.append({
            "name":      name,
            "city":      safe(ws.cell(r, C_CITY).value),
            "coord":     coord,
            "bc_type":   safe(ws.cell(r, C_BC).value),
            "area_type": safe(ws.cell(r, C_AREA).value),
            "road_cond": safe(ws.cell(r, C_ROADC).value),
            "road_type": safe(ws.cell(r, C_ROADT).value),
            "unit_rent": safe(ws.cell(r, C_UNIT).value),
            "bound_rent":safe(ws.cell(r, C_BOUND).value),
        })

    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    print(f"✅ 已导出 {len(rows)} 条记录 → {OUTPUT_CSV}")
    print(f"   （跳过 {skipped} 行空行/无坐标行）")
    print()
    print("下一步：")
    print("  1. git add benchmarks.csv")
    print("  2. git commit -m 'update benchmarks'")
    print("  3. git push")
    print("  → Streamlit Cloud 会自动拉取更新，网页版即时生效")


if __name__ == "__main__":
    main()
