#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
大规模 PDF Statement 批量处理工具 (pdftool.py)
版本: v2.0 零拷贝极速版

核心功能:
- 全流程零拷贝 (Zero-Copy Manifest Architecture): 原目录严格只读，以清单追踪状态。
- Stage 1: 递归扫描目录，依据初始 CSV 排除客户，生成待复核清单 (<= 2页) 与 remaining_files.txt。
- Stage 2: 依据更新后的 CSV 二次排除，支持 Newsletter 独立合并 (不补白不分批)，
          常规账单 (<= 6页) 与大账单 (> 6页) 对称分批合并，大账单奇数页自动补齐空白背页，
          并输出打印统计报表。
"""

import os
import sys
import gc
import re
import csv
import argparse
from pathlib import Path
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple
from collections import defaultdict, Counter

import fitz  # PyMuPDF

# Windows 终端 UTF-8 兼容支持
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass


# ==============================================================================
# 1. 数据结构与文件名智能解析模块 (FilenameParser)
# ==============================================================================

@dataclass
class StatementInfo:
    """PDF 账单元数据对象"""
    path: Path              # 文件绝对路径
    raw_filename: str       # 原始文件名
    user_name: str          # 解析出的客户名 (例如 'CHEN Mei Ling')
    user_id: str            # 解析出的客户ID (例如 '415137934')
    extra_info: str = ""    # 其他描述 (例如 'Aug2026_Interim_Breakdown')
    page_count: int = 0     # 文件总页数 (延迟填充)


class FilenameParser:
    """
    独立的文件名解析器类。
    未来若文件名规则发生变动，仅需调整此类的正则表达式或解析逻辑。
    """

    # 主匹配规则：[客户姓名]_[客户ID数字]_[其他信息].pdf
    # 示例: CHEN_Mei_Ling_415137934_Aug2026_Interim_Breakdown.pdf
    PRIMARY_PATTERN = re.compile(
        r"^(?P<name>[A-Za-z0-9_\s-]+?)_(?P<id>\d{6,12})(?:_(?P<extra>.*))?\.pdf$",
        re.IGNORECASE
    )

    # 回退规则匹配：尝试在文件名中捕获任意 6~12 位连续数字作为用户 ID
    FALLBACK_ID_PATTERN = re.compile(r"(?:^|_)(\d{6,12})(?:_|\.pdf$)", re.IGNORECASE)

    @classmethod
    def parse(cls, file_path: Path) -> Optional[StatementInfo]:
        """
        解析单个 PDF 文件名。
        成功返回 StatementInfo，无法提取客户ID时返回 None。
        """
        filename = file_path.name
        match = cls.PRIMARY_PATTERN.match(filename)
        if match:
            raw_name = match.group("name")
            user_name = " ".join(raw_name.replace("_", " ").split())
            user_id = match.group("id")
            extra_info = match.group("extra") or ""
            return StatementInfo(
                path=file_path.resolve(),
                raw_filename=filename,
                user_name=user_name,
                user_id=user_id,
                extra_info=extra_info
            )

        return cls._fallback_parse(file_path)

    @classmethod
    def _fallback_parse(cls, file_path: Path) -> Optional[StatementInfo]:
        """备用回退解析规则"""
        stem = file_path.stem
        match = cls.FALLBACK_ID_PATTERN.search(file_path.name)
        if match:
            user_id = match.group(1)
            # 尝试截取 ID 之前的部分作为姓名
            idx = file_path.name.find(user_id)
            name_part = file_path.name[:idx].rstrip("_")
            user_name = " ".join(name_part.replace("_", " ").split()) if name_part else "Unknown"
            return StatementInfo(
                path=file_path.resolve(),
                raw_filename=file_path.name,
                user_name=user_name,
                user_id=user_id,
                extra_info=""
            )
        return None


# ==============================================================================
# 2. 通用工具函数 (CSV 读写、底层压缩保存、内存释放)
# ==============================================================================

def load_clients_csv(csv_path: Path) -> Dict[str, str]:
    """
    读取两列客户 CSV 文件 (客户名, 客户ID)。
    支持带/不带表头，自动去除空格与 BOM，返回 {user_id: user_name} 字典。
    """
    if not csv_path.is_file():
        print(f"[!] 错误: CSV 文件不存在: '{csv_path}'")
        sys.exit(1)

    clients: Dict[str, str] = {}
    try:
        with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
            reader = csv.reader(f)
            for row_idx, row in enumerate(reader, start=1):
                if not row or len(row) < 2:
                    continue

                col0 = row[0].strip()
                col1 = row[1].strip()

                # 跳过表头 (如果包含常见表头词)
                if row_idx == 1 and any(k in col1.lower() for k in ("id", "number", "customer", "code", "客户", "卡号")):
                    continue
                if row_idx == 1 and any(k in col0.lower() for k in ("name", "client", "姓名", "用户名", "客户名")):
                    continue

                # 兼容：第一列为姓名，第二列为ID；或第一列为ID，第二列为姓名
                if col1.isdigit():
                    client_id, client_name = col1, col0
                elif col0.isdigit():
                    client_id, client_name = col0, col1
                else:
                    client_name, client_id = col0, col1

                if client_id:
                    clients[client_id] = client_name

    except UnicodeDecodeError:
        print(f"[!] 编码错误: 请确保 CSV 文件为 UTF-8 编码格式: '{csv_path}'")
        sys.exit(1)
    except Exception as e:
        print(f"[!] 读取 CSV 出错 ({csv_path}): {e}")
        sys.exit(1)

    return clients


def save_and_close(doc: fitz.Document, output_path: Path) -> None:
    """以最高压缩级别安全保存 PDF 并强制执行内存垃圾回收"""
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        doc.save(str(output_path), garbage=4, deflate=True, clean=True)
        doc.close()
        gc.collect()
    except Exception as e:
        print(f"[!] 保存 PDF 失败 ({output_path}): {e}")
        sys.exit(1)


def merge_statements(
    statements: List[StatementInfo],
    output_path: Path,
    pad_odd_pages: bool = False
) -> None:
    """
    流式合并一批 PDF 账单。
    - pad_odd_pages 为 True 时，若单份文件为奇数页，在末尾插入一页空白页。
    - 采用原生 insert_pdf，画质无损且速度极快。
    """
    dest_doc = fitz.open()

    for idx, stmt in enumerate(statements, start=1):
        try:
            src_doc = fitz.open(stmt.path)
            src_page_count = src_doc.page_count

            # 原生整份插入
            dest_doc.insert_pdf(src_doc)

            # 奇数页补空白页保护 (双面打印专用)
            if pad_odd_pages and (src_page_count % 2 != 0):
                last_page_rect = src_doc[-1].rect
                dest_doc.new_page(
                    width=last_page_rect.width,
                    height=last_page_rect.height
                )

            src_doc.close()

            # 每处理 50 份释放一次垃圾
            if idx % 50 == 0:
                gc.collect()

        except Exception as e:
            print(f"[!] 读取并合并 PDF 失败 ({stmt.path}): {e}")

    save_and_close(dest_doc, output_path)


# ==============================================================================
# 3. 递归扫描与名单过滤底层复用引擎
# ==============================================================================

def scan_and_filter_directory(
    input_dir: Path,
    exclude_ids: Set[str]
) -> Tuple[List[StatementInfo], List[Path], List[StatementInfo]]:
    """
    递归扫描目录中的所有 .pdf 文件，解析元数据，并根据 exclude_ids 进行集合精确排除。
    
    返回:
        retained: 保留的 StatementInfo 列表
        unrecognized: 解析失败的文件 Path 列表
        excluded: 排除的 StatementInfo 列表
    """
    if not input_dir.is_dir():
        print(f"[!] 错误: 输入目录不存在或不是文件夹: '{input_dir}'")
        sys.exit(1)

    print(f"[*] 正在递归扫描目录: {input_dir.resolve()} ...")
    # 严格仅筛选 .pdf 后缀，忽略其他一切类型
    pdf_paths = [
        p.resolve() for p in input_dir.rglob("*")
        if p.is_file() and p.suffix.lower() == ".pdf"
    ]
    print(f"[*] 找到 {len(pdf_paths)} 个 PDF 文件，正在解析文件名与匹配排除名单...")

    retained: List[StatementInfo] = []
    unrecognized: List[Path] = []
    excluded: List[StatementInfo] = []

    for path in pdf_paths:
        stmt = FilenameParser.parse(path)
        if stmt is None:
            unrecognized.append(path)
            continue

        if stmt.user_id in exclude_ids:
            excluded.append(stmt)
        else:
            retained.append(stmt)

    return retained, unrecognized, excluded


def load_and_filter_manifest(
    manifest_path: Path,
    exclude_ids: Set[str]
) -> Tuple[List[StatementInfo], List[Path], List[StatementInfo]]:
    """
    从清单文本文件中读取路径列表，并根据 exclude_ids 进行二次排除。
    """
    if not manifest_path.is_file():
        print(f"[!] 错误: 清单文件不存在: '{manifest_path}'")
        sys.exit(1)

    print(f"[*] 正在读取清单文件: {manifest_path.resolve()} ...")
    retained: List[StatementInfo] = []
    unrecognized: List[Path] = []
    excluded: List[StatementInfo] = []

    with open(manifest_path, "r", encoding="utf-8") as f:
        for line in f:
            line_str = line.strip()
            if not line_str:
                continue
            path = Path(line_str)
            if not path.is_file():
                print(f"[!] 警告: 清单中的文件不存在，跳过: {path}")
                continue

            stmt = FilenameParser.parse(path)
            if stmt is None:
                unrecognized.append(path)
                continue

            if stmt.user_id in exclude_ids:
                excluded.append(stmt)
            else:
                retained.append(stmt)

    return retained, unrecognized, excluded


def populate_page_counts(statements: List[StatementInfo]) -> None:
    """极速批量提取 PDF 页数 (仅读文件头 xref 元数据，单文件 <1ms)"""
    print(f"[*] 正在极速探测 {len(statements)} 个文件的页数元数据...")
    for i, stmt in enumerate(statements):
        try:
            doc = fitz.open(stmt.path)
            stmt.page_count = doc.page_count
            doc.close()
        except Exception as e:
            print(f"[!] 读取文件页数失败 ({stmt.path.name}): {e}")
            stmt.page_count = 0

        if (i + 1) % 500 == 0:
            gc.collect()


# ==============================================================================
# 4. Stage 1: 扫描初筛、生成清单与导出待复核名单
# ==============================================================================

def run_stage1(args: argparse.Namespace) -> None:
    """执行 Stage 1 流程"""
    input_dir = Path(args.input_dir).resolve()
    exclude_csv_path = Path(args.exclude_csv).resolve()
    review_pages_threshold = args.review_pages

    # 1. 加载首轮排除名单
    exclude_map = load_clients_csv(exclude_csv_path)
    exclude_ids = set(exclude_map.keys())
    print(f"[+] 成功加载初始排除名单: 共 {len(exclude_ids)} 位客户 ({exclude_csv_path.name})")

    # 2. 递归扫描并过滤
    retained, unrecognized, excluded = scan_and_filter_directory(input_dir, exclude_ids)

    # 3. 处理无法解析的文件 (防御性机制)
    if unrecognized:
        print(f"\n[!] 警告: 发现 {len(unrecognized)} 个无法提取客户信息的非标 PDF 文件！")
        unrec_csv = Path.cwd() / "unrecognized_files.csv"
        with open(unrec_csv, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["Filename", "FullPath"])
            for p in unrecognized:
                writer.writerow([p.name, str(p)])
        print(f"[!] 未识别文件已输出至: {unrec_csv.resolve()}，已跳过处理。")

    # 4. 生成临时路径清单 remaining_files.txt
    manifest_out = Path(args.remaining_files_out).resolve() if args.remaining_files_out else (Path.cwd() / "remaining_files.txt")
    manifest_out.parent.mkdir(parents=True, exist_ok=True)
    with open(manifest_out, "w", encoding="utf-8") as f:
        for stmt in retained:
            f.write(f"{stmt.path.as_posix()}\n")
    print(f"\n[+] 已保存保留文件清单 ({len(retained)} 份): {manifest_out.resolve()}")

    # 5. 扫描保留文件的页数
    populate_page_counts(retained)

    # 6. 筛选 <= review_pages 的账单并导出复核 CSV
    review_candidates = [s for s in retained if s.page_count <= review_pages_threshold]
    review_candidates.sort(key=lambda s: s.path.name.lower())

    if args.review_csv:
        review_csv_path = Path(args.review_csv).resolve()
    else:
        review_csv_path = Path.cwd() / f"{input_dir.name}_review_under_{review_pages_threshold}pages.csv"

    review_csv_path.parent.mkdir(parents=True, exist_ok=True)
    with open(review_csv_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["用户名", "用户ID", "文件fullpath"])
        for s in review_candidates:
            writer.writerow([s.user_name, s.user_id, str(s.path)])

    # 7. 控制台统计摘要
    print("\n" + "=" * 70)
    print("                      Stage 1 初筛完成报告")
    print("=" * 70)
    print(f" 扫描 PDF 总数          : {len(retained) + len(excluded) + len(unrecognized)}")
    print(f" 首轮排除客户数        : {len(excluded)}")
    print(f" 成功保留文件数        : {len(retained)}")
    print(f" 待复核文件 (≤ {review_pages_threshold}页)    : {len(review_candidates)}")
    print(f" 复核 CSV 导出路径      : {review_csv_path.resolve()}")
    print(f" 临时文件清单路径      : {manifest_out.resolve()}")
    print("=" * 70)
    print("[*] 下一步操作提示:")
    print(f"    1. 请人工检查 '{review_csv_path.name}' 中的客户；")
    print(f"    2. 将确认需要排除的客户直接追加到 '{exclude_csv_path.name}' 文件末尾并保存；")
    print("    3. 运行 'python pdftool.py stage2 ...' 执行二次排除与合并。")


# ==============================================================================
# 5. Stage 2: 二次排除、多轨分类合并与打印统计
# ==============================================================================

def print_page_distribution_report(group_b_statements: List[StatementInfo], report_path: Path) -> None:
    """输出分组 B (超长账单) 补白后的打印页数统计报表"""
    # 统计数据模型
    # final_pages -> {original_page_count: count}
    distribution: Dict[int, Counter] = defaultdict(Counter)
    total_files = len(group_b_statements)

    for stmt in group_b_statements:
        orig = stmt.page_count
        # 奇数页补 1 页空白页
        padded = orig + 1 if orig % 2 != 0 else orig
        distribution[padded][orig] += 1

    lines = []
    lines.append("=" * 80)
    lines.append("                    大文件 (>6页) 打印页数统计报表")
    lines.append("=" * 80)
    lines.append(f"{'最终打印页数':<14}{'原文件页数分布构成':<28}{'文件数量(份)':<14}{'占比(%)':<12}{'总打印面数(P)'}")
    lines.append("-" * 80)

    total_surfaces = 0
    sorted_padded_pages = sorted(distribution.keys())

    for padded_pages in sorted_padded_pages:
        counter = distribution[padded_pages]
        sub_total_files = sum(counter.values())
        percentage = (sub_total_files / total_files * 100) if total_files > 0 else 0.0
        sub_surfaces = padded_pages * sub_total_files
        total_surfaces += sub_surfaces

        # 构造原页数构成字符串，例如: "7页(15份), 8页(10份)"
        comp_parts = [f"{orig}页({cnt}份)" for orig, cnt in sorted(counter.items())]
        comp_str = ", ".join(comp_parts)

        lines.append(f" {padded_pages:<13}{comp_str:<28}{sub_total_files:<14}{percentage:>6.2f}%{sub_surfaces:>14} P")

    lines.append("-" * 80)
    lines.append(f" {'合计':<41}{total_files:<14}{'100.00%':>7}{total_surfaces:>14} P")
    lines.append("=" * 80)
    lines.append("* 说明: 所有奇数页原件已自动补充 1 页空白背页，确保双面打印装订不串页。")

    report_text = "\n".join(lines)
    print("\n" + report_text)

    # 保存报告文件
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report_text + "\n")
    print(f"[+] 大文件打印统计报表已保存至: {report_path.resolve()}")


def run_stage2(args: argparse.Namespace) -> None:
    """执行 Stage 2 流程"""
    # 1. 严格防呆校验: 必须指定 --newsletter_csv 或 --no_newsletter
    if not args.newsletter_csv and not args.no_newsletter:
        print("\n" + "!" * 75)
        print("[!] 错误: Stage 2 要求显式指定 Newsletter 处理规则！")
        print("    为防止遗漏 Newsletter 客户的独立分流合并，请明确指定以下参数之一:")
        print("    1. 若有 Newsletter 客户，请指定: --newsletter_csv <path_to_csv>")
        print("    2. 若本次批次无需处理 Newsletter，请显式声明: --no-newsletter")
        print("!" * 75)
        sys.exit(1)

    # 2. 检查输入源: --input_dir 或 --remaining_files
    if not args.input_dir and not args.remaining_files:
        print("[!] 错误: Stage 2 必须指定输入源 (--input_dir 或 --remaining-files)！")
        sys.exit(1)

    # 3. 加载二次更新后的排除名单 (CSV 1)
    exclude_csv_path = Path(args.exclude_csv).resolve()
    exclude_map = load_clients_csv(exclude_csv_path)
    exclude_ids = set(exclude_map.keys())
    print(f"[+] 加载更新后的排除名单: 共 {len(exclude_ids)} 位客户 ({exclude_csv_path.name})")

    # 4. 获取待处理的 Statement 列表
    if args.input_dir:
        input_dir = Path(args.input_dir).resolve()
        print(f"[*] 模式 A: 基于输入目录重新完整扫描: {input_dir}")
        retained, unrecognized, excluded = scan_and_filter_directory(input_dir, exclude_ids)
    else:
        manifest_path = Path(args.remaining_files).resolve()
        print(f"[*] 模式 B: 基于清单文件执行二次排除: {manifest_path}")
        retained, unrecognized, excluded = load_and_filter_manifest(manifest_path, exclude_ids)

    if unrecognized:
        print(f"[!] 提示: 存在 {len(unrecognized)} 个未识别文件名，已自动跳过。")

    print(f"[+] 二次排除后保留文件: {len(retained)} 份 (共剔除 {len(excluded)} 份)")

    if not retained:
        print("[!] 警告: 经排除后没有剩余的 PDF 文件可供合并！")
        return

    # 5. 确保提取了页数
    populate_page_counts(retained)

    # 6. Newsletter 独立分流 (排除绝对优先于 Newsletter)
    newsletter_statements: List[StatementInfo] = []
    regular_statements: List[StatementInfo] = []

    if args.newsletter_csv:
        newsletter_csv_path = Path(args.newsletter_csv).resolve()
        newsletter_map = load_clients_csv(newsletter_csv_path)
        newsletter_ids = set(newsletter_map.keys())
        print(f"[+] 加载 Newsletter 客户名单: 共 {len(newsletter_ids)} 位客户 ({newsletter_csv_path.name})")

        for stmt in retained:
            if stmt.user_id in newsletter_ids:
                newsletter_statements.append(stmt)
            else:
                regular_statements.append(stmt)
    else:
        print("[*] 已显式声明 --no-newsletter: 不进行 Newsletter 独立分流。")
        regular_statements = retained

    # 7. 常规账单分类: A 组 (<= normal_pages) vs B 组 (> normal_pages)
    normal_pages_threshold = args.normal_pages
    group_a: List[StatementInfo] = []
    group_b: List[StatementInfo] = []

    for stmt in regular_statements:
        if stmt.page_count <= normal_pages_threshold:
            group_a.append(stmt)
        else:
            group_b.append(stmt)

    # 8. 全局文件名字母升序排序 (确保稳定可重现)
    newsletter_statements.sort(key=lambda s: s.path.name.lower())
    group_a.sort(key=lambda s: s.path.name.lower())
    group_b.sort(key=lambda s: s.path.name.lower())

    print("\n" + "-" * 60)
    print(f" 分流统计结果:")
    print(f"  - 分组 N (Newsletter 独立) : {len(newsletter_statements)} 份 (不分批、不补白)")
    print(f"  - 分组 A (主力常规 ≤ {normal_pages_threshold}页)  : {len(group_a)} 份 (不补白)")
    print(f"  - 分组 B (超长特殊 > {normal_pages_threshold}页)  : {len(group_b)} 份 (奇数页补空白背页)")
    print("-" * 60)

    # 9. 准备输出前缀与自动创建父目录
    output_prefix = Path(args.output_prefix)
    output_prefix.parent.mkdir(parents=True, exist_ok=True)
    base_dir = output_prefix.parent
    base_stem = output_prefix.name

    batch_size = -1 if args.no_batch else args.batch_size

    # --- 执行合并 A: Newsletter 分组 (不分批、不补白) ---
    if newsletter_statements:
        news_out = base_dir / f"{base_stem}_newsletter.pdf"
        print(f"\n[>] 正在合并 Newsletter 客户 PDF ({len(newsletter_statements)} 份)...")
        merge_statements(newsletter_statements, news_out, pad_odd_pages=False)
        print(f"[+] 已生成 Newsletter 合并文件: {news_out.resolve()}")

    # --- 执行合并 B: 分组 A (常规文件，不补白，按 batch_size 分批) ---
    if group_a:
        print(f"\n[>] 正在合并常规账单 Group A ({len(group_a)} 份)...")
        if batch_size <= 0:
            out_file = base_dir / f"{base_stem}.pdf"
            print(f"    (不分批合并至单文件: {out_file.name})")
            merge_statements(group_a, out_file, pad_odd_pages=False)
            print(f"[+] 已生成: {out_file.resolve()}")
        else:
            total_parts = (len(group_a) + batch_size - 1) // batch_size
            print(f"    (按每 {batch_size} 份分批，共 {total_parts} 个 Part)")
            for part_idx in range(total_parts):
                batch_slice = group_a[part_idx * batch_size : (part_idx + 1) * batch_size]
                out_file = base_dir / f"{base_stem}_part_{part_idx + 1}.pdf"
                merge_statements(batch_slice, out_file, pad_odd_pages=False)
                print(f"[+] 已生成 Part {part_idx + 1}/{total_parts}: {out_file.name} ({len(batch_slice)} 份)")

    # --- 执行合并 C: 分组 B (超长账单，奇数页补白，按 batch_size 分批) ---
    if group_b:
        print(f"\n[>] 正在合并超长账单 Group B ({len(group_b)} 份，奇数页自动补白)...")
        if batch_size <= 0:
            out_file = base_dir / f"{base_stem}_large.pdf"
            print(f"    (不分批合并至单文件: {out_file.name})")
            merge_statements(group_b, out_file, pad_odd_pages=True)
            print(f"[+] 已生成: {out_file.resolve()}")
        else:
            total_parts = (len(group_b) + batch_size - 1) // batch_size
            print(f"    (按每 {batch_size} 份分批，共 {total_parts} 个 Part)")
            for part_idx in range(total_parts):
                batch_slice = group_b[part_idx * batch_size : (part_idx + 1) * batch_size]
                out_file = base_dir / f"{base_stem}_large_part_{part_idx + 1}.pdf"
                merge_statements(batch_slice, out_file, pad_odd_pages=True)
                print(f"[+] 已生成 Large Part {part_idx + 1}/{total_parts}: {out_file.name} ({len(batch_slice)} 份)")

        # 打印并导出大文件打印统计报表
        stats_path = base_dir / f"{base_stem}_large_stats.txt"
        print_page_distribution_report(group_b, stats_path)

    print("\n" + "=" * 70)
    print("                      Stage 2 全部合并任务完成！")
    print("=" * 70)


# ==============================================================================
# 6. CLI 命令行参数解析入口
# ==============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="大规模 PDF Statement 批量处理工具 (pdftool.py) - 零拷贝极速版",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例用法:
  # Stage 1: 扫描目录，初始排除并生成待复核 CSV (默认筛选 <= 2页)
  python pdftool.py stage1 --input_dir "D:\\statements" --exclude_csv "D:\\deleted.csv"

  # Stage 2: 二次排除并合并 (默认批次 100 份，含 Newsletter 优先分流)
  python pdftool.py stage2 --input_dir "D:\\statements" --exclude_csv "D:\\deleted.csv" --newsletter_csv "D:\\news.csv" --output_prefix "D:\\out\\Jul"

  # Stage 2 (无 Newsletter 场景):
  python pdftool.py stage2 --input_dir "D:\\statements" --exclude_csv "D:\\deleted.csv" --no-newsletter --output_prefix "D:\\out\\Jul"
        """
    )

    subparsers = parser.add_subparsers(dest="command", required=True, help="可用的子命令 (stage1 或 stage2)")

    # ------------------ Stage 1 子命令 ------------------
    p1 = subparsers.add_parser("stage1", help="Stage 1: 扫描初筛、生成清单与导出待复核名单")
    p1.add_argument("--input_dir", required=True, help="包含 PDF 文件的根目录 (递归扫描)")
    p1.add_argument("--exclude_csv", required=True, help="初始排除客户名单 CSV (两列: 客户名, 客户ID)")
    p1.add_argument("--review_pages", type=int, default=2, help="待复核账单的页数上限 (默认: 2页)")
    p1.add_argument("--review_csv", default=None, help="待复核 CSV 的输出路径 (默认自动按目录名命名)")
    p1.add_argument("--remaining_files_out", default=None, help="已保留文件清单的保存路径 (默认: ./remaining_files.txt)")

    # ------------------ Stage 2 子命令 ------------------
    p2 = subparsers.add_parser("stage2", help="Stage 2: 二次排除、Newsletter分流、常规/大文件对称分批合并与统计")
    p2.add_argument("--input_dir", default=None, help="输入目录 (模式 A: 全新重新扫描磁盘)")
    p2.add_argument("--remaining-files", "--remaining_files", dest="remaining_files", default=None,
                    help="清单文件路径 (模式 B: 直接读取文本清单)")
    p2.add_argument("--exclude_csv", required=True, help="更新后的排除客户名单 CSV")

    # Newsletter 互斥防呆选项
    news_group = p2.add_mutually_exclusive_group()
    news_group.add_argument("--newsletter_csv", default=None, help="Newsletter 客户名单 CSV (优先独立合并)")
    news_group.add_argument("--no-newsletter", "--no_newsletter", dest="no_newsletter", action="store_true",
                            help="显式声明本次批次无需处理 Newsletter 客户")

    p2.add_argument("--output_prefix", default="combined", help="输出文件名前缀及路径 (默认: ./combined)")
    p2.add_argument("--normal_pages", type=int, default=6, help="主力常规账单的最高页数界限 (默认: 6页)")
    p2.add_argument("--batch_size", type=int, default=100, help="每批次包含的原始 PDF 份数 (默认: 100)")
    p2.add_argument("--no_batch", "--no-batch", dest="no_batch", action="store_true",
                    help="不分批，将整组文件合并为一个单独的文件")

    args = parser.parse_args()

    if args.command == "stage1":
        run_stage1(args)
    elif args.command == "stage2":
        run_stage2(args)


if __name__ == "__main__":
    main()
