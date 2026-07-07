"""PDF output = conversion of the canonical LI .docx.

One source of truth for layout: the .docx is authoritative, and the PDF is a
faithful conversion of it (ADR-0005).  Conversion backends, in order:
  1. Microsoft Word via docx2pdf / COM (the normal path on analyst PCs);
  2. LibreOffice headless (soffice), if installed;
  3. otherwise a clear, actionable error — never a divergent re-layout.
"""
from __future__ import annotations

import os
import shutil
import subprocess


class PdfConversionUnavailable(RuntimeError):
    pass


def docx_to_pdf(docx_path: str, pdf_path: str | None = None) -> str:
    docx_path = os.path.abspath(docx_path)
    pdf_path = pdf_path or os.path.splitext(docx_path)[0] + ".pdf"
    errors = []

    try:                                    # 1) Word (Windows/macOS)
        from docx2pdf import convert       # type: ignore
        convert(docx_path, pdf_path)
        if os.path.exists(pdf_path):
            return pdf_path
        errors.append("docx2pdf produced no file")
    except ImportError:
        errors.append("docx2pdf not installed")
    except Exception as e:
        errors.append(f"docx2pdf/Word failed: {e}")

    soffice = (shutil.which("soffice") or shutil.which("libreoffice")
               or shutil.which("soffice.exe"))
    if soffice:                             # 2) LibreOffice
        outdir = os.path.dirname(pdf_path) or "."
        try:
            subprocess.run([soffice, "--headless", "--convert-to", "pdf",
                            "--outdir", outdir, docx_path],
                           check=True, capture_output=True, timeout=180)
            produced = os.path.join(
                outdir, os.path.splitext(os.path.basename(docx_path))[0] + ".pdf")
            if os.path.exists(produced):
                if produced != pdf_path:
                    shutil.move(produced, pdf_path)
                return pdf_path
            errors.append("LibreOffice produced no file")
        except Exception as e:
            errors.append(f"LibreOffice failed: {e}")
    else:
        errors.append("LibreOffice not found")

    raise PdfConversionUnavailable(
        "PDF conversion requires Microsoft Word (recommended; pip install "
        "docx2pdf) or LibreOffice.  The Word report was generated at "
        f"{docx_path} — open it in Word and Save As PDF.  "
        f"[{'; '.join(errors)}]")
