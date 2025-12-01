import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional

from text_chunker import count_tokens


class ValidationLevel(Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class ValidationResult:
    is_valid: bool
    level: ValidationLevel
    message: str
    details: Optional[dict] = None

    @staticmethod
    def success(message: str = "Validation passed") -> "ValidationResult":
        return ValidationResult(
            is_valid=True, level=ValidationLevel.INFO, message=message
        )

    @staticmethod
    def error(message: str, details: dict = None) -> "ValidationResult":
        return ValidationResult(
            is_valid=False,
            level=ValidationLevel.ERROR,
            message=message,
            details=details,
        )

    @staticmethod
    def warning(message: str, details: dict = None) -> "ValidationResult":
        return ValidationResult(
            is_valid=True,
            level=ValidationLevel.WARNING,
            message=message,
            details=details,
        )
