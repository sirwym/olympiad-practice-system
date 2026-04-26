#!/usr/bin/env python3
"""
NOC PDF 试卷导入工具（方案C：渲染截图 + 文字提取）
用法:
    python import_noc_pdfs.py [文件名]          # 处理指定PDF
    python import_noc_pdfs.py --all             # 处理所有 NOC PDF
"""

import json
import os
import re
import sys
import base64
from pathlib import Path

# 第三方库
try:
    import pdfplumber
    import fitz  # PyMuPDF
except ImportError:
    print("请安装依赖: pip install pdfplumber pymupdf")
    sys.exit(1)

# 项目路径
BASE_DIR = Path(__file__).parent
PAPERS_DIR = BASE_DIR / "papers"
IMAGES_DIR = BASE_DIR / "assets" / "images" / "noc"
RENDER_DIR = BASE_DIR / ".noc_render_cache"  # 渲染缓存目录

# PDF 文件列表（项目根目录下）
NOC_PDFS = [
    {
        "file": "2021NOC全国模拟考A卷解析（中学Kitten）.pdf",
        "title": "2021年NOCA卷模拟考（中学Kitten）",
        "slug": "noc-kitten-A卷-中学",
        "level": "",
    },
    {
        "file": "2021NOC全国模拟考A卷解析（小学Kitten）(1).pdf",
        "title": "2021年NOCA卷模拟考（小学Kitten）",
        "slug": "noc-kitten-A卷-小学",
        "level": "",
    },
    {
        "file": "2021NOC全国模拟考B卷（中学kitten）.pdf",
        "title": "2021年NOC B卷模拟考（中学Kitten）",
        "slug": "noc-kitten-B卷-中学",
        "level": "",
    },
    {
        "file": "2021NOC全国模拟考B卷（小学组Kitten）.pdf",
        "title": "2021年NOC B卷模拟考（小学Kitten）",
        "slug": "noc-kitten-B卷-小学",
        "level": "",
    },
]


def render_pages(pdf_path: str, slug: str, dpi: int = 200) -> list[str]:
    """
    使用 PyMuPDF 渲染每一页为 PNG，返回图片路径列表。
    缓存到 .noc_render_cache/ 目录避免重复渲染。
    """
    cache_dir = RENDER_DIR / slug
    cache_dir.mkdir(parents=True, exist_ok=True)

    doc = fitz.open(pdf_path)
    img_paths = []
    for i in range(len(doc)):
        img_path = cache_dir / f"page_{i+1:02d}.png"
        if img_path.exists():
            # 已有缓存
            img_paths.append(str(img_path))
            continue

        page = doc[i]
        pix = page.get_pixmap(dpi=dpi)
        pix.save(str(img_path))
        img_paths.append(str(img_path))
        print(f"    📄 渲染第 {i+1}/{len(doc)} 页 → {img_path.name}")

    doc.close()
    return img_paths


def extract_text_and_images(pdf_path: str) -> tuple[str, list[dict]]:
    """
    使用 pdfplumber 提取全文字和图片位置信息。
    返回 (全部文本, 图片信息列表)
    """
    all_text = ""
    images_info = []

    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages):
            text = page.extract_text() or ""
            all_text += text + "\n"

            # 记录图片位置和尺寸
            for j, img in enumerate(page.images):
                images_info.append({
                    "page": i,
                    "index": j,
                    "x0": round(img["x0"], 1),
                    "top": round(img["top"], 1),
                    "x1": round(img["x1"], 1),
                    "bottom": round(img["bottom"], 1),
                    "width": round(img["x1"] - img["x0"], 1),
                    "height": round(img["bottom"] - img["top"], 1),
                })

    return all_text, images_info


def crop_image_from_page(pdf_path: str, page_num: int, bbox: tuple, output_path: str):
    """从指定页面裁切一个区域保存为 PNG"""
    doc = fitz.open(pdf_path)
    page = doc[page_num]

    # fitz 坐标系：bbox = (x0, y0, x1, y1)
    rect = fitz.Rect(bbox)

    # 裁切并保存
    mat = fitz.Matrix(2, 2)  # 放大2倍保证清晰度
    clip = page.get_pixmap(matrix=mat, clip=rect)
    clip.save(output_path)
    doc.close()


def parse_questions(all_text: str, images_info: list[dict], pdf_path: str, slug: str,
                    page_text_positions: list[dict] = None, total_pages: int = 0) -> list[dict]:
    """
    从提取的文本中解析题目，并将图片匹配到对应题目。
    
    解析策略:
    1. 按题号分割文本块（单选 1-10, 多选 11-15, 填空 16-25）
    2. 根据题号所在页面的 Y 坐标范围匹配图片
    3. 裁切图片并保存
    """
    questions = []

    # === 提取答案 ===
    # 格式1: "1.答案：A" 或 "1.答案:A"
    answers_v1 = dict(re.findall(r'(\d+)\.\s*答案[：:]\s*([^\n]{1,20})', all_text))
    # 格式2: "1.B" 或 "1.ACD" （A卷中学格式）
    answers_v2 = {}
    v2_matches = re.findall(r'^(\d+)\.([A-F]{1,4})(?:\s|$)', all_text, re.MULTILINE)
    for qid, ans in v2_matches:
        if qid not in answers_v1:  # 不覆盖格式1的结果
            answers_v2[qid] = ans

    # 合并两种格式的答案
    all_answers = {**answers_v2, **answers_v1}

    print(f"    ✅ 提取到 {len(all_answers)} 个答案")

    # === 分题型解析 ===
    # 单选题 1-10
    for qid in range(1, 11):
        q = parse_choice_question(qid, all_text, all_answers, images_info, pdf_path, slug,
                                   page_text_positions, total_pages)
        if q:
            questions.append(q)

    # 判断/多选题 11-15（看答案长度判断）
    for qid in range(11, 16):
        ans = str(all_answers.get(str(qid), ""))
        # 多选答案特征：长度>1 且全是字母（如 ACD, AB）
        if len(ans) >= 2 and all(c.isalpha() and c in 'ABCDEF' for c in ans):
            # 多选
            q = parse_multi_question(qid, all_text, all_answers, images_info, pdf_path, slug,
                                     page_text_positions, total_pages)
        else:
            # 可能是判断或单选
            q = parse_choice_question(qid, all_text, all_answers, images_info, pdf_path, slug,
                                       page_text_positions, total_pages)
        if q:
            questions.append(q)

    # 填空题 16-25
    for qid in range(16, 26):
        q = parse_fill_question(qid, all_text, all_answers, images_info, pdf_path, slug,
                                 page_text_positions, total_pages)
        if q:
            questions.append(q)

    return questions


def find_question_region(text: str, qid: int) -> dict:
    """
    找到题号在文本中的位置，返回该题目的大致区域信息。
    用于匹配图片。
    返回: {"start_pos": int, "end_pos": int, "page_hint": int}
    """
    # 找题号的起始位置
    patterns = [
        rf'^{qid}\.\s*答案[：:]',
        rf'^{qid}\.\s*([A-Z])\s',
        rf'^{qid}\s*[\.．]',
        rf'\n{qid}\.\s',
    ]
    start_pos = -1
    for pat in patterns:
        m = re.search(pat, text, re.MULTILINE)
        if m:
            start_pos = m.start()
            break

    if start_pos < 0:
        return {"start_pos": -1, "end_pos": -1, "page_hint": -1}

    # 找下一题的位置作为结束
    next_qid = qid + 1
    end_patterns = [
        rf'\n{next_qid}\.',
        rf'\n{next_qid}\s*[\.．]',
        rf'\n{next_qid}\s*答案[：:]',
        r'\n三、填空题',
        r'\n二、判断题',
    ]
    end_pos = len(text)
    for pat in end_patterns:
        m = re.search(pat, text[start_pos:])
        if m:
            end_pos = start_pos + m.start()
            break

    return {"start_pos": start_pos, "end_pos": end_pos, "page_hint": qid}


def match_images_to_question(qid: int, images_info: list[dict], 
                              page_text_positions: list[dict],
                              total_pages: int, all_text: str) -> list[dict]:
    """
    根据题号的页面位置和 Y 坐标，精确匹配属于该题的图片。
    
    策略:
    1. 从 page_text_positions 中找到 qid 所在的页面和 Y 坐标
    2. 找到下一题的位置作为结束边界
    3. 匹配该页面范围内 Y 坐标落在 [qid_Y, next_qid_Y) 区间内的图片
    """
    matched = []
    
    # 找到当前题和下一题的文本位置
    current_pos = None
    next_pos = None
    
    for pos in page_text_positions:
        text = pos["text"].strip()
        # 匹配 "1." 或 "11." 等题号格式
        if re.match(rf'^{qid}[\.．\s]', text):
            if current_pos is None:
                current_pos = pos
            continue
        # 如果已找到当前题号，找下一个更大的题号
        if current_pos is not None and next_pos is None:
            m = re.match(r'^(\d+)[\.．\s]', text)
            if m and int(m.group(1)) > qid:
                next_pos = pos
                break
    
    if not current_pos:
        return []
    
    current_page = current_pos["page"]
    current_y = current_pos["top"]
    
    next_page = total_pages
    next_y = 99999
    if next_pos:
        next_page = next_pos["page"]
        next_y = next_pos["top"]
    
    # 收集匹配范围内的图片
    for img in images_info:
        img_page = img["page"]
        
        if img_page < current_page:
            continue
        if img_page > next_page:
            continue
        
        # 同页面：检查 Y 坐标是否在范围内
        if img_page == current_page:
            if img["top"] >= current_y - 50:  # 允许一定误差
                if next_page == current_page and img["top"] >= next_y:
                    continue
                matched.append(img)
        elif img_page == next_page:
            # 跨页的情况：下一页的图片如果在下一题之前也算
            if img["top"] < next_y:
                matched.append(img)
        else:
            # 中间的页面全部算进去
            matched.append(img)
    
    return matched


def extract_page_text_positions(pdf_path: str) -> list[dict]:
    """
    使用 pdfplumber 提取每页的文本块及其位置。
    返回包含 {page, top, left, text} 的列表。
    """
    positions = []
    
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages):
            words = page.extract_words() or []
            for w in words:
                positions.append({
                    "page": i,
                    "top": round(w["top"], 1),
                    "left": round(w["x0"], 1),
                    "text": w["text"],
                })
    
    return positions


def clean_content(raw: str) -> str:
    """清理题干文本"""
    # NFKC 归一化（兼容字符如 ⼩→小, ⽂→文）
    raw = unic_normalize(raw)
    # 清理多余空白
    raw = re.sub(r'[ \t]+', ' ', raw)
    raw = re.sub(r'\n{3,}', '\n\n', raw).strip()
    return raw


def unic_normalize(s: str) -> str:
    """Unicode NFKC 归一化"""
    import unicodedata
    return unicodedata.normalize('NFKC', s)


def append_images_to_content(qid: int, images_info: list[dict], pdf_path: str,
                             slug: str, page_text_positions: list[dict],
                             total_pages: int, all_text: str,
                             base_content: str) -> str:
    """
    裁切匹配到的图片，用 markdown 格式追加到 content 末尾。
    返回拼接后的完整 content 字符串。
    """
    matched_imgs = match_images_to_question(
        qid, images_info, page_text_positions or [], total_pages, all_text
    )

    img_dir = IMAGES_DIR / slug
    img_dir.mkdir(parents=True, exist_ok=True)

    for idx, img_info in enumerate(matched_imgs):
        img_name = f"q{qid}_{idx}.png"
        img_path = img_dir / img_name
        crop_image_from_page(
            pdf_path, img_info["page"],
            (img_info["x0"], img_info["top"], img_info["x1"], img_info["bottom"]),
            str(img_path)
        )
        # 用 markdown 图片语法追加到 content（和问卷星抓取方式一致）
        base_content += f"\n![img](assets/images/noc/{slug}/{img_name})\n"

    if matched_imgs:
        print(f"       + {len(matched_imgs)} 张图片")
    return base_content


def parse_choice_question(qid: int, all_text: str, answers: dict,
                          images_info: list[dict], pdf_path: str, slug: str,
                          page_text_positions: list[dict] = None,
                          total_pages: int = 0) -> dict | None:
    """解析一道选择题（单选/判断）"""
    region = find_question_region(all_text, qid)
    if region["start_pos"] < 0:
        print(f"    ⚠️ Q{qid}: 未找到题号")
        return None

    content_block = all_text[region["start_pos"]:region["end_pos"]]

    # 提取题干（去掉答案行和选项前的标记）
    lines = content_block.split('\n')
    question_text = []
    options = []

    for line in lines:
        line_stripped = line.strip()
        # 跳过答案行
        if re.match(rf'^{qid}\.\s*答案[：:]', line_stripped):
            continue
        # 跳过纯答案格式行（如 "1.B"）
        if re.match(rf'^{qid}\.\s*[A-F]\s*$', line_stripped):
            continue
        # 选项行
        opt_match = re.match(r'^([A-D])[\.．、\s](.+)$', line_stripped)
        if opt_match:
            options.append({"key": opt_match.group(1), "text": clean_content(opt_match.group(2))})
            continue
        # 跳过解析
        if line_stripped.startswith('解析') or line_stripped.startswith('注'):
            continue
        # 跳过空的选项占位符
        if line_stripped in ('A.', 'B.', 'C.', 'D.'):
            continue
        # 正常内容
        if line_stripped:
            question_text.append(clean_content(line_stripped))

    # 如果没有从文本中提取到选项，但有 A/B/C/D 标记的行
    if not options:
        # 尝试更宽松的匹配
        for line in lines:
            m = re.search(r'\b([A-D])[\.\s]+(.+?)$', line.strip())
            if m and len(m.group(2)) > 0 and len(m.group(2)) < 50:
                options.append({"key": m.group(1), "text": clean_content(m.group(2))})

    answer = str(answers.get(str(qid), ""))

    # 拼接基础内容
    base_content = "\n".join(question_text) if question_text else f"第{qid}题"

    # 裁切图片并追加到 content
    content_with_images = append_images_to_content(
        qid, images_info, pdf_path, slug, page_text_positions or [], total_pages, all_text,
        base_content
    )

    opt_note = f"{len(options)}选项" if options else "无选项"

    result = {
        "type": "choice",
        "id": qid,
        "score": 2 if qid <= 15 else 0,  # 选择题2分，填空题单独算
        "answer": answer,
        "content": content_with_images,
        "options": options if options else [],
    }

    print(f"    Q{qid} [{result['type']:6s}] {opt_note} answer={answer}")
    return result


def parse_multi_question(qid: int, all_text: str, answers: dict,
                         images_info: list[dict], pdf_path: str, slug: str,
                         page_text_positions: list[dict] = None,
                         total_pages: int = 0) -> dict | None:
    """解析多选题"""
    q = parse_choice_question(qid, all_text, answers, images_info, pdf_path, slug,
                               page_text_positions, total_pages)
    if q:
        q["type"] = "multi_choice"
        q["score"] = 4
    return q


def parse_fill_question(qid: int, all_text: str, answers: dict,
                        images_info: list[dict], pdf_path: str, slug: str,
                        page_text_positions: list[dict] = None,
                        total_pages: int = 0) -> dict | None:
    """解析填空题"""
    region = find_question_region(all_text, qid)
    if region["start_pos"] < 0:
        print(f"    ⚠️ Q{qid}: 未找到题号")
        return None

    content_block = all_text[region["start_pos"]:region["end_pos"]]
    lines = content_block.split('\n')

    question_text = []
    answer = ""

    for line in lines:
        line_stripped = line.strip()
        # 答案行
        ans_match = re.match(rf'^{qid}\.\s*(?:答案)?[：:?\s]*([^\n]+?)(?:$|\n)', line_stripped)
        if ans_match:
            potential_ans = ans_match.group(1).strip()
            # 排除明显不是答案的内容
            if not potential_ans.startswith('下列') and \
               not potential_ans.startswith('运行') and \
               not potential_ans.startswith('下图') and \
               len(potential_ans) < 30:
                answer = potential_ans
                continue
        if line_stripped.startswith('解析') or line_stripped.startswith('注'):
            continue
        if line_stripped and len(line_stripped) > 1:
            question_text.append(clean_content(line_stripped))

    # 拼接基础内容
    base_content = "\n".join(question_text) if question_text else f"第{qid}题"

    # 裁切图片并追加到 content
    content_with_images = append_images_to_content(
        qid, images_info, pdf_path, slug, page_text_positions or [], total_pages, all_text,
        base_content
    )

    result = {
        "type": "fill",
        "id": qid,
        "score": 2,
        "answer": answer,
        "content": content_with_images,
        "options": [],
    }

    print(f"    Q{qid} [{'fill':6s}] answer=\"{answer}\"")
    return result


def process_pdf(pdf_config: dict) -> str:
    """处理单个 PDF 文件，返回生成的 JSON 路径"""
    pdf_file = BASE_DIR / pdf_config["file"]
    slug = pdf_config["slug"]
    title = pdf_config["title"]
    level = pdf_config["level"]

    if not pdf_file.exists():
        print(f"❌ 文件不存在: {pdf_file}")
        return ""

    print(f"\n{'='*60}")
    print(f"📝 处理: {title}")
    print(f"   文件: {pdf_file.name}")
    print(f"   Slug: {slug}")
    print(f"{'='*60}")

    # Step 1: 渲染页面截图（用于 AI 辅助审查）
    print("\n📷 Step 1: 渲染页面...")
    render_paths = render_pages(str(pdf_file), slug)

    # Step 2: 提取文本和图片位置
    print("📄 Step 2: 提取文本和图片信息...")
    all_text, images_info = extract_text_and_images(str(pdf_file))
    
    # 提取每页文本块位置（用于精确定位题号）
    page_text_positions = extract_page_text_positions(str(pdf_file))
    print(f"    总文字: {len(all_text)} 字符, 图片: {len(images_info)} 张, 文本位置: {len(page_text_positions)} 条")

    # Step 3: 解析题目
    print("🔍 Step 3: 解析题目...")
    
    # 获取总页数
    doc = fitz.open(str(pdf_file))
    total_pages = len(doc)
    doc.close()
    
    questions = parse_questions(all_text, images_info, str(pdf_file), slug,
                                page_text_positions, total_pages)

    if not questions:
        print("❌ 未解析到任何题目!")
        return ""

    # 统计图片
    total_imgs = sum(len(q.get("images", [])) for q in questions)

    # Step 4: 生成 JSON
    paper_data = {
        "title": title,
        "category": "NOC",
        "level": level,
        "date": "2021",
        "time_limit": 120,
        "total_score": sum(q["score"] for q in questions),
        "description": f"NOC 全国青少年编程能力竞赛模拟考 · {level}",
        "questions": questions,
    }

    # 写入 JSON
    output_dir = PAPERS_DIR / slug
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "index.json"

    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(paper_data, f, ensure_ascii=False, indent=2)

    print(f"\n✅ 完成! {len(questions)} 题 ({total_imgs} 张图片)")
    print(f"   JSON: {json_path}")

    return str(json_path)


def main():
    args = sys.argv[1:]
    target_slug = None

    if "--all" in args:
        target_pdf_configs = NOC_PDFS
    elif args:
        # 查找匹配的 PDF
        target_name = args[0].lower()
        target_pdf_configs = [
            p for p in NOC_PDFS
            if target_name in p["slug"].lower()
            or target_name in p["title"].lower()
            or target_name in p["file"].lower()
        ]
        if not target_pdf_configs:
            print(f"❌ 未找到匹配的 PDF: '{args[0]}'")
            print(f"   可选: {', '.join(p['slug'] for p in NOC_PDFS)}")
            return
    else:
        # 默认处理第一个未处理的
        target_pdf_configs = NOC_PDFS[:1]

    results = []
    for cfg in target_pdf_configs:
        result = process_pdf(cfg)
        if result:
            results.append(result)

    print(f"\n🎉 全部完成! 处理了 {len(results)} 份试卷")


if __name__ == "__main__":
    main()
