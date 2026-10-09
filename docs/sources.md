# Sources and compliance record

One entry per official source. A game is collected only when its entry is
complete, and published only when its distribution mode is `public`. The
machine-readable copy of each record is the `compliance` block of the game in
`sources/source_registry.json` (shown in its `source.json`).

Rules for every source:

* Read only what the operator publishes openly to every visitor.
* Honour robots.txt (the collector reads it before the first request to a host
  and stops when it disallows the request or cannot be read because the server
  fails).
* At most one request per second (default 1.5 s), polite retries, a descriptive
  User-Agent (`LottoStat-DataCollector/2.0`).
* Never bypass CAPTCHAs, logins, geo-blocks or anti-bot systems; never use
  private APIs or leaked credentials. A refusal stops the run (`access_denied`).
* Keep results as published: no invented, estimated or "repaired" draws.
* When terms forbid redistribution, or are unclear, the game stays
  `restricted` (rulesets and source record only, no draws) until resolved.

## Vietlott (Vietnam) — `mega645`, `power655`

| Item | Record |
|---|---|
| Official source | https://vietlott.vn/ (result pages per game) |
| Access | Public result listing; the same paginated requests the site's own table makes (`sources/adapters/vietlott.json`) |
| Terms | Not reviewed from the build environment (its network policy blocks the site) |
| robots.txt | Not reviewed from the build environment; read by the collector on every run |
| Owner decision | Data usage confirmed by the repository owner on 2026-10-07 |
| Distribution mode | `public` |
| Adapter | `vietlott` (`scripts/lottodata/adapters/vietlott.py`) |
| Captured fixtures | none yet (`tests/fixtures/README.md`) |

## Planned sources

The migration plan of the app (`docs/global/migration-plan.md`, §5) lists the
candidate official sources of the next games (Korea, Philippines, Singapore,
Canada, Germany, Spain, Japan, France, United Kingdom, Australia, United
States). Each gets an entry here, with its terms and robots.txt review, before
any collection.
