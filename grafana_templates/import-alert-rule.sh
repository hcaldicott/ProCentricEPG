#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Import SFTPGo alert rule into Grafana with automatic Prometheus datasource UID resolution.

Usage:
  import-alert-rule.sh --grafana-url URL --api-token TOKEN (--datasource-name NAME | --datasource-uid UID) [options]

Required:
  --grafana-url URL         Grafana base URL, e.g. http://localhost:3000
  --api-token TOKEN         Grafana API token with alert provisioning permissions
  --datasource-name NAME    Grafana datasource name to resolve UID
                            OR
  --datasource-uid UID      Grafana datasource UID to use directly

Optional:
  --rule-file PATH          Rule template path (default: ./sftpgo-alert-rule.json)
  --dry-run                 Print transformed JSON instead of POSTing
  -h, --help                Show this help

Examples:
  ./grafana_templates/import-alert-rule.sh \
    --grafana-url http://localhost:3000 \
    --api-token <grafana-api-token> \
    --datasource-name Prometheus

  ./grafana_templates/import-alert-rule.sh \
    --grafana-url http://grafana.internal:3000 \
    --api-token <grafana-api-token> \
    --datasource-uid pbm8kzyh8y0f4d
USAGE
}

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "error: required command not found: $1" >&2
    exit 1
  fi
}

GRAFANA_URL=""
API_TOKEN=""
DATASOURCE_NAME=""
DATASOURCE_UID=""
RULE_FILE="$(cd "$(dirname "$0")" && pwd)/sftpgo-alert-rule.json"
DRY_RUN="false"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --grafana-url)
      GRAFANA_URL="${2:-}"
      shift 2
      ;;
    --api-token)
      API_TOKEN="${2:-}"
      shift 2
      ;;
    --datasource-name)
      DATASOURCE_NAME="${2:-}"
      shift 2
      ;;
    --datasource-uid)
      DATASOURCE_UID="${2:-}"
      shift 2
      ;;
    --rule-file)
      RULE_FILE="${2:-}"
      shift 2
      ;;
    --dry-run)
      DRY_RUN="true"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "error: unknown argument: $1" >&2
      usage
      exit 1
      ;;
  esac
done

if [[ -z "$GRAFANA_URL" || -z "$API_TOKEN" ]]; then
  echo "error: --grafana-url and --api-token are required" >&2
  usage
  exit 1
fi

if [[ -z "$DATASOURCE_UID" && -z "$DATASOURCE_NAME" ]]; then
  echo "error: provide either --datasource-name or --datasource-uid" >&2
  usage
  exit 1
fi

if [[ ! -f "$RULE_FILE" ]]; then
  echo "error: rule file not found: $RULE_FILE" >&2
  exit 1
fi

require_cmd curl
require_cmd jq

GRAFANA_URL="${GRAFANA_URL%/}"

if [[ -z "$DATASOURCE_UID" ]]; then
  ENCODED_DS_NAME="$(jq -rn --arg v "$DATASOURCE_NAME" '$v|@uri')"
  DATASOURCE_UID="$(
    curl -sS \
      -H "Authorization: Bearer $API_TOKEN" \
      "$GRAFANA_URL/api/datasources/name/$ENCODED_DS_NAME" \
    | jq -r '.uid // empty'
  )"

  if [[ -z "$DATASOURCE_UID" ]]; then
    echo "error: could not resolve datasource UID for name '$DATASOURCE_NAME'" >&2
    exit 1
  fi
fi

TRANSFORMED_JSON="$(
  jq --arg uid "$DATASOURCE_UID" '
    .data |= map(
      if .datasourceUid != "__expr__" then
        .datasourceUid = $uid
      else
        .
      end
    )
  ' "$RULE_FILE"
)"

if [[ "$DRY_RUN" == "true" ]]; then
  echo "$TRANSFORMED_JSON"
  exit 0
fi

CURL_RESPONSE="$(
  curl -sS -w $'\n%{http_code}' \
    -X POST "$GRAFANA_URL/api/v1/provisioning/alert-rules" \
    -H "Authorization: Bearer $API_TOKEN" \
    -H "Content-Type: application/json" \
    --data-binary "$TRANSFORMED_JSON"
)"

HTTP_CODE="${CURL_RESPONSE##*$'\n'}"
RESPONSE_BODY="${CURL_RESPONSE%$'\n'*}"

if [[ "$HTTP_CODE" -lt 200 || "$HTTP_CODE" -ge 300 ]]; then
  echo "error: Grafana alert import failed (HTTP $HTTP_CODE)" >&2
  echo "$RESPONSE_BODY" >&2
  exit 1
fi

echo "Alert rule imported successfully (datasource UID: $DATASOURCE_UID)."
echo "$RESPONSE_BODY"
