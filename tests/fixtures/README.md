# Test fixtures

`<adapter>/` holds raw responses captured from official sources with
`python -m scripts.capture_fixture --game <code>` (unchanged bytes, one file
per page). `tests/test_fixtures.py` parses every capture and checks each row
against the published draws, so a parser change cannot silently misread a
real page.

No capture is committed yet: the environment that built this repository
cannot reach the official sources (its network policy blocks them). Capture
pages from a network where the sources are reachable, review them, and commit
them here. Parser tests meanwhile use hand-written pages in the source's
structure, filled with published draws of this repository.
