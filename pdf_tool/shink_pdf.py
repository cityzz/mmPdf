import fitz  # PyMuPDF
import argparse
import sys
import os

def shrink_and_center_pdf(input_path, output_path, scale):
    """
    Reads a PDF, shrinks content to a percentage, and centers it
    on the original page size. Optimized for 5000+ pages.
    """
    # Ensure output has .pdf extension
    if not output_path.lower().endswith(".pdf"):
        output_path += ".pdf"

    try:
        src = fitz.open(input_path)
        doc = fitz.open()

        total_pages = len(src)
        print(f"[*] Total pages to process: {total_pages}")

        for i in range(total_pages):
            src_page = src[i]
            rect = src_page.rect  # Original page dimensions

            # Create a blank page in the new doc with identical dimensions
            new_page = doc.new_page(width=rect.width, height=rect.height)

            # Calculate shrunken dimensions
            new_w = rect.width * scale
            new_h = rect.height * scale

            # Calculate margins to keep content centered
            x_margin = (rect.width - new_w) / 2
            y_margin = (rect.height - new_h) / 2

            # Define target rectangle (x0, y0, x1, y1)
            target_rect = fitz.Rect(
                x_margin,
                y_margin,
                x_margin + new_w,
                y_margin + new_h
            )

            # Overlay original page onto the new page within the target rect
            new_page.show_pdf_page(target_rect, src, i)

            if (i + 1) % 1000 == 0:
                print(f"[>] Processed {i + 1} pages...")

        print(f"[*] Finalizing and saving to: {output_path}")

        # garbage=3: deduplicates fonts/images
        # deflate=True: compresses the file
        doc.save(output_path, garbage=3, deflate=True)
        doc.close()
        src.close()
        print("[+] Task completed successfully.")

    except Exception as e:
        print(f"[!] Error: {e}")
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(
        description="Shrink PDF content to a specific scale while keeping it centered."
    )

    # Positional Arguments
    parser.add_argument("input", help="Path to the original PDF file")
    parser.add_argument("output", help="Desired output filename (extension optional)")
    parser.add_argument("scale", type=float, help="Scaling factor (e.g., 0.7 for 70%%)")

    args = parser.parse_args()

    # Validate scale range
    if not (0 < args.scale <= 1):
        print("[!] Error: Scale must be between 0 and 1 (exclusive of 0).")
        sys.exit(1)

    # Validate input file existence
    if not os.path.exists(args.input):
        print(f"[!] Error: Input file '{args.input}' not found.")
        sys.exit(1)

    shrink_and_center_pdf(args.input, args.output, args.scale)

if __name__ == "__main__":
    main()
