# LG ProCentric EPG Bundle Creator

Automated EPG (Electronic Program Guide) data generator for LG ProCentric hospitality TV systems. Fetches, processes, and formats TV guide data from multiple sources into LG ProCentric-compatible bundles ready for FTP deployment.

## Overview

This tool streamlines EPG data management for LG ProCentric servers by:
- **Fetching** live EPG data from Sky NZ (GraphQL) and XMLTV.net sources
- **Processing** raw data into structured, validated models
- **Formatting** output to meet LG ProCentric JSON specifications
- **Packaging** bundles as dated ZIP files with proper naming conventions
- **Deploying** via FTP server (Docker mode) or local output (development mode)

### Supported Regions

- **New Zealand**: Sky NZ (all channels) - **3 days** of EPG data
- **Australia**: 8 capital cities + 40+ regional cities and areas - **~9 days** of EPG data

**Note**: The amount of EPG data varies by region due to different data sources:
- New Zealand data is fetched from Sky NZ's GraphQL API, configured to retrieve 3 days (today + 2 days)
- Australian data is fetched from XMLTV.net XML feeds, which typically provide approximately 9 days of programming

## Getting Started

### Docker Deployment

The easiest way to run this project is using Docker. See [DOCKER.md](DOCKER.md) for complete instructions.

**Quick start**:
```bash
docker-compose up -d
```

This will:
- Run EPG generation automatically at midnight daily (configurable)
- Expose generated bundles via FTP server
- Expose SFTPGo and per-user staleness metrics for Prometheus/Grafana
- Automatically manage bundle cleanup and updates

### Kubernetes Deployment (Kustomize)

Kubernetes manifests are available under `k8s/` with Kustomize support. See [KUBERNETES.md](KUBERNETES.md) for full setup.

Quick start:
```bash
kubectl apply -k k8s/base
```

The default Kubernetes manifests use single-node scheduling with `ReadWriteOnce` shared storage for bundle data.

### Local Testing

For local development and testing on macOS, use the helper script. See [LOCAL_TESTING.md](LOCAL_TESTING.md) for details.

**Quick start**:
```bash
./epg_generator/run_local.sh
```

This will:
- Set up Python virtual environment automatically
- Install all dependencies
- Run EPG generation locally
- Display results and generated bundles

#### Scheduling with Cron

To run EPG generation automatically on a schedule using the local script (instead of Docker), add a cron job:

```bash
# Edit crontab
crontab -e

# Run daily at 2:00 AM
0 2 * * * cd /path/to/ProCentricEPG && ./epg_generator/run_local.sh >> /var/log/epg_cron.log 2>&1

# Run every 6 hours
0 */6 * * * cd /path/to/ProCentricEPG && ./epg_generator/run_local.sh >> /var/log/epg_cron.log 2>&1
```

Replace `/path/to/ProCentricEPG` with your actual project path.

## LG ProCentric Device Configuration

Once bundles are generated, they must be deployed to an FTP server accessible by your LG ProCentric devices.

### Bundle Format

Each bundle is a ZIP file containing a single JSON file:

**ZIP naming convention**:
```
Procentric_EPG_{COUNTRY_CODE}_{DATE}.zip
```
Example: `Procentric_EPG_NZL_20250207.zip`

**JSON filename** (inside ZIP):
```
Procentric_EPG.json
```

**JSON structure**:
```json
{
  "filetype": "Pro:Centric JSON Program Guide Data NZL",
  "version": "0.1",
  "fetchTime": "2025-02-07T13:22:44+1200",
  "maxMinutes": 60,
  "channels": [
    {
      "channelID": "1",
      "name": "TVNZ 1",
      "resolution": "HD",
      "events": [
        {
          "eventID": "334242",
          "title": "6 News",
          "eventDescription": "TVNZ New Zealand News",
          "rating": "TV-MA",
          "date": "2025-02-07",
          "startTime": "1800",
          "length": "60",
          "genre": "News"
        }
      ]
    }
  ]
}
```

### FTP Directory Structure

When a ProCentric system logs into a remote FTP server, it is not capable of reading bundles directly from the root directory of the FTP server. Hence, this tool is designed to output bundles organized by ISO country code in subdirectories:

```
/EPG/
├── NZL/
│   └── Procentric_EPG_NZL_20250207.zip
├── AUS/
│   ├── SYD/
│   │   └── Procentric_EPG_SYD_20250207.zip
│   ├── MEL/
│   │   └── Procentric_EPG_MEL_20250207.zip
│   └── BNE/
│       └── Procentric_EPG_BNE_20250207.zip
```

Your FTP server should be configured to present the bundles to ProCentric systems with the same subdirectory structure - or at least in a subdirectory of some kind.

### SFTPGo FTP Server (Docker/Kubernetes)

When using Docker Compose or Kubernetes deployment, SFTPGo is automatically configured:

- **Host**: Your server IP
- **Port**: 21 (configurable in `docker-compose.yml` or Kubernetes service manifests)
- **User**: Create per-customer FTP users in `epg-admin` (`/admin/login`)
- **Password**: Set per customer in `epg-admin` (manual or auto-generated)
- **Root**: `/srv/epg/` (mapped from generated bundles volume)

Bundles are automatically placed in the correct directories and old bundles are cleaned up on each run.

`epg-admin` UI:
- **URL**: `http://<host>:8081/admin/login`
- **Auth**: existing SFTPGo admin credentials
- **Workflow**: create customer users with automatic read-only EPG folder/group mapping

SFTPGo built-in Web Admin UI is disabled by default. Set `SFTPGO_ENABLE_WEB_ADMIN_UI=1` to enable it.

### Monitoring

The stack includes an `epg-admin` service that polls SFTPGo's REST API and emits Prometheus metrics.

The purpose of the staleness metrics is to alert when Pro:Centric devices/sites have not downloaded fresh EPG data.
For reliable alerting, use one FTP account per ProCentric installation.

- **Merged metrics (single scrape target)**: `http://<host>:8081/metrics`
- **Exporter health**: `http://<host>:8081/healthz`
- **SFTPGo native metrics** are merged internally by `epg-admin` and not published separately by default.

Tracked per-user metrics include:
- `sftpgo_user_last_login_timestamp`
- `sftpgo_user_seconds_since_last_login`
- `sftpgo_user_stale`

Important note:
- Staleness is derived from SFTPGo user `last_login` via API.
- Use one FTP account per customer for accurate alerting.

Default alert timing:
- Staleness threshold defaults to `24` hours via `STALE_AFTER_HOURS=24` in `epg-admin`.
- The bundled Grafana alert rule fires immediately when stale is detected (`"for": "0s"` in `grafana_templates/sftpgo-alert-rule.json`).
- Effective default alert latency is approximately `24h` plus up to the exporter poll interval (default `60s`).

How to customize:
- Change stale threshold:
  - Docker Compose: set `STALE_AFTER_HOURS` for `epg-admin` in `docker-compose.yml`.
  - Kubernetes: set `STALE_AFTER_HOURS` in `k8s/base/deployment-epg-admin.yaml`.
- Change alert wait time before firing:
  - Edit the alert rule `for` value in `grafana_templates/sftpgo-alert-rule.json` (for example `5m`, `30m`, `1h`) and re-import the rule.

Grafana assets:
- `grafana_templates/sftpgo-observability-dashboard.json`
- `grafana_templates/sftpgo-alert-rule.json`
- `grafana_templates/import-alert-rule.sh` (helper script to import alert rule with datasource UID resolution)

Quick Grafana setup:
1. Import dashboard:
   - Grafana -> Dashboards -> New -> Import
   - Upload `grafana_templates/sftpgo-observability-dashboard.json`
   - Select your Prometheus datasource
2. Import alert rule with helper script:
   ```bash
   ./grafana_templates/import-alert-rule.sh \
     --grafana-url http://localhost:3000 \
     --api-token <grafana-api-token> \
     --datasource-name Prometheus
   ```

### LG ProCentric Configuration

1. Login to your LG ProCentric server web admin panel.
2. Navigate to the Settings tab.
3. In the left menu, expand out the "External Service" section.
4. Click EPG
5. Configure FTP connection:
   - **FTP Site**: Your FTP server IP/hostname
   - **Site Directory**: `/EPG/{COUNTRY_CODE}/`
   - **Site User**: FTP server username
   - **Site Password**: FTP server password
6. Set "Hours of EPG Data" based on your region:
   - **New Zealand**: Set to "72 hours (3 Days)"
   - **Australia**: Set to "168 hours (7 Days)"
7. Test connection and verify EPG data loads.

### Manual FTP Deployment

If not using Docker's built-in FTP server:

```bash
# Generate bundles locally
./epg_generator/run_local.sh

# Upload to your FTP server
ftp your-ftp-server.com
> cd /EPG/NZL
> put epg_generator/output/EPG/NZL/Procentric_EPG_NZL_20250207.zip
> quit
```

Or use `scp`/`rsync` for automated deployment:

```bash
# After running ./epg_generator/run_local.sh
rsync -avz epg_generator/output/EPG/ user@server:/home/procentric/EPG/
```

## Key Features

- **Multi-source aggregation**: Sky NZ GraphQL API + XMLTV.net feeds
- **Timezone handling**: Automatic conversion for Australian regions (AEST, AEDT, AWST, ACST, ACDT)
- **Data validation**: Pydantic models ensure data integrity
- **Error resilience**: Continues processing if individual cities fail
- **Webhook notifications**: Real-time alerts to Teams, Discord, or Slack
- **Automated scheduling**: Built-in cron support (Docker) or manual cron setup (local)
- **FTP deployment**: Automatic bundle hosting via integrated FTP server (Docker mode)
- **Download observability**: SFTPGo per-user stale metrics for Prometheus/Grafana alerting

## Repository Structure

The repository is organized into clear components:

- `epg_generator/`: EPG generation application code, Dockerfile, dependencies, and local runner implementation
- `epg_admin/`: Admin UI + Prometheus exporter service for SFTPGo account management and staleness monitoring
- `k8s/`: Kubernetes/Kustomize manifests
- `grafana_templates/`: Grafana dashboard and alert import templates
- root docs (`README.md`, `DOCKER.md`, `KUBERNETES.md`, `LOCAL_TESTING.md`): deployment and operations guidance

Compatibility note:
- Local helper script is `./epg_generator/run_local.sh`.

## GitHub Automation

This repository includes GitHub Actions automation for CI, release management, and image publishing.

### What Is Automated

- **Conventional commit enforcement** (PR title format) via `.github/workflows/conventional-commits.yml`
- **Automatic linting** with Ruff via `.github/workflows/lint.yml`
- **Separate semantic versioning and release PRs** for:
  - `epg_generator` (`epg-generator-vX.Y.Z` tags, `epg_generator/CHANGELOG.md`)
  - `epg_admin` (`epg-admin-vX.Y.Z` tags, `epg_admin/CHANGELOG.md`)
  using Release Please (`.github/workflows/release-please.yml`)
- **Automatic container builds/pushes to GHCR** via `.github/workflows/containers.yml`
  - Pushes to `main` publish `edge` + `sha-<shortsha>` tags
  - Release tags publish `<version>` + `latest` tags

### Container Image Names (GHCR)

- `ghcr.io/<org-or-user>/procentric-epg-generator`
- `ghcr.io/<org-or-user>/procentric-epg-epg-admin`

### One-Time GitHub Setup

1. Enable branch protection on `main`.
2. Require these status checks before merge:
   - `Lint / ruff`
   - `Conventional Commits / validate-pr-title`
3. Prefer squash merges so PR title becomes the release commit message.
4. Ensure repository Actions are allowed to publish packages to GHCR.

## Webhook Notifications

Receive real-time alerts for processing errors and completion status.

### Setup

Set the following environment variables to enable webhook notifications:

```bash
WEBHOOK_URL="your-webhook-url"           # Required: Your webhook URL
WEBHOOK_TYPE="auto"                      # Optional: auto (default), teams, discord, slack, generic
WEBHOOK_NOTIFY_SUCCESS="false"           # Optional: Set to "true" to notify on success
```

### Supported Platforms

**Microsoft Teams**
1. In Teams, go to the channel where you want notifications
2. Click "..." → "Connectors" → "Incoming Webhook"
3. Configure webhook and copy the URL
4. Set `WEBHOOK_URL` to the copied URL

Example:
```bash
WEBHOOK_URL="https://outlook.office.com/webhook/..."
```

**Discord**
1. In Discord, go to Server Settings → Integrations → Webhooks
2. Click "New Webhook" and configure
3. Copy the webhook URL
4. Set `WEBHOOK_URL` to the copied URL

Example:
```bash
WEBHOOK_URL="https://discord.com/api/webhooks/..."
```

**Slack**
1. Go to https://api.slack.com/apps and create an app
2. Enable "Incoming Webhooks" and add webhook to workspace
3. Copy the webhook URL
4. Set `WEBHOOK_URL` to the copied URL

Example:
```bash
WEBHOOK_URL="https://hooks.slack.com/services/..."
```

### Notification Types

- **Error Notifications**: Immediate alerts when city processing fails
- **Warning Summary**: End-of-run summary if any errors occurred
- **Success Notifications**: Optional completion confirmations (set `WEBHOOK_NOTIFY_SUCCESS=true`)

### Examples

**Docker** (`docker-compose.yml`):
```yaml
environment:
  WEBHOOK_URL: "https://outlook.office.com/webhook/your-webhook-url"
  WEBHOOK_TYPE: "teams"
  WEBHOOK_NOTIFY_SUCCESS: "true"
```

**Local**:
```bash
export WEBHOOK_URL="https://discord.com/api/webhooks/your-webhook-url"
export WEBHOOK_TYPE="discord"
./epg_generator/run_local.sh
```

## Technical Details

### Dependencies

- **requests**: HTTP client for API/XML fetching
- **pydantic**: Data validation and modeling
- **pytz**: Timezone conversions
- **xml.etree.ElementTree**: XML parsing (XMLTV feeds)

### Data Sources

| Region | Source | Type | Coverage | EPG Duration |
|--------|--------|------|----------|-------------|
| New Zealand | Sky NZ | GraphQL API | All channels | 3 days |
| Australia | XMLTV.net | XML feeds | 8 capitals + 40+ regional | ~9 days |

### Australian Cities Supported

**Capital Cities**: Sydney, Melbourne, Brisbane, Perth, Adelaide, Canberra, Hobart, Darwin

**Regional**: Albany, Albury/Wodonga, Ballarat, Bendigo, Broken Hill, Bunbury, Cairns, Central Coast, Coffs Harbour, Geelong, Gippsland, Gold Coast, Griffith, Jurien Bay, Launceston, Lismore, Mackay, Mandurah, Mildura/Sunraysia, Newcastle, Orange/Dubbo, Port Augusta, Renmark, Riverland, Rockhampton, Shepparton, South Coast NSW, South East SA, Spencer Gulf, Sunshine Coast, Tamworth, Taree/Port Macquarie, Toowoomba, Townsville, Wagga Wagga, Wide Bay, Wollongong

**Regional Bundles**: NSW Regional, NT Regional, QLD Regional, SA Regional, TAS Regional, WA Regional

## Troubleshooting

### Common Issues

**No bundles generated**
- Check internet connectivity to data sources
- Verify `epg_generator/output/EPG/` directory exists and is writable
- Review logs for API/XML fetch errors

**LG ProCentric not loading EPG**
- Verify FTP server is accessible from LG device
- Check file naming matches convention exactly
- Ensure ZIP contains `Procentric_EPG.json` (not nested in subdirectories)
- Confirm JSON structure matches LG schema

**Timezone issues**
- Australian cities use configured timezone offsets (see `epg_generator/src/main.py`)
- New Zealand uses NZDT/NZST automatically
- Verify `fetchTime` in JSON uses correct timezone format

### Debug Mode

```bash
# Enable debug logging
LOG_LEVEL=DEBUG ./epg_generator/run_local.sh

# Check debug output
cat epg_generator/debug/debug_skynz.json
```

## Acknowledgements

Thanks to [garethcheyne](https://github.com/garethcheyne) for the original code that helped shape the evolution of this project.

## Contributing

Contributions welcome! Areas for improvement:
- Additional EPG data sources
- Support for other regions
- Enhanced error handling
- Performance optimizations
