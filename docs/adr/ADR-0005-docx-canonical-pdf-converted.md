# ADR-0005: LI Word template is canonical; PDF is a conversion

**Status:** accepted · **Date:** 2026-07-06

## Context
Reports must conform to Long International's house style.  That style already
exists as a Word template with named styles (`LI_report_base.docx`,
vendored in `assets/`), used by expert-assist via XML template injection.

## Decision
Generate the .docx by injecting content into the firm template (adapting the
proven expert-assist builder), keeping every style decision in the template.
Produce the PDF by converting that .docx — Microsoft Word (docx2pdf) first,
LibreOffice fallback — never by re-implementing the layout in a PDF library.

## Consequences
- Perfect house-style fidelity and a single place (the template) to restyle.
- PDF generation requires Word or LibreOffice on the machine; analyst PCs
  have Word, and the tool degrades to .docx with an actionable message
  elsewhere.
