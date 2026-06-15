import fitz  # PyMuPDF
import re
import argparse
import gc
import os
import sys

def save_and_close(doc, name):
    """Saves with high compression and releases memory."""
    try:
        doc.save(name, garbage=4, deflate=True, clean=True)
        doc.close()
        gc.collect()
    except Exception as e:
        print(f"[!] Error saving {name}: {e}")

def combine_pdfs(input_dir, output_name):
    """Combines all PDFs in a directory into a single PDF, separating >5 page documents."""
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

    # 构造超过5页的超额文件名 (例如: result.pdf -> result_surplus.pdf)
    base_name, ext = os.path.splitext(output_name)
    surplus_name = f"{base_name}_surplus{ext}"

    # 初始化两个 PDF 文档容器
    dest_normal = fitz.open()
    dest_surplus = fitz.open()

    normal_count = 0
    surplus_count = 0

    for i, filename in enumerate(pdf_files):
        file_path = os.path.join(input_dir, filename)
        try:
            src = fitz.open(file_path)
            page_count = len(src)

            # 根据页数分流
            if page_count > 5:
                dest_surplus.insert_pdf(src)
                surplus_count += 1
            else:
                dest_normal.insert_pdf(src)
                normal_count += 1

            src.close()
        except Exception as e:
            print(f"[!] Error reading {filename}: {e}")

        # 每 100 个文件手动释放一次内存
        if (i + 1) % 100 == 0:
            gc.collect()
            print(f"[*] Processed {i + 1} / {len(pdf_files)} files...")

    print("---")
    # 保存正常合并的文件（只有在里面有内容时才保存）
    if len(dest_normal) > 0:
        print(f"[>] Saving normal combined PDF ({normal_count} files) to {output_name}...")
        save_and_close(dest_normal, output_name)
    else:
        dest_normal.close()
        print("[*] No files with <= 5 pages found. Normal PDF not created.")

    # 保存超过5页合并的文件（只有在里面有内容时才保存）
    if len(dest_surplus) > 0:
        print(f"[>] Saving surplus combined PDF ({surplus_count} files) to {surplus_name}...")
        save_and_close(dest_surplus, surplus_name)
    else:
        dest_surplus.close()
        print("[*] No files with > 5 pages found. Surplus PDF not created.")

    print("[+] Combine task complete.")

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

                # Horizontal center
                x_margin = (rect.width - new_w) / 2

                # Vertical alignment
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

    # Made these nargs='?' so they don't block the execution if --combine is used instead
    parser.add_argument("input", nargs='?', help="Path to input PDF (for standard processing)")
    parser.add_argument("output", nargs='?', help="Output filename prefix (for standard processing)")

    # New combine flag that accepts exactly 2 values
    parser.add_argument("--combine", nargs=2, metavar=('input_folder', 'output_pdf'),
                        help="Combine all PDFs in a folder: --combine [input_folder] [output_pdf]")

    parser.add_argument("--shrink", type=float, default=1.0,
                        help="Scale factor (0.1 to 1.0). Default 1.0 (no shrink).")

    parser.add_argument("--space_top", action="store_true",
                        help="When shrinking, pushes content to the bottom to leave maximum space at the top.")

    parser.add_argument("--pad", action="store_true",
                        help="Add a blank page to statements with an odd number of pages.")

    parser.add_argument("--batch_size", type=int, default=-1,
                        help="Number of statements per output file. Default -1 (all in one).")

    args = parser.parse_args()

    # Route execution based on which inputs were provided
    if args.combine:
        folder, out_pdf = args.combine
        combine_pdfs(folder, out_pdf)
    else:
        # If --combine isn't used, check if the standard positionals are present
        if not args.input or not args.output:
            parser.print_help()
            print("\n[!] Error: Provide 'input' and 'output' OR use '--combine input_folder output_pdf'")
            sys.exit(1)

        if not os.path.exists(args.input):
            print(f"[!] Error: The file '{args.input}' does not exist.")
            sys.exit(1)

        if not (0 < args.shrink <= 1.0):
            print("[!] Error: Shrink must be between 0 and 1.")
            sys.exit(1)

        process_pdf(args)

if __name__ == "__main__":
    main()
