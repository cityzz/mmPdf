#!/usr/bin/env python3
"""
md2pdf.py — Markdown → PDF 转换工具 (markdown-it 驱动版)
  · 采用与 VSCode 完全同源的 markdown-it 解析引擎
  · 完美兼容嵌套列表、未空行列表、表格容错
  · 支持 Mermaid 流程图原生渲染
  · 支持代码块语法高亮 (highlight.js)
  · 支持 GitHub 风格任务列表与排版风格

使用方法:
    python md2pdf.py README.md                  # → README.pdf
    python md2pdf.py README.md -o out.pdf       # 自定义输出路径
    python md2pdf.py README.md --save-html      # 同时保存中间 HTML
    python md2pdf.py README.md --no-mermaid     # 跳过 Mermaid 渲染
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

try:
    from playwright.async_api import async_playwright
except ImportError:
    sys.exit("[ERROR] 缺少依赖, 请运行: pip install playwright && playwright install chromium")


HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/highlightjs/cdn-release@11/build/styles/github.min.css">
<!-- markdown-it (VSCode 同款核心解析器) & 相关插件 -->
<script src="https://cdn.jsdelivr.net/npm/markdown-it@14.1.0/dist/markdown-it.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/markdown-it-task-lists@2.1.1/dist/markdown-it-task-lists.min.js"></script>
<script src="https://cdn.jsdelivr.net/gh/highlightjs/cdn-release@11/build/highlight.min.js"></script>
{mermaid_head}
<style>
/* ── 基础排版 (GitHub Markdown 风格) ── */
body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI",
                 "Microsoft YaHei", "Noto Sans SC", "PingFang SC",
                 Helvetica, Arial, sans-serif;
    font-size: 14px;
    line-height: 1.7;
    color: #24292f;
    background: #fff;
    margin: 0; padding: 0;
}}
.markdown-body {{
    max-width: 860px;
    margin: 0 auto;
    padding: 32px 40px;
}}

/* ── 标题 ── */
h1, h2, h3, h4, h5, h6 {{
    margin-top: 24px; margin-bottom: 16px;
    font-weight: 600; line-height: 1.25;
    page-break-after: avoid;
}}
h1 {{ font-size: 2em;   border-bottom: 1px solid #d0d7de; padding-bottom: .3em; }}
h2 {{ font-size: 1.5em; border-bottom: 1px solid #d0d7de; padding-bottom: .3em; }}
h3 {{ font-size: 1.25em; }}
h4 {{ font-size: 1em; }}

/* ── 段落 & 行内 ── */
p  {{ margin-top: 0; margin-bottom: 16px; }}
a  {{ color: #0969da; text-decoration: none; }}
strong {{ font-weight: 600; }}

/* ── 代码 ── */
code {{
    font-family: "SFMono-Regular", Consolas, "Liberation Mono",
                 Menlo, "Courier New", monospace;
    font-size: 85%;
    background: rgba(175, 184, 193, 0.2);
    padding: 0.2em 0.4em;
    border-radius: 6px;
}}
pre {{
    background: #f6f8fa;
    border-radius: 6px;
    padding: 16px;
    overflow-x: auto;
    font-size: 85%;
    line-height: 1.45;
    margin-bottom: 16px;
    page-break-inside: avoid;
}}
pre code {{
    background: transparent;
    padding: 0; border-radius: 0;
    font-size: 100%;
}}

/* ── 表格 ── */
table {{
    border-collapse: collapse;
    width: 100%;
    margin-bottom: 16px;
    page-break-inside: avoid;
}}
th, td {{
    border: 1px solid #d0d7de;
    padding: 6px 13px; text-align: left;
}}
th {{ font-weight: 600; background: #f6f8fa; }}
tr:nth-child(2n) {{ background: #f6f8fa; }}

/* ── 引用块 ── */
blockquote {{
    border-left: 4px solid #d0d7de;
    color: #57606a;
    margin: 0 0 16px 0;
    padding: 0 16px;
}}

/* ── 列表 ── */
ul, ol {{ padding-left: 2em; margin-bottom: 16px; }}
li + li {{ margin-top: 0.25em; }}

/* ── 任务列表 ── */
.task-list-item {{ list-style-type: none; margin-left: -1.5em; }}
.task-list-item input[type="checkbox"] {{
    margin-right: 0.5em; vertical-align: middle;
}}

/* ── 分隔线 ── */
hr {{ border: none; border-top: 1px solid #d0d7de; margin: 24px 0; }}

/* ── 图片 ── */
img {{ max-width: 100%; height: auto; }}

/* ── Mermaid 流程图 ── */
.mermaid {{
    text-align: center;
    margin: 20px 0;
    page-break-inside: avoid;
}}

/* ── 打印配置 ── */
@media print {{
    .markdown-body {{ max-width: none; padding: 15px; }}
    pre, table, .mermaid {{ page-break-inside: avoid; }}
    h1, h2, h3 {{ page-break-after: avoid; }}
}}
</style>
</head>
<body>
<article class="markdown-body" id="content">
</article>

<script id="raw-markdown" type="text/plain">
{raw_markdown}
</script>

<script>
window.renderMarkdown = async function() {{
    const raw = document.getElementById('raw-markdown').textContent;
    const md = window.markdownit({{
        html: true,
        linkify: true,
        typographer: false,
        breaks: false,
        highlight: function (str, lang) {{
            if (lang && lang.toLowerCase() === 'mermaid') {{
                return '<div class="mermaid">' + str + '</div>';
            }}
            if (lang && hljs.getLanguage(lang)) {{
                try {{
                    return '<pre><code class="hljs language-' + lang + '">' +
                           hljs.highlight(str, {{ language: lang, ignoreIllegals: true }}).value +
                           '</code></pre>';
                }} catch (__) {{}}
            }}
            return '<pre><code class="hljs">' + md.utils.escapeHtml(str) + '</code></pre>';
        }}
    }});

    // 启用任务复选框插件 [x] [ ]
    if (window.markdownitTaskLists) {{
        md.use(window.markdownitTaskLists, {{ enabled: true }});
    }}

    // 渲染 HTML
    document.getElementById('content').innerHTML = md.render(raw);

    {mermaid_init}
    window.renderComplete = true;
}};
</script>
</body>
</html>
"""

MERMAID_HEAD = """<script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>"""

MERMAID_INIT = """\
    // 渲染 Mermaid
    try {
        mermaid.initialize({
            startOnLoad: false,
            theme: 'default',
            flowchart: { useMaxWidth: true, htmlLabels: true, curve: 'basis' },
            securityLevel: 'loose'
        });
        await mermaid.run({
            nodes: document.querySelectorAll('.mermaid')
        });
    } catch (e) {
        console.warn('Mermaid render warning:', e);
    }
"""


def build_html_container(md_text: str, title: str, enable_mermaid: bool = True) -> str:
    """构建包含 markdown-it 解析引擎的完整单页应用 HTML。"""
    mermaid_head = MERMAID_HEAD if enable_mermaid else ""
    mermaid_init = MERMAID_INIT if enable_mermaid else ""
    return HTML_TEMPLATE.format(
        title=title or "Document",
        mermaid_head=mermaid_head,
        mermaid_init=mermaid_init,
        raw_markdown=md_text.replace("</script>", "<\\/script>"),
    )


async def render_pdf_via_markdown_it(
    html: str, output: str, save_html_path: str = None
) -> None:
    """启动 Playwright Chromium，执行 markdown-it 转换并直接输出 PDF。"""
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        page = await browser.new_page()

        await page.set_content(html, wait_until="networkidle")

        # 触发前端 markdown-it 与 mermaid 渲染
        await page.evaluate("window.renderMarkdown()")

        # 等待渲染全部完成标志
        await page.wait_for_function("() => window.renderComplete === true", timeout=30000)

        # 稍微留一点时间等待 SVG 排版完成
        await page.wait_for_timeout(300)

        # 如果需要保存渲染后的静态 HTML
        if save_html_path:
            full_html = await page.content()
            Path(save_html_path).write_text(full_html, encoding="utf-8")
            print(f"      HTML saved: {save_html_path}")

        # 生成 PDF
        await page.pdf(
            path=output,
            format="A4",
            margin={
                "top": "20mm",
                "right": "15mm",
                "bottom": "20mm",
                "left": "15mm",
            },
            print_background=True,
        )
        await browser.close()

    print(f"      PDF size: {Path(output).stat().st_size / 1024:.1f} KB")


def main():
    ap = argparse.ArgumentParser(
        description="Markdown → PDF 转换工具 (markdown-it 驱动版，与 VSCode 渲染 100% 同源)"
    )
    ap.add_argument("input", help="输入 Markdown 文件路径")
    ap.add_argument("-o", "--output", help="输出 PDF 路径 (默认: 同名 .pdf)")
    ap.add_argument(
        "--save-html", action="store_true", help="同时保存渲染后的静态 HTML (便于排查)"
    )
    ap.add_argument(
        "--no-mermaid", action="store_true", help="禁用 Mermaid 图表渲染"
    )
    args = ap.parse_args()

    src = Path(args.input).resolve()
    if not src.is_file():
        sys.exit(f"[ERROR] 文件不存在: {src}")

    dst = Path(args.output).resolve() if args.output else src.with_suffix(".pdf")
    enable_mermaid = not args.no_mermaid

    print(f"[1/3] Reading: {src}")
    md_text = src.read_text(encoding="utf-8")

    mermaid_flag = "ON" if enable_mermaid else "OFF"
    print(f"[2/3] Preparing markdown-it runtime (Mermaid: {mermaid_flag}) ...")
    html_wrapper = build_html_container(md_text, title=src.stem, enable_mermaid=enable_mermaid)

    print(f"[3/3] Rendering PDF with Chromium: {dst}")
    save_html_file = str(dst.with_suffix(".html")) if args.save_html else None
    asyncio.run(render_pdf_via_markdown_it(html_wrapper, str(dst), save_html_file))

    print(f"[OK] Done: {dst}")


if __name__ == "__main__":
    main()
