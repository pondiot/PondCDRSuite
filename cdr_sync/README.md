# cdr_sync

Universal bash script for CDR file synchronization via SFTP with pull (download) and push (upload) operations.

## Features

- **Pull mode**: Download files from remote SFTP server to local directory
- **Push mode**: Upload files from local directory to remote SFTP server
- **Parallel transfers**: Configurable number of simultaneous file transfers
- **Incremental sync**: Only transfers new/changed files
- **Delete sync**: Optional deletion of files missing from source
- **Timeout handling**: Configurable operation timeout
- **Dual logging**: Human-readable text logs + JSON logs for parsing
- **Alerts**: Telegram and Email notifications on failures
- **Log rotation**: Preconfigured logrotate settings

## Requirements

- **bash** 4.0+
- **lftp** - Advanced file transfer utility
- **python3** 3.8+ with pip
- **timeout** (coreutils)

### Install dependencies

```bash
# Ubuntu/Debian
sudo apt-get install lftp python3 python3-pip python3-venv

# RHEL/CentOS/ALT Linux
sudo yum install lftp python3 python3-pip
# or
sudo apt-get install lftp python3 python3-pip
```

## Installation

```bash
cd /path/to/PondCDRSuite/cdr_sync

# Create Python virtual environment
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Copy and edit configuration files
cp .env.example .env
# Edit .env with your Telegram/Email notification settings

cp configs/client_example.env.example configs/client_a.env
# Edit configs/client_a.env with your SFTP credentials

# Make scripts executable
chmod +x cdr_sync.sh send_alert.py
```

## Configuration

### Global settings (.env)

Credentials for notification channels (shared across all clients):

```bash
# Telegram notifications
TELEGRAM_BOT_TOKEN=BOT_TOKEN
TELEGRAM_CHAT_ID=-CHAT_ID

# Email notifications
MS_TENANT_ID=your_tenant_id
MS_CLIENT_ID=your_client_id
MS_CLIENT_SECRET=your_client_secret
EMAIL_FROM=notify@yourcompany.com
EMAIL_TO=admin@yourcompany.com
```

### Operation config (configs/*.env)

Each SFTP connection has its own config file:

```bash
# Connection settings
SFTP_HOST=sftp.example.com
SFTP_PORT=22
SFTP_USER=username
SFTP_PASSWORD=password

# Directories
REMOTE_DIR=/data/cdr
LOCAL_DIR=/path/to/local/cdr/storage

# Sync settings
TIMEOUT=300              # Operation timeout in seconds (default: 300)
PARALLEL_TRANSFERS=2     # Number of parallel file transfers (default: 2)
DELETE_MISSING=false     # Delete files missing from source (default: false)

# Notification settings (per-client)
SEND_TELEGRAM=false      # Enable Telegram alerts for this client
SEND_EMAIL=false         # Enable email alerts for this client
```

## Usage

```bash
# Syntax
./cdr_sync.sh <pull|push> <config_file>

# Download files from remote server
./cdr_sync.sh pull configs/client_a.env

# Upload files to remote server
./cdr_sync.sh push configs/client_c.env
```

## Logging

Logs are stored in the `logs/` directory with daily rotation:

- **Text log**: `{config_name}_{YYYYMMDD}.log` - Human-readable format
- **JSON log**: `{config_name}_{YYYYMMDD}.json` - Machine-parseable format
- **lftp log**: `{config_name}_lftp_{YYYYMMDD}.log` - Raw lftp output

### JSON log format

Each line is a JSON object:

```json
{
  "timestamp": "2026-02-05T16:30:00Z",
  "config": "client_a",
  "operation": "pull",
  "host": "sftp.example.com",
  "status": "success",
  "message": "Sync completed",
  "error": "",
  "duration_sec": 45,
  "files_count": 128
}
```

Status values: `success`, `failed`, `timeout`

## Cron Setup

```bash
crontab -e
```

Add entries:

```cron
# Pull from provider every hour at :00
0 * * * * cd /path/to/PondCDRSuite/cdr_sync && ./cdr_sync.sh pull configs/client_a.env >> /dev/null 2>&1

# Push to client every hour at :10
10 * * * * cd /path/to/PondCDRSuite/cdr_sync && ./cdr_sync.sh push configs/client_c.env >> /dev/null 2>&1

# Multiple pulls with different schedules
*/15 * * * * cd /path/to/PondCDRSuite/cdr_sync && ./cdr_sync.sh pull configs/client_a.env >> /dev/null 2>&1
30 * * * * cd /path/to/PondCDRSuite/cdr_sync && ./cdr_sync.sh pull configs/client_b.env >> /dev/null 2>&1
```

## Log Rotation

Install logrotate configuration:

```bash
# Edit logrotate.conf and replace /path/to with your installation directory
# Replace username:groupname with your user:group

sudo cp logrotate.conf /etc/logrotate.d/cdr_sync

# Test configuration
sudo logrotate -d /etc/logrotate.d/cdr_sync

# Force rotation (for testing)
sudo logrotate -f /etc/logrotate.d/cdr_sync
```

Rotation policy:
- Text logs (`.log`): 30 days retention, compressed
- JSON logs (`.json`): 90 days retention, compressed

## Troubleshooting

### Connection refused

```
Error: Connection refused
```

- Check SFTP_HOST and SFTP_PORT
- Verify firewall allows outbound connections to the SFTP port
- Test manually: `sftp -P 22 user@host`

### Authentication failed

```
Error: Login failed
```

- Verify SFTP_USER and SFTP_PASSWORD
- Check if password contains special characters (escape them or use quotes)
- Test manually: `lftp -u user,password sftp://host`

### Permission denied

```
Error: Permission denied
```

- Check REMOTE_DIR permissions on the SFTP server
- Verify user has read/write access to the directory
- For pull: user needs read access to REMOTE_DIR
- For push: user needs write access to REMOTE_DIR

### Timeout errors

```
Error: Operation timed out after 300s
```

- Increase TIMEOUT value in config
- Check network stability
- Reduce PARALLEL_TRANSFERS if bandwidth is limited
- Check if large files are causing delays

### No files transferred

- Verify REMOTE_DIR and LOCAL_DIR paths are correct
- Check if files already exist (incremental sync skips existing files)
- Review lftp log: `logs/{config}_lftp_{date}.log`

### lftp SSL certificate errors

The script disables certificate verification by default (`ssl:verify-certificate no`). If you need strict verification:

1. Edit `cdr_sync.sh`
2. Remove or comment the line: `set ssl:verify-certificate no`
3. Ensure server certificate is valid and trusted

## Manual Testing

Test SFTP connection:

```bash
# Basic connection test
lftp -u username,password sftp://hostname

# Test with specific port
lftp -p 2222 -u username,password sftp://hostname

# Inside lftp, list files:
lftp> ls /data/cdr/
lftp> bye
```

Test alerts:

```bash
source venv/bin/activate
./send_alert.py --subject "Test Alert" --message "This is a test" --telegram true --email true
```

## Security Notes

- All credentials are stored in `.env` files which are gitignored
- Never commit `.env` files to version control
- Use strong passwords for SFTP accounts
- Consider using SSH keys instead of passwords for production
- Restrict file permissions: `chmod 600 .env configs/*.env`
