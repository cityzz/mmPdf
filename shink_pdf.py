import fitz  # PyMuPDF

def shrink_and_center_pymupdf(input_path, output_path, scale=0.7):
    src = fitz.open(input_path)
    doc = fitz.open()  # Create a new PDF
    
    total_pages = len(src)
    print(f"Processing {total_pages} pages with PyMuPDF...")

    for i in range(total_pages):
        src_page = src[i]
        
        # 1. Get original dimensions
        rect = src_page.rect
        width = rect.width
        height = rect.height
        
        # 2. Create a new blank page with the same dimensions
        new_page = doc.new_page(width=width, height=height)
        
        # 3. Calculate the "target" rectangle (70% size, centered)
        # Shrink dimensions
        new_w = width * scale
        new_h = height * scale
        
        # Calculate margins to center
        x_margin = (width - new_w) / 2
        y_margin = (height - new_h) / 2
        
        # Define the target box: (x0, y0, x1, y1)
        target_rect = fitz.Rect(
            x_margin, 
            y_margin, 
            x_margin + new_w, 
            y_margin + new_h
        )
        
        # 4. Place the source page into the target rectangle
        new_page.show_pdf_page(target_rect, src, i)

        if i % 1000 == 0:
            print(f"Progress: {i}/{total_pages}")

    # Save with optimization
    print("Saving file...")
    doc.save(output_path, garbage=3, deflate=True)
    doc.close()
    src.close()
    print("Done!")


# Run it
filename = 'combined-statements.pdf'
shrink_and_center_pymupdf(filename, "shrunk_centered.pdf")
