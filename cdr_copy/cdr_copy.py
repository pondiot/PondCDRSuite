#!/usr/bin/env python3
"""
cdr_copy - Copy CDR/LU files based on configuration rules.

Usage:
    python3 cdr_copy.py <task_name> [--dry-run]

Example:
    python3 cdr_copy.py telna_cdr
    python3 cdr_copy.py telna_cdr --dry-run
"""
from __future__ import annotations

import argparse
import logging
import os
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple

from config import CDRCopyConfig

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(SCRIPT_DIR, "logs")
LOG_FILE = os.path.join(LOG_DIR, "cdr_copy.log")


def setup_logger(dry_run: bool = False) -> logging.Logger:
    """Setup logging configuration."""
    os.makedirs(LOG_DIR, exist_ok=True)

    logger = logging.getLogger("cdr_copy")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()  # Clear existing handlers

    # File handler
    file_handler = logging.FileHandler(LOG_FILE)
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s - %(message)s", "%Y-%m-%d %H:%M:%S")
    )
    logger.addHandler(file_handler)

    # Console handler for dry-run mode
    if dry_run:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(
            logging.Formatter("%(asctime)s - %(message)s", "%Y-%m-%d %H:%M:%S")
        )
        logger.addHandler(console_handler)

    return logger


def get_file_type(filename: str) -> Optional[str]:
    """Determine file type: CDR or LU."""
    if "_CDR_" in filename:
        return "cdr"
    elif "_LU_" in filename:
        return "lu"
    return None


def extract_company(filename: str) -> Optional[str]:
    """
    Extract company from filename.

    Pattern: LIVE_{Company}_CDR_... or LIVE_{Company}_LU_...
    Returns company name with underscores replaced by spaces.
    """
    if not filename.startswith("LIVE_"):
        return None

    after_prefix = filename[5:]
    cdr_pos = after_prefix.find("_CDR_")
    lu_pos = after_prefix.find("_LU_")

    company = None
    if cdr_pos != -1:
        company = after_prefix[:cdr_pos]
    elif lu_pos != -1:
        company = after_prefix[:lu_pos]

    if company:
        # Replace underscores with spaces
        return company.replace("_", " ")
    return None


def extract_date_from_filename(filename: str) -> Optional[str]:
    """
    Extract date from CDR/LU filename.

    Pattern: LIVE_{CLIENT}_{TYPE}_{YYYYMMDD}...
    Example: LIVE_Company1_CDR_20260406200000_1_20260406211103.csv
    Returns: 2026-04-06
    """
    match = re.search(r"_CDR_(\d{8})", filename) or re.search(r"_LU_(\d{8})", filename)
    if match:
        date_str = match.group(1)  # YYYYMMDD
        try:
            dt = datetime.strptime(date_str, "%Y%m%d")
            return dt.strftime("%Y-%m-%d")  # YYYY-MM-DD
        except ValueError:
            return None
    return None


def should_process_file(
    filename: str, source_path: str, config: CDRCopyConfig
) -> Tuple[bool, str]:
    """
    Check if file should be processed based on filters.

    Returns:
        (should_process, reason) tuple
    """
    # Check file extension
    if not filename.lower().endswith(".csv"):
        return False, "not a CSV file"

    # Check file type
    file_type = get_file_type(filename)
    if not file_type:
        return False, "not a CDR or LU file"

    # Check company filter
    if config.company:
        company = extract_company(filename)
        if not company or config.company.lower() not in company.lower():
            return False, f"company mismatch (expected: {config.company})"

    # Check date range
    from_date, to_date = config.get_date_range()
    if from_date or to_date:
        file_date = extract_date_from_filename(filename)
        if not file_date:
            return False, "no date in filename"

        # Convert YYYY-MM-DD to YYYYMMDD for comparison
        file_date_compact = file_date.replace("-", "")

        if from_date and file_date_compact < from_date:
            return False, f"file date {file_date} before from_date"

        if to_date and file_date_compact > to_date:
            return False, f"file date {file_date} after to_date"

    return True, ""


def build_dest_path(
    source_path: str, filename: str, config: CDRCopyConfig
) -> Optional[str]:
    """
    Build destination path based on flags.

    Returns None if required data cannot be extracted.
    """
    dest_parts = [config.to_path]

    # Apply -by_company flag
    if config.flags["by_company"]:
        company = extract_company(filename)
        if not company:
            return None
        dest_parts.append(company)

    # Apply -by_date flag
    if config.flags["by_date"]:
        date_str = extract_date_from_filename(filename)
        if not date_str:
            return None
        dest_parts.append(date_str)

    # Add filename
    dest_parts.append(filename)

    return os.path.join(*dest_parts)


def should_copy(source_path: str, dest_path: str) -> bool:
    """
    Check if file should be copied.

    Returns False if file already exists at destination.
    """
    return not os.path.exists(dest_path)


def copy_atomically(
    source_path: str, dest_path: str, dry_run: bool = False
) -> bool:
    """Copy file atomically using temp file."""
    if dry_run:
        return True  # Pretend success

    temp_path = dest_path + ".tmp"
    dest_dir = os.path.dirname(dest_path)

    try:
        shutil.copy2(source_path, temp_path)
        os.rename(temp_path, dest_path)
        return True
    except Exception as e:
        if os.path.exists(temp_path):
            try:
                os.unlink(temp_path)
            except Exception:
                pass
        raise e


def process_file(
    source_path: str, filename: str, config: CDRCopyConfig, logger: logging.Logger, dry_run: bool
) -> Tuple[str, int]:
    """
    Process a single file.

    Returns:
        (status, error_count) tuple
        status: "copied", "skipped", "error"
    """
    # Check if file should be processed
    should_process, reason = should_process_file(filename, source_path, config)
    if not should_process:
        logger.info(f"SKIPPED {filename} ({reason})")
        return "skipped", 0

    # Build destination path
    dest_path = build_dest_path(source_path, filename, config)
    if not dest_path:
        if config.flags["by_company"] and config.flags["by_date"]:
            logger.info(f"SKIPPED {filename} (missing company or date in filename)")
        elif config.flags["by_company"]:
            logger.info(f"SKIPPED {filename} (missing company in filename)")
        elif config.flags["by_date"]:
            logger.info(f"SKIPPED {filename} (missing date in filename)")
        return "skipped", 0

    # Check if file should be copied
    if not should_copy(source_path, dest_path):
        logger.info(f"SKIPPED {filename} (already exists)")
        return "skipped", 0

    # Create destination directories
    dest_dir = os.path.dirname(dest_path)
    try:
        os.makedirs(dest_dir, exist_ok=True)
    except Exception as e:
        logger.error(f"ERROR {filename}: cannot create directory: {e}")
        return "error", 1

    # Copy file
    try:
        if dry_run:
            logger.info(f"DRY RUN: Would copy {source_path} -> {dest_path}")
        else:
            copy_atomically(source_path, dest_path, dry_run)
            logger.info(f"COPIED {filename}")
        return "copied", 0
    except Exception as e:
        logger.error(f"ERROR {filename}: {e}")
        return "error", 1


def scan_directory(
    config: CDRCopyConfig, logger: logging.Logger, dry_run: bool
) -> dict:
    """
    Scan source directory and process files.

    Returns statistics dictionary.
    """
    stats = {
        "copied": 0,
        "skipped": 0,
        "errors": 0,
        "dry_run_skipped": 0 if dry_run else None,
    }

    source_dir = config.from_path

    if config.flags["flat"]:
        # Recursive scan with flat structure
        for root, dirs, files in os.walk(source_dir):
            for filename in files:
                source_path = os.path.join(root, filename)
                status, err = process_file(
                    source_path, filename, config, logger, dry_run
                )

                if status == "copied":
                    stats["copied"] += 1
                    if dry_run:
                        stats["dry_run_skipped"] += 1
                elif status == "skipped":
                    stats["skipped"] += 1
                elif status == "error":
                    stats["errors"] += err
    else:
        # Non-recursive scan (top-level only)
        if not os.path.exists(source_dir):
            logger.error(f"Source directory does not exist: {source_dir}")
            return stats

        for filename in os.listdir(source_dir):
            source_path = os.path.join(source_dir, filename)

            if not os.path.isfile(source_path):
                continue

            status, err = process_file(
                source_path, filename, config, logger, dry_run
            )

            if status == "copied":
                stats["copied"] += 1
                if dry_run:
                    stats["dry_run_skipped"] += 1
            elif status == "skipped":
                stats["skipped"] += 1
            elif status == "error":
                stats["errors"] += err

    return stats


def log_summary(stats: dict, logger: logging.Logger):
    """Log operation summary."""
    summary_parts = [
        f"copied={stats['copied']}",
        f"skipped={stats['skipped']}",
        f"errors={stats['errors']}",
    ]

    if stats["dry_run_skipped"] is not None:
        summary_parts.append(f"dry_run_skipped={stats['dry_run_skipped']}")

    summary = "RUN SUMMARY: " + " ".join(summary_parts)
    logger.info(summary)


def main():
    parser = argparse.ArgumentParser(
        description="Copy CDR/LU files based on configuration rules"
    )
    parser.add_argument("task_name", help="Name of the task configuration")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without copying files",
    )

    args = parser.parse_args()

    # Load configuration
    try:
        config = CDRCopyConfig.load(args.task_name)
    except (FileNotFoundError, ValueError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    # Validate configuration
    valid, error = config.validate()
    if not valid:
        print(f"Error: {error}", file=sys.stderr)
        sys.exit(1)

    # Setup logger
    logger = setup_logger(args.dry_run)

    if args.dry_run:
        logger.info("DRY RUN MODE - no files will be copied")

    # Scan and process
    stats = scan_directory(config, logger, args.dry_run)

    # Log summary
    log_summary(stats, logger)

    # Exit with error code if any errors occurred
    if stats["errors"] > 0:
        sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    main()
