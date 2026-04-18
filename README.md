# 信奥在线刷题系统

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue)](https://www.python.org/)
[![Static](https://img.shields.io/badge/Static-Generated-green)](https://en.wikipedia.org/wiki/Static_site_generator)
[![Offline](https://img.shields.io/badge/Offline-Available-orange)](https://en.wikipedia.org/wiki/Offline_first)

类 Hexo 的静态考试系统生成器，从 JSON 试卷数据生成纯静态 HTML，供学生练习 GESP / CSP / NCT 等信奥初赛。**零后端、零 CDN、离线可用。**

## 试卷数据

| 类别 | 数量 | 范围 |
|------|------|------|
| GESP C++ | 92 份 | 2023-03 ~ 2026-03，1-8 级 |
| CSP-J / CSP-S | 14 份 | 2019-2025（J×7 + S×7） |
| NCT | 15 份 | C++ C1/C2 + Kitten K1-K3 |
| **合计** | **121 份** | |

## 功能特性

- **自动评分** — 提交后即时判分，错题红色高亮 + 显示正确答案
- **答题卡导航** — 侧边答题卡快速跳转，进度条实时显示
- **答题记录持久化** — localStorage 存储，刷新不丢失，提交/重置后清空
- **倒计时器** — 按试卷设定时间倒计时，5 分钟警告
- **多题型** — 单选(choice)、判断(judge)、填空(fill)、编程(program)
- **CSP 大题模式** — 阅读程序/完善程序代码只显示一次，子题紧凑排列
- **阅读程序判断题** — 自动识别"正确/错误"选项，渲染为 ✓/✗ 按钮
- **分类选项卡** — GESP / CSP-J / CSP-S / NCT 一级切换
- **级别筛选** — GESP 1-8 级筛选，CSP 自动隐藏
- **首页分页** — 20 份/页，切换分类/级别时重置到第 1 页
- **代码高亮** — Prism.js C++ 语法高亮（One Light 浅色主题）
- **数学公式** — KaTeX 渲染，`$...$` 行内、`$$...$$` 块级
- **Markdown 渲染** — markdown-it-py，支持换行
- **NCT 图片缩放** — Kitten 试卷图片 max-width:60%
- **浏览器历史导航** — scroll → replaceState + popstate 恢复滚动位置
- **全站离线** — CSS / JS / 字体全部打包在 dist/assets/，零 CDN 依赖
- **响应式设计** — 移动端适配

## 技术栈

| 类别 | 技术 | 用途 |
|------|------|------|
| 语言 | Python 3 | 构建脚本 |
| 模板 | Jinja2 | 生成 HTML |
| Markdown | markdown-it-py | 渲染题目内容 |
| 样式 | Tailwind CSS | 响应式 UI |
| 代码高亮 | Prism.js | C++ 语法着色 |
| 数学公式 | KaTeX | 公式渲染 |
| PDF 解析 | pdfplumber | GESP 试卷客观题提取 |
| PDF 渲染 | PyMuPDF | 判断题答案截图 |
| 数据 | JSON | 试卷存储 |

## 目录结构

```
├── build.py              # 核心构建脚本（JSON → HTML）
├── gesp_import.py        # GESP 统一导入入口（7 个子命令）
├── gesp_pdfs.json        # GESP PDF URL 配置（增量更新源）
├── download_pdfs.py      # GESP PDF 增量下载（从 gesp_pdfs.json 读取）
├── pdf_to_json.py        # GESP PDF → JSON（客观题解析，增量模式）
├── import_luogu_programs.py  # GESP 编程题面导入（从洛谷题单，含 LaTeX + 样例）
├── fix_gesp_judge.py     # GESP 判断题修复（截图 + 多模态识别 + 写入）
├── import_csp_data.py    # CSP 试卷导入（sections → questions 格式转换）
├── import_nct.py         # NCT 试卷导入（含图片下载）
├── papers/               # 试卷 JSON 数据（121 份）
│   ├── 2023-03-gesp-1/
│   │   └── index.json
│   ├── 2024-csp-j-2024/
│   │   └── index.json
│   └── nct-kitten-1-K1模拟卷1/
│       └── index.json
├── templates/            # Jinja2 模板
│   ├── index.html        # 首页模板（分类选项卡 + 级别筛选）
│   ├── paper.html        # 试卷详情模板
│   └── 404.html          # 404 页面
├── assets/               # 本地静态资源
├── dist/                 # 构建输出目录
└── requirements.txt      # Python 依赖
```

## 快速开始

### 环境要求

- Python 3.10+
- 依赖：`jinja2`、`markdown-it-py`、`python-frontmatter`

### 安装

```bash
python3 -m venv .venv
source .venv/bin/activate   # macOS/Linux
pip install -r requirements.txt
```

### 构建

```bash
python3 build.py
# 打开 dist/index.html 即可使用
```

## 试卷导入

### GESP 试卷（统一入口）

```bash
# 查看数据完整性
python3 gesp_import.py status

# 扫描官网发现新增（AI 浏览 https://gesp.ccf.org.cn/101/1010/index.html）
python3 gesp_import.py scan

# 一键全流程（下载 → 解析客观题 → 追加编程题 → 修复判断题）
python3 gesp_import.py all

# 单步操作
python3 gesp_import.py download   # 增量下载缺失 PDF
python3 gesp_import.py parse      # 解析客观题（跳过已有 JSON）
python3 gesp_import.py programs   # 从洛谷导入编程题面（含 LaTeX 公式 + 样例）
python3 gesp_import.py judge      # 检查判断题修复状态
```

**增量更新流程**：AI 浏览 GESP 官网子页面 → 提取新 PDF URL → 更新 `gesp_pdfs.json` → 运行 `gesp_import.py all`

每一步自动检测已有数据，跳过已处理项，不会重复覆盖。

> **增量检测机制**：各步骤的"是否需要处理"判断逻辑如下：
>
> | 步骤 | 判断方式 | 依赖 |
> |------|----------|------|
> | `download` | 对比 `gesp_pdfs.json` 配置 vs 本地文件是否已存在 | `pdfs/` 目录（不上传 GitHub） |
> | `parse` | 对比本地 PDF vs `papers/` 中是否已有 JSON | `pdfs/` + `papers/` |
> | `programs` | 读取 `papers/*/index.json`，检查是否已有 program 类型题目 | `papers/` + 洛谷题单 training/551~558 |
> | `judge` | 读取 JSON 中判断题 answer 是否仍为全 False/空 | `papers/` + `pdfs/` |
>
> **`pdfs/` 不上传 GitHub**，但 `gesp_pdfs.json`（~5KB，92 条 URL 记录）在仓库中。新环境克隆后，运行 `gesp_import.py download` 即可从 URL 自动重建 `pdfs/` 目录，然后执行后续步骤。

### GESP 判断题修复

2023-09 起的 PDF 中 √/× 以矢量路径渲染，pdfplumber 无法提取文本，需用多模态识别：

```bash
# 步骤1：渲染判断题答案行截图
python3 fix_gesp_judge.py render

# 步骤2：用多模态模型识别截图中的 √/×
# （人工或 AI 识别后生成 answers.json）

# 步骤3：将识别结果写入 JSON
python3 fix_gesp_judge.py apply --file answers.json

# 查看修复状态
python3 fix_gesp_judge.py status
```

### CSP 试卷

```bash
# 从外部 data 目录导入（sections → questions 格式转换）
python3 import_csp_data.py

# 答案需从外部来源填充（极客网答案文件，内容匹配选项确定 A/B/C/D）
# 判断题：正确 → "True"，错误 → "False"
```

### NCT 试卷

```bash
# 从原始 JSON 导入（含图片下载）
python3 import_nct.py
```

### 手动添加试卷

1. 在 `papers/` 下创建子目录（如 `2024-06-gesp-1`）
2. 创建 `index.json`：

```json
{
  "title": "2024年6月 GESP C++ 1级",
  "category": "GESP",
  "level": "1",
  "date": "2024-06",
  "time_limit": 60,
  "total_score": 100,
  "description": "考试说明",
  "questions": [
    {
      "id": 1,
      "type": "choice",
      "score": 2,
      "content": "题干文本（支持 Markdown）",
      "options": [
        {"key": "A", "text": "选项A"},
        {"key": "B", "text": "选项B"},
        {"key": "C", "text": "选项C"},
        {"key": "D", "text": "选项D"}
      ],
      "answer": "B"
    },
    {
      "id": 11,
      "type": "judge",
      "score": 2,
      "content": "判断题题干",
      "answer": "True"
    },
    {
      "id": 16,
      "type": "fill",
      "score": 5,
      "content": "填空题题干，空格用 ___ 表示",
      "answer": "42"
    },
    {
      "id": 26,
      "type": "program",
      "score": 25,
      "content": "编程题描述",
      "answer": ""
    }
  ]
}
```

3. 运行 `python3 build.py` 重新构建

## JSON 试卷格式说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `title` | string | 试卷标题 |
| `category` | string | 分类：GESP / CSP-J / CSP-S / NCT |
| `level` | string | 级别：GESP 为 "1"-"8"，CSP 为 "CSP-J"/"CSP-S" |
| `date` | string | 考试日期，如 "2024-06" |
| `time_limit` | int | 时长（分钟） |
| `total_score` | int | 总分（GESP 含编程题 100，CSP 初赛 100） |
| `questions[].type` | string | choice / judge / fill / program |
| `questions[].answer` | string | choice: "A"-"D"；judge: "True"/"False"；fill: 文本；program: "" |
| `questions[].section` | string | CSP 专用："单项选择题"/"阅读程序"/"完善程序" |

## 许可证

MIT
