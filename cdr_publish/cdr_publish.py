#!/usr/bin/env python3
"""
cdr_publish - Publish CDR/LU files for HTTP access

Reads from /home/cdr_admin/CDRs/outbound/
Creates three structures in /srv/cdr_publish/:
  - raw: All files mixed
  - by_date: Organized by date extracted from filename
  - by_company: Organized by company (subdirectories only)
"""

import os
import sys
import shutil
import logging
import argparse
import re
from datetime import datetime
from pathlib import Path
from typing import Tuple, Optional, Dict

# Import configuration
try:
    from config import SOURCE_BASE, TARGET_BASE
except ImportError:
    # Default values if config.py not found
    SOURCE_BASE = "/home/cdr_admin/CDRs/outbound"
    TARGET_BASE = "/srv/cdr_publish"

# Setup logging
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(SCRIPT_DIR, "logs")
LOG_FILE = os.path.join(LOG_DIR, "publish_process.log")


def setup_logger():
    """Setup logging configuration."""
    os.makedirs(LOG_DIR, exist_ok=True)

    logger = logging.getLogger('cdr_publish')
    logger.setLevel(logging.INFO)

    handler = logging.FileHandler(LOG_FILE)
    handler.setFormatter(logging.Formatter('%(asctime)s - %(message)s', '%Y-%m-%d %H:%M:%S'))
    logger.addHandler(handler)

    return logger


def extract_date_from_filename(filename: str) -> Optional[str]:
    """
    Extract date from CDR/LU filename.
    Pattern: LIVE_{CLIENT}_{TYPE}_{START_DATETIME}_{N}_{END_DATETIME}.csv
    Example: LIVE_Zeppelincompany_CDR_20260406200000_1_20260406211103.csv
    Returns: 2026-04-06
    """
    match = re.search(r'_CDR_(\d{8})', filename) or re.search(r'_LU_(\d{8})', filename)
    if match:
        date_str = match.group(1)  # 20260406
        try:
            dt = datetime.strptime(date_str, "%Y%m%d")
            return dt.strftime("%Y-%m-%d")  # 2026-04-06
        except ValueError:
            return None
    return None


def build_dest_paths(source_file: str, file_type: str, client: str, filename: str) -> Dict[str, str]:
    """
    Build destination paths for all three structures.

    Returns dict with keys: raw, by_date, by_company
    """
    base_dir = os.path.join(TARGET_BASE, file_type)

    # Raw: files directly in root
    raw_path = os.path.join(base_dir, "raw", filename)

    # By date: extract date from filename
    date_str = extract_date_from_filename(filename)
    if date_str:
        by_date_path = os.path.join(base_dir, "by_date", date_str, filename)
    else:
        by_date_path = None

    # By company: only subdirectories (same structure as source)
    by_company_path = os.path.join(base_dir, "by_company", client, filename)

    return {
        "raw": raw_path,
        "by_date": by_date_path,
        "by_company": by_company_path
    }


def should_copy(source_path: str, dest_path: str) -> bool:
    """Check if file should be copied."""
    if not os.path.exists(dest_path):
        return True
    return os.path.getsize(source_path) != os.path.getsize(dest_path)


def copy_atomically(source_path: str, dest_path: str) -> bool:
    """Copy file atomically using temp file."""
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
            except:
                pass
        raise e


def process_file(source_path: str, file_type: str, client: str, filename: str,
                 modes: list, logger) -> Dict[str, Tuple[str, int]]:
    """
    Process a single file for specified modes.

    Returns dict with mode as key and (status, error_count) as value.
    """
    dest_paths = build_dest_paths(source_path, file_type, client, filename)
    results = {}

    for mode in modes:
        dest_path = dest_paths.get(mode)
        if not dest_path:
            results[mode] = ("skipped", 0)  # by_date not available
            continue

        try:
            os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        except Exception as e:
            logger.error(f"ERROR {mode.upper()} {filename}: cannot create directory: {e}")
            results[mode] = ("error", 1)
            continue

        if not should_copy(source_path, dest_path):
            logger.info(f"{mode.upper()} - SKIPPED {filename}")
            results[mode] = ("skipped", 0)
            continue

        try:
            dest_exists = os.path.exists(dest_path)
            copy_atomically(source_path, dest_path)

            if dest_exists:
                logger.info(f"{mode.upper()} - OVERWRITTEN {filename}")
                results[mode] = ("overwritten", 0)
            else:
                logger.info(f"{mode.upper()} - COPIED {filename}")
                results[mode] = ("copied", 0)
        except Exception as e:
            logger.error(f"ERROR {mode.upper()} {filename}: {e}")
            results[mode] = ("error", 1)

    return results


def scan_directory(source_base: str, modes: list, logger) -> Dict[str, Dict[str, int]]:
    """
    Scan source directory and process files.

    Returns nested dict with mode and status counts.
    """
    counts = {mode: {"copied": 0, "skipped": 0, "overwritten": 0, "errors": 0} for mode in modes}

    for file_type in ["cdr", "lu"]:
        source_dir = os.path.join(source_base, file_type)

        if not os.path.exists(source_dir):
            continue

        # Walk through client subdirectories
        for client in os.listdir(source_dir):
            client_path = os.path.join(source_dir, client)

            if not os.path.isdir(client_path):
                continue

            for filename in os.listdir(client_path):
                if not filename.lower().endswith('.csv'):
                    continue

                source_path = os.path.join(client_path, filename)
                results = process_file(source_path, file_type, client, filename, modes, logger)

                for mode, (status, err) in results.items():
                    if status == "copied":
                        counts[mode]["copied"] += 1
                    elif status == "skipped":
                        counts[mode]["skipped"] += 1
                    elif status == "overwritten":
                        counts[mode]["overwritten"] += 1
                    elif status == "error":
                        counts[mode]["errors"] += err

    return counts


def log_summary(counts: Dict[str, Dict[str, int]], logger):
    """Log operation summary for each mode."""
    for mode, mode_counts in counts.items():
        total_errors = mode_counts["errors"]
        summary = (f"RUN SUMMARY [{mode}]: copied={mode_counts['copied']} "
                  f"skipped={mode_counts['skipped']} "
                  f"overwritten={mode_counts['overwritten']} "
                  f"errors={total_errors}")
        logger.info(summary)


def main():
    parser = argparse.ArgumentParser(description='Publish CDR/LU files for HTTP access')
    parser.add_argument('--mode', choices=['all', 'raw', 'by_date', 'by_company'],
                       default='all', help='Which structures to create (default: all)')

    args = parser.parse_args()

    # Determine which modes to run
    if args.mode == 'all':
        modes = ['raw', 'by_date', 'by_company']
    else:
        modes = [args.mode]

    # Setup logger
    logger = setup_logger()

    # Scan and process
    counts = scan_directory(SOURCE_BASE, modes, logger)

    # Log summary
    log_summary(counts, logger)

    # Exit with error code if any errors occurred
    total_errors = sum(mode_counts["errors"] for mode_counts in counts.values())
    if total_errors > 0:
        sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    main()
