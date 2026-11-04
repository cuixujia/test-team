#!/usr/bin/env python3
"""Verify that a validation report still refers to unchanged artifacts/scripts."""
import argparse
import hashlib
import json
import os
import sys


def digest(path):
    h = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", help="validate_delivery.py 输出的 JSON")
    args = parser.parse_args()
    with open(args.report, encoding="utf-8") as stream:
        report = json.load(stream)
    failures = []
    if report.get("schema_version") != 1:
        failures.append("报告 schema_version 必须为 1")
    if not report.get("steps"):
        failures.append("报告中没有校验步骤")
    if not report.get("toolchain"):
        failures.append("报告中没有校验工具链指纹")
    for path, expected in report.get("toolchain", {}).items():
        if not os.path.isfile(path) or digest(path) != expected:
            failures.append(f"校验流水线工具已变化或不存在: {path}")
    for step in report.get("steps", []):
        if step.get("exit_code") != 0:
            failures.append(f"校验步骤未通过: {step.get('label')}")
        for path, expected in step.get("artifacts", {}).items():
            if not os.path.isfile(path) or digest(path) != expected:
                failures.append(f"产物已变化或不存在: {path}")
        for path, expected in step.get("scripts", {}).items():
            if not os.path.isfile(path) or digest(path) != expected:
                failures.append(f"校验脚本已变化或不存在: {path}")
    if report.get("passed") is not True:
        failures.append("报告状态不是全通过")
    for item in failures:
        print(f"[FAIL] {item}")
    if not failures:
        print(f"[PASS] {len(report.get('steps', []))} 个校验步骤均通过，产物和脚本指纹未变")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
