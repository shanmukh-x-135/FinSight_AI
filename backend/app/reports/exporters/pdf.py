"""Render a report's Markdown to PDF.

Takes the Markdown produced by ``render_markdown`` (the single source of truth)
and lays it out with fpdf2 — a pure-Python engine, so no system libraries are
needed and the image stays light. A lightweight Markdown subset is supported:
``#``/``##``/``###`` headings, ``-`` bullets, ``**bold**`` inline, and blank-line
paragraph breaks — which is exactly what the exporter emits.

Robustness: fpdf2's core fonts are latin-1 only, so any Unicode the LLM might
produce (em dashes, curly quotes, ₹, CJK) is sanitized to a safe latin-1
representation before writing — the roadmap's key PDF edge case. Long text wraps
via ``multi_cell``; missing sections simply don't appear.
"""

from __future__ import annotations

import re

from fpdf import FPDF
from fpdf.enums import XPos, YPos

# Map common Unicode punctuation to latin-1-safe equivalents; anything still
# unrepresentable is replaced (never crashes).
_SUBST = {
    "—": "-", "–": "-", "‘": "'", "’": "'",
    "“": '"', "”": '"', "…": "...", "•": "-",
    "₹": "Rs.", "→": "->", " ": " ",
}


def _latin1(text: str) -> str:
    for uni, rep in _SUBST.items():
        text = text.replace(uni, rep)
    return text.encode("latin-1", "replace").decode("latin-1")


def _strip_inline(text: str) -> str:
    """Remove Markdown bold/italic markers for the flat PDF text."""
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"^\*(.+)\*$", r"\1", text)
    text = re.sub(r"_(.+?)_", r"\1", text)
    return text


class _ReportPDF(FPDF):
    def header(self) -> None:  # no-op; title is rendered in the body
        pass

    def footer(self) -> None:
        self.set_y(-15)
        self.set_font("Helvetica", size=8)
        self.set_text_color(150)
        self.cell(0, 10, f"FinSight AI · page {self.page_no()}", align="C")
        self.set_text_color(0)


def render_pdf(markdown: str) -> bytes:
    pdf = _ReportPDF(format="A4")
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.add_page()
    pdf.set_font("Helvetica", size=11)

    def write(text: str, height: float, *, indent: float = 0.0) -> None:
        # Always start a block at the left margin (+ optional indent) so the
        # width-0 multi_cell has the full line to work with.
        pdf.set_x(pdf.l_margin + indent)
        pdf.multi_cell(0, height, text, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    for raw in markdown.splitlines():
        line = raw.rstrip()
        if not line:
            pdf.ln(3)
            continue

        text = _latin1(_strip_inline(line))

        if line.startswith("### "):
            pdf.set_font("Helvetica", style="B", size=12)
            write(text[4:], 6)
            pdf.set_font("Helvetica", size=11)
        elif line.startswith("## "):
            pdf.ln(2)
            pdf.set_font("Helvetica", style="B", size=14)
            write(text[3:], 7)
            pdf.set_font("Helvetica", size=11)
        elif line.startswith("# "):
            pdf.set_font("Helvetica", style="B", size=18)
            write(text[2:], 9)
            pdf.set_font("Helvetica", size=11)
        elif line.startswith("- "):
            write(_latin1(f"- {text[2:]}"), 5.5, indent=4)
        else:
            write(text, 5.5)

    return bytes(pdf.output())
