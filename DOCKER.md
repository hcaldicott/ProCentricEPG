# Docker Deployment Guide

This guide explains how to run the LG ProCentric EPG Bundle Generator using Docker and Docker Compose.

If you need Kubernetes/Kustomize deployment instead, use [KUBERNETES.md](KUBERNETES.md).

## Overview

The Docker setup consists of three services:

1. **EPG Generator**: Automatically generates EPG bundles at scheduled intervals (default: midnight daily)
2. **SFTPGo FTP Server**: Serves generated bundles and manages customer FTP users
3. **EPG Admin Service**: Exposes per-user last-login/staleness metrics for Prometheus

Health checks:
- `ftp-server` Docker healthcheck validates SFTPGo `GET /healthz` on port `8080`
- `epg-admin` Docker healthcheck validates `GET /healthz` on port `8081`

## Quick Start

### Prerequisites

- Docker Engine 20.10 or later
- Docker Compose 2.0 or later

### Basic Usage

By default, `docker-compose.yml` pulls `epg-generator` and `epg-admin` images from GHCR.

1. **Start the services**:
   ```bash
   docker-compose up -d
   ```

2. **View logs**:
   ```bash
   # View EPG generator logs
   docker-compose logs -f epg-generator

   # View FTP server logs
   docker-compose logs -f ftp-server

   # View epg-admin logs
   docker-compose logs -f epg-admin
   ```

3. **Stop the services**:
   ```bash
   docker-compose down
   ```

### Image Sources

Default image references:
- `EPG_GENERATOR_IMAGE=ghcr.io/hcaldicott/procentric-epg-generator:latest`
- `EPG_ADMIN_IMAGE=ghcr.io/hcaldicott/procentric-epg-admin:latest`
- `SFTPGO_IMAGE=drakkan/sftpgo:latest`

Override images without editing Compose:
```bash
EPG_GENERATOR_IMAGE=ghcr.io/<owner>/procentric-epg-generator:1.2.3 \
EPG_ADMIN_IMAGE=ghcr.io/<owner>/procentric-epg-admin:1.2.3 \
docker compose up -d
```

Use local source builds with the build override:
```bash
docker compose -f docker-compose.yml -f docker-compose.build.yml up -d --build
```

## Configuration

### Environment Variables

Edit the `docker-compose.yml` file to customize the following environment variables:

#### EPG Generator Service

| Variable | Default | Description |
|----------|---------|-------------|
| `CRON_SCHEDULE` | `0 0 * * *` | Cron schedule for EPG generation (midnight daily by default) |
| `TZ` | `UTC` | Timezone for the container |
| `OUTPUT_DIR` | `/bundles` | Output directory inside container |
| `LOG_LEVEL` | `INFO` | Logging verbosity (DEBUG, INFO, WARNING, ERROR, CRITICAL) |
| `RUN_ONCE` | (not set) | Set to `"true"` to run once and exit (useful for testing) |

**Cron Schedule Examples**:
- `0 0 * * *` - Every day at midnight (default)
- `0 */6 * * *` - Every 6 hours
- `0 2 * * *` - Every day at 2 AM
- `30 1 * * *` - Every day at 1:30 AM
- `0 0 * * 0` - Every Sunday at midnight

**Timezone Examples**:
- `UTC` - Coordinated Universal Time
- `Pacific/Auckland` - New Zealand
- `Australia/Sydney` - Australia
- `America/New_York` - US Eastern
- `Europe/London` - UK

**Log Level Examples**:
- `DEBUG` - Detailed diagnostic information (verbose)
- `INFO` - General informational messages (default)
- `WARNING` - Warning messages for potentially problematic situations
- `ERROR` - Error messages for serious problems
- `CRITICAL` - Critical messages for system failures

#### FTP Server Service

| Variable | Default | Description |
|----------|---------|-------------|
| `SFTPGO_FTPD__BINDINGS__0__PORT` | `21` | FTP control port |
| `SFTPGO_FTPD__PASSIVE_PORT_RANGE__START` | `21100` | Passive mode range start |
| `SFTPGO_FTPD__PASSIVE_PORT_RANGE__END` | `21110` | Passive mode range end |
| `SFTPGO_FTPD__BINDINGS__0__FORCE_PASSIVE_IP` | `127.0.0.1` | Passive mode advertised IP (set to server IP in production) |
| `SFTPGO_DEFAULT_ADMIN_USERNAME` | `admin` | Initial SFTPGo admin user |
| `SFTPGO_DEFAULT_ADMIN_PASSWORD` | `Password4Partners` | Initial SFTPGo admin password |
| `SFTPGO_ENABLE_WEB_ADMIN_UI` | `0` | Set to `1` to enable SFTPGo built-in Web Admin UI |
| `SFTPGO_HTTPD__TOKEN_VALIDATION` | `1` | Disable admin token IP binding (prevents logout behind load balancers/Kubernetes networking) |
| `SFTPGO_HTTPD__SIGNING_PASSPHRASE_FILE` | `/var/lib/sftpgo/signing_passphrase` | Signing passphrase file (auto-generated on first start and persisted in `sftpgo-data`) |
| `SFTPGO_TELEMETRY__BIND_PORT` | `10000` | SFTPGo native Prometheus endpoint |

#### EPG Admin Service

| Variable | Default | Description |
|----------|---------|-------------|
| `SFTPGO_API_BASE_URL` | `http://ftp-server:8080/api/v2` | SFTPGo REST API base URL |
| `SFTPGO_API_USERNAME` | `admin` | SFTPGo API username |
| `SFTPGO_API_PASSWORD` | `Password4Partners` | SFTPGo API password |
| `STALE_AFTER_HOURS` | `24` | Hours before a client is considered stale |
| `REFRESH_INTERVAL_SECONDS` | `60` | API polling interval |
| `MERGE_SFTPGO_NATIVE_METRICS` | `true` | If true, epg-admin `/metrics` includes SFTPGo native metrics too |
| `SFTPGO_NATIVE_METRICS_URL` | `http://ftp-server:10000/metrics` | SFTPGo native metrics URL used for merge |
| `PORT` | `8081` | Exporter HTTP port |
| `EPG_ADMIN_SESSION_TTL_SECONDS` | `1800` | Admin UI session lifetime |
| `EPG_ADMIN_MANAGED_FOLDER_NAME` | `epg-bundles` | Managed SFTPGo folder name for shared EPG bundles |
| `EPG_ADMIN_MANAGED_FOLDER_PATH` | `/srv/epg` | Filesystem path used by the managed folder |
| `EPG_ADMIN_MANAGED_GROUP_NAME` | `epg-customers-ro` | Managed read-only group assigned to new users |
| `EPG_ADMIN_MANAGED_VIRTUAL_PATH` | `/EPG` | Virtual folder path presented to customer users |

### Volumes

The `./bundles` directory on your host is mounted to both containers:
- EPG Generator writes bundles to `/bundles` inside the container
- SFTPGo serves these bundles from `/srv/epg/`

SFTPGo state is persisted in:
- `/var/lib/sftpgo` (named volume `sftpgo-data`)

Generated bundles will be accessible at:
- **Host**: `./bundles/EPG/`
- **FTP**: `ftp://procentric@localhost/EPG/`

SFTPGo observability endpoints:
- **Merged metrics (single scrape target)**: `http://localhost:8081/metrics`
- **SFTPGo native metrics** are merged internally by `epg-admin` and not published separately by default.

## Generated Bundle Structure

Bundles are organized by region and city:

```
bundles/
├── EPG/
│   ├── NZ/
│   │   └── Procentric_EPG_NZL_YYYYMMDD.zip
│   └── AUS/
│       ├── SYD/
│       │   └── Procentric_EPG_SYD_YYYYMMDD.zip
│       ├── BNE/
│       │   └── Procentric_EPG_BNE_YYYYMMDD.zip
│       ├── ADL/
│       │   └── Procentric_EPG_ADL_YYYYMMDD.zip
│       ├── OOL/
│       │   └── Procentric_EPG_OOL_YYYYMMDD.zip
│       └── MEL/
│           └── Procentric_EPG_MEL_YYYYMMDD.zip
```

Each ZIP file contains a `Procentric_EPG.json` file with the EPG data.

## Accessing Bundles via FTP

### Default Credentials
- **Host**: `localhost` (or your server IP)
- **Port**: `21`
- **Username/Password**: Create per-customer accounts in EPG Admin (`http://localhost:8081/admin/login`)

### EPG Admin UI

- **URL**: `http://localhost:8081/admin/login`
- **Auth**: existing SFTPGo admin credentials
- **Features**:
  - create customer users (manual or auto-generated password)
  - disable users
  - reset user passwords
  - automatic managed group/folder mapping for EPG access

SFTPGo built-in Web Admin UI is disabled by default. To enable it:

```yaml
environment:
  SFTPGO_ENABLE_WEB_ADMIN_UI: "1"
```

### Using FTP Client

**Command Line**:
```bash
ftp localhost
# Enter a configured SFTPGo FTP username/password
cd EPG/NZ
ls
get Procentric_EPG_NZL_20250101.zip
```

**FileZilla or other GUI clients**:
1. Host: `localhost` (or server IP)
2. Username: SFTPGo FTP username
3. Password: SFTPGo FTP password
4. Port: `21`

### For Remote Access

If you need to access the FTP server from remote machines:

1. Update `SFTPGO_FTPD__BINDINGS__0__FORCE_PASSIVE_IP` in `docker-compose.yml` to your server's public IP:
   ```yaml
   SFTPGO_FTPD__BINDINGS__0__FORCE_PASSIVE_IP: "192.168.1.100"  # Replace with your server IP
   ```

2. Ensure ports 21 and 21100-21110 are open in your firewall

## Logging

### Viewing Logs

All application logs are automatically captured by Docker and can be viewed using standard Docker logging commands:

```bash
# View real-time logs
docker-compose logs -f epg-generator

# View last 100 lines
docker-compose logs --tail=100 epg-generator

# View logs since a specific time
docker-compose logs --since 2h epg-generator

# View logs with timestamps
docker-compose logs -t epg-generator
```

### Log Format

Logs are output in the following format:
```
2025-01-08 12:00:00 - root - INFO - Fetching and parsing the XML data for New Zealand...
2025-01-08 12:00:05 - root - INFO - JSON saved: /bundles/EPG/NZL/Procentric_EPG.json
2025-01-08 12:00:06 - root - INFO - ZIP created: /bundles/EPG/NZL/Procentric_EPG_NZL_20250108.zip
```

Format: `timestamp - logger_name - level - message`

### Adjusting Log Levels

Control logging verbosity using the `LOG_LEVEL` environment variable:

```yaml
# In docker-compose.yml
environment:
  LOG_LEVEL: "DEBUG"  # Very verbose, shows all operations
```

**When to use each level:**
- `DEBUG`: Troubleshooting issues, shows all internal operations
- `INFO`: Normal operation, shows key milestones (default)
- `WARNING`: Only show warnings and errors
- `ERROR`: Only show errors and critical issues
- `CRITICAL`: Only show critical system failures

### Log Persistence

By default, Docker stores logs on the host system. To prevent logs from consuming too much disk space:

**Option 1: Configure Docker log rotation** (recommended)

Create or edit `/etc/docker/daemon.json`:
```json
{
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "10m",
    "max-file": "3"
  }
}
```

Then restart Docker:
```bash
sudo systemctl restart docker
```

**Option 2: Manually clear logs**
```bash
# Clear logs for the container
docker-compose down
sudo sh -c "truncate -s 0 /var/lib/docker/containers/*/*-json.log"
docker-compose up -d
```

**Option 3: Configure per-service in docker-compose.yml**
```yaml
services:
  epg-generator:
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
```

### Integrating with External Logging

For production environments, you can forward logs to external systems:

**Syslog:**
```yaml
services:
  epg-generator:
    logging:
      driver: "syslog"
      options:
        syslog-address: "tcp://192.168.1.100:514"
        tag: "epg-generator"
```

**Fluentd:**
```yaml
services:
  epg-generator:
    logging:
      driver: "fluentd"
      options:
        fluentd-address: "localhost:24224"
        tag: "epg-generator"
```

## FTP Client Tracking and Alerting

Grafana setup files:
- `grafana_templates/sftpgo-observability-dashboard.json` (dashboard import)
- `grafana_templates/sftpgo-alert-rule.json` (Grafana alert provisioning API payload)
- `grafana_templates/import-alert-rule.sh` (imports alert rule and auto-resolves Prometheus datasource UID)

Import the dashboard in Grafana:
1. Dashboards -> New -> Import
2. Upload `grafana_templates/sftpgo-observability-dashboard.json`
3. Select your Prometheus datasource

Create the alert rule using helper script (recommended):
```bash
./grafana_templates/import-alert-rule.sh \
  --grafana-url http://localhost:3000 \
  --api-token <grafana-api-token> \
  --datasource-name Prometheus
```

Optional: manual API import if you want full control:
```bash
curl -X POST "http://<grafana-host>:3000/api/v1/provisioning/alert-rules" \
  -H "Authorization: Bearer <grafana-api-token>" \
  -H "Content-Type: application/json" \
  --data-binary @grafana_templates/sftpgo-alert-rule.json
```

If importing manually, replace `PROMETHEUS_DS_UID` in `grafana_templates/sftpgo-alert-rule.json` with your Grafana Prometheus datasource UID first.

Example scrape target:
```yaml
scrape_configs:
  - job_name: procentric_sftpgo_user_exporter
    static_configs:
      - targets: ["your-hostname:8081"]
```

Important note:
- Use one SFTPGo FTP user per customer for deterministic tracking.
- Alert on `sftpgo_user_stale{status="enabled"} == 1`.
- Default template behavior is immediate firing on stale (`for: "0s"`). To add delay, edit `for` in `grafana_templates/sftpgo-alert-rule.json` and re-import.

**Cloud Logging (AWS CloudWatch, Google Cloud Logging, etc.):**
```yaml
services:
  epg-generator:
    logging:
      driver: "awslogs"
      options:
        awslogs-region: "us-east-1"
        awslogs-group: "epg-generator"
        awslogs-stream: "production"
```

## Testing

### Test EPG Generation

Run the EPG generator once without cron:

```bash
docker-compose run --rm -e RUN_ONCE=true epg-generator
```

This will:
1. Run the EPG generation immediately
2. Exit when complete
3. Leave bundles in `./bundles/`

### Verify Bundles

Check that bundles were created:

```bash
ls -lR ./bundles/EPG/
```

### Test FTP Access

```bash
# List bundles via FTP
curl -u <ftp_username>:<ftp_password> ftp://localhost/EPG/NZL/

# Download a bundle
curl -u <ftp_username>:<ftp_password> -O ftp://localhost/EPG/NZL/Procentric_EPG_NZL_20250101.zip
```

## Troubleshooting

### Check Container Status

```bash
docker-compose ps
```

### View Real-time Logs

```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f epg-generator
```

### Verify Cron Schedule

```bash
# Execute bash in the running container
docker exec -it procentric-epg-generator bash

# View crontab
crontab -l
```

### Check Bundle Generation

If bundles aren't being created:

1. Check logs for errors:
   ```bash
   docker-compose logs epg-generator
   ```

2. Verify the output directory:
   ```bash
   docker exec procentric-epg-generator ls -la /bundles/EPG/
   ```

3. Run manually to see detailed output:
   ```bash
   docker exec procentric-epg-generator python3 /app/src/main.py
   ```

### FTP Connection Issues

1. Verify FTP server is running:
   ```bash
   docker-compose ps ftp-server
   ```

2. Test FTP connection:
   ```bash
   telnet localhost 21
   ```

3. Check FTP logs:
   ```bash
   docker-compose logs ftp-server
   ```

## Production Deployment

### Security Recommendations

1. **Create per-customer FTP users** in `epg-admin` and avoid shared credentials.

2. **Use FTPS** (FTP over TLS): Consider using a different FTP server image that supports FTPS

3. **Firewall**: Restrict FTP access to known LG ProCentric appliances

4. **Backups**: Regularly backup the `./bundles` directory

### Resource Management

The EPG generator is lightweight and requires minimal resources:
- **CPU**: < 0.5 core during generation
- **Memory**: ~ 256-512 MB
- **Disk**: Depends on number of bundles (typically < 100 MB total)

### Monitoring

Monitor the containers using:

```bash
# Resource usage
docker stats procentric-epg-generator procentric-epg-ftp-server procentric-epg-admin

# Health checks
docker ps --filter name=procentric
```

## Advanced Usage

### Custom Cron Schedule

Run EPG generation every 6 hours:

```yaml
environment:
  CRON_SCHEDULE: "0 */6 * * *"
```

### Multiple Timezones

For servers in New Zealand, set timezone:

```yaml
environment:
  TZ: "Pacific/Auckland"
  CRON_SCHEDULE: "0 0 * * *"  # Midnight NZST/NZDT
```

### Building the Image

Build the generator image manually instead of using docker-compose:

```bash
docker build -t procentric-epg-generator:latest -f epg_generator/Dockerfile ./epg_generator
```

Run manually:

```bash
docker run -d \
  --name procentric-epg-generator \
  -e CRON_SCHEDULE="0 0 * * *" \
  -e TZ="UTC" \
  -v $(pwd)/bundles:/bundles \
  procentric-epg-generator:latest
```

## Maintenance

### Update the Application

1. Pull latest code:
   ```bash
   git pull origin main
   ```

2. Pull fresh images and restart:
   ```bash
   docker compose pull
   docker compose up -d
   ```

If using local source builds, use:
```bash
docker compose -f docker-compose.yml -f docker-compose.build.yml up -d --build
```

### Clean Old Bundles

The system automatically removes old bundles when generating new ones. To manually clean:

```bash
find ./bundles -name "*.zip" -mtime +7 -delete
```

This removes bundles older than 7 days.

### Backup Bundles

```bash
tar -czf bundles-backup-$(date +%Y%m%d).tar.gz bundles/
```

## Integration with LG ProCentric

Configure EPG Admin first, then configure each LG ProCentric installation to use its own FTP credentials.

### 1) Create a dedicated FTP user in EPG Admin

1. Open EPG Admin: `http://<your-server>:8081/admin/login`
2. Login with SFTPGo admin credentials (`SFTPGO_ADMIN_USERNAME` / `SFTPGO_ADMIN_PASSWORD`)
3. Go to **Create Customer**
4. Create one user per ProCentric installation (or per customer site)
5. Save the user and record:
   - FTP username
   - FTP password

### 2) Configure LG ProCentric to use that user

For each ProCentric installation:

1. **FTP Host**: your server IP/DNS
2. **FTP Port**: `21`
3. **Username**: the dedicated SFTPGo FTP user for this installation
4. **Password**: that user's password
5. **Path**: `/EPG/{COUNTRY}/{CITY}/` (example: `/EPG/NZL/` or `/EPG/AUS/SYD/`)
6. **File Pattern**: `Procentric_EPG_*.zip`

This gives per-installation credential isolation and enables per-user staleness monitoring in `epg-admin`.
