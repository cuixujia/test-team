#!/usr/bin/env python3
"""new_session_dir.py — 会话目录生成（命名规范：session-<项目id>-<6位随机数>）。

在运行时 file 目录下按规范新建一个会话目录并铺好骨架，输出该目录路径。
流水号取 6 位随机数（000000~999999），与 worker/file/ 下既有目录撞号则
重新生成，绝不覆盖既有目录。

为什么需要本脚本：编号必须由脚本的随机数生成器产出，不能由 agent 手写
或凑号——手编数字会让目录名失去唯一性，同目录名互相覆盖、追溯断链。

用法（仓库根目录起，相对路径单命令）：
  python3 .opencode/skills/test-script-lib/scripts/new_session_dir.py \
    --file-dir "workspace/runtime_*/file"

  --file-dir    运行时 file 目录（支持字面路径或通配模式，模式由脚本自行展开）
  --project-id  项目id（默认从上级目录 runtime_<projectId> 取后缀）
  --print-only  只输出目录名，不创建目录

退出码：0 = 成功；2 = 用法错误（目录不存在 / 多处匹配 / 项目id 推不出）
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
NAME_TEMPLATE = "session-{project_id}-{stamp}"


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


def derive_project_id(file_dir, override):
    if override:
        return override
    parent = os.path.basename(os.path.normpath(os.path.dirname(os.path.abspath(file_dir))))
    if parent.startswith("runtime_"):
        project_id = parent[len("runtime_"):]
        if project_id:
            return project_id
    fail(f"无法从上级目录推导项目id（期望 runtime_<项目id>）: {file_dir}")


def pick_serial(file_dir, project_id):
    while True:
        sno = f"{random.randrange(1_000_000):06d}"
        if not os.path.exists(os.path.join(file_dir, NAME_TEMPLATE.format(project_id=project_id, stamp=sno))):
            return sno


def display_path(path):
    try:
        relative = os.path.relpath(path, os.getcwd())
    except ValueError:
        return path
    return path if relative.startswith("..") else relative


def main():
    parser = argparse.ArgumentParser(description="生成会话目录 session-<项目id>-<6位随机数>")
    parser.add_argument("--file-dir", required=True, help="运行时 file 目录，支持通配模式")
    parser.add_argument("--project-id", default="", help="项目id，默认取 runtime_<项目id> 后缀")
    parser.add_argument("--print-only", action="store_true", help="只输出目录名，不创建")
    args = parser.parse_args()

    file_dir = resolve_file_dir(args.file_dir)
    project_id = derive_project_id(file_dir, args.project_id)
    stamp = pick_serial(file_dir, project_id)
    session_dir = os.path.join(file_dir, NAME_TEMPLATE.format(project_id=project_id, stamp=stamp))

    if not args.print_only:
        os.makedirs(session_dir)
        for relative in SKELETON:
            os.makedirs(os.path.join(session_dir, relative), exist_ok=True)

    print(display_path(session_dir))


if __name__ == "__main__":
    main()
