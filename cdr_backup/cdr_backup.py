#!/usr/bin/env python3
"""
cdr_backup - Archive CDR/LU files to prevent data loss

Reads from /srv/cdr_publish/{cdr,lu}/by_date/
Creates daily .tar.gz archives in /home/cdr_admin/CDRs/backup/
Retention: 1 year (archives older than 365 days are deleted)
"""

import os
import sys
import tarfile
import logging
import argparse
from datetime import datetime, timedelta
from pathlib import Path

# Import configuration
try:
    from config import SOURCE_BASE, TARGET_BASE, RETENTION_DAYS
except ImportError:
    # Default values if config.py not found
    SOURCE_BASE = "/srv/cdr_publish"
    TARGET_BASE = "/home/cdr_admin/CDRs/backup"
    RETENTION_DAYS = 365

# Setup logging
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(SCRIPT_DIR, "logs")
LOG_FILE = os.path.join(LOG_DIR, "backup_process.log")


def setup_logger():
    """Setup logging configuration."""
    os.makedirs(LOG_DIR, exist_ok=True)

    logger = logging.getLogger('cdr_backup')
    logger.setLevel(logging.INFO)

    handler = logging.FileHandler(LOG_FILE)
    handler.setFormatter(logging.Formatter('%(asctime)s - %(message)s', '%Y-%m-%d %H:%M:%S'))
    logger.addHandler(handler)

    return logger


def create_archive(source_dir: str, archive_path: str, date_str: str, logger) -> bool:
    """
    Create a tar.gz archive for a specific date.

    Returns True if successful, False otherwise.
    """
    try:
        os.makedirs(os.path.dirname(archive_path), exist_ok=True)

        with tarfile.open(archive_path, "w:gz") as tar:
            # Add all files from the date directory
            for item in os.listdir(source_dir):
                item_path = os.path.join(source_dir, item)
                if os.path.isfile(item_path):
                    tar.add(item_path, arcname=item)

        logger.info(f"ARCHIVED {date_str} -> {archive_path}")
        return True

    except Exception as e:
        logger.error(f"ERROR archiving {date_str}: {e}")
        return False


def cleanup_old_archives(backup_dir: str, retention_days: int, logger) -> int:
    """
    Delete archives older than retention_days.

    Returns number of deleted archives.
    """
    deleted_count = 0
    cutoff_date = datetime.now() - timedelta(days=retention_days)

    try:
        for archive_file in os.listdir(backup_dir):
            if not archive_file.endswith('.tar.gz'):
                continue

            archive_path = os.path.join(backup_dir, archive_file)

            # Get file modification time
            mtime = datetime.fromtimestamp(os.path.getmtime(archive_path))

            if mtime < cutoff_date:
                try:
                    os.unlink(archive_path)
                    logger.info(f"DELETED old archive: {archive_file} (from {mtime.strftime('%Y-%m-%d')})")
                    deleted_count += 1
                except Exception as e:
                    logger.error(f"ERROR deleting {archive_file}: {e}")

    except Exception as e:
        logger.error(f"ERROR scanning for old archives: {e}")

    return deleted_count


def process_file_type(file_type: str, logger) -> dict:
    """
    Process all dates for a specific file type (cdr or lu).

    Returns dict with stats: archived, skipped, deleted, errors.
    """
    stats = {"archived": 0, "skipped": 0, "deleted": 0, "errors": 0}

    source_base = os.path.join(SOURCE_BASE, file_type, "by_date")
    backup_dir = os.path.join(TARGET_BASE, file_type)

    if not os.path.exists(source_base):
        logger.warning(f"Source directory not found: {source_base}")
        return stats

    # Process each date directory
    for date_str in os.listdir(source_base):
        source_dir = os.path.join(source_base, date_str)

        if not os.path.isdir(source_dir):
            continue

        archive_name = f"{date_str}.tar.gz"
        archive_path = os.path.join(backup_dir, archive_name)

        # Check if archive already exists and is up to date
        if os.path.exists(archive_path):
            # Check if source is newer than archive
            archive_mtime = os.path.getmtime(archive_path)
            source_newer = False

            for file_item in os.listdir(source_dir):
                file_path = os.path.join(source_dir, file_item)
                if os.path.isfile(file_path) and os.path.getmtime(file_path) > archive_mtime:
                    source_newer = True
                    break

            if not source_newer:
                stats["skipped"] += 1
                continue

        # Create archive
        if create_archive(source_dir, archive_path, date_str, logger):
            stats["archived"] += 1
        else:
            stats["errors"] += 1

    # Cleanup old archives
    deleted = cleanup_old_archives(backup_dir, RETENTION_DAYS, logger)
    stats["deleted"] += deleted

    return stats


def log_summary(stats: dict, logger):
    """Log operation summary."""
    total_archived = sum(s["archived"] for s in stats.values())
    total_skipped = sum(s["skipped"] for s in stats.values())
    total_deleted = sum(s["deleted"] for s in stats.values())
    total_errors = sum(s["errors"] for s in stats.values())

    summary = (f"RUN SUMMARY: archived={total_archived} skipped={total_skipped} "
              f"deleted={total_deleted} errors={total_errors}")
    logger.info(summary)


def main():
    parser = argparse.ArgumentParser(description='Backup CDR/LU files to prevent data loss')
    parser.add_argument('--dry-run', action='store_true',
                       help='Show what would be done without making changes')
    parser.add_argument('--file-type', choices=['cdr', 'lu', 'all'],
                       default='all', help='Which file type to process (default: all)')

    args = parser.parse_args()

    # Setup logger
    logger = setup_logger()

    if args.dry_run:
        logger.info("DRY RUN MODE - no changes will be made")

    # Determine which file types to process
    if args.file_type == 'all':
        file_types = ['cdr', 'lu']
    else:
        file_types = [args.file_type]

    # Process each file type
    stats = {}
    for file_type in file_types:
        stats[file_type] = process_file_type(file_type, logger)

    # Log summary
    log_summary(stats, logger)

    # Exit with error code if any errors occurred
    total_errors = sum(s["errors"] for s in stats.values())
    if total_errors > 0:
        sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    main()
