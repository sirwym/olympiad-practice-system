#!/usr/bin/env python3
"""
GESP 试卷数据统一导入工具

支持子命令：
    scan      扫描 GESP 官网，发现新增试卷 PDF 链接，更新 gesp_pdfs.json
    download  增量下载缺失的 PDF 文件
    parse     解析客观题（选择题+判断题），生成 JSON（跳过已有）
    programs  追加编程题到已有 JSON（跳过已有 program 类型）
    judge     修复判断题答案（渲染截图 + 多模态识别）
    all       一键全流程（download → parse → programs → judge）
    status    查看当前数据完整性状态

用法：
    python3 gesp_import.py status
    python3 gesp_import.py scan
    python3 gesp_import.py all
    python3 gesp_import.py download --force
"""

import os
import re
import sys
import json
import glob
import time
import shutil
import argparse
import subprocess

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PAPERS_DIR = os.path.join(BASE_DIR, "papers")
PDF_DIR = os.path.join(BASE_DIR, "pdfs")
CONFIG_PATH = os.path.join(BASE_DIR, "gesp_pdfs.json")
GESP_LIST_URL = "https://gesp.ccf.org.cn/101/1010/index.html"

# ============================================================
# 工具函数
# ============================================================

def parse_paper_slug(slug):
    """从文件夹名解析 year, month, level"""
    m = re.match(r"(\d{4})-(\d{2})-gesp-(\d+)", slug)
    if not m:
        return None
    return {"year": int(m.group(1)), "month": int(m.group(2)), "level": int(m.group(3))}


def parse_pdf_filename(filename):
    """从 PDF 文件名解析 year, month, level"""
    m = re.match(r"(\d{4})-(\d{2})-gesp-cpp-(\d+)\.pdf", filename)
    if not m:
        return None
    return {"year": int(m.group(1)), "month": int(m.group(2)), "level": int(m.group(3))}


def load_config():
    """加载 gesp_pdfs.json 配置"""
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {"_comment": "", "_source": GESP_LIST_URL, "pdfs": {}}


def save_config(config):
    """保存 gesp_pdfs.json 配置"""
    with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
        f.write('\n')


def get_gesp_papers():
    """获取所有 GESP 试卷信息"""
    papers = []
    if not os.path.isdir(PAPERS_DIR):
        return papers

    for slug in sorted(os.listdir(PAPERS_DIR)):
        info = parse_paper_slug(slug)
        if not info:
            continue
        json_path = os.path.join(PAPERS_DIR, slug, "index.json")
        if not os.path.exists(json_path):
            continue
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        papers.append({
            'slug': slug,
            'info': info,
            'json_path': json_path,
            'data': data,
        })
    return papers


def get_gesp_pdfs():
    """获取所有已下载的 GESP PDF 文件列表"""
    if not os.path.isdir(PDF_DIR):
        return []
    return sorted([f for f in os.listdir(PDF_DIR)
                   if f.endswith(".pdf") and "gesp-cpp" in f])


def run_script(script_name, args=None):
    """运行同目录下的其他 Python 脚本"""
    script_path = os.path.join(BASE_DIR, script_name)
    if not os.path.exists(script_path):
        print(f"  ⚠️ 脚本不存在: {script_name}")
        return False

    cmd = [sys.executable, script_path]
    if args:
        cmd.extend(args)

    result = subprocess.run(cmd, cwd=BASE_DIR)
    return result.returncode == 0


# ============================================================
# scan: 扫描官网发现新增
# ============================================================

def cmd_scan(args):
    """扫描 GESP 官网，发现新增试卷 PDF 链接"""
    print("🌐 扫描 GESP 官网...")
    print(f"   列表页: {GESP_LIST_URL}")
    print()

    config = load_config()
    existing_pdfs = config.get('pdfs', {})
    existing_keys = set(existing_pdfs.keys())

    print(f"📄 当前 gesp_pdfs.json 中有 {len(existing_keys)} 条记录")
    print()
    print("⚠️  官网页面需要浏览器交互才能获取完整 PDF 列表。")
    print("   建议通过 AI 浏览器访问以下子页面获取 PDF 链接：")
    print()

    # 列出已知的考试日期和子页面
    known_exams = [
        ("2026年3月", "https://gesp.ccf.org.cn/101/1010/10269.html"),
        ("2025年12月", "https://gesp.ccf.org.cn/101/1010/10242.html"),
        ("2025年9月", "https://gesp.ccf.org.cn/101/1010/10229.html"),
        ("2025年6月", "https://gesp.ccf.org.cn/101/1010/10217.html"),
        ("2025年3月", "https://gesp.ccf.org.cn/101/1010/10200.html"),
        ("2024年12月", "https://gesp.ccf.org.cn/101/1010/10178.html"),
        ("2024年9月", "https://gesp.ccf.org.cn/101/1010/10166.html"),
        ("2024年6月", "https://gesp.ccf.org.cn/101/1010/10147.html"),
        ("2024年3月", "https://gesp.ccf.org.cn/101/1010/10134.html"),
        ("2023年12月", "https://gesp.ccf.org.cn/101/1010/10119.html"),
    ]

    # 检测哪些考试的 C++ PDF 已全部收集
    for exam_name, url in known_exams:
        # 从考试名称推断年份月份
        m = re.match(r"(\d{4})年(\d+)月", exam_name)
        if m:
            year, month = m.group(1), m.group(2).zfill(2)
            # 检查该考试的 C++ 1-8 级 PDF 是否都有
            expected_levels = 8
            # 早期考试级别不全
            if year == "2023" and month == "03":
                expected_levels = 2
            elif year == "2023" and month == "06":
                expected_levels = 4
            elif year == "2023" and month == "09":
                expected_levels = 6

            found = sum(1 for lv in range(1, expected_levels + 1)
                       if f"{year}-{month}-gesp-cpp-{lv}" in existing_keys)
            status = f"✓ {found}/{expected_levels}" if found == expected_levels else f"✗ {found}/{expected_levels}"
        else:
            status = "?"

        print(f"   {exam_name}: {status}  {url}")

    print()
    print("如需添加新 PDF，请：")
    print("  1. AI 访问子页面，提取 C++ 各级 PDF 链接")
    print("  2. 更新 gesp_pdfs.json，添加新条目")
    print("  3. 运行: python3 gesp_import.py download")


# ============================================================
# download: 增量下载
# ============================================================

def cmd_download(args):
    """增量下载缺失的 PDF 文件"""
    print("📥 检查需要下载的 PDF...")
    print()

    # 检查本地 PDF vs 配置中的 PDF
    config = load_config()
    pdf_list = config.get('pdfs', {})
    existing_files = set(get_gesp_pdfs())

    missing = []
    for name, url in pdf_list.items():
        pdf_filename = f"{name}.pdf"
        pdf_path = os.path.join(PDF_DIR, pdf_filename)
        if not os.path.exists(pdf_path) or os.path.getsize(pdf_path) < 1000:
            missing.append((name, url))

    if not missing:
        print("✅ 所有配置中的 PDF 均已下载")
        return

    print(f"发现 {len(missing)} 个缺失的 PDF：")
    for name, _ in missing:
        print(f"  - {name}.pdf")
    print()

    # 调用 download_pdfs.py 下载
    print("开始下载...")
    force_arg = ['--force'] if args.force else []
    run_script('download_pdfs.py', force_arg)


# ============================================================
# parse: 解析客观题
# ============================================================

def cmd_parse(args):
    """解析客观题，生成 JSON（增量，跳过已有）"""
    print("📝 检查需要解析的试卷...")
    print()

    existing_papers = {p['slug'] for p in get_gesp_papers()}
    pdf_files = get_gesp_pdfs()

    missing = []
    for pdf_file in pdf_files:
        info = parse_pdf_filename(pdf_file)
        if not info:
            continue
        slug = f"{info['year']}-{str(info['month']).zfill(2)}-gesp-{info['level']}"
        if slug not in existing_papers:
            missing.append((pdf_file, slug))

    if not missing:
        print("✅ 所有 PDF 均已解析为 JSON")
        return

    print(f"发现 {len(missing)} 份未解析的 PDF：")
    for pdf_file, slug in missing:
        print(f"  - {pdf_file} → {slug}/")
    print()

    print("开始解析...")
    run_script('pdf_to_json.py')


# ============================================================
# programs: 追加编程题
# ============================================================

def cmd_programs(args):
    """追加编程题到已有 JSON"""
    print("💻 检查需要追加编程题的试卷...")
    print()

    papers = get_gesp_papers()
    needs_program = []

    for paper in papers:
        has_program = any(q.get('type') == 'program' for q in paper['data'].get('questions', []))
        if not has_program:
            needs_program.append(paper['slug'])

    if not needs_program:
        print("✅ 所有试卷均已包含编程题")
        return

    print(f"发现 {len(needs_program)} 份试卷缺少编程题：")
    for slug in needs_program:
        print(f"  - {slug}")
    print()

    print("开始从洛谷导入编程题面...")
    force_args = ['--force'] if args.force else []
    run_script('import_luogu_programs.py', force_args)


# ============================================================
# judge: 修复判断题
# ============================================================

def cmd_judge(args):
    """修复判断题答案"""
    print("🔍 检查判断题答案状态...")
    print()

    run_script('fix_gesp_judge.py', ['status', '-v'])
    print()
    print("如需修复，请执行：")
    print("  1. python3 fix_gesp_judge.py render     # 渲染截图")
    print("  2. 用多模态模型识别 √/× 答案")
    print("  3. python3 fix_gesp_judge.py apply --file answers.json")


# ============================================================
# all: 一键全流程
# ============================================================

def cmd_all(args):
    """一键全流程（download → parse → programs → judge）"""
    print("🚀 GESP 数据全流程更新")
    print("=" * 60)

    steps = [
        ("📥 下载 PDF", cmd_download, args),
        ("📝 解析客观题", cmd_parse, args),
        ("💻 追加编程题", cmd_programs, args),
        ("🔍 检查判断题", cmd_judge, args),
    ]

    for i, (name, func, func_args) in enumerate(steps, 1):
        print(f"\n{'='*60}")
        print(f"步骤 {i}/{len(steps)}: {name}")
        print(f"{'='*60}")
        func(func_args)
        print()

    print("🎉 全流程完成！")


# ============================================================
# status: 查看完整性
# ============================================================

def cmd_status(args):
    """查看当前数据完整性状态"""
    print("📊 GESP 数据完整性状态")
    print("=" * 60)

    # 1. PDF 文件统计
    pdf_files = get_gesp_pdfs()
    config = load_config()
    config_pdfs = config.get('pdfs', {})

    print(f"\n📥 PDF 文件:")
    print(f"   已下载: {len(pdf_files)} 个")
    print(f"   配置记录: {len(config_pdfs)} 条")

    # 检查缺失的 PDF
    missing_pdfs = []
    for name in config_pdfs:
        if f"{name}.pdf" not in pdf_files:
            missing_pdfs.append(name)
    if missing_pdfs:
        print(f"   ⚠️ 缺失下载: {len(missing_pdfs)} 个")
        for name in missing_pdfs[:5]:
            print(f"      - {name}.pdf")
        if len(missing_pdfs) > 5:
            print(f"      ... 还有 {len(missing_pdfs) - 5} 个")

    # 2. JSON 试卷统计
    papers = get_gesp_papers()
    total_papers = len(papers)

    # 按状态分类
    has_program = 0
    no_program = 0
    judge_ok = 0
    judge_needs_fix = 0
    no_judge = 0

    for paper in papers:
        qs = paper['data'].get('questions', [])

        if any(q.get('type') == 'program' for q in qs):
            has_program += 1
        else:
            no_program += 1

        judge_qs = [q for q in qs if q.get('type') == 'judge']
        if not judge_qs:
            no_judge += 1
        else:
            all_false = all(q.get('answer') == 'False' or q.get('answer') is False
                          for q in judge_qs)
            has_null = any(q.get('answer') is None or q.get('answer') == ''
                        for q in judge_qs)
            if all_false or has_null:
                judge_needs_fix += 1
            else:
                judge_ok += 1

    print(f"\n📝 JSON 试卷: {total_papers} 份")
    print(f"   含编程题: {has_program}")
    print(f"   缺编程题: {no_program}")
    print(f"   判断题已修复: {judge_ok}")
    print(f"   判断题需修复: {judge_needs_fix}")
    print(f"   无判断题: {no_judge}")

    # 3. PDF vs JSON 对比
    pdf_slugs = set()
    for pdf_file in pdf_files:
        info = parse_pdf_filename(pdf_file)
        if info:
            slug = f"{info['year']}-{str(info['month']).zfill(2)}-gesp-{info['level']}"
            pdf_slugs.add(slug)

    paper_slugs = {p['slug'] for p in papers}

    has_pdf_no_json = pdf_slugs - paper_slugs
    has_json_no_pdf = paper_slugs - pdf_slugs

    if has_pdf_no_json:
        print(f"\n⚠️ 有PDF无JSON ({len(has_pdf_no_json)}):")
        for slug in sorted(has_pdf_no_json):
            print(f"   - {slug}")

    if has_json_no_pdf:
        print(f"\n⚠️ 有JSON无PDF ({len(has_json_no_pdf)}):")
        for slug in sorted(has_json_no_pdf):
            print(f"   - {slug}")

    # 4. 整体健康度
    print(f"\n{'='*60}")
    health_issues = []
    if missing_pdfs:
        health_issues.append(f"⚠️ {len(missing_pdfs)} 个PDF未下载")
    if no_program:
        health_issues.append(f"⚠️ {no_program} 份试卷缺编程题")
    if judge_needs_fix:
        health_issues.append(f"⚠️ {judge_needs_fix} 份试卷判断题需修复")
    if has_pdf_no_json:
        health_issues.append(f"⚠️ {len(has_pdf_no_json)} 个PDF未解析")

    if health_issues:
        print("需要处理:")
        for issue in health_issues:
            print(f"  {issue}")
        print(f"\n运行 python3 gesp_import.py all 一键修复")
    else:
        print("✅ 数据完整，无待处理项！")


# ============================================================
# 主入口
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description='GESP 试卷数据统一导入工具',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python3 gesp_import.py status          # 查看数据完整性
  python3 gesp_import.py scan            # 扫描官网发现新增
  python3 gesp_import.py download        # 增量下载 PDF
  python3 gesp_import.py parse           # 解析客观题
  python3 gesp_import.py programs        # 追加编程题
  python3 gesp_import.py judge           # 检查判断题
  python3 gesp_import.py all             # 一键全流程
        """
    )
    subparsers = parser.add_subparsers(dest='command', help='子命令')

    # scan
    scan_parser = subparsers.add_parser('scan', help='扫描官网发现新增 PDF')
    scan_parser.set_defaults(func=cmd_scan)

    # download
    dl_parser = subparsers.add_parser('download', help='增量下载 PDF')
    dl_parser.add_argument('--force', action='store_true', help='强制重新下载')
    dl_parser.set_defaults(func=cmd_download)

    # parse
    parse_parser = subparsers.add_parser('parse', help='解析客观题')
    parse_parser.set_defaults(func=cmd_parse)

    # programs
    prog_parser = subparsers.add_parser('programs', help='从洛谷导入编程题面')
    prog_parser.add_argument('--force', action='store_true', help='强制重写已有编程题')
    prog_parser.set_defaults(func=cmd_programs)

    # judge
    judge_parser = subparsers.add_parser('judge', help='修复判断题答案')
    judge_parser.set_defaults(func=cmd_judge)

    # all
    all_parser = subparsers.add_parser('all', help='一键全流程')
    all_parser.set_defaults(func=cmd_all)

    # status
    status_parser = subparsers.add_parser('status', help='查看数据完整性')
    status_parser.set_defaults(func=cmd_status)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return

    args.func(args)


if __name__ == '__main__':
    main()
