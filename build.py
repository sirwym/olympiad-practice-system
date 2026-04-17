#!/usr/bin/env python3
"""
静态考试系统生成器 - 类似 Hexo 的构建脚本
读取 papers/ 下的 JSON 文件，生成纯静态 HTML 到 dist/
"""

import os
import sys
import json
import shutil
import re
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

# ===== 配置 =====
BASE_DIR = Path(__file__).parent
PAPERS_DIR = BASE_DIR / "papers"
TEMPLATES_DIR = BASE_DIR / "templates"
DIST_DIR = BASE_DIR / "dist"

TEMPLATE_NAME = "paper.html"


def slugify(text: str) -> str:
    """将文本转为 URL 安全的 slug"""
    text = text.lower().strip()
    # 替换中文日期等常见模式
    text = re.sub(r'[年月]', '-', text)
    text = re.sub(r'[日号]', '', text)
    # 只保留字母、数字、中文、连字符
    text = re.sub(r'[^\w\u4e00-\u9fff-]', '-', text)
    text = re.sub(r'-+', '-', text)
    text = text.strip('-')
    return text


def discover_papers() -> list[dict]:
    """
    发现所有试卷。
    每个试卷是一个文件夹，包含 index.json 文件。
    返回 [{slug, metadata, paper_dir}, ...]
    """
    papers = []

    if not PAPERS_DIR.exists():
        print(f"❌ 试卷目录不存在: {PAPERS_DIR}")
        return papers

    for paper_dir in sorted(PAPERS_DIR.iterdir()):
        if not paper_dir.is_dir():
            continue

        json_file = paper_dir / "index.json"
        if not json_file.exists():
            print(f"⚠️  跳过 {paper_dir.name}：未找到 index.json")
            continue

        # 解析 JSON
        with open(json_file, 'r', encoding='utf-8') as f:
            metadata = json.load(f)

        # 使用文件夹名作为 slug
        slug = paper_dir.name

        # 验证必要字段
        if 'title' not in metadata:
            print(f"⚠️  跳过 {slug}：缺少 title 字段")
            continue
        if 'questions' not in metadata:
            print(f"⚠️  跳过 {slug}：缺少 questions 字段")
            continue

        papers.append({
            'slug': slug,
            'metadata': metadata,
            'paper_dir': paper_dir,
        })

    return papers


def extract_code_block(text: str) -> tuple[str, str] | tuple[None, None]:
    """从 content 中提取第一个 ``` 代码块，返回 (代码块内容, 去掉代码块后的剩余文本)"""
    match = re.search(r'```\s*\n(.*?)```', text, re.DOTALL)
    if not match:
        return None, None
    code = match.group(1).strip()
    # 去掉代码块及其前后空白，保留问题文字
    remaining = (text[:match.start()] + text[match.end():]).strip()
    return code, remaining


def render_markdown(text: str) -> str:
    """
    Markdown → HTML 转换，使用 markdown-it-py。
    代码块生成 <pre><code class="language-cpp"> 结构，
    配合模板中的 Prism.js 实现语法高亮。
    
    同时修复没有语言标识的代码块（CSP PDF 导入的代码块通常缺少标识）。
    """
    if not text:
        return ''

    from markdown_it import MarkdownIt

    # 预处理：给没有语言标识的代码块加上 cpp（修复代码高亮为红色的问题）
    # 注意：只匹配独立的 ``` 行（后面没有语言标识），且必须是代码块开头
    # 策略：匹配 ``` 后紧跟换行+非```行（即代码块开头），跳过代码块结尾的 ```
    # 更安全的做法：逐行扫描，跟踪代码块开关状态
    lines = text.split('\n')
    in_code_block = False
    result_lines = []
    for line in lines:
        stripped = line.strip()
        if not in_code_block:
            # 不在代码块内，检查是否是代码块开头
            if stripped.startswith('```') and len(stripped) == 3:
                # ``` 无语言标识，补上 cpp
                line = '```cpp'
                in_code_block = True
            elif stripped.startswith('```') and len(stripped) > 3:
                # 已有语言标识（如 ```cpp），直接进入代码块
                in_code_block = True
        else:
            # 在代码块内，检查是否是结尾
            if stripped == '```':
                in_code_block = False
        result_lines.append(line)
    text = '\n'.join(result_lines)

    md = MarkdownIt("commonmark", {
        "html": True,
        "breaks": True,
    })

    # 渲染
    html = md.render(text)

    return html


def process_questions(questions: list[dict]) -> list[dict]:
    """
    处理题目列表：
    1. 渲染 Markdown 内容
    2. 对阅读程序/完善程序的相邻同代码题目自动分组：
       - 提取共享代码到 shared_code 字段
       - content 中只保留问题文字（去掉重复代码）
       - 用 group_id 标记属于同一大题
       - 用 is_group_head 标记是否是大题首题（显示代码）
       - 用 is_group_last 标记是否是组内最后一题（关闭容器）
    """
    processed = []
    prev_code = None
    group_counter = 0
    
    # 先做第一遍扫描：确定每题的 group_id 和 shared_code
    group_info_list = []  # (group_id, has_shared_code)
    for q in questions:
        has_section = q.get('section') is not None
        is_reading_or_complete = has_section and ('阅读' in q.get('section', '') or '完善' in q.get('section', ''))
        
        if is_reading_or_complete and 'content' in q:
            raw_content = q['content']
            code, remaining = extract_code_block(raw_content)
            
            if code:
                if code == prev_code:
                    gid = f'g{group_counter}'
                    group_info_list.append((gid, False, remaining if remaining else ''))
                else:
                    group_counter += 1
                    prev_code = code
                    gid = f'g{group_counter}'
                    group_info_list.append((gid, True, code, remaining if remaining else ''))
            else:
                group_info_list.append((None, False, None))
                prev_code = None
        else:
            group_info_list.append((None, False, None))
            prev_code = None
    
    # 第二遍：标记每个 group 的最后一题
    next_group_last = set()
    for i, info in enumerate(group_info_list):
        gid = info[0]
        if gid is not None:
            # 检查下一题是否属于不同组或没有组
            if i + 1 >= len(group_info_list):
                next_group_last.add(i)
            elif group_info_list[i + 1][0] != gid:
                next_group_last.add(i)
    
    # 第三遍：构建最终列表
    for i, q_raw in enumerate(questions):
        q = dict(q_raw)
        info = group_info_list[i]
        gid = info[0]
        is_head = info[1] if len(info) >= 3 and gid is not None else False
        
        if gid is not None:
            q['group_id'] = gid
            q['is_group_head'] = is_head
            q['is_group_last'] = (i in next_group_last)
            if is_head:
                q['shared_code'] = info[2]  # 代码
                q['content'] = info[3] if len(info) > 3 and info[3] else ''  # 问题文字
            else:
                q['shared_code'] = None
                q['content'] = info[2] if len(info) > 2 else ''  # 剩余内容就是问题文字
        else:
            q['group_id'] = None
            q['is_group_head'] = False
            q['is_group_last'] = False
        
        # 渲染题干
        if 'content' in q and q['content']:
            q['content'] = render_markdown(q['content'])
        elif 'content' in q:
            q['content'] = ''
        
        # 渲染共享代码
        if q.get('shared_code'):
            q['shared_code'] = render_markdown('```cpp\n' + q['shared_code'] + '\n```')
        
        # 渲染选项文本
        if 'options' in q:
            q['options'] = [
                {**opt, 'text': render_markdown(opt['text'])}
                for opt in q['options']
            ]
        
        processed.append(q)
    return processed


def build_paper(paper: dict, env: Environment) -> str:
    """构建单份试卷 HTML"""
    template = env.get_template(TEMPLATE_NAME)
    metadata = paper['metadata']

    questions = process_questions(metadata.get('questions', []))

    html = template.render(
        paper=metadata,
        questions=questions,
        paper_slug=paper['slug'],
        is_nct_kitten=(metadata.get('category') == 'NCT-KITTEN'),
    )
    return html


def copy_assets(paper_dir: Path, output_dir: Path):
    """复制试卷目录下的图片等静态资源"""
    for item in paper_dir.iterdir():
        if item.name in ('index.json', 'index.md'):
            continue
        if item.is_dir():
            dest = output_dir / item.name
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(item, dest)
        else:
            shutil.copy2(item, output_dir / item.name)


def build_index(papers: list[dict], env: Environment) -> str:
    """生成试卷列表首页（使用 Jinja2 模板）"""
    import json

    paper_list = []
    categories = []
    levels = []
    cat_set = set()
    lvl_set = set()

    for p in papers:
        m = p['metadata']
        cat = m.get('category', '未分类')
        lvl = str(m.get('level', ''))
        cat_set.add(cat)
        if lvl:
            lvl_set.add(lvl)

        paper_list.append({
            'slug': p['slug'],
            'title': m.get('title', '未命名试卷'),
            'category': cat,
            'level': lvl,
            'date': m.get('date', ''),
            'total_score': m.get('total_score', 100),
            'time_limit': m.get('time_limit', 60),
            'description': m.get('description', ''),
            'question_count': len(m.get('questions', [])),
        })

    # 按日期倒序排列（最新在前）
    paper_list.sort(key=lambda p: p.get('date', ''), reverse=True)

    # 分类排序：GESP 优先，然后 CSP，然后 NCT，其余按字母
    cat_order = ['GESP', 'CSP-J', 'CSP-S', 'NCT-C++', 'NCT-KITTEN']
    categories = sorted(cat_set, key=lambda c: cat_order.index(c) if c in cat_order else 999)
    active_category = categories[0] if categories else ''

    # 级别排序（数字级别在前，非数字在后）
    levels = sorted(lvl_set, key=lambda l: int(l) if l.isdigit() else 999)

    # 分类显示名
    category_labels = {
        'GESP': 'GESP',
        'CSP-J': 'CSP-J（入门）',
        'CSP-S': 'CSP-S（提高）',
        'NCT-C++': 'NCT C++',
        'NCT-KITTEN': 'NCT KITTEN',
    }

    # 级别显示名
    level_labels = {}
    for lvl in levels:
        n = int(lvl) if lvl.isdigit() else 0
        if lvl.isdigit():
            level_labels[lvl] = f'{n}级'
        else:
            # CSP 级别直接使用原值（如 CSP-J, CSP-S）
            level_labels[lvl] = lvl

    # 分类颜色
    category_colors = {
        'GESP': 'bg-blue-50 text-blue-600',
        'CSP-J': 'bg-green-50 text-green-600',
        'CSP-S': 'bg-purple-50 text-purple-600',
        'NCT-C++': 'bg-orange-50 text-orange-600',
        'NCT-KITTEN': 'bg-pink-50 text-pink-600',
    }

    template = env.get_template('index.html')
    html = template.render(
        papers=paper_list,
        categories=categories,
        active_category=active_category,
        levels=levels,
        category_labels=category_labels,
        level_labels=level_labels,
        category_colors=category_colors,
        papers_json=json.dumps(paper_list, ensure_ascii=False),
        level_labels_json=json.dumps(level_labels, ensure_ascii=False),
    )
    return html


def build():
    """主构建流程"""
    print("🚀 开始构建静态考试系统...")
    print(f"   试卷目录: {PAPERS_DIR}")
    print(f"   输出目录: {DIST_DIR}")

    # 清理 dist/
    if DIST_DIR.exists():
        shutil.rmtree(DIST_DIR)
    DIST_DIR.mkdir(parents=True)

    # 复制本地静态资源
    ASSETS_DIR = BASE_DIR / "assets"
    if ASSETS_DIR.exists():
        shutil.copytree(ASSETS_DIR, DIST_DIR / "assets", dirs_exist_ok=True)
        print("   ✅ 复制本地资源 (assets/)")

    # 发现试卷
    papers = discover_papers()
    if not papers:
        print("❌ 未发现任何试卷，请检查 papers/ 目录")
        sys.exit(1)

    print(f"   发现 {len(papers)} 份试卷")

    # 初始化 Jinja2
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=False,  # 我们手动处理 HTML 转义
    )

    # 构建每份试卷
    for paper in papers:
        slug = paper['slug']
        print(f"\n📝 构建: {slug}")

        # 创建输出目录
        output_dir = DIST_DIR / slug
        output_dir.mkdir(parents=True)

        # 渲染 HTML
        html = build_paper(paper, env)

        # 写入文件
        output_file = output_dir / "index.html"
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(html)
        print(f"   ✅ {output_file.relative_to(DIST_DIR)}")

        # 复制静态资源
        copy_assets(paper['paper_dir'], output_dir)

    # 生成首页
    index_html = build_index(papers, env)
    index_file = DIST_DIR / "index.html"
    with open(index_file, 'w', encoding='utf-8') as f:
        f.write(index_html)
    print(f"\n📋 生成首页: index.html")

    print(f"\n✨ 构建完成！共 {len(papers)} 份试卷")
    print(f"   输出目录: {DIST_DIR}")
    print(f"   直接用浏览器打开 dist/index.html 即可使用")


if __name__ == "__main__":
    build()
