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

def process_pdf(args):
    if not os.path.exists(args.input):
        print(f"[!] Error: The file '{args.input}' does not exist.")
        sys.exit(1)

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
                    # Push to bottom, leaving all empty space at the top
                    y_margin = rect.height - new_h
                else:
                    # Center vertically
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
    parser = argparse.ArgumentParser(description="Multi-function PDF Processor (Shrink, Pad, Split)")

    parser.add_argument("input", help="Path to input PDF")
    parser.add_argument("output", help="Output filename prefix")

    parser.add_argument("--shrink", type=float, default=1.0,
                        help="Scale factor (0.1 to 1.0). Default 1.0 (no shrink).")

    parser.add_argument("--space_top", action="store_true",
                        help="When shrinking, pushes content to the bottom to leave maximum space at the top.")

    parser.add_argument("--pad", action="store_true",
                        help="Add a blank page to statements with an odd number of pages.")

    parser.add_argument("--batch_size", type=int, default=-1,
                        help="Number of statements per output file. Default -1 (all in one).")

    args = parser.parse_args()

    if not (0 < args.shrink <= 1.0):
        print("[!] Error: Shrink must be between 0 and 1.")
        sys.exit(1)

    process_pdf(args)

if __name__ == "__main__":
    main()
