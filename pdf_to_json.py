#!/usr/bin/env python3
"""
将GESP C++试卷PDF批量转换为JSON格式
解析客观题（选择题+判断题），输出 papers/*/index.json
"""

import os
import re
import sys
import json
import warnings
import pdfplumber

warnings.filterwarnings('ignore')

PDF_DIR = os.path.join(os.path.dirname(__file__), "pdfs")
PAPERS_DIR = os.path.join(os.path.dirname(__file__), "papers")

CN_LEVEL = {"一级": 1, "二级": 2, "三级": 3, "四级": 4, "五级": 5, "六级": 6, "七级": 7, "八级": 8}


def extract_text(pdf_path):
    """提取PDF全文"""
    full_text = ""
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                full_text += text + "\n"
    return full_text


def parse_filename(filename):
    m = re.match(r"(\d{4})-(\d{2})-gesp-cpp-(\d+)\.pdf", filename)
    if not m:
        return None
    return {"year": int(m.group(1)), "month": int(m.group(2)), "level": int(m.group(3))}


def fix_cjk_radicals(text):
    """修复PDF中CJK偏旁部首替换为正常汉字"""
    replacements = {
        "⽉": "月", "⾏": "行", "⾥": "里", "⻚": "页", "⽅": "方",
        "⽤": "用", "⽬": "目", "⽂": "文", "⽆": "无", "⼊": "入",
        "⼤": "大", "⼩": "小", "⽐": "比", "⽔": "水", "⽚": "片",
        "⽣": "生", "⻓": "长", "⻔": "门", "⻋": "车", "⻛": "风",
        "⻜": "飞", "⻝": "食", "⾸": "首", "⾼": "高", "⾳": "音",
        "⼏": "几", "⼀": "一", "⼆": "二", "⼋": "八", "⼗": "十",
        "⼴": "广", "⼼": "心", "⼿": "手", "⽀": "支", "⽼": "老",
        "⾛": "走", "⾜": "足", "⾝": "身", "⾦": "金", "⻅": "见",
        "⻘": "青", "⻩": "黄", "⿇": "麻", "⿓": "龙", "⿔": "龟",
        "⽲": "禾", "⽳": "穴", "⽵": "竹", "⽶": "米", "⽷": "丝",
        "⽹": "网", "⽺": "羊", "⽻": "羽", "⽿": "耳", "⾁": "肉",
        "⾂": "臣", "⾃": "自", "⾄": "至", "⾈": "舟", "⾊": "色",
        "⾍": "虫", "⾐": "衣", "⾡": "走", "⾢": "邑", "⾣": "酉",
        "⾤": "采", "⾥": "里", "⾧": "长", "⾨": "门", "⾩": "阜",
        "⾪": "隶", "⾬": "雨", "⾭": "青", "⾮": "非", "⾯": "面",
        "⾰": "革", "⾱": "韭", "⾲": "齿", "⾳": "音", "⾴": "页",
        "⾵": "风", "⾶": "飞", "⾷": "食", "⾸": "首", "⾹": "香",
        "⾺": "马", "⾻": "骨", "⾼": "高", "⾽": "髟", "⾾": "鬥",
        "⾿": "鬯", "⿀": "鬲", "⿁": "鬼", "⿂": "鱼", "⿃": "鸟",
        "⿄": "卤", "⿅": "鹿", "⿆": "麦", "⿇": "麻", "⿈": "黄",
        "⿉": "黍", "⿊": "黑", "⿋": "黹", "⿌": "黾", "⿍": "鼎",
        "⿎": "鼓", "⿏": "鼠", "⿐": "鼻", "⿑": "齐", "⿒": "齿",
        "⿓": "龙", "⿔": "龟", "⿕": "龠",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text


def clean_text(text):
    text = fix_cjk_radicals(text)
    # 移除页码行
    text = re.sub(r"第\s*\d+\s*页\s*/\s*共\s*\d+\s*页", "", text)
    # 移除纯数字页码行（单行只有1-3位数字）
    text = re.sub(r"\n\d{1,3}\n", "\n", text)
    text = text.replace("\r\n", "\n")
    return text


def parse_answer_rows(text):
    """
    解析答案行，返回两个dict: choice_answers, judge_answers
    """
    choice_answers = {}
    judge_answers = {}
    
    lines = text.split("\n")
    i = 0
    while i < len(lines) - 1:
        line = lines[i].strip()
        next_line = lines[i + 1].strip() if i + 1 < len(lines) else ""
        
        # 匹配 "题号 ... \n 答案 ..." 模式
        if line.startswith("题号") and next_line.startswith("答案"):
            nums = re.findall(r"\d+", line)
            # 解析答案 - 在答案行中去掉"答案"前缀后逐字提取
            ans_part = next_line[2:].strip()  # 去掉"答案"
            ans_list = []
            for c in ans_part:
                if c in "ABCD":
                    ans_list.append(c)
                elif c in "√✓对":
                    ans_list.append("√")
                elif c in "×✗错":
                    ans_list.append("×")
            
            # 判断是选择题答案还是判断题答案
            if any(a in "ABCD" for a in ans_list):
                for idx, num in enumerate(nums):
                    if idx < len(ans_list):
                        choice_answers[int(num)] = ans_list[idx]
            elif any(a in "√×" for a in ans_list):
                for idx, num in enumerate(nums):
                    if idx < len(ans_list):
                        judge_answers[int(num)] = ans_list[idx]
            i += 2
        else:
            i += 1
    
    return choice_answers, judge_answers


def split_sections(text):
    """
    分割文本为选择题部分和判断题部分
    """
    # 移除编程题部分及之后的内容
    # 匹配 "3 编程题" "3.编程题" "三、编程题" 等
    text = re.sub(r"(?:\d+\.?\s*)?编程题.*", "", text, flags=re.DOTALL)
    
    # 查找判断题的开始位置
    # 匹配 "二、判断题" "2 判断题" "二 判断题" 等
    judge_pattern = r"(?:[一二三四五六七八九十]+[、.\s]*)?(?:\d+[\s.]*)?判断题"
    judge_match = re.search(judge_pattern, text)
    
    # 查找选择题的开始位置
    choice_pattern = r"(?:[一二三四五六七八九十]+[、.\s]*)?(?:\d+[\s.]*)?单选题"
    choice_match = re.search(choice_pattern, text)
    
    choice_text = ""
    judge_text = ""
    
    if choice_match and judge_match:
        choice_text = text[choice_match.end():judge_match.start()]
        judge_text = text[judge_match.end():]
    elif choice_match:
        choice_text = text[choice_match.end():]
    elif judge_match:
        judge_text = text[judge_match.end():]
    else:
        # 如果找不到明确的分区标题，尝试通过答案类型判断
        choice_text = text
        judge_text = ""
    
    # 清理答案行和题号行
    for t in [choice_text, judge_text]:
        t = re.sub(r"题号\s+[\d\s]+", "", t)
        t = re.sub(r"答案\s+[A-D√×✓✗对的错]+[\sA-D√×✓✗对的错的]*", "", t)
    
    return choice_text, judge_text


def parse_questions_from_section(text, q_type, answers, start_id=1):
    """
    从一段文本中解析题目
    q_type: "choice" 或 "judge"
    answers: 对应的答案dict
    start_id: 起始题目编号
    """
    questions = []
    
    # 移除答案行和题号行
    text = re.sub(r"题号\s+[\d\s]+\s*\n", "", text)
    text = re.sub(r"答案\s+[A-D√×✓✗对的错]+[\sA-D√×✓✗对的错的]*\s*\n", "", text)
    
    # 两种题目格式: "第 X 题" 或 "X."
    # 先试 "第 X 题"
    parts = re.split(r"第\s*(\d+)\s*题\s*", text)
    
    if len(parts) <= 3:
        # 再试 "X." 格式（但避免匹配小数如 3.14）
        parts = re.split(r"(?<![.\d])(\d{1,2})\.\s+", text)
    
    if len(parts) <= 3:
        return questions
    
    for i in range(1, len(parts), 2):
        try:
            q_num = int(parts[i])
        except ValueError:
            continue
        q_text = parts[i + 1].strip()
        
        if not q_text:
            continue
        
        answer = answers.get(q_num)
        
        if q_type == "choice":
            q = parse_choice_question(q_num, q_text, answer)
            if q:
                questions.append(q)
        else:
            q = parse_judge_question(q_num, q_text, answer)
            if q:
                questions.append(q)
    
    return questions


def parse_choice_question(q_num, q_text, answer):
    """解析选择题"""
    # 查找选项 A. B. C. D. (支持 A. A． A、格式)
    option_pattern = r"([A-D])[.．、:]\s*"
    option_matches = list(re.finditer(option_pattern, q_text))
    
    if len(option_matches) < 2:  # 至少2个选项才算选择题
        return None
    
    content = q_text[:option_matches[0].start()].strip()
    options = []
    
    for i, m in enumerate(option_matches):
        key = m.group(1)
        start = m.end()
        end = option_matches[i + 1].start() if i + 1 < len(option_matches) else len(q_text)
        opt_text = q_text[start:end].strip()
        # 清理尾部可能残留的下一个选项标记
        opt_text = re.sub(r"\s*[A-D][.．、:]\s*$", "", opt_text)
        options.append({"key": key, "text": opt_text})
    
    return {
        "type": "choice",
        "id": q_num,
        "score": 2,
        "answer": answer or "",
        "content": content,
        "options": options,
    }


def parse_judge_question(q_num, q_text, answer):
    """解析判断题"""
    # 判断题不应该有ABCD选项
    if re.search(r"[A-D][.．、:]\s*", q_text):
        return None
    
    # 转换答案
    if answer == "√":
        bool_answer = True
    elif answer == "×":
        bool_answer = False
    else:
        bool_answer = None  # 未知
    
    return {
        "type": "judge",
        "id": q_num,
        "score": 2,
        "answer": bool_answer,
        "content": q_text.strip(),
    }


def format_code_in_text(text):
    """检测并格式化文本中的代码"""
    lines = text.split("\n")
    has_line_numbers = any(re.match(r"^\d+\s+\S", line) for line in lines)
    
    if has_line_numbers:
        code_lines = []
        for line in lines:
            m = re.match(r"^\d+\s+(.*)", line)
            if m:
                code_lines.append(m.group(1))
            else:
                code_lines.append(line)
        return "```\n" + "\n".join(code_lines) + "\n```"
    
    # 检测是否看起来像代码（含花括号、分号等）
    code_indicators = sum(1 for line in lines if any(c in line for c in "{};()<>=+"))
    if code_indicators > len(lines) * 0.5 and len(lines) > 2:
        return "```\n" + text + "\n```"
    
    return text


def generate_json_data(info, questions):
    """生成 JSON 数据结构"""
    year = info["year"]
    month = info["month"]
    level = info["level"]

    date_str = f"{year}年{month}月"
    title = f"{date_str} GESP C++ {level}级"

    choice_qs = [q for q in questions if q["type"] == "choice"]
    judge_qs = [q for q in questions if q["type"] == "judge"]
    choice_score = len(choice_qs) * 2
    judge_score = len(judge_qs) * 2
    total_score = choice_score + judge_score

    # 统一格式化 questions
    formatted_questions = []
    for q in questions:
        fq = {
            "type": q["type"],
            "id": q["id"],
            "score": q.get("score", 2),
            "answer": str(q.get("answer", "")) if q.get("answer") is not None else "",
            "content": q.get("content", "").strip(),
        }
        if "options" in q and q["options"]:
            fq["options"] = [
                {"key": opt["key"], "text": opt["text"].strip()}
                for opt in q["options"]
            ]
        formatted_questions.append(fq)

    return {
        "title": title,
        "category": "GESP",
        "level": str(level),
        "date": f"{year}-{str(month).zfill(2)}",
        "time_limit": 60,
        "total_score": total_score,
        "description": f"{date_str} GESP C++ {level}级认证考试真题（客观题部分）",
        "questions": formatted_questions,
    }


def process_pdf(pdf_path):
    """处理单个PDF文件"""
    filename = os.path.basename(pdf_path)
    info = parse_filename(filename)
    if not info:
        print(f"SKIP: Cannot parse filename {filename}")
        return False

    text = extract_text(pdf_path)
    text = clean_text(text)

    if len(text) < 100:
        print(f"SKIP: Text too short ({len(text)} chars)")
        return False

    # 解析答案行（分别获取选择题和判断题答案）
    choice_answers, judge_answers = parse_answer_rows(text)
    
    # 合并答案（用于按段落解析时分配）
    all_answers = {}
    all_answers.update(choice_answers)
    all_answers.update(judge_answers)
    
    # 分割选择题和判断题文本段落
    choice_text, judge_text = split_sections(text)
    
    # 解析题目
    questions = []
    
    if choice_text:
        choice_qs = parse_questions_from_section(choice_text, "choice", choice_answers)
        questions.extend(choice_qs)
    
    if judge_text:
        judge_qs = parse_questions_from_section(judge_text, "judge", judge_answers)
        questions.extend(judge_qs)
    
    # 如果分区解析失败，尝试整体解析
    if not questions:
        questions = parse_questions_from_section(text, "choice", choice_answers)
        if questions:
            judge_qs = parse_questions_from_section(text, "judge", judge_answers)
            # 合并去重
    
    if not questions:
        print(f"SKIP: No questions parsed")
        return False

    # 生成 JSON 数据
    data = generate_json_data(info, questions)

    # 写入文件
    year = info["year"]
    month = str(info["month"]).zfill(2)
    level = info["level"]
    slug = f"{year}-{month}-gesp-{level}"
    paper_dir = os.path.join(PAPERS_DIR, slug)
    os.makedirs(paper_dir, exist_ok=True)
    json_path = os.path.join(paper_dir, "index.json")

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    choice_count = sum(1 for q in questions if q["type"] == "choice")
    judge_count = sum(1 for q in questions if q["type"] == "judge")
    print(f"OK: {slug} ({choice_count} choice + {judge_count} judge)")
    return True


def main():
    import argparse
    parser = argparse.ArgumentParser(description='将GESP C++试卷PDF批量转换为JSON格式')
    parser.add_argument('--force', action='store_true', help='强制重新解析（覆盖已有JSON）')
    parser.add_argument('--file', type=str, help='只解析指定PDF文件')
    args = parser.parse_args()

    if args.file:
        pdf_files = [args.file]
    else:
        pdf_files = sorted([f for f in os.listdir(PDF_DIR) if f.endswith(".pdf") and "gesp-cpp" in f])

    print(f"Found {len(pdf_files)} GESP C++ PDF files")
    if not args.force:
        print("(增量模式：跳过已有JSON，使用 --force 强制重新解析)")
    print()

    success = 0
    skipped = 0
    failed = []

    for i, filename in enumerate(pdf_files, 1):
        # 增量检测：如果已有对应 JSON，跳过
        if not args.force:
            info = parse_filename(filename)
            if info:
                slug = f"{info['year']}-{str(info['month']).zfill(2)}-gesp-{info['level']}"
                json_path = os.path.join(PAPERS_DIR, slug, "index.json")
                if os.path.exists(json_path):
                    skipped += 1
                    continue

        pdf_path = os.path.join(PDF_DIR, filename) if not os.path.isabs(filename) else filename
        print(f"[{i}/{len(pdf_files)}] {filename}...", end=" ")
        try:
            if process_pdf(pdf_path):
                success += 1
            else:
                failed.append(filename)
        except Exception as e:
            import traceback
            print(f"ERROR: {e}")
            traceback.print_exc()
            failed.append(filename)

    print(f"\nDone: {success} parsed, {skipped} skipped, {len(failed)} failed")
    if failed:
        print(f"Failed ({len(failed)}):")
        for f in failed:
            print(f"  - {f}")


if __name__ == "__main__":
    main()
