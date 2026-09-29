# ELN SMW Adapter
A webservice to collect experiment data from various ELN (electronic lab notebook) and insert into SMW (Semantic MediaWiki) with a unified data structure. This tool uses a simple plugin architecture to flexibly adapt to different data sources.

## Run with Docker

```bash
docker run -d --name eln-smw-adapter -p 5000:5000 \
  -e SMW_API_URL=https://wiki.example.org/api.php \
  -e SMW_USERNAME=MigratorBot \
  -e SMW_PASSWORD=<BOT-PASSWORD> \
  -e ENABLED_PLUGINS=eLabFTW,Excel-local \
  -e ELABFTW_API_URL=https://elab.example.org/api/v2/ \
  -e ELABFTW_API_KEY=<API-TOKEN> \
  -e EXCEL_LOCAL_TYPE=upload \
  -v adapter-log:/app/log -v adapter-jobs:/app/jobs -v adapter-uploads:/app/uploads \
  ghcr.io/tibhannover/eln-smw-adapter:1.0.0
```

The container is healthy when `/status` reports `smw_connection: connected`. No secrets are baked into the image.

### Configuration

Environment variables take precedence over `config/config.ini`, which is optional (mount it to `/app/config/config.ini`).

| Variable | Config equivalent | Description |
| --- | --- | --- |
| `SMW_API_URL`, `SMW_USERNAME`, `SMW_PASSWORD` | `[SMW]` | Semantic MediaWiki API and bot credentials |
| `DEBUG_MODE` | `[Main] debug_mode` | `on` creates no pages, only reports them |
| `UPLOAD_PATH` | `[Main] upload_path` | Upload directory (default `./uploads`) |
| `ENABLED_PLUGINS` | `[Plugins]` | Comma separated plugin names, e.g. `eLabFTW,Excel-local` |
| `<PLUGIN>_<OPTION>` | `[<Plugin>] <option>` | Plugin options for enabled plugins, e.g. `ELABFTW_API_URL`, `ELABFTW_API_KEY`, `ELABFTW_VERIFY_SSL`, `EXCEL_LOCAL_TYPE`. Non-alphanumeric characters in the plugin name become `_`. |

TLS certificates of eLabFTW are verified by default. Set `ELABFTW_VERIFY_SSL=off` (or `verify_ssl = off`) for instances with self-signed certificates.

CORS is not enabled; the adapter is meant to be called by backend services, not directly from browsers.

### Run without Docker

```bash
pip install -r requirements.txt
gunicorn --workers 1 --threads 8 --timeout 300 --bind 127.0.0.1:5000 app:app
```

Use a single worker: async jobs run in-process. See `service/` for a systemd unit.

## Versioning and releases

The version is stored in the `VERSION` file and follows [Semantic Versioning](https://semver.org/). Tags have no `v` prefix (`1.0.0`, not `v1.0.0`).

To create a release:

1. Set the new version in `VERSION` and merge it into `master`.
2. Create a GitHub release with the tag `X.Y.Z` on `master` (GitHub UI, or `gh release create X.Y.Z --target master --generate-notes`).
3. The workflow `Publish container image` checks that the tag matches `VERSION` and publishes `ghcr.io/tibhannover/eln-smw-adapter` with the tags `X.Y.Z`, `X.Y` and `X` (and `latest`). Check the run in the Actions tab.

Hotfixes for older versions go to the maintenance branch `X.Y.x` (e.g. `0.9.x`). Branch from the tag of the last release of that line, and release from that branch as described above.

The image is published on release only, not on every push. The GHCR package must be set to public once (package settings on GitHub) so that deployments can pull it without credentials.
