#!/usr/bin/env python3
"""new_session_dir.py — 会话目录生成（命名规范：session-<6位随机数>）。

在工作空间的 file 目录下按规范新建一个会话目录并铺好骨架，输出该目录路径。
流水号取 6 位随机数（000000~999999），与 file 目录下既有同名目录撞号则
重新生成，绝不覆盖既有目录。

为什么需要本脚本：编号必须由脚本的随机数生成器产出，不能由 agent 手写
或凑号——手编数字会让目录名失去唯一性，同目录名互相覆盖、追溯断链。

用法（仓库根目录起，相对路径单命令）：
  python3 .opencode/skills/test-script-lib/scripts/new_session_dir.py \
    --file-dir "file"

  --file-dir    工作空间下的 file 目录（支持字面路径或通配模式，模式由脚本自行展开）
  --print-only  只输出目录名，不创建目录

退出码：0 = 成功；2 = 用法错误（目录不存在 / 多处匹配）
"""
import argparse
import glob
import os
import random
import sys


SKELETON = (
    "user-input",
    "scope",
    "state",
    "output/tp",
    "output/tc",
    "output/reports",
)
NAME_TEMPLATE = "session-{stamp}"


def fail(message):
    print(f"[FAIL] {message}", file=sys.stderr)
    raise SystemExit(2)


def resolve_file_dir(pattern):
    matches = sorted(p for p in glob.glob(pattern) if os.path.isdir(p))
    if not matches:
        fail(f"file 目录不存在: {pattern}")
    if len(matches) > 1:
        fail(f"file 目录匹配多处，请指定其一: {matches}")
    return matches[0]


def pick_serial(file_dir):
    """随机取 6 位流水号；与既有会话目录撞号即重取，绝不覆盖。"""
    while True:
        sno = f"{random.randrange(1_000_000):06d}"
        if not os.path.exists(os.path.join(file_dir, NAME_TEMPLATE.format(stamp=sno))):
            return sno


def display_path(path):
    try:
        relative = os.path.relpath(path, os.getcwd())
    except ValueError:
        return path
    return path if relative.startswith("..") else relative


def main():
    parser = argparse.ArgumentParser(description="生成会话目录 session-<6位随机数>")
    parser.add_argument("--file-dir", required=True, help="工作空间下的 file 目录，支持通配模式")
    parser.add_argument("--print-only", action="store_true", help="只输出目录名，不创建")
    args = parser.parse_args()

    file_dir = resolve_file_dir(args.file_dir)
    stamp = pick_serial(file_dir)
    session_dir = os.path.join(file_dir, NAME_TEMPLATE.format(stamp=stamp))

    if not args.print_only:
        os.makedirs(session_dir)
        for relative in SKELETON:
            os.makedirs(os.path.join(session_dir, relative), exist_ok=True)

    print(display_path(session_dir))


if __name__ == "__main__":
    main()
