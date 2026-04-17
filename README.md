# 信奥在线刷题系统

[![Static Badge](https://img.shields.io/badge/Python-3.10%2B-blue)](https://www.python.org/)
[![Static Badge](https://img.shields.io/badge/Static-Generated-green)](https://en.wikipedia.org/wiki/Static_site_generator)
[![Static Badge](https://img.shields.io/badge/Offline-Available-orange)](https://en.wikipedia.org/wiki/Offline_first)

## 项目简介

信奥在线刷题系统是一个静态考试系统生成器，类似 Hexo 的构建脚本，用于生成信息学奥林匹克（信奥）相关的在线练习平台。该系统支持 GESP、CSP、NCT 等多种信奥考试类型，提供纯静态 HTML 输出，无需后端服务器，离线可用。

## 功能特性

### 核心功能
- **静态生成**：从 JSON 数据生成纯静态 HTML 页面，无需后端服务器
- **多考试类型支持**：覆盖 GESP、CSP-J、CSP-S、NCT 等多种信奥考试
- **答题系统**：支持选择题、编程题等多种题型，提供自动评分
- **代码高亮**：支持 C++ 等编程语言的代码语法高亮
- **本地存储**：使用 localStorage 存储答题记录和最高分
- **响应式设计**：适配不同设备屏幕尺寸
- **试卷导入**：支持从 Markdown 文件导入 CSP 试卷
- **PDF 下载**：批量下载 GESP 官方试卷 PDF

### 技术特点
- **离线可用**：无需网络连接，随时随地练习
- **易于部署**：只需复制静态文件到任何服务器或本地目录
- **数据安全**：本地存储，无需担心数据泄露
- **模块化架构**：清晰的代码结构，易于扩展和维护
- **智能分组**：对阅读程序/完善程序的相邻同代码题目自动分组

## 技术栈

| 类别 | 技术/库 | 用途 |
|------|---------|------|
| 后端语言 | Python 3 | 主要开发语言 |
| 模板引擎 | Jinja2 | 生成 HTML 页面 |
| Markdown 渲染 | markdown-it-py | 渲染 Markdown 内容 |
| 前端框架 | Tailwind CSS | 响应式样式 |
| 代码高亮 | Prism.js | 代码语法高亮 |
| 数学公式 | KaTeX | 数学公式渲染 |
| 数据存储 | localStorage | 本地存储答题记录 |
| 数据格式 | JSON | 试卷数据存储 |

## 目录结构

```
├── .venv/              # Python 虚拟环境
├── assets/             # 静态资源
│   ├── css/            # CSS 文件
│   ├── images/         # 图片资源
│   └── js/             # JavaScript 文件
├── dist/               # 生成的静态 HTML 输出目录
│   ├── assets/         # 复制的静态资源
│   ├── 2023-03-gesp-1/ # 各试卷的 HTML 目录
│   └── index.html      # 首页
├── papers/             # 试卷 JSON 数据
│   ├── 2023-03-gesp-1/ # 各试卷目录
│   └── index.json      # 试卷数据
├── templates/          # HTML 模板
│   ├── index.html      # 首页模板
│   └── paper.html      # 试卷详情模板
├── build.py            # 主构建脚本
├── download_pdfs.py    # 批量下载 GESP 试卷 PDF
├── import_csp.py       # 导入 CSP 试卷
└── 其他工具脚本        # 辅助功能
```

## 快速开始

### 环境要求
- Python 3.10 或更高版本
- 依赖库：
  - jinja2
  - markdown-it-py
  - frontmatter (用于导入 CSP 试卷)

### 安装依赖

```bash
# 创建虚拟环境（可选）
python3 -m venv .venv

# 激活虚拟环境
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate

# 安装依赖
pip install jinja2 markdown-it-py python-frontmatter
```

### 构建项目

```bash
# 构建静态网站
python build.py

# 构建完成后，打开 dist/index.html 开始使用
```

## 使用方法

### 1. 浏览试卷
- 打开 `dist/index.html` 查看试卷列表
- 选择考试分类（GESP、CSP-J、CSP-S、NCT）
- 选择级别（如 GESP 1-8级）
- 点击试卷卡片进入试卷详情

### 2. 答题
- 在试卷详情页面，阅读题目并选择答案
- 点击「提交答案」按钮查看得分
- 系统会自动记录最高分

### 3. 导入试卷

#### 导入 CSP 试卷
```bash
# 从 Downloads/csp题目/ 目录导入 CSP 试卷
python import_csp.py
```

#### 下载 GESP 试卷 PDF
```bash
# 批量下载 GESP 官方试卷 PDF
python download_pdfs.py
```

### 4. 添加自定义试卷
1. 在 `papers/` 目录下创建新的子目录，如 `2024-06-gesp-1`
2. 在该目录中创建 `index.json` 文件，按照以下格式填写：

```json
{
  "title": "2024年6月 GESP C++ 一级",
  "category": "GESP",
  "level": "1",
  "date": "2024-06",
  "time_limit": 60,
  "total_score": 100,
  "description": "2024年6月 GESP C++ 一级考试试卷",
  "questions": [
    {
      "id": 1,
      "type": "choice",
      "score": 5,
      "content": "以下哪个是 C++ 的关键字？",
      "options": [
        {"key": "A", "text": "printf"},
        {"key": "B", "text": "cin"},
        {"key": "C", "text": "int"},
        {"key": "D", "text": "main"}
      ],
      "answer": "C"
    }
    // 更多题目...
  ]
}
```

3. 运行 `python build.py` 重新构建项目

## 项目优势

### 技术优势
1. **静态生成**：无需后端服务器，部署简单，加载速度快
2. **离线可用**：本地存储，无需网络连接
3. **响应式设计**：适配不同设备，移动端友好
4. **模块化架构**：清晰的代码结构，易于扩展和维护
5. **代码高亮**：支持多种编程语言的代码语法高亮
6. **智能分组**：对阅读程序/完善程序的相邻同代码题目自动分组

### 功能优势
1. **多考试类型支持**：覆盖 GESP、CSP、NCT 等多种信奥考试
2. **完整的答题系统**：支持多种题型，提供自动评分
3. **本地数据存储**：记录答题情况和最高分
4. **批量导入功能**：支持从 Markdown 文件批量导入试卷
5. **PDF 下载功能**：提供官方试卷 PDF 下载
6. **用户友好界面**：美观、直观的用户界面

### 系统优势
1. **零配置部署**：只需复制 dist/ 目录到任何静态文件服务器
2. **数据安全**：本地存储，无需担心数据泄露
3. **跨平台兼容**：支持所有现代浏览器
4. **易于扩展**：模块化设计，便于添加新功能
5. **资源整合**：集中管理多种信奥考试资源
6. **免费使用**：完全开源，免费使用

## 应用场景

### 主要应用场景
1. **学生练习**：学生可以在离线环境下练习信奥题目
2. **教师教学**：教师可以使用系统组织练习题
3. **考试模拟**：模拟真实考试环境，帮助学生熟悉考试形式
4. **自学备考**：自学信奥的学生可以使用系统进行备考
5. **赛事准备**：为 GESP、CSP、NCT 等赛事做准备

### 适用人群
- **信奥考生**：准备参加 GESP、CSP、NCT 等考试的学生
- **信息学教师**：需要组织练习题和考试的教师
- **编程爱好者**：对算法和编程感兴趣的学习者
- **教育机构**：提供信奥培训的机构

## 贡献指南

欢迎贡献代码和提出建议！

1. Fork 本仓库
2. 创建 feature 分支
3. 提交更改
4. 发起 Pull Request

## 许可证

本项目采用 MIT 许可证。详见 [LICENSE](LICENSE) 文件。

## 联系方式

如有问题或建议，请通过以下方式联系：

- GitHub Issues：[提交问题](https://github.com/yourusername/olympiad-practice-system/issues)

---

**信奥在线刷题系统** - 为信奥学习者提供便捷、高效的在线练习平台！