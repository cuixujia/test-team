#!/usr/bin/env python3
"""口袋词表 WARN 机检（2026-11-08-缺陷单：经理出单，主会话维护者落地）。

对 TP 主件"验证意图"列做"补充-TP切分与命名判别.md"§二"验证意图词面筛检"四类的
确定性子串预筛：结果词 / 处理逻辑 / 具体值 / 并列双结果谓词。

性质：
- WARN，不 FAIL：退出码恒 0；命中只提示"可疑，人工判定"，语义裁决归质检专家。
- PRD 原词照抄例外无法机器判定，命中时标注"人工判定"。
- 结果词/处理逻辑/具体值词面与补充件§二一致；未命中该三类属"PRD 原词照抄"场景的，
  由人工按主从裁决与直引证据认定，不在本工具免责范围之外另设判定。

用法（经理侧，shell 单命令形态）：
  python3 .opencode/skill/test-script-lib/scripts/screen_intent_words.py \
    --tp-file <测试点清单.md> [--report <输出的json路径>]
"""
import argparse
import hashlib
import json
import re
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mdtable import parse_first_table  # 表格解析唯一实现，从共享库导入

# 词表（与 补充-TP切分与命名判别.md §二"验证意图词面筛检"对齐）
RESULT_WORDS = ["成功", "不能", "不可", "自动生成", "进入"]
PROCESS_WORDS = ["返回"]
PARALLEL_WORDS = ["并", "且"]
CATEGORY_NAME = {
    "结果词": "词面筛检 1",
    "处理逻辑": "词面筛检 2",
    "具体值": "词面筛检 3",
    "并列双结果谓词": "词面筛检 4（需人工判是否触发合并/拆分）",
}
DIGIT_RE = re.compile(r"\d+")


def _hits(intent: str):
    found = []
    for w in RESULT_WORDS:
        if w in intent:
            found.append(("结果词", w))
    for w in PROCESS_WORDS:
        if w in intent:
            found.append(("处理逻辑", w))
    if DIGIT_RE.search(intent):
        found.append(("具体值", "数字字面量"))
    for w in PARALLEL_WORDS:
        if w in intent:
            found.append(("并列双结果谓词", "连接词「%s」" % w))
    return found


def screen(tp_text: str):
    """返回 (warns, n_rows, sha)。warns = [{id, intent, category, term}]"""
    # 主表 = 第一个 "##" 之前的唯一表格（test-point-spec 主契约）；截断防第二张表被当数据行
    cut = len(tp_text)
    for m in re.finditer(r"^##", tp_text, flags=re.M):
        cut = m.start()
        break
    main_part = tp_text[:cut]
    header, rows = parse_first_table(main_part)
    warns = []
    if header is None:
        return warns, 0, ""
    try:
        idx_id = [h.strip() for h in header].index("编号")
        idx_intent = [h.strip() for h in header].index("验证意图")
    except ValueError:
        return [{"id": "-", "intent": "-",
                 "category": "解析错", "term": "主表缺少「编号/验证意图」列"}], len(rows), ""
    for cells in rows:
        if len(cells) <= max(idx_id, idx_intent):
            continue
        tid = cells[idx_id].strip()
        intent = cells[idx_intent].strip()
        for cat, term in _hits(intent):
            warns.append({"id": tid, "intent": intent, "category": cat, "term": term})
    import hashlib
    sha = hashlib.sha256(tp_text.encode("utf-8")).hexdigest()[:16]
    return warns, len(rows), sha


def main():
    ap = argparse.ArgumentParser(description="TP 验证意图口袋词表 WARN 预筛（WARN-only）")
    ap.add_argument("--tp-file", required=True)
    ap.add_argument("--report", help="可选：写入 JSON 工件路径")
    args = ap.parse_args()
    from mdtable import read_text
    text = read_text(args.tp_file)
    warns, n_rows, sha = screen(text)
    for w in warns:
        print("WARN: %s 意图命中「%s」（%s；PRD 原词照抄除外，人工判定）"
              % (w["id"], w["term"], CATEGORY_NAME.get(w["category"], w["category"])))
    print("预设词表预筛摘要: rows=%d warnings=%d tp_sha=%s%s"
          % (n_rows, len(warns), sha,
             " report=%s" % args.report if args.report else ""))
    if args.report:
        with open(args.report, "w", encoding="utf-8") as f:
            json.dump({"tool": "screen_intent_words", "tp_file": args.tp_file,
                       "tp_sha": sha, "rows": n_rows,
                       "warnings": warns}, f, ensure_ascii=False, indent=2)
    sys.exit(0)


if __name__ == "__main__":
    main()
