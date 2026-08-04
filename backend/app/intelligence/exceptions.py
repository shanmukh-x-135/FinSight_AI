"""Intelligence-domain exceptions."""

from __future__ import annotations

from fastapi import status

from app.shared.exceptions import AppException


class ReportNotFoundError(AppException):
    status_code = status.HTTP_404_NOT_FOUND
    error_type = "report_not_found"

    def __init__(self) -> None:
        super().__init__("Report not found.")
