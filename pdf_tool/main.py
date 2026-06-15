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
        print(f"Error saving {name}: {e}")

def process_pdf(input_path, output_prefix, batch_size):
    if not os.path.exists(input_path):
        print(f"Error: The file '{input_path}' does not exist.")
        sys.exit(1)

    src = fitz.open(input_path)
    # Regex to find "Page 1 of Y"
    start_pattern = re.compile(r"Page\s+1\s+of", re.IGNORECASE)

    start_indices = []
    print(f"Scanning {len(src)} pages for statement boundaries...")

    for i in range(len(src)):
        page = src[i]
        # Only scan the bottom 10% of the page to save RAM/CPU
        footer_rect = fitz.Rect(0, page.rect.height * 0.9, page.rect.width, page.rect.height)
        if start_pattern.search(page.get_text("text", clip=footer_rect)):
            start_indices.append(i)

    start_indices.append(len(src))
    total_statements = len(start_indices) - 1
    print(f"Found {total_statements} individual statements.")

    dest = fitz.open()
    statements_in_current_batch = 0
    batch_count = 1

    for j in range(total_statements):
        start = start_indices[j]
        end = start_indices[j+1]
        length = end - start

        dest.insert_pdf(src, from_page=start, to_page=end-1)

        # Add blank page if the individual statement length is odd
        if length % 2 != 0:
            last_page_rect = src[end-1].rect
            dest.new_page(width=last_page_rect.width, height=last_page_rect.height)

        statements_in_current_batch += 1

        # Save batch if limit reached (and batch_size is not -1)
        if batch_size != -1 and statements_in_current_batch >= batch_size:
            output_name = f"{output_prefix}_part_{batch_count}.pdf"
            print(f"Writing {output_name}...")
            save_and_close(dest, output_name)

            dest = fitz.open()
            statements_in_current_batch = 0
            batch_count += 1

    # Final save for the remaining pages or the combined file
    if len(dest) > 0:
        output_name = f"{output_prefix}_combined.pdf" if batch_size == -1 else f"{output_prefix}_part_{batch_count}.pdf"
        print(f"Writing {output_name}...")
        save_and_close(dest, output_name)

    src.close()
    print("Processing complete.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Split and pad multi-tenant PDF statements.")

    parser.add_argument("input", help="Path to the input PDF file")
    parser.add_argument("output", help="Prefix for the output file(s)")

    # Optional argument: if not provided, it defaults to -1
    parser.add_argument(
        "batch_size",
        type=int,
        nargs='?',
        default=-1,
        help="Statements per file. Default is -1 (combined file)."
    )

    args = parser.parse_args()
    process_pdf(args.input, args.output, args.batch_size)
