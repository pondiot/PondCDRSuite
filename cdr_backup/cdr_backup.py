#!/usr/bin/env python3
"""
cdr_backup - Archive CDR/LU files to prevent data loss

Reads directly from /home/cdr_admin/CDRs/outbound/ (source of truth)
Archives files for current day to /home/cdr_admin/CDRs/backup/
Retention: 1 year (archives older than 365 days are deleted)

Runs daily via cron at 23:50
"""

import os
import sys
import tarfile
import logging
import argparse
import re
from datetime import datetime, timedelta
from pathlib import Path

# Import configuration
try:
    from config import SOURCE_BASE, TARGET_BASE, RETENTION_DAYS
except ImportError:
    # Default values if config.py not found
    SOURCE_BASE = "/home/cdr_admin/CDRs/outbound"
    TARGET_BASE = "/home/cdr_admin/CDRs/backup"
    RETENTION_DAYS = 365

# Setup logging
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(SCRIPT_DIR, "logs")
LOG_FILE = os.path.join(LOG_DIR, "backup_process.log")


def setup_logger(dry_run: bool = False):
    """Setup logging configuration."""
    os.makedirs(LOG_DIR, exist_ok=True)

    logger = logging.getLogger('cdr_backup')
    logger.setLevel(logging.INFO)

    handler = logging.FileHandler(LOG_FILE)
    handler.setFormatter(logging.Formatter('%(asctime)s - %(message)s', '%Y-%m-%d %H:%M:%S'))
    logger.addHandler(handler)

    # In dry-run mode, also print to console
    if dry_run:
        console = logging.StreamHandler()
        console.setFormatter(logging.Formatter('%(asctime)s - %(message)s', '%Y-%m-%d %H:%M:%S'))
        logger.addHandler(console)

    return logger


def extract_date_from_filename(filename: str) -> str:
    """
    Extract date from CDR/LU filename.
    Pattern: LIVE_{CLIENT}_{TYPE}_{START_DATETIME}_{N}_{END_DATETIME}.csv
    Example: LIVE_Company1_CDR_20260406200000_1_20260406211103.csv
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


def archive_files_for_date(file_type: str, target_date: str, logger) -> dict:
    """
    Find and archive all files for a specific date from outbound.

    Scans outbound/{file_type}/{client}/ for files matching target_date.
    Creates archive in backup/{file_type}/{target_date}.tar.gz

    Returns dict with stats: archived, errors.
    """
    stats = {"archived": 0, "errors": 0}

    source_base = os.path.join(SOURCE_BASE, file_type)
    backup_dir = os.path.join(TARGET_BASE, file_type)
    archive_name = f"{target_date}.tar.gz"
    archive_path = os.path.join(backup_dir, archive_name)

    if not os.path.exists(source_base):
        logger.warning(f"Source directory not found: {source_base}")
        return stats

    # Check if archive already exists for today
    if os.path.exists(archive_path):
        logger.info(f"Archive already exists: {archive_path}")
        stats["archived"] = 1  # Count as archived (already done)
        return stats

    # Find all files for target date
    files_to_archive = []

    for client in os.listdir(source_base):
        client_path = os.path.join(source_base, client)

        if not os.path.isdir(client_path):
            continue

        for filename in os.listdir(client_path):
            if not filename.lower().endswith('.csv'):
                continue

            file_date = extract_date_from_filename(filename)
            if file_date == target_date:
                files_to_archive.append((os.path.join(client_path, filename), client, filename))

    if not files_to_archive:
        logger.info(f"No files found for date {target_date} in {file_type}")
        return stats

    # Create archive
    try:
        os.makedirs(backup_dir, exist_ok=True)

        with tarfile.open(archive_path, "w:gz") as tar:
            for file_path, client, filename in files_to_archive:
                # Add file with client prefix to avoid naming conflicts
                arcname = f"{client}_{filename}"
                tar.add(file_path, arcname=arcname)
                logger.info(f"Added {file_path} as {arcname}")

        logger.info(f"ARCHIVED {file_type} {target_date} -> {archive_path} ({len(files_to_archive)} files)")
        stats["archived"] = len(files_to_archive)

    except Exception as e:
        logger.error(f"ERROR archiving {file_type} {target_date}: {e}")
        stats["errors"] = 1

    return stats


def cleanup_old_archives(file_type: str, retention_days: int, logger) -> int:
    """
    Delete archives older than retention_days.

    Returns number of deleted archives.
    """
    deleted_count = 0
    backup_dir = os.path.join(TARGET_BASE, file_type)

    if not os.path.exists(backup_dir):
        return 0

    cutoff_date = datetime.now() - timedelta(days=retention_days)

    try:
        for archive_file in os.listdir(backup_dir):
            if not archive_file.endswith('.tar.gz'):
                continue

            archive_path = os.path.join(backup_dir, archive_file)

            # Extract date from filename (format: YYYY-MM-DD.tar.gz)
            date_str = archive_file.replace('.tar.gz', '')
            try:
                archive_date = datetime.strptime(date_str, "%Y-%m-%d")

                if archive_date < cutoff_date:
                    try:
                        os.unlink(archive_path)
                        logger.info(f"DELETED old archive: {archive_file}")
                        deleted_count += 1
                    except Exception as e:
                        logger.error(f"ERROR deleting {archive_file}: {e}")

            except ValueError:
                # Filename doesn't match expected format, skip
                continue

    except Exception as e:
        logger.error(f"ERROR scanning for old archives in {file_type}: {e}")

    return deleted_count


def log_summary(stats: dict, deleted_count: int, logger):
    """Log operation summary."""
    total_archived = sum(s["archived"] for s in stats.values())
    total_errors = sum(s["errors"] for s in stats.values())

    summary = (f"RUN SUMMARY: archived={total_archived} deleted={deleted_count} errors={total_errors}")
    logger.info(summary)


def main():
    parser = argparse.ArgumentParser(description='Backup CDR/LU files to prevent data loss')
    parser.add_argument('--date', type=str,
                       help='Date to archive in YYYY-MM-DD format (default: today)')
    parser.add_argument('--file-type', choices=['cdr', 'lu', 'all'],
                       default='all', help='Which file type to process (default: all)')
    parser.add_argument('--dry-run', action='store_true',
                       help='Show what would be done without making changes')

    args = parser.parse_args()

    # Determine target date
    if args.date:
        target_date = args.date
    else:
        target_date = datetime.now().strftime("%Y-%m-%d")

    # Setup logger (console output in dry-run mode)
    logger = setup_logger(dry_run=args.dry_run)

    if args.dry_run:
        logger.info(f"DRY RUN MODE - would archive date: {target_date}")

    # Determine which file types to process
    if args.file_type == 'all':
        file_types = ['cdr', 'lu']
    else:
        file_types = [args.file_type]

    # Process each file type
    stats = {}
    total_deleted = 0

    for file_type in file_types:
        if not args.dry_run:
            stats[file_type] = archive_files_for_date(file_type, target_date, logger)
            deleted = cleanup_old_archives(file_type, RETENTION_DAYS, logger)
            total_deleted += deleted
        else:
            logger.info(f"DRY RUN: Would archive {file_type} for date {target_date}")

    # Log summary
    if not args.dry_run:
        log_summary(stats, total_deleted, logger)

    # Exit with error code if any errors occurred
    if not args.dry_run:
        total_errors = sum(s["errors"] for s in stats.values())
        if total_errors > 0:
            sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    main()
