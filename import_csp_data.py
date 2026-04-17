#!/usr/bin/env python3
"""
从外部 data 目录导入 CSP 试卷（sections 格式），转换为 papers/ 下的 questions 扁平格式。

外部 data 格式:
  sections[] → code_blocks[] → sub_questions[]

目标 papers 格式:
  questions[] 扁平列表，每题有 section 字段，
  阅读程序/完善程序的代码嵌入 content 的 ``` 代码块中。
"""

import json
import os
import shutil
from pathlib import Path

DATA_DIR = Path("/Users/mymac/Downloads/data")
PAPERS_DIR = Path(__file__).parent / "papers"

# section.type → section 名称映射
SECTION_TYPE_MAP = {
    "single_choice": "单项选择题",
    "program_reading": "阅读程序",
    "program_completion": "完善程序",
}

# section.type → question.type 映射
SECTION_QTYPE_MAP = {
    "single_choice": "choice",
    "program_reading": "choice",  # 子题可能是 choice 或 judge
    "program_completion": "choice",
}


def determine_question_type(sub_q: dict, section_type: str) -> str:
    """
    判断子题类型：
    - 单项选择题 → choice
    - 阅读程序/完善程序中，选项只有"正确/错误"两个 → judge
    - 其他 → choice
    """
    if section_type == "single_choice":
        return "choice"

    options = sub_q.get("options", [])
    if len(options) == 2:
        texts = [opt.get("text", "").strip() for opt in options]
        if "正确" in texts[0] or "错误" in texts[1] or "错误" in texts[0] or "正确" in texts[1]:
            return "judge"

    return "choice"


def convert_paper(data: dict) -> dict:
    """将外部 data 格式转换为 papers 的 questions 扁平格式"""
    questions = []
    question_id = 0

    for section in data.get("sections", []):
        section_type = section.get("type", "single_choice")
        section_name = section.get("section", SECTION_TYPE_MAP.get(section_type, ""))

        if section_type == "single_choice":
            # 单项选择题：直接展平
            for sub_q in section.get("sub_questions", []):
                question_id += 1
                q = {
                    "type": "choice",
                    "id": sub_q.get("sub_id", question_id),
                    "section": section_name,
                    "score": sub_q.get("score", 2),
                    "answer": sub_q.get("answer") if sub_q.get("answer") is not None else "None",
                    "content": sub_q.get("content", ""),
                    "options": sub_q.get("options", []),
                }
                questions.append(q)

        elif section_type in ("program_reading", "program_completion"):
            # 阅读程序/完善程序：遍历 code_blocks
            for code_block in section.get("code_blocks", []):
                code = code_block.get("code", "")
                title = code_block.get("title", "")
                description = code_block.get("description", "")

                for sub_q in code_block.get("sub_questions", []):
                    question_id += 1
                    q_type = determine_question_type(sub_q, section_type)

                    # 将代码块嵌入 content
                    content_parts = []
                    if description and section_type == "program_completion":
                        # 完善程序的 description 通常包含问题描述，放在代码块前面
                        # 但对于子题来说，description 已经在 code_block 层面，不需要每个子题都重复
                        pass

                    # 代码块用 ``` 包裹
                    if code:
                        content_parts.append(f"```\n{code}\n```")
                        content_parts.append("")  # 空行

                    # 子题题干
                    sub_content = sub_q.get("content", "")
                    if sub_content:
                        content_parts.append(sub_content)

                    content = "\n".join(content_parts)

                    q = {
                        "type": q_type,
                        "id": sub_q.get("sub_id", question_id),
                        "section": section_name,
                        "score": sub_q.get("score", 2),
                        "answer": sub_q.get("answer") if sub_q.get("answer") is not None else "None",
                        "content": content,
                        "options": sub_q.get("options", []),
                    }

                    # 对于 judge 类型，调整选项答案逻辑
                    # 外部数据中 judge 题的 answer 是 null，选项是 A=正确 B=错误
                    # 我们保持原样，让前端 judge 检测逻辑处理

                    questions.append(q)

    # 构建最终的 paper JSON
    paper = {
        "title": data.get("title", ""),
        "category": data.get("category", ""),
        "level": data.get("level", ""),
        "date": data.get("date", ""),
        "time_limit": data.get("time_limit", 120),
        "total_score": data.get("total_score", 100),
        "description": data.get("description", ""),
        "questions": questions,
    }

    return paper


def slugify_paper(data: dict) -> str:
    """根据试卷信息生成 URL slug"""
    category = data.get("category", "").lower()
    date = data.get("date", "")
    year = date.split("-")[0] if date else ""

    # CSP-J 2024 → csp-j-2024
    return f"{category}-{year}"


def main():
    print("🚀 开始从外部 data 目录导入 CSP 试卷...")

    # 先删除旧的 CSP 试卷
    print("\n📁 删除旧的 CSP 试卷...")
    old_count = 0
    for paper_dir in sorted(PAPERS_DIR.iterdir()):
        if not paper_dir.is_dir():
            continue
        if paper_dir.name.startswith("csp-"):
            shutil.rmtree(paper_dir)
            print(f"   🗑️  删除: {paper_dir.name}")
            old_count += 1
    print(f"   共删除 {old_count} 份旧 CSP 试卷")

    # 导入外部 data
    print("\n📥 导入外部 data...")
    new_count = 0

    for category_dir in sorted(DATA_DIR.iterdir()):
        if not category_dir.is_dir():
            continue
        category = category_dir.name  # csp-j 或 csp-s

        for json_file in sorted(category_dir.glob("*.json")):
            with open(json_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            # 转换格式
            paper = convert_paper(data)

            # 生成 slug
            slug = slugify_paper(data)

            # 创建输出目录
            out_dir = PAPERS_DIR / slug
            out_dir.mkdir(parents=True, exist_ok=True)

            # 写入 JSON
            out_file = out_dir / "index.json"
            with open(out_file, "w", encoding="utf-8") as f:
                json.dump(paper, f, ensure_ascii=False, indent=2)

            q_count = len(paper["questions"])
            print(f"   ✅ {slug} ({q_count} 题) ← {json_file.name}")
            new_count += 1

    print(f"\n✨ 导入完成！共导入 {new_count} 份 CSP 试卷")


if __name__ == "__main__":
    main()
