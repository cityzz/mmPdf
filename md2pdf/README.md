# Markdown 转 PDF 工具 (`md2pdf`)

基于 **Playwright (Chromium)** 与 **markdown-it**（VSCode Markdown 预览同款解析内核）构建的高保真 Markdown → PDF 转换工具。

---

## 核心特性

- 🎯 **与 VSCode 预览 100% 同源**：采用 VSCode 官方底层的 `markdown-it` 解析引擎，列表层级、表格、缩进容错表现完全一致。
- 📊 **原生 Mermaid 流程图**：自动将 ` ```mermaid ` 代码块动态渲染为矢量 SVG 图表。
- 🎨 **代码高亮**：集成 `highlight.js`，自动识别多种编程语言并渲染 GitHub 风格代码块。
- 📝 **GitHub 风格排版**：支持任务列表复选框 (`[x]` / `[ ]`)、表格 (`table`)、引用块、中文友好字体族。

---

## 环境准备与依赖清单

假设你处在一个**全新的 Python 纯净环境**（除了 Python 自带的标准库外没有任何第三方包）：

### 1. 依赖分类分析

- **Python 标准库（已自带，无需安装）**：
  - `argparse`（命令行参数解析）
  - `asyncio`（异步调度）
  - `pathlib`（路径管理）
  - `json`、`sys`、`re`
- **需要安装的唯一 Python 第三方包**：
  - **`playwright`**：用于调度底层 Chromium 浏览器引擎。
- **需要下载的二进制运行环境**：
  - **`chromium`**：Playwright 专用的无头浏览器内核（用于执行 JS 排版、Mermaid 渲染与打印生成 PDF，约 150~200 MB）。
- **前端 JS/CSS 引擎（运行时 CDN 自动加载，无需本地安装）**：
  - `markdown-it.min.js`（与 VSCode 同款的 Markdown 解析引擎）
  - `markdown-it-task-lists.min.js`（任务复选框支持）
  - `mermaid.min.js`（Mermaid 图表引擎）
  - `highlight.min.js`（代码语法高亮）

---

## 零基础安装步骤（仅需 2 步）

在命令行（CMD、PowerShell 或终端）中执行：

### Step 1: 安装 Playwright Python 库

```bash
pip install playwright
```

### Step 2: 下载 Chromium 浏览器内核

```bash
python -m playwright install chromium
```

> **注意**：
> 1. 无需安装 `markdown` 或 `markdown2` 等任何第三方 Python Markdown 库，因为解析引擎完全由 `markdown-it` 在浏览器中直接执行；
> 2. 只有首次使用时需要运行 `Step 2` 下载浏览器内核，后续直接运行脚本即可。

---

## 使用方法与命令行参数

### 基本语法

```bash
python md2pdf.py <输入文件.md> [可选参数]
```

### 常用命令示例

1. **基础转换**（默认在同级目录下输出同名 `.pdf` 文件）：
   ```bash
   python md2pdf.py PDF_TOOL_PLAN.md
   # 生成: PDF_TOOL_PLAN.pdf
   ```

2. **指定输出文件路径**（`-o` 或 `--output`）：
   ```bash
   python md2pdf.py PDF_TOOL_PLAN.md -o "D:\output\plan_v2.pdf"
   ```

3. **保存渲染后的静态 HTML**（`--save-html`，推荐，方便在浏览器中排查效果）：
   ```bash
   python md2pdf.py PDF_TOOL_PLAN.md --save-html
   # 将额外生成同名的 PDF_TOOL_PLAN.html，双击即可用 Chrome / Edge 打开查看
   ```

4. **跳过 Mermaid 图表渲染**（`--no-mermaid`，纯文本提速）：
   ```bash
   python md2pdf.py PDF_TOOL_PLAN.md --no-mermaid
   ```

---

## 参数完整列表

| 参数名 | 简写 | 是否必选 | 默认值 | 作用说明 |
| :--- | :--- | :--- | :--- | :--- |
| `input` | 无 | **必选** | - | 要转换的目标 Markdown 文件路径（支持相对/绝对路径）。 |
| `--output` | `-o` | 可选 | 与输入同名 `.pdf` | 指定导出的 PDF 目标路径。 |
| `--save-html` | 无 | 可选 | `False` | 转换时同时保存一份 Chromium 最终渲染好的 `.html` 文件。 |
| `--no-mermaid`| 无 | 可选 | `False` | 禁用 Mermaid 流程图渲染，跳过图表脚本加载。 |
| `--help` | `-h` | 可选 | - | 查看命令行帮助信息。 |

---

## 常见问题与排查 (FAQ)

### Q1: 运行提示 `UnicodeEncodeError: 'gbk' codec can't encode...`？
**解答**：Windows PowerShell / CMD 默认编码为 GBK，如果在命令行重定向输出时遇到中文编码报错，可在运行前设置环境变量或切换 UTF-8 编码页：
```cmd
set PYTHONIOENCODING=utf-8
chcp 65001
python md2pdf.py your_file.md
```

### Q2: 提示 `Executable doesn't exist at ms-playwright\...`？
**解答**：说明当前 Python 环境所依赖的 Playwright 缺少对应的 Chromium 浏览器内核文件。只需执行以下命令重新补齐即可：
```bash
python -m playwright install chromium
```
