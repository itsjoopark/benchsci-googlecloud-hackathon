#!/usr/bin/env bash
# Source this file in your shell to get config switch helpers:
#   source scripts/gcp/switch-config.sh

BENCHSPARK_PROJECT_ID="benchspark-data-1771447466"
MULTIHOP_PROJECT_ID="multihopwanderer-1771992134"

# Override these in your shell if needed.
MULTIHOP_SA1_EMAIL="${MULTIHOP_SA1_EMAIL:-multihopwanderer-1771992134@appspot.gserviceaccount.com}"
MULTIHOP_SA2_EMAIL="${MULTIHOP_SA2_EMAIL:-113940992739-compute@developer.gserviceaccount.com}"

# Optional local key files (used by *_key helpers).
MULTIHOP_SA1_KEY_PATH="${MULTIHOP_SA1_KEY_PATH:-}"
MULTIHOP_SA2_KEY_PATH="${MULTIHOP_SA2_KEY_PATH:-}"
MULTIHOP_KEY_SEARCH_DIR="${MULTIHOP_KEY_SEARCH_DIR:-$PWD}"

_ensure_config() {
  local name="$1"
  if ! gcloud config configurations describe "$name" >/dev/null 2>&1; then
    gcloud config configurations create "$name" >/dev/null
  fi
  gcloud config configurations activate "$name" >/dev/null
}

_print_active_context() {
  echo "Active config: $(gcloud config configurations list --filter=is_active:true --format='value(name)')"
  echo "Active project: $(gcloud config get-value core/project)"
  echo "Active account: $(gcloud config get-value core/account 2>/dev/null || true)"
  local impersonated
  impersonated="$(gcloud config get-value auth/impersonate_service_account 2>/dev/null || true)"
  if [[ -n "${impersonated}" && "${impersonated}" != "(unset)" ]]; then
    echo "Impersonating: ${impersonated}"
  fi
}

_detect_base_account() {
  local account
  account="$(gcloud config get-value core/account 2>/dev/null || true)"
  if [[ -n "${account}" && "${account}" != "(unset)" ]]; then
    echo "${account}"
    return 0
  fi

  local config_dir="${HOME}/.config/gcloud/configurations"
  if [[ -d "${config_dir}" ]]; then
    account="$(
      awk -F' = ' '
        /^\[core\]/ { in_core=1; next }
        /^\[/ { in_core=0 }
        in_core && $1=="account" && $2!="" { print $2; exit }
      ' "${config_dir}"/config_* 2>/dev/null
    )"
  fi
  if [[ -n "${account}" ]]; then
    echo "${account}"
    return 0
  fi

  account="$(gcloud auth list --filter=status:ACTIVE --format='value(account)' 2>/dev/null | head -n1)"
  if [[ -n "${account}" ]]; then
    echo "${account}"
  fi
}

_set_user_context() {
  local config_name="$1"
  local project_id="$2"
  _ensure_config "${config_name}"
  gcloud config unset auth/impersonate_service_account >/dev/null 2>&1 || true
  gcloud config set core/project "${project_id}" >/dev/null
  _print_active_context
}

_set_impersonation_context() {
  local config_name="$1"
  local project_id="$2"
  local service_account_email="$3"
  _ensure_config "${config_name}"
  local base_account
  base_account="$(_detect_base_account)"
  if [[ -n "${base_account}" ]]; then
    gcloud config set core/account "${base_account}" >/dev/null
  fi
  gcloud config set core/project "${project_id}" >/dev/null
  gcloud config set auth/impersonate_service_account "${service_account_email}" >/dev/null
  _print_active_context
}

_set_key_context() {
  local config_name="$1"
  local project_id="$2"
  local service_account_email="$3"
  local key_path="$4"
  if [[ -z "${key_path}" ]]; then
    echo "Missing key path. Export the key variable and retry."
    return 1
  fi
  if [[ ! -f "${key_path}" ]]; then
    echo "Key file not found: ${key_path}"
    return 1
  fi
  _ensure_config "${config_name}"
  gcloud config unset auth/impersonate_service_account >/dev/null 2>&1 || true
  gcloud auth activate-service-account "${service_account_email}" --key-file="${key_path}" --project="${project_id}" >/dev/null
  gcloud config set core/project "${project_id}" >/dev/null
  gcloud config set core/account "${service_account_email}" >/dev/null
  export GOOGLE_APPLICATION_CREDENTIALS="${key_path}"
  echo "GOOGLE_APPLICATION_CREDENTIALS=${GOOGLE_APPLICATION_CREDENTIALS}"
  _print_active_context
}

set_multihop_sa_keys() {
  local sa1_key_path="$1"
  local sa2_key_path="$2"
  if [[ -n "${sa1_key_path}" ]]; then
    export MULTIHOP_SA1_KEY_PATH="${sa1_key_path}"
  fi
  if [[ -n "${sa2_key_path}" ]]; then
    export MULTIHOP_SA2_KEY_PATH="${sa2_key_path}"
  fi
  show_multihop_sa_key_paths
}

auto_detect_multihop_sa_keys() {
  local search_dir="${MULTIHOP_KEY_SEARCH_DIR}"
  local f
  if [[ ! -d "${search_dir}" ]]; then
    echo "Key search dir not found: ${search_dir}"
    return 1
  fi

  for f in "${search_dir}"/*.json; do
    [[ -f "${f}" ]] || continue
    if [[ -z "${MULTIHOP_SA1_KEY_PATH}" ]] && grep -q "\"client_email\"[[:space:]]*:[[:space:]]*\"${MULTIHOP_SA1_EMAIL}\"" "${f}"; then
      export MULTIHOP_SA1_KEY_PATH="${f}"
    fi
    if [[ -z "${MULTIHOP_SA2_KEY_PATH}" ]] && grep -q "\"client_email\"[[:space:]]*:[[:space:]]*\"${MULTIHOP_SA2_EMAIL}\"" "${f}"; then
      export MULTIHOP_SA2_KEY_PATH="${f}"
    fi
  done

  show_multihop_sa_key_paths
}

show_multihop_sa_key_paths() {
  echo "MULTIHOP_SA1_KEY_PATH=${MULTIHOP_SA1_KEY_PATH:-<unset>}"
  echo "MULTIHOP_SA2_KEY_PATH=${MULTIHOP_SA2_KEY_PATH:-<unset>}"
}

use_benchspark() {
  _set_user_context "benchspark-read" "${BENCHSPARK_PROJECT_ID}"
}

use_multihop() {
  _set_user_context "multihop-rw" "${MULTIHOP_PROJECT_ID}"
}

use_multihop_sa1_impersonation() {
  _set_impersonation_context "multihop-sa1-imp" "${MULTIHOP_PROJECT_ID}" "${MULTIHOP_SA1_EMAIL}"
}

use_multihop_sa2_impersonation() {
  _set_impersonation_context "multihop-sa2-imp" "${MULTIHOP_PROJECT_ID}" "${MULTIHOP_SA2_EMAIL}"
}

use_multihop_sa1_key() {
  [[ -n "${MULTIHOP_SA1_KEY_PATH}" ]] || auto_detect_multihop_sa_keys >/dev/null
  _set_key_context "multihop-sa1-key" "${MULTIHOP_PROJECT_ID}" "${MULTIHOP_SA1_EMAIL}" "${MULTIHOP_SA1_KEY_PATH}"
}

use_multihop_sa2_key() {
  [[ -n "${MULTIHOP_SA2_KEY_PATH}" ]] || auto_detect_multihop_sa_keys >/dev/null
  _set_key_context "multihop-sa2-key" "${MULTIHOP_PROJECT_ID}" "${MULTIHOP_SA2_EMAIL}" "${MULTIHOP_SA2_KEY_PATH}"
}
