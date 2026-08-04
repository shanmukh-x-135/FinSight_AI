"""Report exporters. Markdown is the single source of truth; PDF is rendered
from the Markdown, so the two formats never drift (design doc: render on demand,
never store redundantly)."""

from app.reports.exporters.markdown import render_markdown
from app.reports.exporters.pdf import render_pdf

__all__ = ["render_markdown", "render_pdf"]
