# Multi-Function PDF Processor

A high-performance command-line utility powered by PyMuPDF (`fitz`) designed for advanced PDF manipulation. It handles specialized tasks such as scanning for structural statement boundaries based on text anchors, page shrinking, odd-page padding, statement batching, and high-performance merging of bulk files (handling 1,000+ PDFs seamlessly) with strict memory management.

## Features

- **Bulk PDF Combining**: Merges large numbers of PDF files from a specified folder into a single file with predictable alphabetical ordering and active garbage collection to maintain low RAM usage.
- **Statement Boundary Detection**: Scans documents to identify logical boundaries via dynamic regex parsing (e.g., matching footer patterns like `Page 1 of`).
- **Content Scaling & Positioning**: Shrinks layout contents dynamically, centering them horizontally and aligning them either vertically centered or pushed down to leave top margins open.
- **Smart Padding**: Seamlessly adds clean structural filler pages to statements containing odd page counts for proper duplex print alignment.
- **Batch Splitting**: Breaks up a massive monolithic stream of statements into distinct, multi-statement batch files.

---

## Installation

Ensure you have Python 3.7+ installed alongside the required `PyMuPDF` dependency:

```bash
pip install pymupdf
```

## Usage
### To shink files with top space
```bash
python pdftool.py --shrink 0.955 --space_top combined-statements.pdf output_prefix
```
### To combine all pdfs in one folder to one pdf file
```bash
python pdftool.py --combine C:\Document\folder\some_statements output_all.pdf
```
### To exclude PDFs using customer numbers from a CSV file

The CSV must contain two columns: customer name followed by customer number. The
tool excludes PDFs whose filename contains the complete `_customer_number_`
segment, then copies all remaining PDFs into the output folder. It does not
overwrite files already in that folder.

```bash
python pdftool.py --exclude_by_csv C:\Document\all_statements C:\Document\customers.csv C:\Document\remaining_statements
```
### To shink files with top space and then split to 200 statements each
```bash
python pdftool.py --shrink 0.955 --space_top --batch_size 200 all_statements.pdf output_prefix
```
