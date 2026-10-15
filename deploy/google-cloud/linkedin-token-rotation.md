# LinkedIn token refresh: Cloud Run requirements

The token refresh writes all three LinkedIn token fields into one new version of
the existing consolidated Secret Manager secret. It reads that version back and
validates the complete JSON before destroying any older versions. Disabled
versions are not a cost-saving substitute: Google counts enabled and disabled
versions as active for pricing.

## Configure the existing secret

Set these non-secret Cloud Run environment variables to the exact existing
resource values. Secret IDs are case-sensitive; copy the exact ID shown in Secret Manager if it differs from the repository default:

- `SOCIAL_MCPS_SECRET_NAME`: the consolidated secret ID
  (`social-mcps-credentials`, as reported in the current project).
- `GOOGLE_CLOUD_PROJECT`: the project ID containing that secret
  (`socialmcps` in the repository's current deployment configuration).

Keep `SOCIAL_MCPS_SECRETS_JSON` mapped to the same secret's `latest` version.
Never create a second secret for LinkedIn. Cloud Run fails closed if these
settings are absent; it does not silently fall back to an ephemeral `.env`.

## Grant least privilege on this secret

The Cloud Run service account needs both roles on this one secret:

- `roles/secretmanager.secretAccessor` to read the current JSON.
- `roles/secretmanager.secretVersionManager` to list, add, and destroy versions.

The application checks the effective permissions before creating a version.
The Secret Version Manager role does not include access to secret payloads, so
the accessor role is also required. Do not grant either role project-wide when
secret-level access is sufficient.

## Serialize refreshes

A shared lock object in the existing `QUEUE_GCS_BUCKET` serializes automatic
refreshes with `rotate-secret.sh`; a process-level lock also prevents
simultaneous refreshes within one instance.
Secret Manager's add-version API does not provide compare-and-swap for the
`latest` alias. The shared lock uses a temporary object in the existing
`QUEUE_GCS_BUCKET`; Cloud Run's service account needs object create, read, and
delete access on that bucket. The rotation script uses the same lock. Keep the
service at **one instance**; concurrent requests inside it are safe because the
process-level lock serializes refreshes:

```sh
gcloud run services update unified-mcp \
  --project=socialmcps --region=europe-west1 \
  --max-instances=1 --concurrency=80
```

Do not use `--concurrency=1`: editorial publishing makes the server fetch its own
`/editorial-asset/` URL while the publish request is still running, and MCP
clients may keep connections open, so a single slot returns 429 "no available
instance" (seen by clients as connection timeouts). Keep the shared lock enabled
if the service later needs multiple instances.

## Rotation and recovery behavior

Before contacting LinkedIn, the application acquires the shared lock and checks that Cloud Run metadata, Secret Manager permissions, and the current JSON payload are valid. This avoids rotating a refresh token when durable storage is already known to be unavailable. After LinkedIn responds, the sequence is: read `latest`, add one JSON version, read
that exact version back, validate its full contents, confirm it remains
`latest`, then destroy every older non-destroyed version. Destruction is
irreversible. If write-back validation fails, no old version is destroyed. If
cleanup fails after verification, the verified new credentials remain in the
running process and the operation reports the cleanup error; inspect service
logs and Secret Manager versions. A subsequent successful refresh will also
clean up leftover versions.

No Cloud Run service settings or IAM policies are changed by this code change.
