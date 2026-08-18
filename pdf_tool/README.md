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
### To combine PDFs into three page-count groups

`--combine` creates up to three files: single-page PDFs are written to
`output_single.pdf`, PDFs with 2 through `--surplus_pages` pages are written to
`output.pdf`, and PDFs exceeding that threshold are written to
`output_surplus.pdf`.

```bash
python pdftool.py --combine C:\Document\folder\some_statements output_all.pdf --surplus_pages 4
```

To limit each combined output to a number of source PDFs, add `--batch_size`.
For example, this creates names such as `output_single_part_1.pdf`,
`output_part_1.pdf`, and `output_surplus_part_1.pdf`, with at most 200 source
PDFs in each part.

```bash
python pdftool.py --combine C:\Document\folder\some_statements output_all.pdf --surplus_pages 4 --batch_size 200
```

### To preview combine output without creating PDFs

Add `--dry-run` to write `output_all_dry_run.csv` instead of combining files.
The CSV contains the original filename, its planned combined output filename, and
its page count. The preview applies the same page grouping and `--batch_size`
rules as a real combine.

```bash
python pdftool.py --combine C:\Document\folder\some_statements output_all.pdf --surplus_pages 4 --batch_size 200 --dry-run
```
### To exclude PDFs using customer numbers from a CSV file

The CSV must contain two columns: customer name followed by customer number. The
tool excludes PDFs whose filename contains the complete `_customer_number_`
segment, then copies all remaining PDFs into the output folder. It does not
overwrite files already in that folder.

```bash
python pdftool.py --exclude_by_csv C:\Document\all_statements C:\Document\customers.csv C:\Document\remaining_statements
```

To preview exclusions without copying PDFs, add `--dry-run`. It writes
`exclude_dry_run.csv` inside the output folder. The report lists every excluded
PDF and every customer number from the CSV that did not match a PDF.

```bash
python pdftool.py --exclude_by_csv C:\Document\all_statements C:\Document\customers.csv C:\Document\remaining_statements --dry-run
```
### To shink files with top space and then split to 200 statements each
```bash
python pdftool.py --shrink 0.955 --space_top --batch_size 200 all_statements.pdf output_prefix
```
