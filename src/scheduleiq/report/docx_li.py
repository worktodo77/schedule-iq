"""LI-house-style .docx writer (template-injection, pure stdlib).

Adapted from Long International's expert-assist section builder
(skills/draft-section/reference/report_docx.py): the firm template
(assets/LI_report_base.docx) supplies the styles — Heading 1/2/3 (ALL-CAPS
H1-2 per house style), Numbered Paragraph body, Excerpt or Quote, Caption,
FootnoteText — and we inject a new document body, footnotes, and media.

House style rules applied here: two spaces between sentences are the
author's responsibility in block text; smart quotes applied; teal (#1F6F7B)
LI table headers with gray grid; captions centered; US Letter or A4.

Block model (list of dicts):
  {"type": "h1"|"h2"|"h3"|"np"|"bodytext"|"excerpt"|"caption", "text": ...}
  {"type": "table", "rows": [[...], ...]}          header = first row
  {"type": "figure", "image": "/abs/path.png"}
Text tokens:  [[C:key]] -> footnote reference;  {{i:...}} -> italics.
"""
from __future__ import annotations

import os
import re
import struct
import zipfile

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
TEAL = "1F6F7B"
STYLE = {"h1": "Heading1", "h2": "Heading2", "h3": "Heading3",
         "np": "NumberedParagraph", "excerpt": "ExcerptorQuote",
         "bodytext": "BodyText", "caption": "Caption"}
DEFAULT_TEMPLATE = os.path.join(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
    "assets", "LI_report_base.docx")


def _template_path() -> str:
    if os.path.exists(DEFAULT_TEMPLATE):
        return DEFAULT_TEMPLATE
    # packaged (PyInstaller) layout: assets next to the executable
    import sys
    base = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    cand = os.path.join(base, "assets", "LI_report_base.docx")
    if os.path.exists(cand):
        return cand
    raise FileNotFoundError("LI_report_base.docx template not found")


def esc(t) -> str:
    return (str(t).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def smart(t: str) -> str:
    t = re.sub(r"(?<=\w)'(?=\w)", "’", t)
    t = re.sub(r'"([^"]*)"', "“\\1”", t)
    return t.replace("'", "’")


def png_size(path):
    with open(path, "rb") as f:
        head = f.read(24)
    if len(head) == 24 and head[:8] == b"\x89PNG\r\n\x1a\n" and head[12:16] == b"IHDR":
        return struct.unpack(">II", head[16:24])
    return None


class _Runs:
    def __init__(self):
        self.footnote_seq: list[str] = []

    def render(self, text: str) -> str:
        out, i = [], 0
        for m in re.finditer(r"\[\[C:([a-z0-9_]+)\]\]|\{\{i:(.*?)\}\}", text):
            if m.start() > i:
                out.append(f'<w:r><w:t xml:space="preserve">{esc(text[i:m.start()])}</w:t></w:r>')
            if m.group(1):
                self.footnote_seq.append(m.group(1))
                fid = len(self.footnote_seq)
                out.append('<w:r><w:rPr><w:rStyle w:val="FootnoteReference"/></w:rPr>'
                           f'<w:footnoteReference w:id="{fid}"/></w:r>')
            else:
                out.append('<w:r><w:rPr><w:i/></w:rPr>'
                           f'<w:t xml:space="preserve">{esc(m.group(2))}</w:t></w:r>')
            i = m.end()
        if i < len(text):
            out.append(f'<w:r><w:t xml:space="preserve">{esc(text[i:])}</w:t></w:r>')
        return "".join(out)

    def para(self, style: str, text: str, jc: str | None = None) -> str:
        j = f'<w:jc w:val="{jc}"/>' if jc else ""
        return (f'<w:p><w:pPr><w:pStyle w:val="{style}"/>{j}</w:pPr>'
                f'{self.render(smart(text))}</w:p>')


def table_xml(rows: list[list[str]], font_sz: int = 18) -> str:
    n = len(rows[0])
    total = 10106
    cw = [total // n] * n
    cw[-1] = total - sum(cw[:-1])
    bdr = "<w:tblBorders>" + "".join(
        f'<w:{x} w:val="single" w:sz="4" w:space="0" w:color="BFBFBF"/>'
        for x in ["top", "left", "bottom", "right", "insideH", "insideV"]
    ) + "</w:tblBorders>"

    def cell(t, w, hdr):
        shd = f'<w:shd w:val="clear" w:color="auto" w:fill="{TEAL}"/>' if hdr else ""
        rpr = (f'<w:rPr><w:b/><w:color w:val="FFFFFF"/><w:sz w:val="{font_sz}"/></w:rPr>'
               if hdr else f'<w:rPr><w:sz w:val="{font_sz}"/></w:rPr>')
        return (f'<w:tc><w:tcPr><w:tcW w:w="{w}" w:type="dxa"/>{shd}'
                '<w:tcMar><w:top w:w="40" w:type="dxa"/><w:left w:w="80" w:type="dxa"/>'
                '<w:bottom w:w="40" w:type="dxa"/><w:right w:w="80" w:type="dxa"/></w:tcMar>'
                '<w:vAlign w:val="center"/></w:tcPr>'
                f'<w:p><w:pPr><w:spacing w:before="20" w:after="20"/>{rpr}</w:pPr>'
                f'<w:r>{rpr}<w:t xml:space="preserve">{esc(smart(str(t)))}</w:t></w:r></w:p></w:tc>')

    trs = []
    for ri, row in enumerate(rows):
        hdr = ri == 0
        trs.append(f'<w:tr>{"<w:trPr><w:tblHeader/></w:trPr>" if hdr else ""}'
                   + "".join(cell(c, cw[ci], hdr) for ci, c in enumerate(row))
                   + "</w:tr>")
    return ('<w:tbl><w:tblPr><w:tblW w:w="10106" w:type="dxa"/>' + bdr +
            '<w:tblLook w:val="04A0"/></w:tblPr><w:tblGrid>' +
            "".join(f'<w:gridCol w:w="{w}"/>' for w in cw) +
            "</w:tblGrid>" + "".join(trs) + "</w:tbl>")


def figure_xml(rid: str, cx: int, cy: int, idn: int) -> str:
    return (
        '<w:p><w:pPr><w:jc w:val="center"/></w:pPr><w:r><w:drawing>'
        '<wp:inline xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"'
        f' distT="0" distB="0" distL="0" distR="0"><wp:extent cx="{cx}" cy="{cy}"/>'
        f'<wp:effectExtent l="0" t="0" r="0" b="0"/><wp:docPr id="{idn}" name="Figure {idn}"/>'
        '<wp:cNvGraphicFramePr><a:graphicFrameLocks '
        'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" noChangeAspect="1"/>'
        '</wp:cNvGraphicFramePr>'
        '<a:graphic xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">'
        '<a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">'
        '<pic:pic xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture">'
        f'<pic:nvPicPr><pic:cNvPr id="{idn}" name="Figure {idn}"/><pic:cNvPicPr/></pic:nvPicPr>'
        f'<pic:blipFill><a:blip r:embed="{rid}"/><a:stretch><a:fillRect/></a:stretch></pic:blipFill>'
        f'<pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm>'
        '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr></pic:pic>'
        '</a:graphicData></a:graphic></wp:inline></w:drawing></w:r></w:p>')


def footnotes_xml(seq: list[str], fns: dict) -> str:
    seps = ('<w:footnote w:type="separator" w:id="-1"><w:p><w:pPr>'
            '<w:spacing w:after="0" w:line="240" w:lineRule="auto"/></w:pPr>'
            '<w:r><w:separator/></w:r></w:p></w:footnote>'
            '<w:footnote w:type="continuationSeparator" w:id="0"><w:p><w:pPr>'
            '<w:spacing w:after="0" w:line="240" w:lineRule="auto"/></w:pPr>'
            '<w:r><w:continuationSeparator/></w:r></w:p></w:footnote>')
    body = ""
    for i, key in enumerate(seq, 1):
        f = fns.get(key, {"text": key, "tag": ""})
        body += (f'<w:footnote w:id="{i}"><w:p><w:pPr>'
                 '<w:pStyle w:val="FootnoteText"/></w:pPr>'
                 '<w:r><w:rPr><w:rStyle w:val="FootnoteReference"/></w:rPr>'
                 '<w:footnoteRef/></w:r>'
                 f'<w:r><w:t xml:space="preserve"> {esc(f.get("text", ""))}  </w:t></w:r>'
                 f'<w:r><w:rPr><w:b/></w:rPr><w:t xml:space="preserve">'
                 f'{esc(f.get("tag", ""))}</w:t></w:r></w:p></w:footnote>')
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            f'<w:footnotes xmlns:w="{W}">{seps}{body}</w:footnotes>')


MAXCX = 5486400   # 6" printable width in EMU


def build_docx(blocks: list[dict], out_path: str,
               footnotes: dict | None = None,
               template: str | None = None,
               paper: str = "letter") -> str:
    template = template or _template_path()
    footnotes = footnotes or {}
    runs = _Runs()
    parts: list[str] = []
    media: dict[str, str] = {}
    figs: list[tuple[str, str]] = []

    for bi, blk in enumerate(blocks):
        ty = blk["type"]
        if ty == "table":
            parts.append(table_xml(blk["rows"], blk.get("font_sz", 18)))
        elif ty == "figure":
            img = blk["image"]
            if not os.path.exists(img):
                raise FileNotFoundError(f"figure image not found: {img} (block {bi})")
            n = len(figs) + 1
            ph = f"rIdFIG{n}"
            sz = png_size(img)
            cx, cy = MAXCX, 2939000
            if sz and sz[0] > 0:
                cy = int(MAXCX * sz[1] / sz[0])
            arc = f"word/media/zfig{n}.png"
            figs.append((ph, arc))
            media[arc] = img
            parts.append(figure_xml(ph, cx, cy, idn=100 + n))
        elif ty in STYLE:
            parts.append(runs.para(STYLE[ty], blk["text"],
                                   jc="center" if ty == "caption" else None))
        else:
            raise ValueError(f"unknown block type '{ty}' (block {bi})")

    body = "".join(parts)
    with zipfile.ZipFile(template) as z:
        doc = z.read("word/document.xml").decode("utf-8")
        rels = z.read("word/_rels/document.xml.rels").decode("utf-8")
        ct = z.read("[Content_Types].xml").decode("utf-8")
    sect = re.findall(r"<w:sectPr\b.*?</w:sectPr>", doc, re.S)[-1]
    if paper:
        pg = {"a4": 'w:w="11906" w:h="16838"',
              "letter": 'w:w="12240" w:h="15840"'}[paper]
        sect = re.sub(r"<w:pgSz[^/]*/>", f"<w:pgSz {pg}/>", sect)
    doc = re.sub(r"<w:body>.*</w:body>",
                 lambda m: "<w:body>" + body + sect + "</w:body>", doc, flags=re.S)

    def nextrid(r):
        return "rId" + str(max(int(x) for x in re.findall(r'Id="rId(\d+)"', r)) + 1)

    if "/footnotes" not in rels:
        fid = nextrid(rels)
        rels = rels.replace("</Relationships>",
                            f'<Relationship Id="{fid}" Type="http://schemas.openxmlformats.org/'
                            'officeDocument/2006/relationships/footnotes" '
                            'Target="footnotes.xml"/></Relationships>')
    for ph, arc in figs:
        rid = nextrid(rels)
        rels = rels.replace("</Relationships>",
                            f'<Relationship Id="{rid}" Type="http://schemas.openxmlformats.org/'
                            f'officeDocument/2006/relationships/image" Target="{arc[5:]}"/>'
                            '</Relationships>')
        doc = doc.replace(ph, rid)
    if "footnotes+xml" not in ct:
        ct = ct.replace("</Types>",
                        '<Override PartName="/word/footnotes.xml" ContentType='
                        '"application/vnd.openxmlformats-officedocument.wordprocessingml.'
                        'footnotes+xml"/></Types>')
    if figs and 'Extension="png"' not in ct:
        ct = ct.replace("</Types>",
                        '<Default Extension="png" ContentType="image/png"/></Types>')
    fx = footnotes_xml(runs.footnote_seq, footnotes)

    with zipfile.ZipFile(template) as zin, \
            zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zout:
        for n in zin.namelist():
            if n in ("word/document.xml", "word/_rels/document.xml.rels",
                     "[Content_Types].xml", "word/footnotes.xml"):
                continue
            zout.writestr(n, zin.read(n))
        zout.writestr("word/document.xml", doc)
        zout.writestr("word/_rels/document.xml.rels", rels)
        zout.writestr("[Content_Types].xml", ct)
        zout.writestr("word/footnotes.xml", fx)
        for arc, src in media.items():
            zout.write(src, arc)
    return out_path
