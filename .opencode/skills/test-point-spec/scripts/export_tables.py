#!/usr/bin/env python3
"""export_tables.py — 由清单主件生成便于查看的纯数据视图（只读投影）

视图规则（2026-11-04 决策）：
  - 主件唯一权威：output/tp/test-point.md / output/tc/test-case.md。
    视图 test-point-table.md / test-case-table.md 仅作查看与筛选，不作为确认/质检对象、
    不承载语义；每当局件变更且机验 PASS 后由**经理**重新生成。
  - TP 视图表头：编号 | 验证意图 | 类型 | 依据 | 所属系统 | 业务活动 | 业务功能
    依据=指针级（文件:行号 / CL-xxx，用「、」连接），不做改写，保真以主件机验为准。
    归属解析链：需求→TP 覆盖表反查 TP→REQ → 基线 feature_id（取「（）」内名称）
    → scope-list「归属登记」表查 所属系统/所属业务活动；查不到即留空并 WARN。
  - TC 视图表头：用例编号 | 标题 | 关联TP | 测试点验证意图 | 优先级 | 用例类型 |
    前置条件 | 测试数据 | 操作步骤 | 预期结果 | 所属系统 | 业务活动 | 业务功能 | 依据（主TP）
    归属取自主件「标签」列（所属系统/所属业务活动/所属业务功能 三键拆列）；
    测试点验证意图=主 TP（关联TP 首个）；依据（主TP）= 该 TP 的依据指针。
  - 自洽校验：视图行数与编号集合必须与主表一致，否则 exit 1。

用法：
  python3 export_tables.py --phase tp --tp-file <test-point.md> \
    --baseline <requirements-baseline.json> --scope-list <scope-list.md> \
    --output <test-point-table.md>
  python3 export_tables.py --phase tc --tc-file <test-case.md> \
    --tp-file <test-point.md> --output <test-case-table.md>

退出码：0 = 生成成功；1 = 解析/自洽失败；2 = 用法错误
"""
import argparse
import json
import os
import re
import sys

WARNED = []


def read_text(path):
    for enc in ("utf-8", "utf-8-sig", "gbk"):
        try:
            with open(path, "r", encoding=enc) as f:
                return f.read()
        except UnicodeDecodeError:
            continue
    raise RuntimeError(f"无法解码: {path}")


def _tables(text):
    """抽取全文 md 表格 -> [(章节标题, 表头, 数据行)]。进入新 ## 章节即封存旧表（C1 同源语义）。"""
    text = re.sub(r"```.*?```", "", text, flags=re.S)  # 代码块内表格不参与解析
    out = []
    title = ""
    header = None
    rows = []
    for line in text.splitlines():
        s = line.rstrip()
        if s.lstrip().startswith("#"):
            if header is not None:
                out.append((title, header, rows))
                header, rows = None, []
            title = s.lstrip("#").strip()
            continue
        if s.strip().startswith("|"):
            cells = [c.strip() for c in s.strip().strip("|").split("|")]
            if header is None:
                header, rows = cells, []
            elif all(re.fullmatch(r":?-{2,}:?", c) for c in cells if c != ""):
                continue  # 分隔行
            else:
                rows.append(cells)
        else:
            if header is not None:
                out.append((title, header, rows))
                header, rows = None, []
    if header is not None:
        out.append((title, header, rows))
    return out


def find_table(text, keyword=None):
    """按章节关键词取表；keyword=None 时优先取首个 ## 之前的主表，否则取全文第一张表。"""
    ts = _tables(text)
    if not ts:
        raise KeyError("文件中未发现任何表格")
    if keyword is not None:
        for t in ts:
            if keyword in t[0]:
                return t
        raise KeyError(f"未找到章节「{keyword}」")
    for t in ts:
        if t[0] == "":
            return t
    return ts[0]


def split_ids(cell):
    return [x for x in re.split(r"[、，,;；\s]+", cell or "") if x]


def esc(cell):
    """写入视图的单元格转义：竖线替换、去换行。"""
    return (cell or "").replace("|", "｜").replace("\n", " ").strip()


def evidence_pointers(cell):
    """依据列 -> 指针级串：文件:行号 / CL-xxx，其余 token 截断 30 字并 WARN。"""
    ptrs = []
    for tok in re.split(r"\s*⟂\s*", cell or ""):
        tok = tok.strip()
        if not tok:
            continue
        m = re.match(r"^(?P<f>[^:：]+?\.(?:md|markdown|txt|csv))\s*[:：]\s*L?(?P<ln>\d+(?:\s*[-–]\s*\d+)?)", tok)
        if m:
            ptrs.append(f"{m.group('f')}:{m.group('ln').replace(' ', '')}")
            continue
        m = re.match(r"^(CL-\d+)", tok)
        if m:
            ptrs.append(m.group(1))
            continue
        WARNED.append(f"依据 token 无法解析为指针：{tok[:30]}…")
        ptrs.append(tok[:24])
    return "、".join(ptrs)


def bracket_name(s):
    m = re.search(r"（(.+?)）", s or "")
    return m.group(1).strip() if m else (s or "").strip()


def lookup_belong(name, registry):
    if not name:
        return "", ""
    if name in registry:
        return registry[name]
    for key, val in registry.items():
        if key and (key in name or name in key):
            return val
    return "", ""


def load_registry(scope_text):
    """scope-list「归属登记」表 -> {名称: (所属系统, 所属业务活动)}。表缺失返回空 dict 并 WARN。"""
    try:
        _, header, rows = find_table(scope_text, keyword="归属登记")
    except KeyError:
        WARNED.append("scope-list 未找到「归属登记」表，视图归属列将为空")
        return {}
    idx = {h: i for i, h in enumerate(header)}
    name_i = idx.get("功能/依赖名称", 0)
    sys_i = idx.get("所属系统", 1)
    act_i = idx.get("所属业务活动", 2)
    reg = {}
    for r in rows:
        if len(r) <= max(name_i, sys_i, act_i):
            WARNED.append(f"归属登记行列数不足：{'|'.join(r)}")
            continue
        reg[esc(r[name_i])] = (esc(r[sys_i]), esc(r[act_i]))
    return reg


def export_tp(args):
    tp_text = read_text(args.tp_file)
    try:
        _, header, rows = find_table(tp_text, keyword="测试点主表")
    except KeyError:
        # 2026-11-05 契约收敛：主表定位主契约 = 第一个 ## 之前的表（与 verify_test_points 一致）；
        # 章节标题含「测试点主表」仅为可选择性增强，查不到时回退主契约，不再让视图管线一票否决。
        _, header, rows = find_table(tp_text, keyword=None)
    if rows and not any(re.fullmatch(r"TP-\d+", r[0]) for r in rows if r):
        # 兜底仍解析出非主表（如文件以说明表开头）→ 继续 keyword 提示 WB。
        WARNED.append("TP 视图：主契约定位到的首表未含 TP 行，请检查清单主表结构")

    with open(args.baseline, "r", encoding="utf-8-sig") as f:
        baseline = json.load(f)
    # 2026-11-05 归属契约修复（复盘 A3）：视图"业务功能"列取 selected_scope 中与 feature_id
    # 对应的功能**名称原文**——业务功能编号仅限过程使用，不得进入最终交付的视图；
    # name 缺失时才降级用 bracket_name(feature_id) 并 WARN。
    scope_names = {
        item.get("feature_id"): (item.get("name") or "").strip()
        for item in baseline.get("selected_scope", [])
        if isinstance(item, dict)
    }
    req2feat = {}
    for r in baseline.get("requirements", []):
        fid = r.get("feature_id", "")
        if fid in scope_names and scope_names[fid]:
            req2feat[r.get("id")] = scope_names[fid]
        elif fid:
            req2feat[r.get("id")] = bracket_name(fid)
            WARNED.append(f"基线 selected_scope 缺「{fid}」名称，功能列降级用编号（最终交付不应出现编号）")

    # 需求→TP 覆盖表反查 TP→REQ→功能
    tp2reqs = {}
    scope_text = read_text(args.scope_list)
    try:
        _, cov_header, cov_rows = find_table(tp_text, keyword="需求→测试点覆盖表")
        for r in cov_rows:
            tps = [x for x in split_ids(r[1]) if re.fullmatch(r"TP-\d+", x)]
            for tp in tps:
                tp2reqs.setdefault(tp, [])
                for req in re.findall(r"REQ-\d+", r[0]):
                    if req not in tp2reqs[tp]:
                        tp2reqs[tp].append(req)
    except KeyError:
        WARNED.append("未找到「需求→测试点覆盖表」，业务功能列将为空")

    registry = load_registry(scope_text)

    # 列序（校验契约）：编号 | 验证意图 | 类型 | 分析方法 | 依据
    out_rows = []
    tb_ids = []
    valid_master = 0
    for r in rows:
        if len(r) < 5 or not re.fullmatch(r"TP-\d+", r[0]):
            WARNED.append(f"主表忽略非 TP 行：{'|'.join(r)[:40]}")
            continue
        valid_master += 1
        tid, intent, tp_type, _, basis = r[0], r[1], r[2], r[3], r[4]
        tb_ids.append(tid)
        feats = []
        for req in tp2reqs.get(tid, []):
            fname = req2feat.get(req, "")
            if fname and fname not in feats:
                feats.append(fname)
        feat_cell = "、".join(feats)
        sys_cell, act_cell = "", ""
        for fname in feats:  # 主归属（首个）优先；缺失则试后续特征
            sys_cell, act_cell = lookup_belong(fname, registry)
            if sys_cell or act_cell:
                break
        out_rows.append([tid, intent, tp_type, evidence_pointers(basis), sys_cell, act_cell, feat_cell])

    _check(out_rows, tb_ids, "test-point")

    # 视图定位（2026-11-05 收敛修正）：面向用户的**呈现层**，仅包含一张表——
    # 是测试点主表（编号/验证意图/类型/依据）与归属信息的纯映射；
    # 主件变更且机验 PASS 后由经理重跑 export_tables 即获得最新映射（数据自动跟随主件）。
    lines = [
        "| 编号 | 验证意图 | 类型 | 依据 | 所属系统 | 业务活动 | 业务功能 |",
        "|---|---|---|---|---|---|---|",
    ]
    lines += ["| " + " | ".join(esc(c) for c in r) + " |" for r in out_rows]
    _no_codes_guard(out_rows, feat_col=6)
    _write(args.output, lines)
    return len(out_rows)


def export_tc(args):
    tc_text = read_text(args.tc_file)
    _, header, rows = find_table(tc_text)
    if header is None:
        _, header, rows = find_table(tc_text, keyword="测试用例主表")
    idx = {h: i for i, h in enumerate(header)}
    need = ["编号", "标题", "关联TP", "优先级", "前置条件", "测试数据", "操作步骤", "预期结果", "用例类型", "标签"]
    missing = [h for h in need if h not in idx]
    if missing:
        raise KeyError(f"TC 主表缺少契约字段：{'、'.join(missing)}")

    tp_text = read_text(args.tp_file)
    _, tp_hdr, tp_rows = find_table(tp_text, keyword="测试点主表")
    tp2intent, tp2basis = {}, {}
    for r in tp_rows:
        if len(r) >= 5 and re.fullmatch(r"TP-\d+", r[0]):
            tp2intent[r[0]] = r[1]
            tp2basis[r[0]] = evidence_pointers(r[4])

    out_rows = []
    tc_ids = []
    for r in rows:
        tc_id = r[idx["编号"]]
        if not re.fullmatch(r"TC-\d+", tc_id):
            WARNED.append(f"主表忽略非 TC 行：{tc_id}")
            continue
        tc_ids.append(tc_id)
        linked = split_ids(r[idx["关联TP"]])
        primary = linked[0] if linked else ""
        tags = _parse_tags(r[idx["标签"]])
        sys_c = tags.get("所属系统", "")
        act_c = tags.get("所属业务活动", "")
        feat_c = tags.get("所属业务功能", "")
        intent = tp2intent.get(primary, "")
        if primary and not intent:
            WARNED.append(f"{tc_id} 主 TP {primary} 在测试点清单中不存在，验证意图留空")
        basis = tp2basis.get(primary, "") if primary else ""
        out_rows.append([
            tc_id, r[idx["标题"]], r[idx["关联TP"]], intent, r[idx["优先级"]], r[idx["用例类型"]],
            r[idx["前置条件"]], r[idx["测试数据"]], r[idx["操作步骤"]], r[idx["预期结果"]],
            sys_c, act_c, feat_c, basis,
        ])

    _check(out_rows, tc_ids, "test-case")

    # 视图定位同 export_tp：呈现层、仅一张表、纯主件映射
    lines = [
        "| 用例编号 | 标题 | 关联TP | 测试点验证意图 | 优先级 | 用例类型 | 前置条件 | 测试数据 | 操作步骤 | 预期结果 | 所属系统 | 业务活动 | 业务功能 | 依据（主TP） |",
        "|" + "---|" * 14,
    ]
    lines += ["| " + " | ".join(esc(c) for c in r) + " |" for r in out_rows]
    _no_codes_guard(out_rows, feat_col=12)
    _write(args.output, lines)
    return len(out_rows)


def _parse_tags(cell):
    d = {}
    for part in re.split(r"[；;]+", cell or ""):
        part = part.strip()
        if not part:
            continue
        m = re.match(r"^(所属系统|所属业务活动|所属业务功能)\s*[:：]\s*(.*)$", part)
        if m:
            d[m.group(1)] = m.group(2).strip()
    return d


def _check(out_rows, ids, name):
    if len(out_rows) != len(ids):
        print(f"[FAIL] {name} 视图行数与编号数不一致：{len(out_rows)} vs {len(ids)}")
        sys.exit(1)
    data_ids = [r[0] for r in out_rows]
    if data_ids != ids:
        print(f"[FAIL] {name} 视图编号集合与主表不一致")
        sys.exit(1)


def _no_codes_guard(out_rows, feat_col):
    """视图自检（2026-11-05 新增，复盘 A3）：业务功能编号仅限过程使用，不得进入归属列。

    仅检查"业务功能"归属列（feat_col：TP 视图=第 7 列 / TC 视图=第 13 列）——
    验证意图/预期结果等列的 F 编号属于**逐字引文原文**（如「触发 F8 跳转」），合法。
    命中即 exit 1——此前该类问题只能靠人眼发现。
    """
    hits = []
    for row in out_rows:
        if len(row) <= feat_col:
            continue
        cell = row[feat_col]
        if cell and re.search(r"\bF\d+\b", cell):
            hits.append((row[0], cell))
    if hits:
        preview = "; ".join(f"{tid} `{c[:40]}`" for tid, c in hits[:5])
        print(f'[FAIL] 视图"业务功能"归属列出现业务功能编号（应使用功能名称原文）: {preview}')
        sys.exit(1)


def _write(path, lines):
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def main():
    ap = argparse.ArgumentParser(description="从清单主件生成纯数据视图（-table.md）")
    ap.add_argument("--phase", required=True, choices=["tp", "tc"])
    ap.add_argument("--tp-file")
    ap.add_argument("--tc-file")
    ap.add_argument("--baseline")
    ap.add_argument("--scope-list")
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    try:
        if args.phase == "tp":
            if not (args.tp_file and args.baseline and args.scope_list):
                ap.error("--phase tp 需要 --tp-file / --baseline / --scope-list / --output")
            n = export_tp(args)
        else:
            if not (args.tc_file and args.tp_file):
                ap.error("--phase tc 需要 --tc-file / --tp-file / --output")
            n = export_tc(args)
    except KeyError as e:
        msg = e.args[0] if e.args else str(e)
        print(f"[FAIL] {msg}")
        sys.exit(1)

    for w in WARNED:
        print(f"[WARN] {w}")
    print(f"[OK] 已生成 {args.output}（{n} 行，与主表自洽）")
    sys.exit(0)


if __name__ == "__main__":
    main()
