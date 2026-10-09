# Adding a game

1. **Rules.** Verify the rules and their history from the operator's official
   pages (pool sizes, extra balls, separate pools, draw days, time zone, ID
   format, first draw, every rule change with its first draw date).
2. **Source review.** Read the official source's terms and robots.txt; record
   them in `docs/sources.md` and in the game's `compliance` block. Decide the
   distribution mode. If redistribution is not allowed or unclear, use
   `restricted`.
3. **Registry.** Add the game to `sources/source_registry.json`
   (`games/<cc>/<slug>`, IANA time zone, ISO weekdays, `sequential` or `date`
   IDs, coverage start, adapter).
4. **Rulesets.** Write `games/<cc>/<slug>/rulesets.json`: one ruleset per era,
   ids `<game_code>_v<n>`, only the latest open-ended. The app ships the same
   eras in its game pack; published eras may later be added or close the
   current one, never change a shipped one.
5. **Adapter.** Reuse or add an adapter in `scripts/lottodata/adapters/` (only
   fetching and parsing; everything else is shared), its settings in
   `sources/adapters/<adapter>.json`, and register it in `adapters()`.
6. **Fixtures.** Capture real pages (`python -m scripts.capture_fixture`),
   review and commit them; write parser tests for the source's formats.
7. **Collect.** `python -m scripts.update --game <code> --max-pages N` (dry
   run), then `--write`; backfill older history the same way or with a
   documented import. Record unexplained gaps in `config/known_gaps.json`.
8. **Check.** `python -m scripts.validate`, `python -m pytest -q`,
   `python -m scripts.health_check --live --game <code>`.
9. **App.** Enable the game's pack in the app only when its data is published.
