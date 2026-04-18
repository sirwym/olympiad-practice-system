#!/usr/bin/env python3
"""
从洛谷题单获取 GESP 编程题面，替换本地 papers/ 中的编程题 content。

数据源：
- 题单列表：https://www.luogu.com.cn/training/551 ~ 558（1-8 级）
- 题面详情：https://www.luogu.com.cn/problem/Bxxxx（HTML 中内嵌 JSON）

洛谷数据包含完整的 LaTeX 公式（$...$），完美适配 KaTeX 渲染，
解决了 PDF 提取中变量/公式丢失的问题。

用法：
    python3 import_luogu_programs.py          # 增量更新（跳过已有洛谷数据的题）
    python3 import_luogu_programs.py --force   # 强制更新所有编程题
    python3 import_luogu_programs.py status    # 查看当前状态
"""

import json
import os
import re
import sys
import time
import unicodedata
from pathlib import Path
from urllib.parse import unquote

import subprocess


def http_get(url: str, timeout: int = 15) -> str:
    """用 curl 发起 HTTP GET 请求，避免 Python urllib 的重定向问题。"""
    result = subprocess.run(
        ["curl", "-s", "-L", "--max-time", str(timeout),
         "-H", f"User-Agent: {HEADERS['User-Agent']}",
         url],
        capture_output=True, text=True, timeout=timeout + 5,
    )
    return result.stdout

BASE_DIR = Path(__file__).parent
PAPERS_DIR = BASE_DIR / "papers"

# 洛谷题单 ID：1级=551, 2级=552, ..., 8级=558
TRAINING_IDS = {level: 550 + level for level in range(1, 9)}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
}

# 请求间隔（秒），避免触发反爬
REQUEST_DELAY = 1.5


def fetch_training_list(training_id: int) -> list[dict]:
    """从洛谷题单页面获取题目列表（pid + title）。"""
    url = f"https://www.luogu.com.cn/training/{training_id}"
    print(f"  📡 获取题单 {url}")
    html = http_get(url)

    match = re.search(
        r'window\._feInjection\s*=\s*JSON\.parse\(decodeURIComponent\("(.*?)"\)\)',
        html,
    )
    if not match:
        print(f"  ❌ 未找到题单数据（可能需要登录或被反爬）")
        return []

    decoded = unquote(match.group(1))
    j = json.loads(decoded)
    training = j["currentData"]["training"]
    problems = training.get("problems", [])

    result = []
    for p in problems:
        prob = p.get("problem", {})
        pid = prob.get("pid", "")
        title = prob.get("title", "")
        if pid:
            result.append({"pid": pid, "title": title})
    return result


def fetch_problem_detail(pid: str) -> dict | None:
    """从洛谷题目页面获取完整题面（description, inputFormat, outputFormat, samples, hint, limits）。"""
    url = f"https://www.luogu.com.cn/problem/{pid}"
    html = http_get(url)

    # 方法1：从 script 标签中的 JSON 提取
    scripts = re.findall(r'<script[^>]*>(.*?)</script>', html, re.DOTALL)
    for s in scripts:
        if '"problem"' in s and '"pid"' in s:
            try:
                j = json.loads(s)
                return j["data"]["problem"]
            except (json.JSONDecodeError, KeyError):
                continue

    # 方法2：从 _feInjection 提取
    match = re.search(
        r'window\._feInjection\s*=\s*JSON\.parse\(decodeURIComponent\("(.*?)"\)\)',
        html,
    )
    if match:
        try:
            decoded = unquote(match.group(1))
            j = json.loads(decoded)
            return j["currentData"]["problem"]
        except (json.JSONDecodeError, KeyError):
            pass

    return None


def parse_gesp_info(title: str) -> dict | None:
    """
    从洛谷题目标题解析 GESP 考次和级别。
    格式：[GESP202303 一级] 长方形面积
    或：[GESP样题 一级] 闰年求和
    """
    m = re.match(r'\[GESP(\d{6})\s+(\S+级)\]\s*(.+)', title)
    if m:
        exam = m.group(1)  # "202303"
        level_str = m.group(2)  # "一级"
        name = m.group(3)
        level_map = {"一级": 1, "二级": 2, "三级": 3, "四级": 4,
                     "五级": 5, "六级": 6, "七级": 7, "八级": 8}
        level = level_map.get(level_str, 0)
        return {"exam": exam, "level": level, "name": name}

    m = re.match(r'\[GESP样题\s+(\S+级)\]\s*(.+)', title)
    if m:
        level_str = m.group(1)
        name = m.group(2)
        level_map = {"一级": 1, "二级": 2, "三级": 3, "四级": 4,
                     "五级": 5, "六级": 6, "七级": 7, "八级": 8}
        level = level_map.get(level_str, 0)
        return {"exam": "sample", "level": level, "name": name}

    return None


def build_program_content(prob: dict, info: dict) -> str:
    """
    将洛谷题目数据构建为 Markdown 格式的编程题 content。
    格式与现有 papers/ 中的编程题保持一致，但使用 **加粗** 替代 ### 标题。
    """
    contenu = prob.get("contenu", {})
    if not contenu:
        # 有些题的数据结构可能不同
        contenu = prob.get("content", {})
        if isinstance(contenu, str):
            contenu = {}

    parts = []

    # 试题名称
    name = info.get("name", "")
    if name:
        parts.append(f"**试题名称：{name}**")
        parts.append("")

    # 时间/内存限制
    limits = prob.get("limits", {})
    time_limits = limits.get("time", [])
    memory_limits = limits.get("memory", [])
    if time_limits and memory_limits:
        time_ms = time_limits[0]
        memory_kb = memory_limits[0]
        time_s = time_ms / 1000 if time_ms >= 1000 else time_ms
        memory_mb = memory_kb / 1024
        parts.append(f"> 时间限制：{time_s:.1f} s | 内存限制：{memory_mb:.0f}.0 MB")
        parts.append("")

    # 题目描述
    description = contenu.get("description", "")
    if description:
        parts.append("**题目描述**")
        parts.append("")
        parts.append(description)
        parts.append("")

    # 输入格式
    format_i = contenu.get("formatI", "")
    if format_i:
        parts.append("**输入格式**")
        parts.append("")
        parts.append(format_i)
        parts.append("")

    # 输出格式
    format_o = contenu.get("formatO", "")
    if format_o:
        parts.append("**输出格式**")
        parts.append("")
        parts.append(format_o)
        parts.append("")

    # 样例
    samples = prob.get("samples", [])
    for i, sample in enumerate(samples):
        if isinstance(sample, list) and len(sample) >= 2:
            input_data = sample[0]
            output_data = sample[1]
            parts.append(f"**样例输入 #{i+1}**")
            parts.append("```")
            parts.append(input_data)
            parts.append("```")
            parts.append("")
            parts.append(f"**样例输出 #{i+1}**")
            parts.append("```")
            parts.append(output_data)
            parts.append("```")
            parts.append("")

    # 提示/数据范围
    hint = contenu.get("hint", "")
    if hint:
        parts.append("**说明/提示**")
        parts.append("")
        parts.append(hint)
        parts.append("")

    content = "\n".join(parts).strip()
    return content


def normalize_text(text: str) -> str:
    """Unicode 归一化 + 去除空格，用于模糊匹配。
    
    PDF 提取的文本中常有 Unicode 兼容字符：
    - ⼩(U+F329) → 小(U+5C0F)
    - ⽂(U+F302) → 文(U+6587)
    - ⽇(U+F311) → 日(U+65E5)
    NFKC 归一化可将这些兼容字符转换为常用字符。
    """
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r'\s+', '', text)  # 去除所有空格
    return text


def find_local_paper(exam: str, level: int) -> Path | None:
    """
    根据 GESP 考次和级别找到本地对应的试卷目录。
    exam 格式：202303, 202306, ..., sample
    """
    if exam == "sample":
        return None  # 样题没有对应试卷

    # 格式：2023-03-gesp-1
    year = exam[:4]
    month = exam[4:6]
    slug = f"{year}-{month}-gesp-{level}"

    paper_dir = PAPERS_DIR / slug
    if paper_dir.exists():
        return paper_dir

    return None


def match_program_question(paper_dir: Path, name: str) -> dict | None:
    """
    在试卷 JSON 中找到匹配的编程题（按名称模糊匹配）。
    """
    json_file = paper_dir / "index.json"
    if not json_file.exists():
        return None

    with open(json_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    programs = [q for q in data["questions"] if q.get("type") == "program"]
    if not programs:
        return None

    # 尝试精确匹配试题名称
    for q in programs:
        content = q.get("content", "")
        # 提取 content 中的试题名称
        m = re.search(r'\*?\*?试题名称[：:]\s*(.+?)\*?\*?\n', content)
        if m:
            q_name = m.group(1).strip("* \n")
            if q_name == name:
                return q

    # 模糊匹配：名称包含关系
    for q in programs:
        content = q.get("content", "")
        m = re.search(r'\*?\*?试题名称[：:]\s*(.+?)\*?\*?\n', content)
        if m:
            q_name = m.group(1).strip("* \n")
            # 去掉常见前缀再比较
            clean_name = name.replace("小杨的", "").replace("小明的", "")
            clean_q = q_name.replace("小杨的", "").replace("小明的", "")
            if clean_name in clean_q or clean_q in clean_name:
                return q

    # 最后手段：按顺序匹配（同一级别的编程题通常按顺序对应）
    # 但这不可靠，只在有1-2道编程题时使用
    if len(programs) <= 2:
        return None  # 不用顺序匹配，避免错误

    return None


def has_luogu_content(content: str) -> bool:
    """检查 content 是否已经包含洛谷数据（通过 LaTeX 公式判断）。"""
    return bool(re.search(r'\$[^$]+\$', content))


def update_program_content(paper_dir: Path, question_id: int, new_content: str) -> bool:
    """更新试卷 JSON 中指定编程题的 content。"""
    json_file = paper_dir / "index.json"
    with open(json_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    for q in data["questions"]:
        if q.get("type") == "program" and q.get("id") == question_id:
            q["content"] = new_content
            with open(json_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return True

    return False


def run_status():
    """查看当前编程题数据状态。"""
    total = 0
    with_latex = 0
    without_latex = 0
    with_sample = 0
    without_sample = 0

    for paper_dir in sorted(PAPERS_DIR.iterdir()):
        if not paper_dir.is_dir():
            continue
        json_file = paper_dir / "index.json"
        if not json_file.exists():
            continue

        with open(json_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        if data.get("category") != "GESP":
            continue

        for q in data["questions"]:
            if q.get("type") != "program":
                continue
            total += 1
            content = q.get("content", "")

            if has_luogu_content(content):
                with_latex += 1
            else:
                without_latex += 1

            if "样例" in content:
                with_sample += 1
            else:
                without_sample += 1

    print(f"GESP 编程题状态：")
    print(f"  总计：{total} 道")
    print(f"  含 LaTeX 公式：{with_latex} 道 ✅")
    print(f"  缺 LaTeX 公式：{without_latex} 道 ❌（需从洛谷更新）")
    print(f"  含样例：{with_sample} 道")
    print(f"  缺样例：{without_sample} 道")


def run_import(force: bool = False):
    """从洛谷题单获取 GESP 编程题面并更新本地数据。"""
    print("🚀 开始从洛谷获取 GESP 编程题面...")

    # Step 1: 获取所有题单的题目列表
    all_luogu_problems = []  # [(pid, title, level, info)]
    for level in range(1, 9):
        tid = TRAINING_IDS[level]
        problems = fetch_training_list(tid)
        for p in problems:
            info = parse_gesp_info(p["title"])
            if info:
                all_luogu_problems.append((p["pid"], p["title"], level, info))
        time.sleep(0.5)

    print(f"\n📋 洛谷题单共 {len(all_luogu_problems)} 道编程题（1-8 级）")

    # Step 2: 逐一获取题面并匹配本地试卷
    updated = 0
    skipped = 0
    failed = 0
    no_match = 0

    for i, (pid, title, level, info) in enumerate(all_luogu_problems):
        if info["exam"] == "sample":
            print(f"  ⏭️  [{i+1}/{len(all_luogu_problems)}] {pid} 样题，跳过")
            skipped += 1
            continue

        # 找本地试卷
        paper_dir = find_local_paper(info["exam"], info["level"])
        if not paper_dir:
            # 可能该级别没有本地试卷
            print(f"  ⏭️  [{i+1}/{len(all_luogu_problems)}] {pid} {title} → 无本地试卷")
            skipped += 1
            continue

        # 读取本地 JSON，找匹配的编程题
        json_file = paper_dir / "index.json"
        with open(json_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        programs = [q for q in data["questions"] if q.get("type") == "program"]
        matched_q = None

        # 按名称匹配（使用 NFKC 归一化处理 PDF 兼容字符）
        norm_luogu_name = normalize_text(info["name"])
        for q in programs:
            content = q.get("content", "")
            m = re.search(r'\*?\*?试题名称[：:]\s*(.+?)\*?\*?\n', content)
            if m:
                q_name = m.group(1).strip("* \n")
                norm_q_name = normalize_text(q_name)
                # 精确匹配（归一化后）
                if norm_q_name == norm_luogu_name:
                    matched_q = q
                    break
                # 模糊匹配（归一化后）
                clean_name = norm_luogu_name.replace("小杨的", "").replace("小明的", "")
                clean_q = norm_q_name.replace("小杨的", "").replace("小明的", "")
                if clean_name == clean_q or (len(clean_name) > 2 and clean_name in clean_q) or (len(clean_q) > 2 and clean_q in clean_name):
                    matched_q = q
                    break

        # 如果名称匹配失败，尝试按顺序匹配（同级别编程题数量吻合时）
        if not matched_q:
            # 检查该级别洛谷题数 == 本地编程题数，且索引对应
            level_luogu_count = sum(1 for _, _, _, inf in all_luogu_problems
                                    if inf["exam"] == info["exam"] and inf["level"] == info["level"])
            level_luogu_index = sum(1 for _, _, _, inf in all_luogu_problems[:i+1]
                                    if inf["exam"] == info["exam"] and inf["level"] == info["level"]) - 1
            if level_luogu_count == len(programs) and 0 <= level_luogu_index < len(programs):
                matched_q = programs[level_luogu_index]
                print(f"  🔄 [{i+1}/{len(all_luogu_problems)}] {pid} {title} → 按顺序匹配 q{matched_q['id']}")

        if not matched_q:
            print(f"  ⚠️  [{i+1}/{len(all_luogu_problems)}] {pid} {title} → 未找到匹配的编程题")
            no_match += 1
            continue

        # 检查是否已有 LaTeX 内容（增量模式）
        if not force and has_luogu_content(matched_q.get("content", "")):
            print(f"  ✅ [{i+1}/{len(all_luogu_problems)}] {pid} {title} → 已有洛谷数据，跳过")
            skipped += 1
            continue

        # 获取洛谷题面
        print(f"  📡 [{i+1}/{len(all_luogu_problems)}] 获取 {pid} {title}...")
        prob = fetch_problem_detail(pid)

        if not prob:
            print(f"  ❌ 获取失败：{pid}")
            failed += 1
            continue

        # 构建新 content
        new_content = build_program_content(prob, info)

        # 更新 JSON
        if update_program_content(paper_dir, matched_q["id"], new_content):
            print(f"  ✅ 更新成功：{paper_dir.name} q{matched_q['id']}")
            updated += 1
        else:
            print(f"  ❌ 更新失败：{paper_dir.name} q{matched_q['id']}")
            failed += 1

        # 请求间隔
        time.sleep(REQUEST_DELAY)

    print(f"\n{'='*50}")
    print(f"📈 导入完成：")
    print(f"  更新：{updated} 道")
    print(f"  跳过：{skipped} 道")
    print(f"  未匹配：{no_match} 道")
    print(f"  失败：{failed} 道")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd == "status":
            run_status()
        elif cmd == "--force":
            run_import(force=True)
        else:
            print(f"未知参数：{cmd}")
            print("用法：python3 import_luogu_programs.py [status|--force]")
    else:
        run_import(force=False)
