# cdr_backup

Archive CDR/LU files to prevent data loss from provider retention policies.

## How it works

- Reads directly from `/home/cdr_admin/CDRs/outbound/` (source of truth)
- Finds files for current day by parsing dates from filenames
- Creates daily `.tar.gz` archives in `/home/cdr_admin/CDRs/backup/`
- Archives older than 365 days are automatically deleted

## Directory Structure

```
/home/cdr_admin/CDRs/backup/
├── cdr/
│   ├── 2026-04-06.tar.gz
│   ├── 2026-04-07.tar.gz
│   └── ...
└── lu/
    ├── 2026-04-06.tar.gz
    ├── 2026-04-07.tar.gz
    └── ...
```

**Archive contents:** Files are stored as `{CLIENT}_{FILENAME}` to avoid naming conflicts.

## Usage

```bash
# Backup today's files (default)
python3 cdr_backup.py

# Backup specific date
python3 cdr_backup.py --date 2026-04-06

# Backup specific file type
python3 cdr_backup.py --file-type cdr
python3 cdr_backup.py --file-type lu

# Dry run (show what would be done)
python3 cdr_backup.py --dry-run
```

## Cron Integration

Add to crontab to run daily at 23:50:

```bash
# CDR Backup - Daily backup at 23:50
50 23 * * * cdr_admin /home/cdr_admin/PondCDRSuite/cdr_backup/cdr_backup.py
```

Note: Runs independently of cdr_sync/cdr_organize/cdr_publish chain.

## Logging

Logs: `logs/backup_process.log`

Format:
```
2025-04-08 23:50:00 - Added /home/cdr_admin/CDRs/outbound/cdr/Zeppelincompany/file.csv as Zeppelincompany_file.csv
2025-04-08 23:50:01 - ARCHIVED cdr 2026-04-06 -> /home/cdr_admin/CDRs/backup/cdr/2026-04-06.tar.gz (150 files)
2025-04-08 23:50:02 - DELETED old archive: 2025-01-01.tar.gz
2025-04-08 23:50:03 - RUN SUMMARY: archived=300 deleted=5 errors=0
```
