#!/usr/bin/env bash
# Source this file in your shell to get config switch helpers:
#   source scripts/gcp/switch-config.sh

use_benchspark() {
  gcloud config configurations activate benchspark-read >/dev/null
  gcloud config set core/project benchspark-data-1771447466 >/dev/null
  echo "Active config: $(gcloud config configurations list --filter=is_active:true --format='value(name)')"
  echo "Active project: $(gcloud config get-value core/project)"
  echo "Active account: $(gcloud config get-value core/account 2>/dev/null || true)"
}

use_multihop() {
  gcloud config configurations activate multihop-rw >/dev/null
  gcloud config set core/project multihopwanderer-1771992134 >/dev/null
  echo "Active config: $(gcloud config configurations list --filter=is_active:true --format='value(name)')"
  echo "Active project: $(gcloud config get-value core/project)"
  echo "Active account: $(gcloud config get-value core/account 2>/dev/null || true)"
}
