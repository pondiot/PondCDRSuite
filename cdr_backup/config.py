#!/usr/bin/env python3
"""
cdr_backup configuration
"""

# Source directory (cdr_organize output - source of truth)
SOURCE_BASE = "/home/cdr_admin/CDRs/outbound"

# Target directory (backup storage)
TARGET_BASE = "/home/cdr_admin/CDRs/backup"

# Retention period in days (archives older than this are deleted)
RETENTION_DAYS = 365
