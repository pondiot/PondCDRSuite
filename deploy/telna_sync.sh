#!/usr/bash/

## Telna CDR sync chain - CDR,LU
## Run via cron

app_dir="/home/cdr_admin/PondCDRSuite/cdr_sync"
config_dir="/home/cdr_admin/PondCDRSuite/cdr_sync/configs"

"$app_dir"/cdr_sync.sh pull "$config_dir"/telna_cdr.env
"$app_dir"/cdr_sync.sh pull "$config_dir"/telna_lu.env


