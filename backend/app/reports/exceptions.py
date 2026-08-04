"""Reports-domain exceptions."""

from __future__ import annotations

from fastapi import status

from app.shared.exceptions import AppException


class ReportNotFoundError(AppException):
    status_code = status.HTTP_404_NOT_FOUND
    error_type = "report_not_found"

    def __init__(self) -> None:
        super().__init__("Report not found.")


class UnsupportedExportFormatError(AppException):
    status_code = status.HTTP_400_BAD_REQUEST
    error_type = "unsupported_export_format"

    def __init__(self, fmt: str) -> None:
        super().__init__(f"Unsupported export format: {fmt!r}.")
