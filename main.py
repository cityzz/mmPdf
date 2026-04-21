import fitz  # PyMuPDF
import re

def heavy_duty_pad_pdf(input_path, output_path):
    # Open the source document
    # Using 'with' ensures the file is closed properly
    src = fitz.open(input_path)
    dest = fitz.open()

    start_pattern = re.compile(r"Page\s+1\s+of", re.IGNORECASE)

    # We store only integers (page indices) in this list.
    # Even for 100,000 pages, a list of integers is tiny in RAM.
    start_indices = []

    print("Scanning document structure...")
    for i in range(len(src)):
        # We only extract text from the bottom portion of the page
        # to save CPU and RAM.
        page = src[i]

        # Define a "footer area" (bottom 10% of the page)
        # Rect(x0, y0, x1, y1)
        footer_rect = fitz.Rect(0, page.rect.height * 0.9, page.rect.width, page.rect.height)
        footer_text = page.get_text("text", clip=footer_rect)

        if start_pattern.search(footer_text):
            start_indices.append(i)

    start_indices.append(len(src)) # End boundary

    print(f"Processing {len(start_indices)-1} statements...")

    for j in range(len(start_indices) - 1):
        start = start_indices[j]
        end = start_indices[j+1]
        length = end - start

        # Insert the block of pages
        dest.insert_pdf(src, from_page=start, to_page=end-1)

        if length % 2 != 0:
            # Add blank page matching the size of the last statement page
            last_page_rect = src[end-1].rect
            dest.new_page(width=last_page_rect.width, height=last_page_rect.height)

        # Every 50 statements, we tell Python to try and clear unused memory
        if j % 50 == 0:
            import gc
            gc.collect()

    print("Saving file (this may take a moment for 5000+ pages)...")

    # CRITICAL FOR LARGE FILES:
    # garbage=4: Remove all unused objects and compact the file
    # deflate=True: Compress the internal streams
    dest.save(
        output_path,
        garbage=4,
        deflate=True,
        clean=True
    )

    dest.close()
    src.close()
    print("Finished!")

# Execute


input_file = "combined-statements.pdf"

heavy_duty_pad_pdf(input_file, "compact_output.pdf")
