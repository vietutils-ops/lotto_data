# Data provenance

Where every published record comes from, what was done to it, and what is
known to be uncertain. The machine-readable history is
`metadata/audit_log.jsonl` (append-only); rejected source rows are kept in
`metadata/quarantine/`. Each game's `metadata.json` describes its latest
acquisition and `source.json` its official source and compliance record.

Wording used throughout: "Historical results derived from publicly available
results of the operator." No official API is used, and this repository is not
an official source.

## Vietnam — Vietlott (`mega645`, `power655`)

| | Mega 6/45 | Power 6/55 |
|---|---|---|
| Original public source | Vietlott result information (vietlott.vn) | Vietlott result information (vietlott.vn) |
| Acquisition here | Conversion from `viettran88/vietlott-data` dataset 2026.10.07.001 | same |
| Records | 1,375 | 1,406 |
| Coverage | draw 00198 (2017-10-25) – 01572 (2026-10-07) | draw 00001 (2017-08-01) – 01407 (2026-10-06) |
| Known missing draws | none inside the range; draws 00001–00197 are not covered | 00944 (`config/known_gaps.json`) |
| Rules | `mega645_v1`: 6 of 1–45 | `power655_v1`: 6 of 1–55 + bonus ball from the remaining balls |

### Lineage

1. **2026-10-07 — bootstrap** (in `vietlott-data`): records imported from the
   public repository https://github.com/vietvudanh/vietlott-data at commit
   `a632f03feeb227a74f8da70979a31fd4126efa83`, retrieved 2026-10-07T14:33:00Z;
   data only, no code. One record filed under Power 6/55 draw 00944 was a Mega
   6/45 result and was quarantined; that draw is recorded as missing. Licence
   observations and the full bootstrap record: `vietlott-data/PROVENANCE.md`
   and [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
2. **2026-10-07 — owner confirmation**: the repository owner confirmed the
   data usage terms before `vietlott-data` was published.
3. **2026-10-08 — conversion** (here): `scripts/convert_vietlott_data.py`
   rewrote both datasets in the global format (schema 2), adding each draw's
   ruleset; it refuses to write unless every draw is identical to the source
   (also checked by `tests/test_repository_data.py` and by the app's tests).

### Ongoing updates

`python -m scripts.update --game mega645|power655 --write` reads the public
result listing of vietlott.vn (the same requests its own result table makes)
from a network where the site is reachable, honouring robots.txt and a rate
limit. Every run appends an audit event with the source URL, retrieval time,
added draw range and dataset version.

## Adding a source

Before a game is collected, its record in [docs/sources.md](docs/sources.md)
must state the official source, its terms and robots.txt review, and the
distribution decision (`public`, `restricted` or `disabled`).
