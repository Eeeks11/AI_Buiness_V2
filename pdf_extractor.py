"""
PDF Text Extraction Utility

Fixed version that handles None values from extract_text() calls.
Some PDFs with images, encrypted text, or complex encoding can return None.
"""

# Standard library
import sys
from pathlib import Path

# Third-party
import pypdf

# Local - models first (single source of truth)
project_root = Path(__file__).parent
codebase_memory = project_root / "memory_systems" / "codebase_memory"
if str(codebase_memory) not in sys.path:
    sys.path.insert(0, str(codebase_memory))

from models.core import ConstitutionalError


def extract_pdf_text(pdf_path: str) -> str:
    """
    Extract text from a PDF file, handling None values from extract_text().
    
    Args:
        pdf_path: Path to the PDF file
    
    Returns:
        str: Extracted text from all pages
    
    Raises:
        FileNotFoundError: If PDF file doesn't exist
        ConstitutionalError: For other PDF reading errors (Rule 4 compliance)
    """
    try:
        with open(pdf_path, 'rb') as pdf:
            reader = pypdf.PdfReader(pdf)
            # Filter out None values before joining to prevent TypeError
            # PDFs with images, encrypted text, or complex encoding can return None
            text = '\n'.join(filter(None, [page.extract_text() for page in reader.pages]))
            return text
    except FileNotFoundError:
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")
    except Exception as e:
        raise ConstitutionalError(f"Error extracting PDF text: {e}")


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python pdf_extractor.py <pdf_file_path>")
        sys.exit(1)
    
    pdf_path = sys.argv[1]
    try:
        text = extract_pdf_text(pdf_path)
        sys.stdout.buffer.write(text.encode('utf-8'))
    except (FileNotFoundError, ConstitutionalError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

