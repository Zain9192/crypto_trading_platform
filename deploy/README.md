# Production deployment

Phase 11 uses a single Linux VM with Docker Compose. The VM needs Docker with the Compose plugin, `openssl`, `curl`, `restic`, `flock`, and `pg_restore` (the verification script runs `pg_restore` in a container). Allocate enough disk and memory for TensorFlow, the three databases, and image updates. Expose only ports 80 and 443; restrict SSH to administrators. The databases and API have no host ports. DNS for `APP_DOMAIN` must point to the VM.

Create `/opt/crypto-platform` owned by the SSH deployment user. Place a mode-600 `.env.production` there from `deploy/production.env.example` with new random credentials. Place a matching certificate and key at `tls/fullchain.pem` and `tls/privkey.pem` (key mode 600); renew them before expiry. The release script verifies the domain, key match, and at least seven days of certificate validity. Store `restic.env` mode 600 with `RESTIC_REPOSITORY`, `RESTIC_PASSWORD_FILE` and your offsite repository's credentials; put the restic password in a separate mode-600 file. Initialize the encrypted offsite repository with `restic init` once. Never copy these files into Git.

Set GitHub environment `production` with secrets `DEPLOY_HOST`, `DEPLOY_USER`, `DEPLOY_SSH_KEY`, and `DEPLOY_KNOWN_HOSTS` (the verified SSH host key line). Grant that environment approval protection if desired. Set repository variable `PRODUCTION_URL` to `https://APP_DOMAIN` for the ten-minute uptime workflow. After Phase 10 and Phase 11 are merged to main and CI is green, run **Deploy production** manually from main. The workflow publishes commit-SHA-tagged GHCR images, uploads the stack, and starts the release; no feature-branch build deploys automatically. Grant the deployment user Docker access and GHCR package read access via the workflow token. The server keeps secrets locally; Actions only supplies SSH and a short-lived registry token.

For an existing database initialized by older Compose files, review that migrations 001–012 are present, back it up, and run the backend image once with `python -m app.ops.migrate --baseline` before the first production release. Fresh databases apply all migrations automatically. Every subsequent release verifies migration checksums and runs only new SQL migrations. Schema changes must remain compatible with the previous app image because image rollback does not reverse a database migration.

Enable the daily UTC backup timer on the VM:

```sh
sudo cp /opt/crypto-platform/deploy/systemd/crypto-platform-backup.* /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now crypto-platform-backup.timer
sudo systemctl start crypto-platform-backup.service
sudo bash -c 'source /opt/crypto-platform/restic.env; /opt/crypto-platform/deploy/verify-backup.sh'
```

The timer retains seven daily, four weekly and six monthly encrypted offsite snapshots of PostgreSQL, MongoDB and immutable model bundles. Review `systemctl status crypto-platform-backup.service`, `journalctl -u crypto-platform-backup.service`, and restic snapshots regularly. A restore is an operator action: stop backend and workers, restore one verified restic snapshot to a restricted temporary directory, use `pg_restore` and `mongorestore` with the archived files into replacement databases, restore the model artifact archive into its volume, verify data, then start the app. Preserve the original volumes until the restore is verified.

For operations, `/api/v1/health` is public liveness; `/api/v1/ready` checks all three stores from inside the backend container and is blocked at the gateway. Docker health checks mark the backend, frontend, gateway, and databases. API logs include generated request IDs, status and duration without query strings or credentials. Set `SENTRY_DSN` only when an approved error-tracking account is ready; request bodies, headers, cookies, and local variables are excluded. Confirm alert routing for failed uptime and backup jobs in the chosen GitHub and VM notification channels.
