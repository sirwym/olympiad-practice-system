#!/usr/bin/env python3
"""
GESP 试卷格式化脚本（DeepSeek API 版）
使用 DeepSeek V3.2 大模型对题干和选项文本进行格式化。

规则：
1. C++ 关键字/类型/函数名/小代码片段 → `反引号` 包裹
2. 数学变量/公式/有数学含义的数字 → $...$ 包裹
3. 去掉文本段落中间不必要的 \n（PDF 排版换行残留）
4. ```cpp 代码块中 for/if/while 无花括号时，下一行缩进 4 空格
5. 不改变题意，不增删内容

用法:
  python3 format_gesp.py [--dry-run] [--force] [--paper PAPER_NAME]
  
选项:
  --dry-run         只输出变更，不写文件
  --force           强制处理包括标杆 2026-03-gesp-2
  --paper NAME      只处理指定试卷（如 2023-03-gesp-1）
  --concurrency N   并发请求数（默认 5）
"""

import json
import re
import sys
import os
import time
import argparse
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from openai import OpenAI

# ============================================================
# DeepSeek API 配置
# ============================================================
API_KEY = os.environ.get("DEEPSEEK_API_KEY", "sk-947103cf9b5044cca8b2d837ecf7b884")
BASE_URL = "https://api.deepseek.com"
MODEL = "deepseek-chat"  # DeepSeek V3.2

client = OpenAI(api_key=API_KEY, base_url=BASE_URL)

# ============================================================
# 系统提示词（固定，可利用缓存命中）
# ============================================================
SYSTEM_PROMPT = """你是一个 GESP C++ 考试试卷文本格式化助手。你的任务是将原始题干和选项文本按以下规则格式化，使其在 Markdown 渲染后更专业、更易读。

## 格式化规则

### 规则1：C++ 关键字/类型/函数名/小代码片段 → 反引号
- C++ 类型名：`int`、`char`、`bool`、`float`、`double`、`void`、`long`、`short`、`unsigned`、`string`
- C++ 关键字：`if`、`else`、`for`、`while`、`do`、`switch`、`case`、`break`、`continue`、`return`、`const`、`static`、`true`、`false`
- C++ 标准库对象/函数：`cout`、`cin`、`endl`、`main`、`sqrt`、`abs`、`pow`、`vector`、`sort`、`swap`、`max`、`min`
- 运算符作为概念提及时：`&&`、`||`、`!`、`++`、`--`、`+=`、`-=`、`==`、`!=`、`>=`、`<=`
- 小代码片段：如 `a = b`、`a++`、`i++`、`a *= 3`、`a %= 4`、`(int)b`、`(char)a` 等
- 注意：已在 ```cpp 代码块内的内容不要加反引号

### 规则2：数学变量/公式/有数学含义的数字 → $...$
- 单字母变量名：$a$、$b$、$c$、$N$、$M$、$n$、$m$、$i$、$j$ 等
- 数学表达式：$a + b$、$a \times b$、$2^n$、$n^2$ 等
- 有数学含义的数字：$0$、$1$、$2$、$3$ 等（但"第1题"中的1不包裹，"4GB"中的4不包裹，"3.5"这种浮点数不强制包裹）
- 范围表达：$1 \leq n \leq 100$、$0 \leq a \leq 255$
- 注意：不要包裹已在反引号或代码块内的变量

### 规则3：去掉段落中间不必要的换行
- PDF 解析残留的换行：如 "则下列哪个表\n达式" → "则下列哪个表达式"
- "如果 a为int类型\n的变量" → "如果 $a$ 为 `int` 类型的变量"
- 保留代码块内的换行和段落间的空行（\n\n）

### 规则4：代码块缩进修复
- ```cpp 代码块中，for/while/if 语句没有花括号时，其下一行语句应缩进 4 空格
- 如：
```cpp
for (int i = 0; i < n; i++)
    cout << i;  // 已缩进，保持
```
- 如果没有缩进，则补上

### 规则5：其他清理
- 去掉题干末尾多余的 \n
- 去掉判断题末尾可能残留的 "三、" 等标记
- 反引号与中文字符之间加一个空格：`int` 类型、变量 `a`
- $...$ 与中文之间加一个空格：$a$ 的值、$n$ 个

## 标杆样例

以下是已格式化的题目样例，请参照其风格：

**样例1 - 选择题题干：**
输入：下面 C++ 代码可以执行，有关说法正确的是( )。
输出：下面 C++ 代码可以执行，有关说法正确的是( )。

**样例2 - 选项文本：**
输入：C++的+运算符在处理小数时存在bug
输出：C++ 的 `+` 运算符在处理小数时存在 bug

**样例3 - 含变量和数学：**
输入：0.1 、0.2 和 0.3 在计算机中无法用二进制浮点数精确表示，导致 0.1 + 0.2 的结果与 0.3 存在微小误差
输出：$0.1$ 、$0.2$ 和 $0.3$ 在计算机中无法用二进制浮点数精确表示，导致 $0.1 + 0.2$ 的结果与 $0.3$ 存在微小误差

**样例4 - 含代码片段的选项：**
输入：x <= 5 && y > 10
输出：`x <= 5 && y > 10`

**样例5 - 变量描述：**
输入：如果 a为int类型的变量，且 a的值为 6
输出：如果 $a$ 为 `int` 类型的变量，且 $a$ 的值为 $6$

**样例6 - 含代码块的题干：**
输入：下面代码用来找出输入的 N 个正整数中最大的一个。
```cpp
int N, max=0, val;
cin >> N;
while(N){
    cin >> val;
    if(val > max)
    max = val;
    N--;
}
cout << max;
```
输出：下面代码用来找出输入的 $N$ 个正整数中最大的一个。

```cpp
int N, max=0, val;
cin >> N;
while(N){
    cin >> val;
    if(val > max)
        max = val;
    N--;
}
cout << max;
```

## 输出格式

你将收到一个 JSON 对象，包含 "content"（题干）和 "options"（选项数组，每项有 key 和 text）。
请返回相同结构的 JSON，只修改 content 和 options 中的 text 字段。
不要修改 key、answer、id、score 等其他字段。
不要修改 ```cpp 代码块内部的代码逻辑，只做缩进修复。
确保输出是合法的 JSON。
"""

# 用户提示词模板（每次不同，不会命中缓存）
USER_PROMPT_TEMPLATE = """请格式化以下 GESP 考试题目：

{question_json}

请按规则格式化后返回 JSON，只修改 content 和 options 中的 text 字段。"""


def call_deepseek(question_data, max_retries=3):
    """调用 DeepSeek API 格式化一道题"""
    q_json = json.dumps(question_data, ensure_ascii=False, indent=2)
    user_prompt = USER_PROMPT_TEMPLATE.format(question_json=q_json)
    
    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(
                model=MODEL,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.1,  # 低温度，减少随机性
                max_tokens=2000,
                response_format={"type": "json_object"},
            )
            
            result_text = response.choices[0].message.content.strip()
            result = json.loads(result_text)
            return result
            
        except json.JSONDecodeError as e:
            print(f"    ⚠️ JSON 解析失败 (尝试 {attempt+1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                time.sleep(1)
        except Exception as e:
            print(f"    ⚠️ API 调用失败 (尝试 {attempt+1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                time.sleep(2)
    
    return None


def format_paper(paper_dir, dry_run=False, concurrency=5):
    """格式化一份试卷"""
    json_path = os.path.join(paper_dir, 'index.json')
    if not os.path.exists(json_path):
        print(f"  跳过（未找到 {json_path}）")
        return False
    
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    questions = data.get('questions', [])
    changed = False
    changes = []
    
    # 收集需要格式化的题目
    tasks = []
    for q in questions:
        if q.get('type') == 'program':
            continue
        
        # 构造发送给 API 的数据（只包含需要格式化的字段）
        api_data = {
            "id": q.get("id"),
            "type": q.get("type"),
            "content": q.get("content", ""),
            "options": [{"key": opt.get("key"), "text": opt.get("text", "")} for opt in q.get("options", [])]
        }
        tasks.append((q, api_data))
    
    if not tasks:
        print(f"  无需处理的题目")
        return False
    
    print(f"  处理 {len(tasks)} 道题...")
    
    # 并发调用 API
    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = {}
        for q, api_data in tasks:
            future = executor.submit(call_deepseek, api_data)
            futures[future] = q
        
        for future in as_completed(futures):
            q = futures[future]
            qid = q.get('id', '?')
            
            try:
                result = future.result()
                if result is None:
                    print(f"    Q{qid}: ❌ API 失败，跳过")
                    continue
                
                # 检查并更新 content
                new_content = result.get('content', q.get('content', ''))
                if new_content != q.get('content', ''):
                    changes.append(f"  Q{qid}: content 变更")
                    q['content'] = new_content
                    changed = True
                
                # 检查并更新 options
                result_options = result.get('options', [])
                for r_opt in result_options:
                    r_key = r_opt.get('key')
                    r_text = r_opt.get('text', '')
                    for opt in q.get('options', []):
                        if opt.get('key') == r_key and opt.get('text', '') != r_text:
                            changes.append(f"  Q{qid} 选项{r_key}: text 变更")
                            opt['text'] = r_text
                            changed = True
                            break
                
                print(f"    Q{qid}: ✅")
                
            except Exception as e:
                print(f"    Q{qid}: ❌ 异常: {e}")
    
    if changed:
        if changes:
            print(f"  变更项:")
            for c in changes:
                print(c)
        
        if not dry_run:
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            print(f"  ✅ 已写入")
        else:
            print(f"  (dry-run，未写入)")
    else:
        print(f"  无变更")
    
    return changed


def main():
    parser = argparse.ArgumentParser(description='GESP 试卷格式化（DeepSeek API）')
    parser.add_argument('--dry-run', action='store_true', help='只输出变更，不写文件')
    parser.add_argument('--force', action='store_true', help='强制处理包括标杆文件')
    parser.add_argument('--paper', type=str, help='只处理指定试卷（如 2023-03-gesp-1）')
    parser.add_argument('--concurrency', type=int, default=5, help='并发请求数（默认 5）')
    args = parser.parse_args()
    
    papers_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'papers')
    gold_standard = '2026-03-gesp-2'
    
    if args.paper:
        dirs = [os.path.join(papers_dir, args.paper)]
    else:
        dirs = sorted([
            os.path.join(papers_dir, d)
            for d in os.listdir(papers_dir)
            if 'gesp' in d and os.path.isdir(os.path.join(papers_dir, d))
        ])
    
    total = len(dirs)
    changed_count = 0
    start_time = time.time()
    
    print(f"=" * 60)
    print(f"GESP 试卷格式化（DeepSeek V3.2）")
    print(f"模式: {'dry-run' if args.dry_run else '写入'}")
    print(f"并发: {args.concurrency}")
    print(f"共 {total} 份试卷待处理")
    print(f"=" * 60)
    
    for idx, paper_dir in enumerate(dirs, 1):
        name = os.path.basename(paper_dir)
        
        if not args.force and name == gold_standard:
            print(f"[{idx}/{total}] ⏭️  {name}（标杆，跳过）")
            continue
        
        print(f"\n[{idx}/{total}] 📝 {name}")
        if format_paper(paper_dir, args.dry_run, args.concurrency):
            changed_count += 1
    
    elapsed = time.time() - start_time
    print(f"\n{'=' * 60}")
    print(f"处理完成：{total} 份中 {changed_count} 份有变更")
    print(f"耗时：{elapsed:.1f}s")


if __name__ == '__main__':
    main()
