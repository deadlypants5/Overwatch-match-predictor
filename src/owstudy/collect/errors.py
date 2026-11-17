"""Error types and the exit code each one maps to (contracts/cli.md).

0 ok · 1 validation/audit failure · 2 usage/config error · 3 retrieval blocked · 4 partial success
"""

from __future__ import annotations


class CollectError(Exception):
    """Base class. `exit_code` is what the command line exits with."""

    exit_code = 1


class ValidationError(CollectError):
    """Data failed a check (bad table, changed raw file, failed audit)."""

    exit_code = 1


class ConfigError(CollectError):
    """A settings file is missing, malformed, or has unknown keys or bad values."""

    exit_code = 2


class UsageError(CollectError):
    """The command was called wrongly (bad scope, missing argument)."""

    exit_code = 2


class RetrievalBlocked(CollectError):
    """An outside source can't be used right now: terms not acknowledged, rate limit,
    access refused, missing User-Agent contact, or no network."""

    exit_code = 3


class PartialSuccess(CollectError):
    """Some items failed and the rest succeeded; details are in the state file."""

    exit_code = 4
