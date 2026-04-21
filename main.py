import fitz  # PyMuPDF
import re

def pad_odd_statements(input_pdf, output_pdf):
    doc = fitz.open(input_pdf)
    final_doc = fitz.open()
    
    # Regex to find "Page 1 of" (ignoring case and extra spaces)
    start_pattern = re.compile(r"Page\s+1\s+of", re.IGNORECASE)
    
    # 1. Identify the starting page index for every new statement
    statement_starts = []
    for i in range(len(doc)):
        # Extract text from the page to check for the "Page 1" marker
        text = doc[i].get_text("text")
        if start_pattern.search(text):
            statement_starts.append(i)
            
    # Add a marker for the very end of the document
    statement_starts.append(len(doc))
    
    print(f"Found {len(statement_starts) - 1} statements in the file.")

    # 2. Loop through the chunks
    for j in range(len(statement_starts) - 1):
        start_idx = statement_starts[j]
        end_idx = statement_starts[j+1]
        
        # Calculate how many pages this specific statement has
        statement_length = end_idx - start_idx
        
        # Copy the original statement pages into our final document
        final_doc.insert_pdf(doc, from_page=start_idx, to_page=end_idx - 1)
        
        # 3. Add a blank page if the length is odd (1, 3, 5 pages)
        if statement_length % 2 != 0:
            # Match the dimensions of the last page of the statement
            last_page = doc[end_idx - 1]
            final_doc.new_page(width=last_page.rect.width, height=last_page.rect.height)
            print(f"Statement {j+1} was {statement_length} page(s). Added blank padding.")
        else:
            print(f"Statement {j+1} was {statement_length} page(s). No padding needed.")

    # 4. Save the compiled PDF
    final_doc.save(output_pdf)
    final_doc.close()
    doc.close()
    print(f"\nSuccess! Processed PDF saved as: {output_pdf}")

# --- EXECUTION ---
# Replace these with your actual file names


input_file = "combined-statements.pdf"

pad_odd_statements(input_file, "padded_output.pdf")
