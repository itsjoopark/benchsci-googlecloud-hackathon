# GCP Access Setup (Dual Project)

This project uses two GCP projects with different storage permission levels.

- Project A: `benchspark-data-1771447466`
- Bucket A (read-only): `gs://benchspark-data-1771447466-datasets`
- Project B: `multihopwanderer-1771992134`
- Bucket B (read/write): `gs://multihopwanderer-1771992134-team-bucket`

## 1) Install Google Cloud SDK

```bash
brew install --cask gcloud-cli
```

If `gcloud` is not on `PATH` after install:

```bash
echo 'source /opt/homebrew/share/google-cloud-sdk/path.zsh.inc' >> ~/.zshrc
echo 'source /opt/homebrew/share/google-cloud-sdk/completion.zsh.inc' >> ~/.zshrc
source ~/.zshrc
```

## 2) Authenticate (User Login + ADC)

```bash
gcloud auth login
gcloud auth application-default login
```

Verify:

```bash
gcloud auth list
gcloud auth application-default print-access-token >/dev/null && echo "ADC OK"
```

## 3) Create Named gcloud Configs

```bash
gcloud config configurations create benchspark-read
gcloud config set core/project benchspark-data-1771447466

gcloud config configurations create multihop-rw
gcloud config set core/project multihopwanderer-1771992134

gcloud config configurations activate benchspark-read
```

If a config already exists, use `gcloud config configurations activate <name>`.

## 4) Shell Helpers for Safe Switching

Source helper functions:

```bash
source scripts/gcp/switch-config.sh
```

Use:

```bash
use_benchspark
use_multihop
```

## 5) Grant IAM Roles (Least Privilege)

Run these as a project/bucket IAM admin. Replace `USER_EMAIL` with the account from `gcloud auth list`.

### Project A (`benchspark-data-1771447466`)

- Project read access:

```bash
gcloud projects add-iam-policy-binding benchspark-data-1771447466 \
  --member="user:USER_EMAIL" \
  --role="roles/viewer"
```

- Bucket read-only access:

```bash
gcloud storage buckets add-iam-policy-binding gs://benchspark-data-1771447466-datasets \
  --member="user:USER_EMAIL" \
  --role="roles/storage.objectViewer"
```

### Project B (`multihopwanderer-1771992134`)

- Project read access:

```bash
gcloud projects add-iam-policy-binding multihopwanderer-1771992134 \
  --member="user:USER_EMAIL" \
  --role="roles/viewer"
```

- Bucket read/write access:

```bash
gcloud storage buckets add-iam-policy-binding gs://multihopwanderer-1771992134-team-bucket \
  --member="user:USER_EMAIL" \
  --role="roles/storage.objectAdmin"
```

## 6) CLI Verification

### Project A read-only checks

```bash
use_benchspark
gcloud storage ls gs://benchspark-data-1771447466-datasets
gcloud storage cp gs://benchspark-data-1771447466-datasets/<OBJECT_NAME> /tmp/
```

Expected failures (permission denied):

```bash
echo "test" >/tmp/should-fail.txt
gcloud storage cp /tmp/should-fail.txt gs://benchspark-data-1771447466-datasets/
gcloud storage rm gs://benchspark-data-1771447466-datasets/<OBJECT_NAME>
```

### Project B read/write checks

```bash
use_multihop
gcloud storage ls gs://multihopwanderer-1771992134-team-bucket
echo "test" >/tmp/gcs-rw.txt
gcloud storage cp /tmp/gcs-rw.txt gs://multihopwanderer-1771992134-team-bucket/_codex_smoke/gcs-rw.txt
gcloud storage rm gs://multihopwanderer-1771992134-team-bucket/_codex_smoke/gcs-rw.txt
```

## 7) Python SDK (ADC) Verification

Install dependency:

```bash
pip3 install google-cloud-storage
```

Run read-only check:

```bash
python3 scripts/gcp/storage_smoke.py \
  --project-id benchspark-data-1771447466 \
  --bucket benchspark-data-1771447466-datasets \
  --mode read
```

Run read/write check:

```bash
python3 scripts/gcp/storage_smoke.py \
  --project-id multihopwanderer-1771992134 \
  --bucket multihopwanderer-1771992134-team-bucket \
  --mode readwrite
```

## Troubleshooting

- `gcloud: command not found`:
  - Ensure `/opt/homebrew/bin` is in PATH.
- `Anonymous caller` or `403`:
  - IAM roles are missing or applied to wrong user/project/bucket.
- `ADC` errors in Python:
  - Re-run `gcloud auth application-default login`.
- Wrong project in commands:
  - Run `gcloud config list` and switch config via `use_benchspark` / `use_multihop`.
