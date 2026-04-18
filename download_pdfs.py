#!/usr/bin/env python3
"""
批量下载 GESP C++ 试卷 PDF（增量模式）

从 gesp_pdfs.json 读取 URL 列表，跳过已下载的文件。
新增 PDF URL 需先更新 gesp_pdfs.json（可通过 gesp_import.py scan 自动完成）。

用法：
    python3 download_pdfs.py              # 增量下载（跳过已有）
    python3 download_pdfs.py --force      # 强制重新下载全部
"""

import os
import json
import urllib.request
import time
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PDF_DIR = os.path.join(BASE_DIR, "pdfs")
CONFIG_PATH = os.path.join(BASE_DIR, "gesp_pdfs.json")


def load_pdf_list():
    """从 gesp_pdfs.json 加载 PDF URL 列表"""
    if not os.path.exists(CONFIG_PATH):
        print(f"错误: 配置文件不存在: {CONFIG_PATH}")
        print("请先运行: python3 gesp_import.py scan")
        sys.exit(1)

    with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
        config = json.load(f)

    return config.get('pdfs', {})


def download_all(skip_existing=True):
    """下载所有 PDF"""
    pdfs = load_pdf_list()
    os.makedirs(PDF_DIR, exist_ok=True)

    total = len(pdfs)
    success = 0
    skipped = 0
    failed = []

    for i, (name, url) in enumerate(sorted(pdfs.items()), 1):
        filepath = os.path.join(PDF_DIR, f"{name}.pdf")

        if skip_existing and os.path.exists(filepath) and os.path.getsize(filepath) > 1000:
            skipped += 1
            continue

        print(f"[{i}/{total}] Downloading: {name}.pdf ...", end=" ", flush=True)
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"
            })
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = resp.read()
                with open(filepath, "wb") as f:
                    f.write(data)
            size_kb = len(data) / 1024
            print(f"OK ({size_kb:.0f}KB)")
            success += 1
        except Exception as e:
            print(f"FAILED: {e}")
            failed.append((name, str(e)))

        time.sleep(0.5)

    print(f"\nDone: {success} downloaded, {skipped} skipped, {len(failed)} failed")
    if failed:
        print(f"Failed ({len(failed)}):")
        for name, err in failed:
            print(f"  - {name}: {err}")

    return len(failed) == 0


if __name__ == "__main__":
    force = '--force' in sys.argv
    download_all(skip_existing=not force)
