# cdr_backup

Archive CDR/LU files to prevent data loss from provider retention policies.

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

## Usage

```bash
# Backup all file types (default)
python3 cdr_backup.py

# Backup specific file type
python3 cdr_backup.py --file-type cdr
python3 cdr_backup.py --file-type lu

# Dry run (show what would be done)
python3 cdr_backup.py --dry-run
```

## Retention

- Archives older than 365 days are automatically deleted
- Configurable via `RETENTION_DAYS` in config.py

## Integration

Run after cdr_publish in cron:
```bash
cdr_sync.sh pull configs/telna_cdr.env && \
cdr_organize.py /home/cdr_admin/CDRs/inbound/telna_cdr /home/cdr_admin/CDRs/outbound && \
cdr_publish.py && \
cdr_backup.py
```

## Logging

Logs: `logs/backup_process.log`

Format:
```
2025-04-08 10:00:00 - ARCHIVED 2026-04-06 -> /home/cdr_admin/CDRs/backup/cdr/2026-04-06.tar.gz
2025-04-08 10:00:01 - DELETED old archive: 2025-01-01.tar.gz (from 2025-01-01)
2025-04-08 10:00:02 - RUN SUMMARY: archived=2 skipped=0 deleted=5 errors=0
```
