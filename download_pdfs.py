#!/usr/bin/env python3
"""批量下载GESP C++各级别试卷PDF"""

import os
import urllib.request
import time
import sys

# 所有GESP C++试卷PDF链接（2023年3月 ~ 2026年3月）
PDFS = {
    # 2026年3月 (1-8级)
    "2026-03-gesp-cpp-1": "https://gesp.ccf.org.cn/101/attach/1734124574343200.pdf",
    "2026-03-gesp-cpp-2": "https://gesp.ccf.org.cn/101/attach/1734124601606176.pdf",
    "2026-03-gesp-cpp-3": "https://gesp.ccf.org.cn/101/attach/1734775052173344.pdf",
    "2026-03-gesp-cpp-4": "https://gesp.ccf.org.cn/101/attach/1734124643549216.pdf",
    "2026-03-gesp-cpp-5": "https://gesp.ccf.org.cn/101/attach/1734457367199776.pdf",
    "2026-03-gesp-cpp-6": "https://gesp.ccf.org.cn/101/attach/1738426015547424.pdf",
    "2026-03-gesp-cpp-7": "https://gesp.ccf.org.cn/101/attach/1734447340716064.pdf",
    "2026-03-gesp-cpp-8": "https://gesp.ccf.org.cn/101/attach/1734124729532448.pdf",

    # 2025年12月 (1-8级)
    "2025-12-gesp-cpp-1": "https://gesp.ccf.org.cn/101/attach/1723012510384160.pdf",
    "2025-12-gesp-cpp-2": "https://gesp.ccf.org.cn/101/attach/1723012535549984.pdf",
    "2025-12-gesp-cpp-3": "https://gesp.ccf.org.cn/101/attach/1723012369874976.pdf",
    "2025-12-gesp-cpp-4": "https://gesp.ccf.org.cn/101/attach/1723012925620256.pdf",
    "2025-12-gesp-cpp-5": "https://gesp.ccf.org.cn/101/attach/1727912539586592.pdf",
    "2025-12-gesp-cpp-6": "https://gesp.ccf.org.cn/101/attach/1727912589918240.pdf",
    "2025-12-gesp-cpp-7": "https://gesp.ccf.org.cn/101/attach/1723013022089248.pdf",
    "2025-12-gesp-cpp-8": "https://gesp.ccf.org.cn/101/attach/1723013038866464.pdf",

    # 2025年9月 (1-8级)
    "2025-09-gesp-cpp-1": "https://gesp.ccf.org.cn/101/attach/1703972987469856.pdf",
    "2025-09-gesp-cpp-2": "https://gesp.ccf.org.cn/101/attach/1703973006344224.pdf",
    "2025-09-gesp-cpp-3": "https://gesp.ccf.org.cn/101/attach/1703975921385504.pdf",
    "2025-09-gesp-cpp-4": "https://gesp.ccf.org.cn/101/attach/1703973044092960.pdf",
    "2025-09-gesp-cpp-5": "https://gesp.ccf.org.cn/101/attach/1704013600915488.pdf",
    "2025-09-gesp-cpp-6": "https://gesp.ccf.org.cn/101/attach/1703973079744544.pdf",
    "2025-09-gesp-cpp-7": "https://gesp.ccf.org.cn/101/attach/1703973098618912.pdf",
    "2025-09-gesp-cpp-8": "https://gesp.ccf.org.cn/101/attach/1703973115396128.pdf",

    # 2025年6月 (1-8级)
    "2025-06-gesp-cpp-1": "https://gesp.ccf.org.cn/101/attach/1687195805024288.pdf",
    "2025-06-gesp-cpp-2": "https://gesp.ccf.org.cn/101/attach/1687195838578720.pdf",
    "2025-06-gesp-cpp-3": "https://gesp.ccf.org.cn/101/attach/1699464809021472.pdf",
    "2025-06-gesp-cpp-4": "https://gesp.ccf.org.cn/101/attach/1687195991670816.pdf",
    "2025-06-gesp-cpp-5": "https://gesp.ccf.org.cn/101/attach/1697487540715552.pdf",
    "2025-06-gesp-cpp-6": "https://gesp.ccf.org.cn/101/attach/1687196042002464.pdf",
    "2025-06-gesp-cpp-7": "https://gesp.ccf.org.cn/101/attach/1687196062973984.pdf",
    "2025-06-gesp-cpp-8": "https://gesp.ccf.org.cn/101/attach/1687196088139808.pdf",

    # 2025年3月 (1-8级)
    "2025-03-gesp-cpp-1": "https://gesp.ccf.org.cn/101/attach/1669256632598560.pdf",
    "2025-03-gesp-cpp-2": "https://gesp.ccf.org.cn/101/attach/1669256796176416.pdf",
    "2025-03-gesp-cpp-3": "https://gesp.ccf.org.cn/101/attach/1670868226801696.pdf",
    "2025-03-gesp-cpp-4": "https://gesp.ccf.org.cn/101/attach/1669256863285280.pdf",
    "2025-03-gesp-cpp-5": "https://gesp.ccf.org.cn/101/attach/1684804529553440.pdf",
    "2025-03-gesp-cpp-6": "https://gesp.ccf.org.cn/101/attach/1669256961851424.pdf",
    "2025-03-gesp-cpp-7": "https://gesp.ccf.org.cn/101/attach/1669256997503008.pdf",
    "2025-03-gesp-cpp-8": "https://gesp.ccf.org.cn/101/attach/1669257026863136.pdf",

    # 2024年12月 (1-8级)
    "2024-12-gesp-cpp-1": "https://gesp.ccf.org.cn/101/attach/1652740757389344.pdf",
    "2024-12-gesp-cpp-2": "https://gesp.ccf.org.cn/101/attach/1650239656165408.pdf",
    "2024-12-gesp-cpp-3": "https://gesp.ccf.org.cn/101/attach/1650388837072928.pdf",
    "2024-12-gesp-cpp-4": "https://gesp.ccf.org.cn/101/attach/1650239710691360.pdf",
    "2024-12-gesp-cpp-5": "https://gesp.ccf.org.cn/101/attach/1733577765027904.pdf",
    "2024-12-gesp-cpp-6": "https://gesp.ccf.org.cn/101/attach/1733580036243488.pdf",
    "2024-12-gesp-cpp-7": "https://gesp.ccf.org.cn/101/attach/1650239779897376.pdf",
    "2024-12-gesp-cpp-8": "https://gesp.ccf.org.cn/101/attach/1650239836520480.pdf",

    # 2024年9月 (1-8级)
    "2024-09-gesp-cpp-1": "https://gesp.ccf.org.cn/101/attach/1633835940839456.pdf",
    "2024-09-gesp-cpp-2": "https://gesp.ccf.org.cn/101/attach/1633836163137568.pdf",
    "2024-09-gesp-cpp-3": "https://gesp.ccf.org.cn/101/attach/1644702761746464.pdf",
    "2024-09-gesp-cpp-4": "https://gesp.ccf.org.cn/cms/api/news/downloadFile?id=1634204225896480",
    "2024-09-gesp-cpp-5": "https://gesp.ccf.org.cn/101/attach/1633836261703712.pdf",
    "2024-09-gesp-cpp-6": "https://gesp.ccf.org.cn/101/attach/1633836295258144.pdf",
    "2024-09-gesp-cpp-7": "https://gesp.ccf.org.cn/101/attach/1633836324618272.pdf",
    "2024-09-gesp-cpp-8": "https://gesp.ccf.org.cn/101/attach/1633836360269856.pdf",

    # 2024年6月 (1-8级)
    "2024-06-gesp-cpp-1": "https://gesp.ccf.org.cn/101/attach/1621071329493024.pdf",
    "2024-06-gesp-cpp-2": "https://gesp.ccf.org.cn/101/attach/1621071434350624.pdf",
    "2024-06-gesp-cpp-3": "https://gesp.ccf.org.cn/101/attach/1621071490973728.pdf",
    "2024-06-gesp-cpp-4": "https://gesp.ccf.org.cn/101/attach/1621071528722464.pdf",
    "2024-06-gesp-cpp-5": "https://gesp.ccf.org.cn/101/attach/1621071558082592.pdf",
    "2024-06-gesp-cpp-6": "https://gesp.ccf.org.cn/101/attach/1621071589539872.pdf",
    "2024-06-gesp-cpp-7": "https://gesp.ccf.org.cn/101/attach/1621071620997152.pdf",
    "2024-06-gesp-cpp-8": "https://gesp.ccf.org.cn/101/attach/1621071654551584.pdf",

    # 2024年3月 (1-8级)
    "2024-03-gesp-cpp-1": "https://gesp.ccf.org.cn/101/attach/1602047004639264.pdf",
    "2024-03-gesp-cpp-2": "https://gesp.ccf.org.cn/101/attach/1613037396033568.pdf",
    "2024-03-gesp-cpp-3": "https://gesp.ccf.org.cn/101/attach/1602047101108256.pdf",
    "2024-03-gesp-cpp-4": "https://gesp.ccf.org.cn/101/attach/1602047134662688.pdf",
    "2024-03-gesp-cpp-5": "https://gesp.ccf.org.cn/101/attach/1602047172411424.pdf",
    "2024-03-gesp-cpp-6": "https://gesp.ccf.org.cn/101/attach/1602047203868704.pdf",
    "2024-03-gesp-cpp-7": "https://gesp.ccf.org.cn/101/attach/1602047231131684.pdf",
    "2024-03-gesp-cpp-8": "https://gesp.ccf.org.cn/101/attach/1602047270977568.pdf",

    # 2023年12月 (1-8级)
    "2023-12-gesp-cpp-1": "https://gesp.ccf.org.cn/101/attach/1585703601307680.pdf",
    "2023-12-gesp-cpp-2": "https://gesp.ccf.org.cn/101/attach/1601261860290592.pdf",
    "2023-12-gesp-cpp-3": "https://gesp.ccf.org.cn/101/attach/1584917876047904.pdf",
    "2023-12-gesp-cpp-4": "https://gesp.ccf.org.cn/101/attach/1601236293910560.pdf",
    "2023-12-gesp-cpp-5": "https://gesp.ccf.org.cn/101/attach/1599969567965216.pdf",
    "2023-12-gesp-cpp-6": "https://gesp.ccf.org.cn/101/attach/1584918408724512.pdf",
    "2023-12-gesp-cpp-7": "https://gesp.ccf.org.cn/101/attach/1584918444376096.pdf",
    "2023-12-gesp-cpp-8": "https://gesp.ccf.org.cn/101/attach/1584918480027680.pdf",

    # 2023年9月 (1-6级)
    "2023-09-gesp-cpp-1": "https://gesp.ccf.org.cn/101/attach/1570611155435552.pdf",
    "2023-09-gesp-cpp-2": "https://gesp.ccf.org.cn/101/attach/1570611195281440.pdf",
    "2023-09-gesp-cpp-3": "https://gesp.ccf.org.cn/101/attach/1570611239321632.pdf",
    "2023-09-gesp-cpp-4": "https://gesp.ccf.org.cn/101/attach/1570611272876064.pdf",
    "2023-09-gesp-cpp-5": "https://gesp.ccf.org.cn/101/attach/1570611325304864.pdf",
    "2023-09-gesp-cpp-6": "https://gesp.ccf.org.cn/101/attach/1718304913752096.pdf",

    # 2023年6月 (1-4级)
    "2023-06-gesp-cpp-1": "https://gesp.ccf.org.cn/101/attach/1553039792013344.pdf",
    "2023-06-gesp-cpp-2": "https://gesp.ccf.org.cn/101/attach/1553039846539296.pdf",
    "2023-06-gesp-cpp-3": "https://gesp.ccf.org.cn/101/attach/1553039911551008.pdf",
    "2023-06-gesp-cpp-4": "https://gesp.ccf.org.cn/101/attach/1553241699516448.pdf",

    # 2023年3月 (1-2级)
    "2023-03-gesp-cpp-1": "https://gesp.ccf.org.cn/101/attach/1536716611518496.pdf",
    "2023-03-gesp-cpp-2": "https://gesp.ccf.org.cn/cms/api/news/downloadFile?id=1725198644543520",
}

PDF_DIR = os.path.join(os.path.dirname(__file__), "pdfs")

def download_all(skip_existing=True):
    os.makedirs(PDF_DIR, exist_ok=True)
    total = len(PDFS)
    success = 0
    failed = []

    for i, (name, url) in enumerate(PDFS.items(), 1):
        filepath = os.path.join(PDF_DIR, f"{name}.pdf")
        if skip_existing and os.path.exists(filepath) and os.path.getsize(filepath) > 1000:
            print(f"[{i}/{total}] SKIP (exists): {name}.pdf")
            success += 1
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

        time.sleep(0.5)  # 礼貌性延迟

    print(f"\nDone: {success}/{total} succeeded")
    if failed:
        print(f"Failed ({len(failed)}):")
        for name, err in failed:
            print(f"  - {name}: {err}")

if __name__ == "__main__":
    download_all()
