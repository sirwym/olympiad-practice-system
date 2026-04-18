#!/usr/bin/env python3
"""
修复 GESP 判断题答案：通过多模态视觉识别从 PDF 中提取 √/× 答案

完整流程：
1. 用 pdfplumber 定位判断题答案行位置
2. 用 PyMuPDF 600DPI 渲染答案行截图
3. 调用多模态模型识别 √/× 符号（需外部 AI 协助）
4. 将识别结果写入 papers/*/index.json

用法：
    python3 fix_gesp_judge.py render   # 步骤1+2: 渲染截图
    python3 fix_gesp_judge.py status   # 查看哪些试卷需要修复
    python3 fix_gesp_judge.py apply --answers '{"slug1": [True, False, ...]}'  # 步骤4: 应用答案
    python3 fix_gesp_judge.py apply --file answers.json                       # 从 JSON 文件读取答案

原理：
- 2023-09 及以后的 GESP PDF 中，√/× 以矢量路径渲染，pdfplumber 无法提取文本
- 方案：pdfplumber 定位 + PyMuPDF 600DPI 渲染 + 多模态模型看图识别 √/×
- 注意：新版 PDF 的 "题号" 和 "答案" x0 坐标有 ~1pt 偏移，匹配时需容差 <3pt
"""

import os
import re
import sys
import json
import argparse
import warnings
import pdfplumber
import fitz  # PyMuPDF
from PIL import Image

warnings.filterwarnings('ignore')

PDF_DIR = os.path.join(os.path.dirname(__file__), "pdfs")
PAPERS_DIR = os.path.join(os.path.dirname(__file__), "papers")
SCREENSHOT_DIR = "/tmp/judge_answer_rows"

AFFECTED_FROM = (2023, 9)  # 受影响的起始日期


def parse_paper_slug(slug):
    """从文件夹名解析 year, month, level"""
    m = re.match(r"(\d{4})-(\d{2})-gesp-(\d+)", slug)
    if not m:
        return None
    return {"year": int(m.group(1)), "month": int(m.group(2)), "level": int(m.group(3))}


def get_gesp_papers():
    """获取所有 GESP 试卷列表，返回 [{slug, info, json_path, data, judge_count}]"""
    papers = []
    for slug in sorted(os.listdir(PAPERS_DIR)):
        info = parse_paper_slug(slug)
        if not info:
            continue
        json_path = os.path.join(PAPERS_DIR, slug, "index.json")
        if not os.path.exists(json_path):
            continue
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        judge_qs = [q for q in data.get('questions', []) if q.get('type') == 'judge']
        if not judge_qs:
            continue
        papers.append({
            'slug': slug,
            'info': info,
            'json_path': json_path,
            'data': data,
            'judge_count': len(judge_qs),
            'judge_questions': judge_qs,
        })
    return papers


def get_pdf_path(info):
    """根据试卷信息找到对应的 PDF 文件路径"""
    pdf_filename = f"{info['year']}-{str(info['month']).zfill(2)}-gesp-cpp-{info['level']}.pdf"
    pdf_path = os.path.join(PDF_DIR, pdf_filename)
    return pdf_path if os.path.exists(pdf_path) else None


# ============================================================
# 步骤1+2: 渲染截图
# ============================================================

def find_judge_answer_area(pdf_path):
    """
    用 pdfplumber 找到判断题答案行的位置信息。
    返回: {page_num, x_start, y_top, y_bottom, x_end, q_count} 或 None
    """
    with pdfplumber.open(pdf_path) as pdf:
        for page_idx, page in enumerate(pdf.pages):
            words = page.extract_words(keep_blank_chars=True, x_tolerance=3, y_tolerance=3)
            if not words:
                continue

            ti_hao_words = [w for w in words if w['text'] == '题号']
            for th in ti_hao_words:
                th_top = th['top']
                # 答案行在题号行下方 5-25pt，x0 坐标容差 <3pt
                matching_da = [d for d in words if d['text'] == '答案'
                              and abs(d['x0'] - th['x0']) < 3
                              and 5 < (d['top'] - th_top) < 25]
                if not matching_da:
                    continue

                da = matching_da[0]

                # 确认是判断题答案行（后面无 ABCD）
                answer_row_words = [w for w in words
                                   if abs(w['top'] - da['top']) < 5
                                   and w['x0'] > da['x1']]
                answer_texts = ''.join(w['text'] for w in answer_row_words)
                if re.search(r'[ABCD]', answer_texts):
                    continue

                # 获取题号行最后一个数字的位置（确定右侧范围）
                ti_hao_row_words = [w for w in words
                                    if abs(w['top'] - th_top) < 5
                                    and w['x0'] > th['x1']]
                q_nums = [w for w in ti_hao_row_words if w['text'].isdigit()]

                if not q_nums:
                    continue

                last_q_num = max(q_nums, key=lambda w: w['x1'])

                return {
                    'page_num': page_idx,
                    'x_start': th['x0'],
                    'y_top': th['top'] - 5,
                    'y_bottom': da['bottom'] + 8,
                    'x_end': last_q_num['x1'] + 20,
                    'q_count': len(q_nums)
                }
    return None


def render_answer_row(pdf_path, area_info):
    """渲染答案行高清图（600DPI）"""
    doc = fitz.open(pdf_path)
    page = doc[area_info['page_num']]

    zoom = 600 / 72
    mat = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=mat)
    img = Image.frombytes('RGB', [pix.width, pix.height], pix.samples)

    x1 = int(area_info['x_start'] * zoom)
    y1 = int(area_info['y_top'] * zoom)
    x2 = int(area_info['x_end'] * zoom)
    y2 = int(area_info['y_bottom'] * zoom)

    crop = img.crop((x1, y1, x2, y2))
    doc.close()
    return crop


def cmd_render(args):
    """渲染所有需要修复的判断题答案行截图"""
    os.makedirs(SCREENSHOT_DIR, exist_ok=True)
    papers = get_gesp_papers()

    # 过滤出需要处理的（受影响范围内 + 有 PDF）
    results = []
    for paper in papers:
        if (paper['info']['year'], paper['info']['month']) < AFFECTED_FROM:
            continue

        pdf_path = get_pdf_path(paper['info'])
        if not pdf_path:
            print(f"SKIP {paper['slug']}: no PDF")
            results.append({'slug': paper['slug'], 'status': 'no_pdf'})
            continue

        # 检查判断题答案是否已修复
        all_false = all(q.get('answer') == 'False' or q.get('answer') is False
                       for q in paper['judge_questions'])
        has_null = any(q.get('answer') is None or q.get('answer') == ''
                     for q in paper['judge_questions'])

        if not all_false and not has_null:
            print(f"SKIP {paper['slug']}: already fixed")
            results.append({'slug': paper['slug'], 'status': 'already_fixed'})
            continue

        area = find_judge_answer_area(pdf_path)
        if not area:
            print(f"SKIP {paper['slug']}: cannot find answer row")
            results.append({'slug': paper['slug'], 'status': 'no_position'})
            continue

        img = render_answer_row(pdf_path, area)
        output_path = os.path.join(SCREENSHOT_DIR, f"{paper['slug']}.png")
        img.save(output_path)

        print(f"OK   {paper['slug']} ({area['q_count']} questions) -> {output_path}")
        results.append({
            'slug': paper['slug'],
            'status': 'ok',
            'path': output_path,
            'q_count': area['q_count']
        })

    # 输出 manifest
    manifest_path = os.path.join(SCREENSHOT_DIR, "_manifest.json")
    ok_results = [r for r in results if r['status'] == 'ok']
    with open(manifest_path, 'w') as f:
        json.dump(ok_results, f, ensure_ascii=False, indent=2)

    print(f"\nDone: {len(ok_results)}/{len(results)} rendered")
    print(f"Manifest: {manifest_path}")
    print(f"\n下一步: 用多模态模型识别截图中的 √/× 答案，然后执行:")
    print(f"  python3 fix_gesp_judge.py apply --file answers.json")


# ============================================================
# 步骤4: 应用答案
# ============================================================

def cmd_apply(args):
    """将识别的判断题答案写入 JSON 文件"""
    # 读取答案数据
    answers_map = {}
    if args.file:
        with open(args.file, 'r', encoding='utf-8') as f:
            answers_map = json.load(f)
    elif args.answers:
        answers_map = json.loads(args.answers)
    else:
        print("错误: 必须指定 --answers 或 --file")
        return

    # answers_map 格式: {slug: [True, False, ...], ...}
    # 也支持 {slug: ["True", "False", ...]} 字符串格式
    updated_count = 0
    skipped = 0
    errors = []

    for slug, answers in answers_map.items():
        json_path = os.path.join(PAPERS_DIR, slug, "index.json")
        if not os.path.exists(json_path):
            print(f"SKIP {slug}: file not found")
            skipped += 1
            continue

        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        judge_qs = [q for q in data['questions'] if q.get('type') == 'judge']
        if not judge_qs:
            print(f"SKIP {slug}: no judge questions")
            skipped += 1
            continue

        if len(judge_qs) != len(answers):
            print(f"SKIP {slug}: answer count mismatch ({len(judge_qs)} vs {len(answers)})")
            errors.append(slug)
            skipped += 1
            continue

        # 转换答案格式
        normalized = []
        for a in answers:
            if isinstance(a, bool):
                normalized.append(a)
            elif isinstance(a, str):
                normalized.append(a == 'True')
            else:
                normalized.append(bool(a))

        changed = 0
        for i, q in enumerate(judge_qs):
            new_answer = "True" if normalized[i] else "False"
            old_answer = q.get('answer', '')
            if old_answer != new_answer:
                q['answer'] = new_answer
                changed += 1

        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write('\n')

        if changed > 0:
            ans_str = ', '.join('T' if a else 'F' for a in normalized)
            print(f"✓ {slug} ({changed}/{len(normalized)}) [{ans_str}]")
            updated_count += 1
        else:
            print(f"= {slug} (no change)")

    print(f"\n{'='*50}")
    print(f"Updated: {updated_count}")
    print(f"Skipped: {skipped}")
    if errors:
        print(f"Errors:  {errors}")


# ============================================================
# 状态查看
# ============================================================

def cmd_status(args):
    """查看 GESP 判断题答案的完整性状态"""
    papers = get_gesp_papers()

    total = len(papers)
    all_fixed = 0
    needs_fix = 0
    no_pdf = 0
    details = []

    for paper in papers:
        pdf_path = get_pdf_path(paper['info'])

        # 检查答案状态
        judge_qs = paper['judge_questions']
        all_false = all(q.get('answer') == 'False' or q.get('answer') is False
                       for q in judge_qs)
        has_null = any(q.get('answer') is None or q.get('answer') == ''
                     for q in judge_qs)

        if not pdf_path:
            no_pdf += 1
            status = "NO_PDF"
        elif all_false or has_null:
            needs_fix += 1
            status = "NEEDS_FIX"
        else:
            all_fixed += 1
            status = "OK"

        details.append({
            'slug': paper['slug'],
            'judge_count': paper['judge_count'],
            'status': status,
        })

    print(f"GESP 判断题答案状态")
    print(f"{'='*60}")
    print(f"总计: {total} 份试卷含判断题")
    print(f"  ✓ 已修复: {all_fixed}")
    print(f"  ✗ 需修复: {needs_fix}")
    print(f"  - 无PDF:  {no_pdf}")

    if needs_fix > 0:
        print(f"\n需要修复的试卷:")
        for d in details:
            if d['status'] == 'NEEDS_FIX':
                print(f"  {d['slug']} ({d['judge_count']}道判断题)")

    if args.verbose:
        print(f"\n全部试卷:")
        for d in details:
            icon = {'OK': '✓', 'NEEDS_FIX': '✗', 'NO_PDF': '-'}.get(d['status'], '?')
            print(f"  {icon} {d['slug']} ({d['judge_count']}道判断题) [{d['status']}]")


# ============================================================
# 主入口
# ============================================================

def main():
    parser = argparse.ArgumentParser(description='修复 GESP 判断题答案')
    subparsers = parser.add_subparsers(dest='command', help='子命令')

    # render
    render_parser = subparsers.add_parser('render', help='渲染判断题答案行截图')
    render_parser.set_defaults(func=cmd_render)

    # apply
    apply_parser = subparsers.add_parser('apply', help='应用识别结果到 JSON')
    apply_group = apply_parser.add_mutually_exclusive_group(required=True)
    apply_group.add_argument('--answers', help='JSON 格式答案: \'{"slug": [True, False, ...]}\'')
    apply_group.add_argument('--file', help='JSON 文件路径，格式同上')
    apply_parser.set_defaults(func=cmd_apply)

    # status
    status_parser = subparsers.add_parser('status', help='查看判断题答案状态')
    status_parser.add_argument('-v', '--verbose', action='store_true', help='显示全部试卷')
    status_parser.set_defaults(func=cmd_status)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return

    args.func(args)


if __name__ == '__main__':
    main()
