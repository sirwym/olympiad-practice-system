#!/usr/bin/env python3
"""
从 /Users/mymac/Downloads/nct_papers/ 导入 NCT 试卷
将 nct_papers 的 sections 格式转换为 papers 的 questions 扁平格式

用法: python import_nct.py
"""

import json
import os
import re
from pathlib import Path

NCT_DIR = '/Users/mymac/Downloads/nct_papers'
PAPERS_DIR = Path(__file__).parent / 'papers'
URL_MAP_FILE = '/tmp/nct_url_map.json'

# category 映射
CATEGORY_MAP = {
    'C++': 'NCT-C++',
    'Kitten': 'NCT-KITTEN',
}

# 题型映射
TYPE_MAP = {
    '单项选择题': 'choice',
    '填空题': 'fill',
    'C++ 编程操作题': 'program',
    'Kitten 编程操作题': 'program',
}


def load_url_map():
    """加载 URL 到本地文件名的映射"""
    if os.path.exists(URL_MAP_FILE):
        with open(URL_MAP_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


def replace_images(text, url_map):
    """将 [图片: URL] 替换为 Markdown 图片语法，指向本地文件"""
    def replacer(match):
        url = match.group(1).strip()
        local_name = url_map.get(url)
        if local_name:
            return f'![img](../assets/images/nct/{local_name})'
        else:
            # fallback: 保留外链
            return f'![img]({url})'

    return re.sub(r'\[图片:\s*(https?://[^\]]+)\]', replacer, text)


def extract_title_html_images(q_data, url_map):
    """
    从 titleHtml 中提取 <img src="..."> 标签的图片。
    返回 Markdown 图片语法的字符串列表（用于追加到 content 末尾）。
    同时收集发现的 URL，供下载脚本使用。
    """
    title_html = q_data.get('titleHtml', '')
    if not title_html:
        return []

    img_urls = re.findall(r'<img[^>]*src=["\']?(https?://[^"\'>\s]+)["\']?', title_html)
    result = []
    for url in img_urls:
        local_name = url_map.get(url)
        if local_name:
            result.append(f'![img](../assets/images/nct/{local_name})')
        else:
            result.append(f'![img]({url})')
    return result


def convert_paper(filepath, url_map):
    """转换单份 NCT 试卷"""
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # 解析 category 和 level
    raw_category = data.get('category', '')
    category = CATEGORY_MAP.get(raw_category, raw_category)

    # 从 paperName 解析 level（C1→1, K1→1, C2→2, K3→3 等）
    paper_name = data.get('paperName', '')
    level_match = re.search(r'[CK](\d+)', paper_name)
    level = level_match.group(1) if level_match else '1'

    # 生成 title
    if raw_category == 'C++':
        title = f'NCT C++ {level}级 {paper_name}'
    else:
        title = f'NCT KITTEN {level}级 {paper_name}'

    # 扁平化 questions
    questions = []
    global_id = 0
    section_types = set()

    for section in data.get('sections', []):
        section_name = section.get('typeName', '')
        q_type = TYPE_MAP.get(section_name, 'choice')
        section_types.add(section_name)

        for q in section.get('questions', []):
            global_id += 1

            # 处理 content（替换图片）
            content = replace_images(q.get('title', ''), url_map)

            # 从 titleHtml 中提取额外图片（K2/K3 等级图片在 titleHtml 的 <img> 中）
            html_images = extract_title_html_images(q, url_map)
            if html_images:
                content += '\n\n' + '\n'.join(html_images)

            # 处理选项
            options = []
            for opt in q.get('options', []):
                opt_text = replace_images(opt.get('text', ''), url_map)
                options.append({
                    'key': opt.get('label', ''),
                    'text': opt_text,
                })

            # 处理答案
            answer = q.get('correctAnswer', '')
            if not answer:
                answer = 'None'

            question = {
                'type': q_type,
                'id': global_id,
                'score': q.get('questionScore', 0),
                'answer': answer,
                'content': content,
            }

            # 只有 choice 和 fill 才有 options
            if q_type in ('choice', 'fill'):
                question['options'] = options

            # choice 题有 section（用于分组显示）
            if section_name not in ('单项选择题',):
                question['section'] = section_name

            questions.append(question)

    # 生成 slug
    if raw_category == 'C++':
        slug = f'nct-cpp-{level}-{paper_name}'
    else:
        slug = f'nct-kitten-{level}-{paper_name}'

    # 构建试卷 JSON
    paper_data = {
        'title': title,
        'category': category,
        'level': level,
        'date': '2026-04',
        'time_limit': 60,
        'total_score': data.get('totalScore', 100),
        'description': 'NCT 全国青少年编程能力等级测试',
        'questions': questions,
    }

    return slug, paper_data


def main():
    # 第一步：收集所有图片 URL（包括 titleHtml 中的 <img>）
    print('📷 收集图片 URL...')
    all_urls = set()
    for fname in sorted(os.listdir(NCT_DIR)):
        if not fname.endswith('.json'):
            continue
        if fname in ('all_papers_summary.json',):
            continue
        with open(os.path.join(NCT_DIR, fname), 'r', encoding='utf-8') as f:
            data = json.load(f)
        for sec in data.get('sections', []):
            for q in sec.get('questions', []):
                # [图片: URL] 格式
                for m in re.finditer(r'\[图片:\s*(https?://[^\]]+)\]', q.get('title', '')):
                    all_urls.add(m.group(1).strip())
                for opt in q.get('options', []):
                    for m in re.finditer(r'\[图片:\s*(https?://[^\]]+)\]', opt.get('text', '')):
                        all_urls.add(m.group(1).strip())
                # titleHtml 中的 <img src="...">
                for m in re.finditer(r'<img[^>]*src=["\']?(https?://[^"\'>\s]+)', q.get('titleHtml', '')):
                    all_urls.add(m.group(1))
                for opt in q.get('options', []):
                    if isinstance(opt, dict) and opt.get('optionHtml'):
                        for m in re.finditer(r'<img[^>]*src=["\']?(https?://[^"\'>\s]+)', opt['optionHtml']):
                            all_urls.add(m.group(1))

    print(f'  共发现 {len(all_urls)} 个图片 URL')

    # 第二步：加载已有映射，下载缺失的图片
    url_map = load_url_map()
    img_dir = Path(__file__).parent / 'assets/images/nct'
    img_dir.mkdir(parents=True, exist_ok=True)

    new_downloaded = 0
    try:
        import urllib.request
        for url in sorted(all_urls):
            if url in url_map:
                continue

            # 从 URL 推断文件名
            parsed = urllib.parse.urlparse(url)
            name = os.path.basename(parsed.path)
            # 如果没有扩展名或名字太短（如 H1qx0679D），加 .png
            if '.' not in name or len(name.split('.')[-1]) > 4:
                name += '.png'
            local_path = img_dir / name

            try:
                req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(req, timeout=15) as resp:
                    data = resp.read()
                    ct = resp.headers.get('Content-Type', '')
                    # 根据 Content-Type 确定扩展名
                    if 'gif' in ct:
                        ext = '.gif'
                    elif 'png' in ct:
                        ext = '.png'
                    elif 'jpeg' in ct or 'jpg' in ct:
                        ext = '.jpg'
                    elif 'webp' in ct:
                        ext = '.webp'
                    else:
                        ext = '.png'

                    # 更新最终路径
                    final_name = name.rsplit('.', 1)[0] + ext
                    final_path = img_dir / final_name
                    with open(final_path, 'wb') as out:
                        out.write(data)

                    url_map[url] = final_name
                    new_downloaded += 1
                    print(f'  ⬇️ {final_name} ({len(data)}B)')
            except Exception as e:
                print(f'  ❌ 下载失败 {url}: {e}')

        # 保存 URL 映射
        with open(URL_MAP_FILE, 'w', encoding='utf-8') as f:
            json.dump(url_map, f)
        print(f'\n📦 图片处理完成：已有 {len(url_map)-new_downloaded} 张，新下载 {new_downloaded} 张')
    except ImportError:
        pass  # 无 urllib 时跳过下载

    # 第三步：转换试卷
    print(f'\n加载 URL 映射: {len(url_map)} 条')

    # 处理所有 JSON 文件
    converted = 0
    for fname in sorted(os.listdir(NCT_DIR)):
        if not fname.endswith('.json'):
            continue
        # 跳过汇总文件等非试卷文件
        if fname in ('all_papers_summary.json',):
            continue

        filepath = os.path.join(NCT_DIR, fname)
        slug, paper_data = convert_paper(filepath, url_map)

        # 创建输出目录
        out_dir = PAPERS_DIR / slug
        out_dir.mkdir(parents=True, exist_ok=True)

        # 写入 index.json
        out_file = out_dir / 'index.json'
        with open(out_file, 'w', encoding='utf-8') as f:
            json.dump(paper_data, f, ensure_ascii=False, indent=2)

        q_count = len(paper_data['questions'])
        # 统计该卷的图片数
        img_count = sum(
            1 for q in paper_data['questions']
            if re.search(r'!\[img\]\(', q.get('content', ''))
        )
        print(f'✅ {slug}: {q_count}题, {img_count}张图, {paper_data["category"]} {paper_data["level"]}级')
        converted += 1

    print(f'\n共转换 {converted} 份 NCT 试卷')


if __name__ == '__main__':
    main()
