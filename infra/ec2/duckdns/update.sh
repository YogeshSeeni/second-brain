#!/bin/bash
# /usr/local/bin/duckdns-update.sh — refresh the DuckDNS A record with the
# instance's current public IP. Reads config from /etc/default/brain-duckdns:
#
#   DUCKDNS_DOMAIN=brain-yogesh
#   DUCKDNS_TOKEN=<token from duckdns.org>
#
# With an Elastic IP attached, the record almost never actually changes, but
# the refresh keeps the subdomain from expiring (DuckDNS prunes after 30 days
# of inactivity).

set -euo pipefail

CONFIG=/etc/default/brain-duckdns
if [[ ! -f "$CONFIG" ]]; then
    echo "missing $CONFIG" >&2
    exit 2
fi

# shellcheck disable=SC1090
source "$CONFIG"

: "${DUCKDNS_DOMAIN:?DUCKDNS_DOMAIN required}"
: "${DUCKDNS_TOKEN:?DUCKDNS_TOKEN required}"

# Blank ip= lets DuckDNS auto-detect from the request source — works with EIP.
RESPONSE=$(curl -sS --retry 3 --max-time 15 \
    "https://www.duckdns.org/update?domains=${DUCKDNS_DOMAIN}&token=${DUCKDNS_TOKEN}&ip=")

echo "$(date -Is) duckdns update: $RESPONSE"
[[ "$RESPONSE" == "OK" ]] || exit 1
