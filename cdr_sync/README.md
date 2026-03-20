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
REMOTE_DIR=/path/to/remote/cdr/directory
LOCAL_DIR=/path/to/local/cdr/directory

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

### Understanding Pull vs Push

It's important to understand the direction of data flow:

| Operation | Source     | Destination | SFTP_HOST Role                      |
|-----------|------------|-------------|-------------------------------------|
| **pull**  | REMOTE_DIR | LOCAL_DIR   | Remote server (download from)       |
| **push**  | LOCAL_DIR  | REMOTE_DIR  | Remote server (upload to)           |

**Key points:**
- `SFTP_HOST` - Always the remote SFTP server you connect to
- `REMOTE_DIR` - Always the path **on the SFTP server**
- `LOCAL_DIR` - Always the path **on your local machine**

**Examples:**
- `pull` downloads files **from** `REMOTE_DIR` on `SFTP_HOST` **to** `LOCAL_DIR` on your machine
- `push` uploads files **from** `LOCAL_DIR` on your machine **to** `REMOTE_DIR` on `SFTP_HOST`

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

Add entries to user crontab or `/etc/cron.d/cdr_sync`:

```cron
# Pull from client_a every hour at :00
0 * * * * cd /path/to/PondCDRSuite/cdr_sync && ./cdr_sync.sh pull configs/client_a.env >> /dev/null 2>&1

# Push to client_b every hour at :10
10 * * * * cd /path/to/PondCDRSuite/cdr_sync && ./cdr_sync.sh push configs/client_b.env >> /dev/null 2>&1

# Multiple pulls and pushes with different schedules
*/15 * * * * cd /path/to/PondCDRSuite/cdr_sync && ./cdr_sync.sh pull configs/client_a.env >> /dev/null 2>&1
30 * * * * cd /path/to/PondCDRSuite/cdr_sync && ./cdr_sync.sh pull configs/client_b.env >> /dev/null 2>&1
0 */4 * * * cd /path/to/PondCDRSuite/cdr_sync && ./cdr_sync.sh push configs/client_c.env >> /dev/null 2>&1
0 0 * * 6,0 cd /path/to/PondCDRSuite/cdr_sync && ./cdr_sync.sh push configs/client_d.env >> /dev/null 2>&1
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
