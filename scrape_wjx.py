#!/usr/bin/env python3
"""
从问卷星 wjx.com 抓取 NOC Kitten 试卷
提取题目文本 + 图片，下载图片到 assets/images/noc/

用法: python scrape_wjx.py
"""

import json
import os
import re
import time
import urllib.request
import urllib.parse
from pathlib import Path

BASE_DIR = Path(__file__).parent
IMG_DIR = BASE_DIR / 'assets' / 'images' / 'noc'
IMG_DIR.mkdir(parents=True, exist_ok=True)

# 两份试卷配置
PAPERS = [
    {
        'url': 'https://ks.wjx.com/vm/rm1Auxe.aspx',
        'title': 'NOC Kitten图形化编程练习卷一',
        'slug': 'noc-kitten-练习卷一',
    },
    {
        'url': 'https://ks.wjx.com/vm/tFWiwTy.aspx',
        'title': 'NOC Kitten图形化编程练习卷二',
        'slug': 'noc-kitten-练习卷二',
    },
    {
        'url': 'https://ks.wjx.com/vm/wea00JL.aspx',
        'title': 'NOC Kitten图形化编程练习卷三',
        'slug': 'noc-kitten-练习卷三',
    },
]

# 全局图片 URL → 本地文件名映射
url_map = {}
MAP_FILE = BASE_DIR / '.wjx_url_map.json'
if MAP_FILE.exists():
    with open(MAP_FILE, 'r', encoding='utf-8') as f:
        url_map = json.load(f)


def download_image(url):
    """下载图片，返回本地文件名"""
    # 补全协议
    if url.startswith('//'):
        url = 'https:' + url

    if url in url_map:
        return url_map[url]

    # 从 URL 生成文件名
    parsed = urllib.parse.urlparse(url)
    name = os.path.basename(parsed.path)
    if not name or '.' not in name:
        name = str(hash(url))[-8:] + '.png'

    local_path = IMG_DIR / name
    # 避免文件名冲突
    if local_path.exists():
        base, ext = os.path.splitext(name)
        i = 1
        while (IMG_DIR / f'{base}_{i}{ext}').exists():
            i += 1
        name = f'{base}_{i}{ext}'

    try:
        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)',
            'Referer': 'https://ks.wjx.com/',
        })
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = resp.read()
            ct = resp.headers.get('Content-Type', '')
            if 'gif' in ct:
                ext = '.gif'
            elif 'png' in ct:
                ext = '.png'
            elif 'jpeg' in ct or 'jpg' in ct:
                ext = '.jpg'
            elif 'webp' in ct:
                ext = '.webp'
            else:
                ext = os.path.splitext(name)[1] or '.png'

            final_name = os.path.splitext(name)[0] + ext
            final_path = IMG_DIR / final_name
            with open(final_path, 'wb') as out:
                out.write(data)

            url_map[url] = final_name
            # 也保存协议相对格式的 key
            if url.startswith('https:'):
                url_map['//' + url[8:]] = final_name
            print(f'  ⬇️ {final_name} ({len(data)}B)')
            return final_name
    except Exception as e:
        print(f'  ❌ 下载失败 {url}: {e}')
        return None


def scrape_paper(paper_config):
    """用 Playwright 抓取单份试卷"""
    from playwright.sync_api import sync_playwright

    url = paper_config['url']
    print(f"\n{'='*60}")
    print(f"📝 抓取: {paper_config['title']}")
    print(f"   URL: {url}")
    print(f"{'='*60}")

    questions = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url, wait_until='networkidle', timeout=60000)
        page.wait_for_timeout(3000)

        # 滚动到底部以确保所有懒加载图片加载
        for i in range(30):
            page.evaluate('window.scrollBy(0, 800)')
            page.wait_for_timeout(400)
        page.evaluate('window.scrollTo(0, 0)')
        page.wait_for_timeout(1000)

        q_divs = page.query_selector_all('div.field')
        print(f"  找到 {len(q_divs)} 个 div.field")

        qid = 0
        for idx, q_div in enumerate(q_divs):
            # 跳过班级/姓名等非题目字段
            label_el = q_div.query_selector('div.field-label')
            if not label_el:
                continue

            label_text = label_el.inner_text().strip()

            # 检查是否包含题号（数字+点）
            if not re.search(r'\d+[.．]', label_text):
                continue

            qid += 1
            question_data = extract_question(q_div, qid, label_el)
            if question_data:
                questions.append(question_data)

        browser.close()

    return questions


def extract_question(q_div, qid, label_el):
    """从单个题目 div 中提取题目信息"""

    # ===== 判断题型 =====
    has_checkboxes = len(q_div.query_selector_all('input[type="checkbox"]')) > 0
    has_radios = len(q_div.query_selector_all('input[type="radio"]')) > 0
    has_textarea = len(q_div.query_selector_all('textarea')) > 0
    has_text_input = len(q_div.query_selector_all('input[type="text"]')) > 0

    # 检查题型标签
    type_label = ''
    label_el_inner = q_div.query_selector('div.field-label')
    if label_el_inner:
        label_text = label_el_inner.inner_text()
        if '多选' in label_text or '【多选题】' in label_text:
            type_label = '多选'

    if '多选' in type_label or has_checkboxes:
        q_type = 'multi_choice'
    elif (has_text_input or has_textarea) and not has_radios and not has_checkboxes:
        q_type = 'fill'
    else:
        q_type = 'choice'

    # ===== 提取题干 =====
    # 题干文本在 div.field-label 中，需去掉题号前缀
    label_text = label_el.inner_text().strip()
    # 去掉 * 号和题号前缀: "*\n1.题目文本" → "题目文本"
    content_text = re.sub(r'^[*\s]*\d+[.．]\s*', '', label_text)
    # 去掉题型标签 【多选题】
    content_text = re.sub(r'【多选题】\s*', '', content_text)
    # 去掉 【填空题】 标签
    content_text = re.sub(r'【填空题】\s*', '', content_text)
    content_text = content_text.strip()

    # 提取题干中的图片（在 div.topichtml 或 div.field-label 的 img 中）
    content_imgs = []

    # 检查 div.topichtml（问卷星图片题的图片容器）
    topichtml_el = q_div.query_selector('div.topichtml')
    if topichtml_el:
        img_els = topichtml_el.query_selector_all('img')
        for img_el in img_els:
            src = img_el.get_attribute('src') or ''
            data_src = img_el.get_attribute('data-src') or ''
            img_url = data_src or src
            if img_url and ('paperol' in img_url or img_url.startswith('http')):
                content_imgs.append(img_url)

    # 也检查 field-label 中的图片
    if label_el:
        img_els = label_el.query_selector_all('img')
        for img_el in img_els:
            src = img_el.get_attribute('src') or ''
            data_src = img_el.get_attribute('data-src') or ''
            img_url = data_src or src
            if img_url and ('paperol' in img_url or img_url.startswith('http')):
                if img_url not in content_imgs:
                    content_imgs.append(img_url)

    # ===== 构建题干 Markdown =====
    content_md = content_text

    # 下载并追加题干图片
    for img_url in content_imgs:
        local_name = download_image(img_url)
        if local_name:
            content_md += f'\n![img](../assets/images/noc/{local_name})'

    # ===== 提取选项 =====
    options = []

    # 单选题选项: div.ui-radio > div.label
    # 多选题选项: div.ui-checkbox > div.label
    if q_type == 'multi_choice':
        option_items = q_div.query_selector_all('div.ui-checkbox')
    else:
        option_items = q_div.query_selector_all('div.ui-radio')

    for opt_idx, opt_el in enumerate(option_items):
        # 选项文本在 div.label 中
        label_div = opt_el.query_selector('div.label')
        opt_text = label_div.inner_text().strip() if label_div else ''

        # 提取选项 key (A/B/C/D)
        opt_key = ''
        if opt_text:
            m = re.match(r'^([A-Da-d])[\s．.:：]', opt_text)
            if m:
                opt_key = m.group(1).upper()
                opt_text = opt_text[m.end():].strip()
        if not opt_key:
            opt_key = chr(65 + opt_idx)

        # 提取选项中的图片（在 div.option_picture 中）
        opt_imgs = []
        opt_pic_el = opt_el.query_selector('div.option_picture')
        if opt_pic_el:
            img_els = opt_pic_el.query_selector_all('img')
            for img_el in img_els:
                src = img_el.get_attribute('src') or ''
                data_src = img_el.get_attribute('data-src') or ''
                img_url = data_src or src
                if img_url and ('paperol' in img_url or img_url.startswith('http')):
                    opt_imgs.append(img_url)
        else:
            # 也检查选项中直接的 img
            img_els = opt_el.query_selector_all('img')
            for img_el in img_els:
                src = img_el.get_attribute('src') or ''
                data_src = img_el.get_attribute('data-src') or ''
                img_url = data_src or src
                if img_url and ('paperol' in img_url or img_url.startswith('http')):
                    opt_imgs.append(img_url)

        opt_md = opt_text
        for img_url in opt_imgs:
            local_name = download_image(img_url)
            if local_name:
                opt_md += f'\n![img](../assets/images/noc/{local_name})'

        if opt_md or opt_imgs:
            options.append({'key': opt_key, 'text': opt_md})

    # ===== 构建题目数据 =====
    if not content_md and not content_imgs and not options:
        return None

    question = {
        'type': q_type,
        'id': qid,
        'score': 2,
        'answer': '',  # 答案留空，用户手动填
        'content': content_md,
    }

    if options and q_type in ('choice', 'multi_choice'):
        question['options'] = options

    return question


def main():
    """主流程"""
    import sys
    
    # 支持命令行指定要抓取的 slug（如: python scrape_wjx.py noc-kitten-练习卷一）
    target_slugs = set(sys.argv[1:]) if len(sys.argv) > 1 else None
    
    print("🚀 开始抓取 NOC Kitten 试卷...")
    
    if target_slugs:
        print(f"   仅抓取: {', '.join(target_slugs)}")

    for paper_cfg in PAPERS:
        # 如果指定了目标 slug，跳过不在列表中的
        if target_slugs and paper_cfg['slug'] not in target_slugs:
            print(f"\n⏭️ 跳过: {paper_cfg['title']}")
            continue
        questions = scrape_paper(paper_cfg)

        # 按题型统计
        type_counts = {}
        img_count = 0
        for q in questions:
            t = q['type']
            type_counts[t] = type_counts.get(t, 0) + 1
            if '![' in q.get('content', ''):
                img_count += 1
            for opt in q.get('options', []):
                if '![' in opt.get('text', ''):
                    img_count += 1

        print(f"\n  📊 题型统计: {type_counts}, 含图片: {img_count}处")

        # 生成试卷 JSON
        paper_data = {
            'title': paper_cfg['title'],
            'category': 'OTHER',
            'level': 'NOC',
            'date': '2026-04',
            'time_limit': 60,
            'total_score': sum(q['score'] for q in questions),
            'description': 'NOC 全国中小学信息技术创新与实践大赛 Kitten 图形化编程',
            'questions': questions,
        }

        # 写入
        out_dir = BASE_DIR / 'papers' / paper_cfg['slug']
        out_dir.mkdir(parents=True, exist_ok=True)
        out_file = out_dir / 'index.json'
        with open(out_file, 'w', encoding='utf-8') as f:
            json.dump(paper_data, f, ensure_ascii=False, indent=2)

        print(f"  ✅ 已写入: {out_file.relative_to(BASE_DIR)}")
        print(f"  共 {len(questions)} 题, 总分 {paper_data['total_score']}")

    # 保存 URL 映射
    with open(MAP_FILE, 'w', encoding='utf-8') as f:
        json.dump(url_map, f, ensure_ascii=False, indent=2)
    print(f"\n📦 图片映射已保存: {MAP_FILE.name} ({len(url_map)} 张)")


if __name__ == '__main__':
    main()
