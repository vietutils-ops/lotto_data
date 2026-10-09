"""Structured errors of the data pipeline.

Every failure is reported with a stable ``code`` so runs can be compared and
alerts can be filtered. None of them is ever "handled" by guessing data.
"""

from __future__ import annotations


class LottoDataError(Exception):
    code = "error"

    def __init__(self, message: str, *, game: str | None = None):
        super().__init__(message)
        self.game = game

    def render(self) -> str:
        prefix = f"[{self.code}]" + (f" {self.game}:" if self.game else "")
        return f"{prefix} {self}"


class SourceUnavailable(LottoDataError):
    """The official source could not be read (network, HTTP status, timeout)."""

    code = "source_unavailable"


class AccessDenied(SourceUnavailable):
    """The source refused access (401/403/451 or a challenge page). Never bypassed."""

    code = "access_denied"


class RobotsDisallowed(SourceUnavailable):
    """robots.txt of the source does not allow the request. Never overridden."""

    code = "robots_disallowed"


class RateLimited(SourceUnavailable):
    """The source kept answering 429 after the polite retries."""

    code = "rate_limited"


class ParseFailed(LottoDataError):
    """The source answered, but not in the format the adapter understands."""

    code = "parse_failed"


class NoDataFound(LottoDataError):
    """The source answered with no usable draw at all."""

    code = "no_data_found"


class DataInvalid(LottoDataError):
    """Draws or files break the canonical rules."""

    code = "data_invalid"


class RulesetUnknown(LottoDataError):
    """A draw date is covered by no ruleset of the game."""

    code = "ruleset_unknown"


class SchemaMismatch(LottoDataError):
    """A file does not match its JSON Schema or schema version."""

    code = "schema_mismatch"


class ChecksumFailed(LottoDataError):
    """A published file does not match its recorded SHA-256."""

    code = "checksum_failed"


class HistoryChanged(LottoDataError):
    """New data would change or delete already published draws."""

    code = "history_changed"


class DistributionRestricted(LottoDataError):
    """The game's data may not be published (distribution mode)."""

    code = "distribution_restricted"
