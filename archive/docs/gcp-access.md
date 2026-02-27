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

## 2.1) Multi-Account CLI Model (Recommended)

Use one `gcloud` configuration per `(project, principal)` pair.

- `benchspark-read` -> project `benchspark-data-1771447466`, account 'Your google email'
- `multihop-rw` -> project `multihopwanderer-1771992134`, account 'Your google email'

Set account explicitly inside each config:

```bash
gcloud config configurations activate benchspark-read
gcloud config set account 'Your google email'

gcloud config configurations activate multihop-rw
gcloud config set account 'Your google email'
```

If you add another human account later:

```bash
gcloud auth login --update-adc
gcloud config configurations activate <config>
gcloud config set account <other-user@example.com>
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

Use user-account configs:

```bash
use_benchspark
use_multihop
```

Use service-account configs for `multihopwanderer-1771992134`:

```bash
# No key files required (recommended), requires TokenCreator IAM:
use_multihop_sa1_impersonation
use_multihop_sa2_impersonation

# Key-file fallback (requires local JSON keys + env vars):
use_multihop_sa1_key
use_multihop_sa2_key
```

## 4.1) Service Accounts for `multihopwanderer-1771992134`

Known service accounts in that project:

- `multihopwanderer-1771992134@appspot.gserviceaccount.com` (App Engine default SA)
- `113940992739-compute@developer.gserviceaccount.com` (Compute Engine default SA)

Two supported CLI approaches (configured in `scripts/gcp/switch-config.sh`):

1. Impersonation (recommended, no key files):

- Admin must grant your user `roles/iam.serviceAccountTokenCreator` on each SA.
- First-time check:

```bash
gcloud auth print-access-token \
  --impersonate-service-account=multihopwanderer-1771992134@appspot.gserviceaccount.com >/dev/null && echo "SA1 impersonation OK"
gcloud auth print-access-token \
  --impersonate-service-account=113940992739-compute@developer.gserviceaccount.com >/dev/null && echo "SA2 impersonation OK"
```

2. Key file auth (fallback):

- Download one key JSON per service account.
- Keep them outside this repo.
- Export paths once in your shell profile:

```bash
export MULTIHOP_SA1_KEY_PATH=/absolute/path/multihop-sa1.json
export MULTIHOP_SA2_KEY_PATH=/absolute/path/multihop-sa2.json
```

Dashboard steps to export JSON keys:

1. Open Service Accounts in project `multihopwanderer-1771992134`:
   - <https://console.cloud.google.com/iam-admin/serviceaccounts?project=multihopwanderer-1771992134>
2. Click service account `multihopwanderer-1771992134@appspot.gserviceaccount.com`.
3. Open `Keys` tab -> `Add key` -> `Create new key` -> choose `JSON` -> `Create`.
4. Repeat for `113940992739-compute@developer.gserviceaccount.com`.
5. Move downloaded files to a private folder and lock permissions:

```bash
mkdir -p ~/.config/gcloud/sa-keys
mv ~/Downloads/*.json ~/.config/gcloud/sa-keys/
chmod 600 ~/.config/gcloud/sa-keys/*.json
```

6. Set persistent exports in `~/.zshrc`:

```bash
export MULTIHOP_SA1_KEY_PATH="$HOME/.config/gcloud/sa-keys/<sa1-file>.json"
export MULTIHOP_SA2_KEY_PATH="$HOME/.config/gcloud/sa-keys/<sa2-file>.json"
```

If keys are in the repo root temporarily, helpers can auto-detect them by `client_email`:

```bash
source scripts/gcp/switch-config.sh
auto_detect_multihop_sa_keys
show_multihop_sa_key_paths
```

Optional overrides if SA emails differ:

```bash
export MULTIHOP_SA1_EMAIL=multihopwanderer-1771992134@appspot.gserviceaccount.com
export MULTIHOP_SA2_EMAIL=113940992739-compute@developer.gserviceaccount.com
```

Current observed state from this machine:

- User account storage access works on both buckets.
- Service-account impersonation is currently denied (missing `iam.serviceAccounts.getAccessToken`).

## 4.2) Observed Access Matrix (Current)

- `benchspark-data-1771447466`
  - Bucket listing/read: works
  - Project service listing (`gcloud services list`): denied
- `multihopwanderer-1771992134`
  - Bucket listing/read/write: works
  - Project service listing (`gcloud services list`): works
- ADC quota project assignment:
  - `gcloud auth application-default set-quota-project ...` currently fails (missing `serviceusage.services.use`)

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

### Project B checks using each service account

Impersonation mode:

```bash
use_multihop_sa1_impersonation
gcloud storage ls gs://multihopwanderer-1771992134-team-bucket

use_multihop_sa2_impersonation
gcloud storage ls gs://multihopwanderer-1771992134-team-bucket
```

Key-file mode:

```bash
use_multihop_sa1_key
gcloud storage ls gs://multihopwanderer-1771992134-team-bucket

use_multihop_sa2_key
gcloud storage ls gs://multihopwanderer-1771992134-team-bucket
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
- `Failed to impersonate ... iam.serviceAccounts.getAccessToken denied`:
  - Grant `roles/iam.serviceAccountTokenCreator` on that service account to your user.
- Wrong project in commands:
  - Run `gcloud config list` and switch config via `use_benchspark` / `use_multihop`.
- `Cannot add project as ADC quota project ... serviceusage.services.use`:
  - Your account lacks `serviceusage.services.use` on that project.
  - This does not remove storage IAM permissions; it affects quota-project assignment for ADC.
