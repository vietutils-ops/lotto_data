# lotto-data — global historical lottery results for LottoStat

Static, versioned, checksummed datasets of historical lottery results, read by
the LottoStat app over HTTPS (GitHub Raw or GitHub Pages). There is no server,
API or database: the app downloads `catalog.json`, then only the files of the
games its user follows.

> Historical results for statistical research. Not an official source; not
> affiliated with any lottery operator. Always check results with the official
> source. See [PROVENANCE.md](PROVENANCE.md) and [docs/sources.md](docs/sources.md).

This repository replaces nothing: the Vietlott-only repository
(`viettran88/vietlott-data`) stays as it is for installed app versions. Its
draws were converted here, not re-collected, and are identical.

## Games

| Game | Country / operator | Rules (current era) | Draws | Coverage |
|---|---|---|---|---|
| `mega645` Mega 6/45 | VN / Vietlott | 6 of 1–45 | Wed, Fri, Sun | from draw 00198 (2017-10-25) |
| `power655` Power 6/55 | VN / Vietlott | 6 of 1–55 + bonus ball | Tue, Thu, Sat | from draw 00001 (2017-08-01); 00944 missing |

More countries are added one game at a time (adapter, verified rules,
captured fixtures, compliance record); see [docs/adding-a-game.md](docs/adding-a-game.md).

## Layout

```
catalog.json                        games with published data, relative URLs (schema 1)
games/<cc>/<slug>/draws.json        canonical draws, one per line (schema 2)
games/<cc>/<slug>/metadata.json     version, counts, coverage, SHA-256 of draws and rulesets
games/<cc>/<slug>/rulesets.json     the game's rule eras (maintained by hand)
games/<cc>/<slug>/source.json       official source, distribution mode, compliance record
schemas/                            JSON Schemas of every file
sources/source_registry.json        every game: identity, schedule, ID format, source, adapter
sources/adapters/<adapter>.json     source-specific request settings
config/known_gaps.json              draw IDs knowingly missing, each with a reason
metadata/audit_log.jsonl            append-only history of every change
metadata/quarantine/                rejected source rows, with reasons
checksums/SHA256SUMS                sha256sum-compatible checksums of the published files
scripts/                            the tools (developer tooling, not a backend)
tests/                              pytest suite; fixtures/ holds captured source pages
```

The file formats are documented in the app repository
(`docs/global/data-format-v2.md`) and enforced by `schemas/`. Every draw names
its `ruleset_version`; the app validates it under that ruleset exactly as
`scripts/` does.

## Setup

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt     # jsonschema, beautifulsoup4, pytest
python -m pytest -q
```

## Tools

Commands that write default to a **dry run**; add `--write`.

```bash
python -m scripts.update --game power655                 # what would change
python -m scripts.update --all --write [--run-tests]     # collect, validate, publish, audit
python -m scripts.validate                               # whole repository
python -m scripts.health_check [--live] [--game CODE]    # freshness, consistency, sources
python -m scripts.build [--write] [--accept-changes]     # after editing rulesets.json or the registry
python -m scripts.capture_fixture --game power655        # save a raw source page as a test fixture
python -m scripts.convert_vietlott_data --source ../vietlott-data [--write]
```

`update` runs, per game: fetch (source adapter; robots.txt honoured, at least
1 s between requests, no access-control bypass) → normalize → assign the
ruleset of each draw date → validate → detect changes → write draws,
metadata, source, catalog and checksums → append to the audit log. One
game's failure never stops the others. Published draws are never changed or
removed unless `--accept-changes` is given after checking the official
source; the audit log records it.

Failures carry stable codes: `source_unavailable`, `access_denied`,
`robots_disallowed`, `rate_limited`, `parse_failed`, `no_data_found`,
`data_invalid`, `ruleset_unknown`, `schema_mismatch`, `checksum_failed`,
`history_changed`, `distribution_restricted`.

Network settings (environment): `LOTTO_HTTP_TIMEOUT`, `LOTTO_RETRY_COUNT`,
`LOTTO_RETRY_BACKOFF`, `LOTTO_RATE_LIMIT_DELAY` (≥ 1 s), `LOTTO_USER_AGENT`,
`LOTTO_PROXY`.

## Publishing

Collection needs a network that can reach the official sources: a
maintainer's machine, or the optional self-hosted runner workflow
(`.github/workflows/collect.yml`). GitHub-hosted CI only validates
(`.github/workflows/validate.yml`). After a run with `--write`:

```bash
python -m scripts.validate && sha256sum -c checksums/SHA256SUMS
git add catalog.json games checksums metadata && git commit -m "data: <games> update"
```

The app reads `https://raw.githubusercontent.com/<owner>/lotto-data/main/`
with `LOTTO_DATA_FORMAT=catalog`.

## Licence

Code and documents: MIT ([LICENSE](LICENSE)). Data: factual historical results,
provided as is; see the data notice in [LICENSE](LICENSE),
[PROVENANCE.md](PROVENANCE.md) and [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
