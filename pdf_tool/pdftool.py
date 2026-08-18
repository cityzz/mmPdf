import fitz  # PyMuPDF
import re
import argparse
import csv
import gc
import os
import shutil
import sys

def save_and_close(doc, name):
    """Saves with high compression and releases memory."""
    try:
        doc.save(name, garbage=4, deflate=True, clean=True)
        doc.close()
        gc.collect()
    except Exception as e:
        print(f"[!] Error saving {name}: {e}")


def combined_output_name(base_name, ext, group_name, batch_number, batch_size):
    """Returns the combined PDF filename for a page-count group and batch."""
    suffixes = {"single": "_single", "normal": "", "surplus": "_surplus"}
    suffix = suffixes[group_name]
    if batch_size == -1:
        return f"{base_name}{suffix}{ext}"
    return f"{base_name}{suffix}_part_{batch_number}{ext}"


def page_count_group(page_count, surplus_pages):
    """Classifies a PDF by page count for the combine operation."""
    if page_count == 1:
        return "single"
    if page_count <= surplus_pages:
        return "normal"
    return "surplus"


def combine_pdfs(input_dir, output_name, args):
    """Combines PDFs into single-page, normal, and surplus output groups."""
    if not os.path.isdir(input_dir):
        print(f"[!] Error: '{input_dir}' is not a valid directory.")
        sys.exit(1)

    pdf_files = [f for f in os.listdir(input_dir) if f.lower().endswith('.pdf')]
    pdf_files.sort()  # Ensure predictable, alphabetical order

    if not pdf_files:
        print(f"[!] No PDFs found in directory: '{input_dir}'")
        sys.exit(1)

    print(f"[*] Found {len(pdf_files)} PDFs in '{input_dir}'. Starting merge...")

    # 规范化主输出文件名
    if not output_name.lower().endswith('.pdf'):
        output_name += ".pdf"

    base_name, ext = os.path.splitext(output_name)

    # The normal group retains the original output name for backwards compatibility.
    groups = {
        "single": {"label": "single-page", "suffix": "_single", "document": fitz.open(),
                   "batch": 1, "in_batch": 0, "total": 0},
        "normal": {"label": "normal", "suffix": "", "document": fitz.open(),
                   "batch": 1, "in_batch": 0, "total": 0},
        "surplus": {"label": "surplus", "suffix": "_surplus", "document": fitz.open(),
                    "batch": 1, "in_batch": 0, "total": 0},
    }

    def save_group_batch(group_name, continue_batch=True):
        group = groups[group_name]
        out_name = combined_output_name(
            base_name, ext, group_name, group["batch"], args.batch_size
        )
        print(f"[>] Writing {out_name} ({group['in_batch']} files)...")
        save_and_close(group["document"], out_name)
        if continue_batch:
            group["document"] = fitz.open()
            group["in_batch"] = 0
            group["batch"] += 1

    for i, filename in enumerate(pdf_files):
        file_path = os.path.join(input_dir, filename)
        try:
            src = fitz.open(file_path)
            page_count = len(src)

            # 分流：单页、2 至 surplus_pages 页、以及超过 surplus_pages 页。
            group_name = page_count_group(page_count, args.surplus_pages)
            current_dest = groups[group_name]["document"]

            # 遍历当前PDF的每一页，应用 shrink 逻辑
            for page_num in range(page_count):
                src_page = src[page_num]
                rect = src_page.rect

                new_page = current_dest.new_page(width=rect.width, height=rect.height)

                if args.shrink < 1.0:
                    new_w = rect.width * args.shrink
                    new_h = rect.height * args.shrink
                    x_margin = (rect.width - new_w) / 2
                    y_margin = rect.height - new_h if args.space_top else (rect.height - new_h) / 2
                    target_rect = fitz.Rect(x_margin, y_margin, x_margin + new_w, y_margin + new_h)
                    new_page.show_pdf_page(target_rect, src, page_num)
                else:
                    new_page.show_pdf_page(rect, src, page_num)

            # 处理奇数页补空白页逻辑 (--pad)
            if args.pad and page_count % 2 != 0:
                last_rect = src[page_count - 1].rect
                current_dest.new_page(width=last_rect.width, height=last_rect.height)

            src.close()

            # Batch size counts source PDFs, rather than pages.
            group = groups[group_name]
            group["in_batch"] += 1
            group["total"] += 1
            if args.batch_size != -1 and group["in_batch"] >= args.batch_size:
                save_group_batch(group_name)

        except Exception as e:
            print(f"[!] Error reading {filename}: {e}")

        # 每 100 个文件释放一次内存
        if (i + 1) % 100 == 0:
            gc.collect()
            print(f"[*] Processed {i + 1} / {len(pdf_files)} files...")

    print("---")

    # 保存尚未达到 batch_size 的最后一批。
    for group_name, group in groups.items():
        if len(group["document"]) > 0:
            save_group_batch(group_name, continue_batch=False)
        else:
            group["document"].close()

    print(
        "[+] Combine task complete. "
        f"(Single-page: {groups['single']['total']}, "
        f"Normal: {groups['normal']['total']}, "
        f"Surplus: {groups['surplus']['total']})"
    )


def dry_run_combine(input_dir, output_name, args):
    """Writes a CSV showing where each source PDF would be combined."""
    if not os.path.isdir(input_dir):
        print(f"[!] Error: '{input_dir}' is not a valid directory.")
        sys.exit(1)

    pdf_files = sorted(
        filename for filename in os.listdir(input_dir)
        if filename.lower().endswith(".pdf") and os.path.isfile(os.path.join(input_dir, filename))
    )
    if not pdf_files:
        print(f"[!] No PDFs found in directory: '{input_dir}'")
        sys.exit(1)

    if not output_name.lower().endswith(".pdf"):
        output_name += ".pdf"
    base_name, ext = os.path.splitext(output_name)
    report_path = f"{base_name}_dry_run.csv"
    batches = {name: {"number": 1, "file_count": 0} for name in ("single", "normal", "surplus")}
    written_rows = 0

    try:
        with open(report_path, "w", encoding="utf-8-sig", newline="") as report_file:
            writer = csv.writer(report_file)
            writer.writerow(["原始文件名", "合并后文件名", "页数"])

            for filename in pdf_files:
                file_path = os.path.join(input_dir, filename)
                try:
                    with fitz.open(file_path) as source_pdf:
                        page_count = len(source_pdf)
                except Exception as error:
                    print(f"[!] Error reading {filename}: {error}")
                    continue

                group_name = page_count_group(page_count, args.surplus_pages)
                batch = batches[group_name]
                combined_name = combined_output_name(
                    base_name, ext, group_name, batch["number"], args.batch_size
                )
                writer.writerow([filename, os.path.basename(combined_name), page_count])
                written_rows += 1

                batch["file_count"] += 1
                if args.batch_size != -1 and batch["file_count"] >= args.batch_size:
                    batch["number"] += 1
                    batch["file_count"] = 0
    except OSError as error:
        print(f"[!] Error writing dry-run CSV '{report_path}': {error}")
        sys.exit(1)

    print(f"[+] Dry run complete. Wrote {written_rows} rows to {report_path}.")


def load_customers_from_csv(csv_path):
    """Reads customer names and numbers from a two-column UTF-8 CSV."""
    if not os.path.isfile(csv_path):
        print(f"[!] Error: CSV file '{csv_path}' does not exist.")
        sys.exit(1)

    customers = {}
    try:
        # utf-8-sig also accepts a UTF-8 CSV that has no BOM.
        with open(csv_path, "r", encoding="utf-8-sig", newline="") as csv_file:
            for row_number, row in enumerate(csv.reader(csv_file), start=1):
                if len(row) < 2:
                    if row:
                        print(f"[!] Skipping CSV row {row_number}: expected two columns.")
                    continue

                name, customer_number = row[0].strip(), row[1].strip()
                # Allows a normal header such as "Name,Customer Number".
                if row_number == 1 and "customer" in customer_number.lower():
                    continue
                if not customer_number:
                    print(f"[!] Skipping CSV row {row_number}: customer number is empty.")
                    continue
                customers[customer_number] = name
    except UnicodeDecodeError:
        print("[!] Error: CSV must be saved as UTF-8 (CSV UTF-8 in Excel).")
        sys.exit(1)
    except OSError as error:
        print(f"[!] Error reading CSV: {error}")
        sys.exit(1)

    if not customers:
        print("[!] No customer numbers were found in the CSV.")
        sys.exit(1)
    return customers


def exclude_pdfs_by_customer_csv(input_dir, csv_path, output_dir):
    """Copies PDFs except those whose filename contains a customer number from a CSV."""
    if not os.path.isdir(input_dir):
        print(f"[!] Error: '{input_dir}' is not a valid directory.")
        sys.exit(1)

    customers = load_customers_from_csv(csv_path)
    os.makedirs(output_dir, exist_ok=True)
    pdf_files = sorted(
        filename for filename in os.listdir(input_dir)
        if filename.lower().endswith(".pdf") and os.path.isfile(os.path.join(input_dir, filename))
    )

    excluded_numbers = set()
    copied_count = 0
    skipped_count = 0
    for filename in pdf_files:
        excluded_number = next(
            (number for number in customers if f"_{number}_" in filename), None
        )
        if excluded_number is not None:
            excluded_numbers.add(excluded_number)
            continue

        source_path = os.path.join(input_dir, filename)
        destination_path = os.path.join(output_dir, filename)
        if os.path.exists(destination_path):
            print(f"[!] Skipping existing file: {destination_path}")
            skipped_count += 1
        else:
            shutil.copy2(source_path, destination_path)
            print(f"[>] Copied: {filename}")
            copied_count += 1

    unmatched_numbers = sorted(set(customers) - excluded_numbers)
    print(
        f"[+] Exclusion complete. Copied: {copied_count}; "
        f"customers excluded: {len(excluded_numbers)}; existing files skipped: {skipped_count}."
    )
    if unmatched_numbers:
        print(f"[!] {len(unmatched_numbers)} excluded customer number(s) had no matching PDF:")
        for customer_number in unmatched_numbers:
            name = customers[customer_number]
            print(f"    {name} ({customer_number})")


def dry_run_exclude_by_customer_csv(input_dir, csv_path, output_dir):
    """Writes a report of PDFs that would be excluded and customer numbers not found."""
    if not os.path.isdir(input_dir):
        print(f"[!] Error: '{input_dir}' is not a valid directory.")
        sys.exit(1)

    customers = load_customers_from_csv(csv_path)
    os.makedirs(output_dir, exist_ok=True)
    report_path = os.path.join(output_dir, "exclude_dry_run.csv")
    pdf_files = sorted(
        filename for filename in os.listdir(input_dir)
        if filename.lower().endswith(".pdf") and os.path.isfile(os.path.join(input_dir, filename))
    )

    excluded_numbers = set()
    excluded_files = 0
    try:
        with open(report_path, "w", encoding="utf-8-sig", newline="") as report_file:
            writer = csv.writer(report_file)
            writer.writerow(["状态", "客户名称", "客户号", "PDF文件名"])

            for filename in pdf_files:
                excluded_number = next(
                    (number for number in customers if f"_{number}_" in filename), None
                )
                if excluded_number is None:
                    continue

                excluded_numbers.add(excluded_number)
                writer.writerow(["已排除", customers[excluded_number], excluded_number, filename])
                excluded_files += 1

            for customer_number in sorted(set(customers) - excluded_numbers):
                writer.writerow(["未找到", customers[customer_number], customer_number, ""])
    except OSError as error:
        print(f"[!] Error writing dry-run CSV '{report_path}': {error}")
        sys.exit(1)

    print(
        f"[+] Exclusion dry run complete. Excluded files: {excluded_files}; "
        f"customer numbers not found: {len(customers) - len(excluded_numbers)}."
    )
    print(f"[+] Wrote report to {report_path}.")


def process_pdf(args):
    """Original processing logic for a single PDF statement."""
    src = fitz.open(args.input)
    start_pattern = re.compile(r"Page\s+1\s+of", re.IGNORECASE)

    start_indices = []
    print(f"[*] Scanning {len(src)} pages for statement boundaries...")

    for i in range(len(src)):
        page = src[i]
        footer_rect = fitz.Rect(0, page.rect.height * 0.9, page.rect.width, page.rect.height)
        if start_pattern.search(page.get_text("text", clip=footer_rect)):
            start_indices.append(i)

    start_indices.append(len(src))
    total_statements = len(start_indices) - 1
    print(f"[*] Found {total_statements} individual statements.")

    dest = fitz.open()
    statements_in_current_batch = 0
    batch_count = 1

    for j in range(total_statements):
        start = start_indices[j]
        end = start_indices[j+1]

        for page_num in range(start, end):
            src_page = src[page_num]
            rect = src_page.rect

            new_page = dest.new_page(width=rect.width, height=rect.height)

            if args.shrink < 1.0:
                new_w = rect.width * args.shrink
                new_h = rect.height * args.shrink
                x_margin = (rect.width - new_w) / 2
                if args.space_top:
                    y_margin = rect.height - new_h
                else:
                    y_margin = (rect.height - new_h) / 2
                target_rect = fitz.Rect(x_margin, y_margin, x_margin + new_w, y_margin + new_h)
                new_page.show_pdf_page(target_rect, src, page_num)
            else:
                new_page.show_pdf_page(rect, src, page_num)

        if args.pad and (end - start) % 2 != 0:
            last_rect = src[end-1].rect
            dest.new_page(width=last_rect.width, height=last_rect.height)

        statements_in_current_batch += 1

        if args.batch_size != -1 and statements_in_current_batch >= args.batch_size:
            out_name = f"{args.output}_part_{batch_count}.pdf"
            print(f"[>] Writing {out_name}...")
            save_and_close(dest, out_name)

            dest = fitz.open()
            statements_in_current_batch = 0
            batch_count += 1

    if len(dest) > 0:
        suffix = "_combined.pdf" if args.batch_size == -1 else f"_part_{batch_count}.pdf"
        out_name = args.output + suffix
        print(f"[>] Writing {out_name}...")
        save_and_close(dest, out_name)

    src.close()
    print("[+] All tasks complete.")


def main():
    parser = argparse.ArgumentParser(description="Multi-function PDF Processor (Shrink, Pad, Split, Combine)")

    parser.add_argument("input", nargs='?', help="Path to input PDF (for standard processing)")
    parser.add_argument("output", nargs='?', help="Output filename prefix (for standard processing)")

    parser.add_argument("--combine", nargs=2, metavar=('input_folder', 'output_pdf'),
                        help="Combine all PDFs in a folder: --combine [input_folder] [output_pdf]")

    parser.add_argument("--dry-run", action="store_true",
                        help="With --combine or --exclude_by_csv, write a CSV preview instead of creating or copying PDFs.")

    parser.add_argument("--exclude_by_csv", nargs=3,
                        metavar=('input_folder', 'customers_csv', 'output_folder'),
                        help="Copy PDFs excluding filenames that contain _customer_number_ from a two-column CSV.")

    parser.add_argument("--shrink", type=float, default=1.0,
                        help="Scale factor (0.1 to 1.0). Default 1.0 (no shrink).")

    parser.add_argument("--space_top", action="store_true",
                        help="When shrinking, pushes content to the bottom to leave maximum space at the top.")

    parser.add_argument("--pad", action="store_true",
                        help="Add a blank page to statements with an odd number of pages.")

    parser.add_argument("--batch_size", type=int, default=-1,
                        help="Number of source PDFs per combined output file. Default -1 (all in one).")

    # 新增参数：设定区分 surplus 的页数阈值
    parser.add_argument("--surplus_pages", type=int, default=4,
                        help="Single-page PDFs go to _single; 2 through this page count are normal; more go to _surplus. Default 4.")

    args = parser.parse_args()

    # 验证缩放参数
    if not (0 < args.shrink <= 1.0):
        print("[!] Error: Shrink must be between 0 and 1.")
        sys.exit(1)

    # 验证 surplus_pages
    if args.surplus_pages < 1:
        print("[!] Error: max_pages must be at least 1.")
        sys.exit(1)

    # 路由执行
    if args.dry_run and not (args.combine or args.exclude_by_csv):
        parser.error("--dry-run can only be used with --combine or --exclude_by_csv.")
    elif args.exclude_by_csv:
        folder, csv_path, output_folder = args.exclude_by_csv
        if args.dry_run:
            dry_run_exclude_by_customer_csv(folder, csv_path, output_folder)
        else:
            exclude_pdfs_by_customer_csv(folder, csv_path, output_folder)
    elif args.combine:
        folder, out_pdf = args.combine
        if args.dry_run:
            dry_run_combine(folder, out_pdf, args)
        else:
            combine_pdfs(folder, out_pdf, args)
    else:
        if not args.input or not args.output:
            parser.print_help()
            print("\n[!] Error: Provide 'input' and 'output', '--combine', or '--exclude_by_csv'.")
            sys.exit(1)

        if not os.path.exists(args.input):
            print(f"[!] Error: The file '{args.input}' does not exist.")
            sys.exit(1)

        process_pdf(args)

if __name__ == "__main__":
    main()
