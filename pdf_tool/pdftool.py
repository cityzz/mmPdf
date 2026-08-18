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

def combine_pdfs(input_dir, output_name, args):
    """Combines all PDFs in a directory, separating > surplus_pages docs, with shrink, pad, and batching support."""
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

    # 初始化文档容器和计数器
    dest_normal = fitz.open()
    dest_surplus = fitz.open()

    normal_batch_count = 1
    surplus_batch_count = 1

    normal_in_current_batch = 0
    surplus_in_current_batch = 0

    total_normal_saved = 0
    total_surplus_saved = 0

    for i, filename in enumerate(pdf_files):
        file_path = os.path.join(input_dir, filename)
        try:
            src = fitz.open(file_path)
            page_count = len(src)

            # 判断分流：是正常文件还是超额文件
            is_surplus = page_count > args.surplus_pages
            current_dest = dest_surplus if is_surplus else dest_normal

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

            # 更新当前 Batch 的计数
            if is_surplus:
                surplus_in_current_batch += 1
                total_surplus_saved += 1
                # 触发超额文件的 Batch 保存
                if args.batch_size != -1 and surplus_in_current_batch >= args.batch_size:
                    out_name = f"{base_name}_surplus_part_{surplus_batch_count}{ext}"
                    print(f"[>] Writing {out_name} ({surplus_in_current_batch} files)...")
                    save_and_close(dest_surplus, out_name)
                    dest_surplus = fitz.open()
                    surplus_in_current_batch = 0
                    surplus_batch_count += 1
            else:
                normal_in_current_batch += 1
                total_normal_saved += 1
                # 触发正常文件的 Batch 保存
                if args.batch_size != -1 and normal_in_current_batch >= args.batch_size:
                    out_name = f"{base_name}_part_{normal_batch_count}{ext}"
                    print(f"[>] Writing {out_name} ({normal_in_current_batch} files)...")
                    save_and_close(dest_normal, out_name)
                    dest_normal = fitz.open()
                    normal_in_current_batch = 0
                    normal_batch_count += 1

        except Exception as e:
            print(f"[!] Error reading {filename}: {e}")

        # 每 100 个文件释放一次内存
        if (i + 1) % 100 == 0:
            gc.collect()
            print(f"[*] Processed {i + 1} / {len(pdf_files)} files...")

    print("---")

    # 循环结束后，保存最后一批（或不分批时的全部文件）
    if len(dest_normal) > 0:
        if args.batch_size == -1:
            out_name = output_name  # 不分批，用原名
        else:
            out_name = f"{base_name}_part_{normal_batch_count}{ext}"
        print(f"[>] Saving normal combined PDF to {out_name}...")
        save_and_close(dest_normal, out_name)
    else:
        dest_normal.close()

    if len(dest_surplus) > 0:
        if args.batch_size == -1:
            out_name = f"{base_name}_surplus{ext}"  # 不分批，加 _surplus
        else:
            out_name = f"{base_name}_surplus_part_{surplus_batch_count}{ext}"
        print(f"[>] Saving surplus combined PDF to {out_name}...")
        save_and_close(dest_surplus, out_name)
    else:
        dest_surplus.close()

    print(f"[+] Combine task complete. (Total Normal: {total_normal_saved}, Total Surplus: {total_surplus_saved})")


def exclude_pdfs_by_customer_csv(input_dir, csv_path, output_dir):
    """Copies PDFs except those whose filename contains a customer number from a CSV."""
    if not os.path.isdir(input_dir):
        print(f"[!] Error: '{input_dir}' is not a valid directory.")
        sys.exit(1)
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
                        help="Number of statements per output file. Default -1 (all in one).")

    # 新增参数：设定区分 surplus 的页数阈值
    parser.add_argument("--surplus_pages", type=int, default=4,
                        help="Maximum page count for a 'normal' statement. Statements with more pages go to _surplus. Default 4.")

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
    if args.exclude_by_csv:
        folder, csv_path, output_folder = args.exclude_by_csv
        exclude_pdfs_by_customer_csv(folder, csv_path, output_folder)
    elif args.combine:
        folder, out_pdf = args.combine
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
