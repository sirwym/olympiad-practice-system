#!/usr/bin/env python3
"""
import_gesp_programs.py — 从 GESP PDF 提取编程题，追加到现有试卷 JSON 中

用法：
    python3 import_gesp_programs.py              # 处理全部 91 份
    python3 import_gesp_programs.py --dry-run     # 只分析不写入
    python3 import_gesp_programs.py --level 4      # 只处理指定级别

功能：
- 用 pdfplumber 解析 PDF 的「3 编程题」章节
- 提取每道编程题的：名称、时间/内存限制、题目描述、输入输出格式、样例、数据范围
- 不提取参考程序（用户要求）
- 追加 program 类型 questions 到现有 index.json
- 更新 total_score: 50 → 100
"""

import json
import os
import re
import glob
import argparse
import pdfplumber


# ============================================================
# PDF 文本解析 — 提取编程题部分
# ============================================================

def extract_program_section(pdf_path):
    """从 PDF 中提取编程题部分的纯文本，返回 (text, page_start_idx) 或 (None, None)"""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            full_pages = []
            for i, page in enumerate(pdf.pages):
                text = (page.extract_text() or '').strip()
                if text:
                    full_pages.append((i, text))

            # 合并所有页面文本
            combined = '\n---PAGEBREAK---\n'.join(t for _, t in full_pages)

            # 兼容多种标题格式
            idx = -1
            for pattern in ['3 编程题', '三、编程题', '三、编程操作题', '编程题（每题']:
                pos = combined.find(pattern)
                if pos != -1:
                    idx = pos
                    break

            if idx == -1:
                return None, None

            # 截取从编程题标题到文档末尾
            section = combined[idx:]

            # 清理页码标记等噪音
            section = re.sub(r'第\s*\d+\s*页\s*/\s*共\s*\d+\s*页', '', section)

            return section, len(full_pages)
    except Exception as e:
        print(f"  ⚠️  解析 PDF 失败: {e}")
        return None, None


def is_early_format(text):
    """判断是否为早期 GESP 格式（2023年，使用【】括号）"""
    return '【问题描述】' in text or '【输入描述】' in text


def split_problems(section_text):
    """将编程题部分按题目分割为各子题列表"""
    
    # 早期格式：以 "N. 题名" 开头分割
    if is_early_format(section_text):
        pattern = r'(?:^|\n)\s*(\d+)\.\s+([^\n【]+?)(?:\n|$)'
        matches = list(re.finditer(pattern, section_text))
        if len(matches) >= 2:
            problems = []
            for i, m in enumerate(matches):
                start = m.start()
                end = matches[i + 1].start() if i + 1 < len(matches) else len(section_text)
                problems.append(section_text[start:end].strip())
            return problems
        else:
            # 只有一道或无法分割，返回整体
            return [section_text]

    # 新格式 (2024+)：「X.X 编程题 N」
    pattern = r'(?:^|\n)\s*(\d+\.\d+)\s+编程题\s*(\d+)'
    matches = list(re.finditer(pattern, section_text))

    if not matches:
        return [section_text]  # 整体作为一道题

    problems = []
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(section_text)
        problem_text = section_text[start:end].strip()
        problems.append(problem_text)

    return problems


def parse_single_problem(text):
    """解析单道编程题文本，返回结构化 dict"""
    result = {
        'name': '',
        'time_limit': '',
        'memory_limit': '',
        'description': '',
        'input_format': '',
        'output_format': '',
        'samples': [],       # [{'input': ..., 'output': ...}, ...]
        'sample_explanation': '',
        'data_range': '',
    }

    # 检测是否为早期格式（2023年，使用【】括号）
    if is_early_format(text):
        return _parse_early_format(text, result)

    lines = text.split('\n')
    current_section = None
    content_buf = []

    def flush():
        nonlocal content_buf, current_section
        if current_section and content_buf:
            cleaned = '\n'.join(content_buf).strip()
            if current_section == 'desc':
                result['description'] = cleaned
            elif current_section == 'input':
                result['input_format'] = cleaned
            elif current_section == 'output':
                result['output_format'] = cleaned
            elif current_section == 'sample':
                result['sample_explanation'] = cleaned
            elif current_section == 'range':
                result['data_range'] = cleaned
        content_buf = []

    for line in lines:
        stripped = line.strip()

        # 跳过空行和分隔符
        if not stripped or stripped.startswith('---PAGEBREAK---'):
            flush()
            current_section = None
            continue

        # 试题名称（两种形式：独立行 或 嵌入 3.X.1 行）
        m = re.match(r'^[\s.]*试题名称[：:](.+)$', stripped)
        if m:
            flush()
            result['name'] = m.group(1).strip()
            current_section = None
            continue

        # 3.1.1 短文本 = 题名（如"3.1.1 图书馆里的老鼠"，非标准section）
        m = re.match(r'^(\d+\.\d+)\.\d+\s+(.{2,30})$', stripped)
        if m and not result['name'] and not any(kw in stripped for kw in ['题目描述', '题面描述', '输入', '输出', '样例', '数据范围', '参考程序']):
            result['name'] = m.group(2).strip()
            continue

        # 时间/内存限制
        m = re.match(r'^[\s.]*时间限制[：:](.+)$', stripped)
        if m:
            result['time_limit'] = m.group(1).strip()
            continue
        m = re.match(r'^[\s.]*内存限制[：:](.+)$', stripped)
        if m:
            result['memory_limit'] = m.group(1).strip()
            continue

        # 题目描述 / 题面描述
        if re.match(r'^\d+\.\d+\.\d+\s*题目描述$|^题面描述$', stripped):
            flush()
            current_section = 'desc'
            continue

        # 输入格式
        if re.match(r'^\d+\.\d+\.\d+\s*输入格式$|^输入格式$', stripped):
            flush()
            current_section = 'input'
            continue

        # 输出格式
        if re.match(r'^\d+\.\d+\.\d+\s*输出格式$|^输出格式$', stripped):
            flush()
            current_section = 'output'
            continue

        # 样例区域 — 需要特殊处理
        if re.match(r'^\d+\.\d+\.\d+\s*样例$|^样例$', stripped):
            flush()
            current_section = 'sample_collect'  # 特殊模式
            continue

        # 样例解释
        if re.match(r'^\d+\.\d+\.\d+\s*样例解释', stripped) or stripped.startswith('样例解释'):
            flush()
            current_section = 'sample'
            continue

        # 数据范围 / 数据约束
        if re.match(r'^\d+\.\d+\.\d+\s*数据(范围|约束)', stripped) or stripped.startswith('数据范围') or stripped.startswith('数据约束'):
            flush()
            current_section = 'range'
            continue

        # 参考程序 — 到此为止，停止解析
        if re.match(r'^\d+\.\d+\.\d+\s*参考程序', stripped) or stripped.startswith('参考程序'):
            flush()
            break

        # 样例收集模式 — 识别输入/输出样例对
        if current_section == 'sample_collect':
            inp_m = re.match(r'^[\d\s]*输入样例[#\s\d]*[：:]?\s*$', stripped) or \
                    re.match(r'^[\d\s]*输入[：:]\s*$', stripped)
            out_m = re.match(r'^[\d\s]*输出样例[#\s\d]*[：:]?\s*$', stripped) or \
                    re.match(r'^[\d\s]*输出[：:]\s*$', stripped)

            if inp_m:
                # 开始新的样例对
                result['samples'].append({'input': '', 'output': ''})
                continue
            if out_m:
                continue

            # 样例行内容（可能是数字行或实际数据）
            if result['samples']:
                last = result['samples'][-1]
                # 如果还没有 output 或者当前看起来像输出
                if not last['output']:
                    # 判断是 input 还是 output 内容
                    if last['input'] and is_output_line(stripped):
                        last['output'] += ('\n' if last['output'] else '') + stripped
                    else:
                        last['input'] += ('\n' if last['input'] else '') + stripped
                else:
                    # 可能是下一个样例的输入
                    pass
            continue

        # 普通内容缓冲
        if current_section:
            content_buf.append(stripped)

    # 最后 flush
    flush()

    return result


def _parse_early_format(text, result):
    """解析早期 GESP 格式（2023年，使用【】括号）"""
    lines = text.split('\n')

    # 第一行通常是 "N. 题名" 格式
    first_line = ''
    for line in lines:
        s = line.strip()
        if s and not s.startswith('---PAGEBREAK---'):
            first_line = s
            break

    # 提取题目名称
    name_m = re.match(r'^\d+\.\s*(.+)$', first_line)
    if name_m:
        result['name'] = name_m.group(1).strip()

    # 用【】标记分割各部分
    combined = '\n'.join(lines)

    # 【问题描述】
    desc_m = re.search(r'【问题描述】\s*\n?(.*?)(?=【|$)', combined, re.DOTALL)
    if desc_m:
        result['description'] = desc_m.group(1).strip()

    # 【输入描述】
    inp_m = re.search(r'【输入(?:说明|描述)?】\s*\n?(.*?)(?=【|$)', combined, re.DOTALL)
    if inp_m:
        result['input_format'] = inp_m.group(1).strip()

    # 【输出描述】
    out_m = re.search(r'【输出(?:说明|描述)?】\s*\n?(.*?)(?=【|$)', combined, re.DOTALL)
    if out_m:
        result['output_format'] = out_m.group(1).strip()

    # 提取样例对
    sample_pairs = re.findall(
        r'【样例输入(\d*)】\s*\n?(.*?)\s*【样例输出(\d*)】\s*\n?(.*?)(?=(?:【)|$)',
        combined, re.DOTALL
    )
    for _, sin, _, sout in sample_pairs:
        if len(result['samples']) < 2:  # 最多2组样例
            result['samples'].append({
                'input': sin.strip(),
                'output': sout.strip(),
            })

    # 【样例解释】或【提示】
    hint_m = re.search(r'【(?:样例解释|提示|说明)】\s*\n?(.*?)(?:(?:【)|(?:参考程序)|$)', combined, re.DOTALL)
    if hint_m:
        result['sample_explanation'] = hint_m.group(1).strip()

    # 数据范围可能在最后一段
    range_m = re.search(r'(?:对于全部数据|数据范围|数据约束)[^\n]*(.*?)(?=$|(?:参考程序))', combined, re.DOTALL)
    if range_m:
        result['data_range'] = (range_m.group(0)).strip()[:500]

    # 如果没有提取到名称，用第一行的题名
    if not result['name'] and first_line:
        result['name'] = first_line.strip().lstrip('0123456789. ')

    return result


def is_output_line(line):
    """简单启发式判断一行是否像输出样例"""
    # 如果这行很短且纯数字，可能是输出
    if len(line) < 30 and re.match(r'^[\d\s\-]+$', line.strip()):
        return True
    return False


def build_program_markdown(problem, prob_num):
    """将结构化的编程题数据渲染为 Markdown 字符串"""
    parts = []

    header = f"**试题名称：{problem['name']}**"
    parts.append(header)

    meta_parts = []
    if problem.get('time_limit'):
        meta_parts.append(f"时间限制：{problem['time_limit']}")
    if problem.get('memory_limit'):
        meta_parts.append(f"内存限制：{problem['memory_limit']}")
    if meta_parts:
        parts.append('\n> ' + ' | '.join(meta_parts))

    if problem.get('description'):
        parts.append(f"\n### 题目描述\n{problem['description']}")

    if problem.get('input_format'):
        parts.append(f"\n### 输入格式\n{problem['input_format']}")

    if problem.get('output_format'):
        parts.append(f"\n### 输出格式\n{problem['output_format']}")

    if problem.get('samples'):
        parts.append("\n### 样例")
        for si, sample in enumerate(problem['samples'], 1):
            if sample.get('input') and si <= 2:  # 最多显示2组样例
                parts.append(f"\n**输入样例 #{si}:**")
                parts.append(f"```")
                parts.append(sample['input'].strip())
                parts.append(f"```")
            if sample.get('output') and si <= 2:
                parts.append(f"\n**输出样例 #{si}:**")
                parts.append(f"```")
                parts.append(sample['output'].strip())
                parts.append(f"```")

    if problem.get('sample_explanation'):
        parts.append(f"\n### 样例解释\n{problem['sample_explanation']}")

    if problem.get('data_range'):
        parts.append(f"\n### 数据范围\n{problem['data_range']}")

    return '\n'.join(parts)


# ============================================================
# 主逻辑：遍历 PDF → 解析 → 写入 JSON
# ============================================================

def find_pdf_for_paper(paper_dir, pdfs_dir):
    """根据试卷目录名找到对应的 PDF 文件"""
    dir_name = os.path.basename(paper_dir)
    # papers/2026-03-gesp-1/ → pdfs/2026-03-gesp-cpp-1.pdf
    m = re.match(r'(\d{4}-\d{2}-gesp)-(\d+)$', dir_name)
    if m:
        date_prefix = m.group(1)  # 2026-03-gesp
        level = m.group(2)
        pdf_name = f"{date_prefix}-cpp-{level}.pdf"
        pdf_path = os.path.join(pdfs_dir, pdf_name)
        if os.path.exists(pdf_path):
            return pdf_path
    return None


def process_one_paper(paper_dir, pdfs_dir, dry_run=False, target_level=None):
    """处理一份 GESP 试卷：从 PDF 提取编程题并追加到 JSON"""
    json_path = os.path.join(paper_dir, 'index.json')

    # 检查是否已包含 program 类型的题目
    with open(json_path, 'r') as f:
        data = json.load(f)

    has_program = any(q.get('type') == 'program' for q in data.get('questions', []))
    if has_program:
        return {'status': 'skip_already_has_program', 'paper': os.path.basename(paper_dir)}

    # 找对应 PDF
    pdf_path = find_pdf_for_paper(paper_dir, pdfs_dir)
    if not pdf_path:
        return {'status': 'skip_no_pdf', 'paper': os.path.basename(paper_dir)}

    # 可选级别过滤
    level = str(data.get('level', ''))
    if target_level and str(target_level) != level:
        return {'status': 'skip_level_filter', 'paper': os.path.basename(paper_dir)}

    # 提取编程题
    section, num_pages = extract_program_section(pdf_path)
    if not section:
        return {'status': 'skip_no_program_section', 'paper': os.path.basename(paper_dir), 'pages': num_pages}

    # 分割为各子题
    raw_problems = split_problems(section)

    # 解析每道编程题
    program_questions = []
    next_id = max((q['id'] for q in data['questions']), default=0) + 1

    for pi, rp in enumerate(raw_problems):
        parsed = parse_single_problem(rp)
        if not parsed['name']:
            continue

        markdown_content = build_program_markdown(parsed, pi + 1)

        pq = {
            "type": "program",
            "id": next_id,
            "score": 25,  # 默认每题25分
            "answer": "None",
            "content": markdown_content,
            "options": [],
            "section": "GESP 编程操作题",
        }
        program_questions.append(pq)
        next_id += 1

    if not program_questions:
        return {'status': 'skip_no_valid_problems', 'paper': os.path.basename(paper_dir)}

    # 计算编程题总分
    prog_total_score = sum(pq['score'] for pq in program_questions)

    if dry_run:
        return {
            'status': 'dry_run',
            'paper': os.path.basename(paper_dir),
            'level': level,
            'num_programs': len(program_questions),
            'prog_score': prog_total_score,
            'names': [pq['content'].split('**')[1].replace('试题名称：', '')
                      if '**试题名称：' in pq['content'] else f'程序{pi+1}'
                      for pi, pq in enumerate(program_questions)],
        }

    # 写入 JSON
    data['questions'].extend(program_questions)
    data['total_score'] = 100  # 客观题50 + 编程题50
    data['description'] = data.get('description', '').replace(
        '客观题', '含编程操作题'
    ) if '客观题' in data.get('description', '') else data.get('description', '')

    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    return {
        'status': 'ok',
        'paper': os.path.basename(paper_dir),
        'level': level,
        'num_programs': len(program_questions),
        'prog_score': prog_total_score,
    }


def main():
    parser = argparse.ArgumentParser(description='从 GESP PDF 提取编程题并追加到 JSON')
    parser.add_argument('--dry-run', action='store_true', help='只分析不写入')
    parser.add_argument('--level', type=int, help='只处理指定级别')
    args = parser.parse_args()

    base_dir = os.path.dirname(os.path.abspath(__file__))
    papers_dir = os.path.join(base_dir, 'papers')
    pdfs_dir = os.path.join(base_dir, 'pdfs')

    # 找到所有 GESP 试卷目录
    gesp_dirs = sorted([
        d for d in glob.glob(os.path.join(papers_dir, '*-gesp-*'))
        if os.path.isdir(d) and '-csp-' not in d and '-nct-' not in d
    ])

    print(f"📂 共找到 {len(gesp_dirs)} 个 GESP 试卷目录")
    if args.level:
        print(f"🔍 过滤级别: Level {args.level}")
    if args.dry_run:
        print("👀 DRY-RUN 模式（不会修改任何文件）")
    print("=" * 70)

    results = []
    ok_count = 0
    skip_counts = {}
    fail_count = 0

    for paper_dir in gesp_dirs:
        result = process_one_paper(paper_dir, pdfs_dir,
                                   dry_run=args.dry_run,
                                   target_level=args.level)
        results.append(result)
        status = result['status']

        if status == 'ok':
            ok_count += 1
            print(f"✅ {result['paper']:40s} | L{result['level']} | "
                  f"{result['num_programs']}道编程题 (+{result['prog_score']}分)")
        elif status == 'dry_run':
            ok_count += 1
            names_str = ', '.join(result.get('names', ['?'])[:3])
            print(f"🔍 {result['paper']:40s} | L{result['level']} | "
                  f"{result['num_programs']}道编程题 (+{result['prog_score']}分) | {names_str}")
        else:
            skip_counts[status] = skip_counts.get(status, 0) + 1
            label = {
                'skip_already_has_program': '⏭️ 已有编程题',
                'skip_no_pdf': '❌ 无PDF',
                'skip_no_program_section': '⚠️ PDF无编程题',
                'skip_level_filter': '⏭️ 级别过滤',
                'skip_no_valid_problems': '⚠️ 未提取到有效题目',
            }.get(status, f'? {status}')
            print(f"{label} {result.get('paper', '?'):40s}")

    # 统计汇总
    print("\n" + "=" * 70)
    print(f"📊 处理完成:")
    print(f"   ✅ 成功: {ok_count} 份")
    for st, cnt in sorted(skip_counts.items(), key=lambda x: -x[1]):
        label = {
            'skip_already_has_program': '已有编程题',
            'skip_no_pdf': '无对应PDF',
            'skip_no_program_section': 'PDF中无编程题章节',
            'skip_level_filter': '被级别过滤',
            'skip_no_valid_problems': '未提取到有效题目',
        }.get(st, st)
        print(f"   ⏭️  {label}: {cnt} 份")


if __name__ == '__main__':
    main()
