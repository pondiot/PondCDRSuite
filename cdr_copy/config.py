#!/usr/bin/env python3
"""
Configuration loader for cdr_copy module.

Loads task configurations from .env files in config/ directory.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from dotenv import dotenv_values

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_DIR = os.path.join(SCRIPT_DIR, "config")


@dataclass
class CDRCopyConfig:
    """Configuration for a cdr_copy task."""

    config_name: str
    from_path: str
    to_path: str
    company: Optional[str] = None
    flags: dict | None = None
    from_date: Optional[str] = None
    to_date: Optional[str] = None

    def __post_init__(self):
        if self.flags is None:
            self.flags = {}

    @classmethod
    def load(cls, config_name: str) -> "CDRCopyConfig":
        """Load configuration from .env file."""
        config_path = os.path.join(CONFIG_DIR, f"{config_name}.env")

        if not os.path.exists(config_path):
            raise FileNotFoundError(f"Configuration file not found: {config_path}")

        # Load .env file
        env_values = dotenv_values(config_path)

        # Extract mandatory parameters
        from_path = env_values.get("from", "").strip().strip('"\'')
        to_path = env_values.get("to", "").strip().strip('"\'')

        if not from_path:
            raise ValueError(f"Missing mandatory parameter 'from' in {config_path}")
        if not to_path:
            raise ValueError(f"Missing mandatory parameter 'to' in {config_path}")

        # Extract optional parameters
        company = env_values.get("company", "").strip().strip('"\'') or None
        from_date = env_values.get("from_date", "").strip().strip('"\'') or None
        to_date = env_values.get("to_date", "").strip().strip('"\'') or None

        # Extract flags (parameters without values or with specific values)
        flags = {
            "by_company": _is_flag_set(env_values, "-by_company"),
            "flat": _is_flag_set(env_values, "-flat"),
            "by_date": _is_flag_set(env_values, "-by_date"),
            "yesterday": _is_flag_set(env_values, "-yesterday"),
            "today": _is_flag_set(env_values, "-today"),
        }

        return cls(
            config_name=config_name,
            from_path=from_path,
            to_path=to_path,
            company=company,
            flags=flags,
            from_date=from_date,
            to_date=to_date,
        )

    def validate(self) -> tuple[bool, Optional[str]]:
        """Validate configuration parameters."""
        # Check source directory
        if not os.path.exists(self.from_path):
            return False, f"Source directory does not exist: {self.from_path}"

        if not os.path.isdir(self.from_path):
            return False, f"Source path is not a directory: {self.from_path}"

        # Check or create destination directory
        if os.path.exists(self.to_path) and not os.path.isdir(self.to_path):
            return False, f"Destination exists but is not a directory: {self.to_path}"

        if not os.path.exists(self.to_path):
            try:
                os.makedirs(self.to_path, exist_ok=True)
            except Exception as e:
                return False, f"Cannot create destination directory: {self.to_path}: {e}"

        if not os.access(self.to_path, os.W_OK):
            return False, f"Destination directory is not writable: {self.to_path}"

        # Validate date formats
        if self.from_date and not _is_valid_date(self.from_date):
            return False, f"Invalid from_date format: {self.from_date}. Use YYYYMMDD"

        if self.to_date and not _is_valid_date(self.to_date):
            return False, f"Invalid to_date format: {self.to_date}. Use YYYYMMDD"

        # Check date range logic
        if self.from_date and self.to_date:
            if self.from_date > self.to_date:
                return False, "from_date cannot be greater than to_date"

        # Check incompatible flags
        if self.flags["yesterday"] and self.flags["today"]:
            return False, "Cannot use both -yesterday and -today flags"

        return True, None

    def get_date_range(self) -> tuple[Optional[str], Optional[str]]:
        """
        Get effective date range for filtering.

        Returns:
            (from_date, to_date) tuple in YYYYMMDD format or (None, None)
        """
        from_date = self.from_date
        to_date = self.to_date

        # Apply convenient flags
        if self.flags["yesterday"]:
            yesterday = datetime.now() - timedelta(days=1)
            yesterday_str = yesterday.strftime("%Y%m%d")
            from_date = from_date or yesterday_str
            to_date = to_date or yesterday_str
        elif self.flags["today"]:
            today = datetime.now()
            today_str = today.strftime("%Y%m%d")
            from_date = from_date or today_str
            to_date = to_date or today_str

        return from_date, to_date


def _is_flag_set(env_values: dict, flag_name: str) -> bool:
    """Check if a flag is set in .env values."""
    # Flag is set if key exists in env_values
    return flag_name in env_values


def _is_valid_date(date_str: str) -> bool:
    """Check if date string is in valid YYYYMMDD format."""
    if len(date_str) != 8:
        return False
    try:
        datetime.strptime(date_str, "%Y%m%d")
        return True
    except ValueError:
        return False
