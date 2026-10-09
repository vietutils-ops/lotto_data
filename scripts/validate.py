"""Validates the whole repository: schemas, rulesets, every draw under its
ruleset, generated files (metadata, source, catalog) and checksums.

    python -m scripts.validate
"""

from __future__ import annotations

import argparse
import sys

from scripts.lottodata.cli import now_utc
from scripts.lottodata.layout import RepoLayout
from scripts.lottodata.repo_validation import validate_repository


def main(argv=None) -> int:
    argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter).parse_args(argv)
    report = validate_repository(RepoLayout(), now_utc())
    for line in report.lines():
        print(line)
    print("OK" if report.ok else "FAILED")
    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main())
