"""`owstudy-collect` command line (contracts/cli.md).

Every command is registered here. Commands that aren't built yet say which task builds them
and exit with code 2.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

from owstudy.collect import __version__
from owstudy.collect.config import DEFAULT_CONFIG, Config, load_config
from owstudy.collect.errors import CollectError, UsageError

# (command path, help, task that builds it, extra-argument setup)
Setup = Callable[[argparse.ArgumentParser], None]


def _ids(p: argparse.ArgumentParser, name: str, help: str) -> None:
    p.add_argument(name, nargs="+", help=help)


COMMANDS: list[tuple[tuple[str, ...], str, str, Setup | None]] = [
    (("refs", "fetch"), "Retrieve a new Liquipedia or OWTV snapshot within rate limits.", "T033",
     lambda p: (p.add_argument("source", choices=["liquipedia", "owtv"]),
                p.add_argument("--since-snapshot", metavar="ID"))),
    (("refs", "import-sheet"), "Parse the Hero Bans & Metas spreadsheet into a snapshot.", "T033",
     lambda p: p.add_argument("path", type=Path)),
    (("refs", "probe-owtv"), "OWTV probe: save what OWTV offers for a few series.", "T064",
     lambda p: _ids(p, "series", "series keys")),
    (("videos", "list"), "Snapshot the ObsSojourn channel's video list (no downloads).", "T033", None),
    (("catalog", "build"), "Build entities, alias proposals, series, maps, lineups and video links.", "T033", None),
    (("inventory",), "Footage inventory: series, maps and hours of POV video per event.", "T025", None),
    (("hud", "probe"), "HUD probe: sample frames from a few videos and save crops and a checklist.", "T059",
     lambda p: _ids(p, "videos", "video IDs")),
    (("icons", "harvest"), "Group hero portrait crops from videos for naming.", "T059",
     lambda p: _ids(p, "videos", "video IDs")),
    (("icons", "label"), "Name each group of hero portrait crops.", "T059", None),
    (("extract",), "Download, read and delete each video (safe to stop and restart).", "T059",
     lambda p: (p.add_argument("--videos", nargs="+", metavar="ID"), p.add_argument("--force", action="store_true"),
                p.add_argument("--keep-video", action="store_true"),
                p.add_argument("--check-determinism", action="store_true"))),
    (("broadcast-test",), "Score broadcast VODs against POV readings for a few series.", "T091",
     lambda p: _ids(p, "series", "series keys")),
    (("build",), "Interpret, reconcile, compare and set map status. No network.", "T080", None),
    (("review",), "Settle open discrepancies one by one.", "T077",
     lambda p: (p.add_argument("--kind"), p.add_argument("--map", dest="map_id", metavar="MAP_ID"))),
    (("audit",), "Prove every value traces to raw data or a decision.", "T078", None),
    (("validate",), "Check every data layer.", "T078", None),
    (("gold", "init"), "Make hand-label templates for gold maps.", "T061",
     lambda p: _ids(p, "maps", "map IDs")),
    (("gold", "score"), "Score the viewer against the gold labels.", "T061", None),
    (("plant-errors",), "Plant errors in a copy of the data and check each one is caught.", "T079",
     lambda p: (p.add_argument("--maps", type=int, required=True), p.add_argument("--out", type=Path, required=True))),
    (("export",), "Write feature 001 input, analysis tables, summary and provenance.", "T088",
     lambda p: (p.add_argument("--include", choices=["verified", "partial", "all"]),
                p.add_argument("--out", type=Path), p.add_argument("--no-analysis-tables", action="store_true"))),
    (("status",), "Coverage per region-stage.", "T034", None),
]  # fmt: skip


def resolve_scope(cfg: Config, scope: str, force: bool = False) -> list[str]:
    """Region-stage keys for `--scope`.

    `pilot` -> the pilot; `all` -> every approved region-stage; a key -> that key, which must be
    approved unless `force` is set (FR-023: expand one approved region-stage at a time).
    """
    if scope == "pilot":
        return [cfg.scope.pilot]
    if scope == "all":
        return list(cfg.scope.approved)
    if scope in cfg.scope.approved or force:
        return [scope]
    raise UsageError(
        f"region-stage {scope!r} isn't approved yet (scope.approved in default.yaml); "
        "add it there after the pilot gate, or pass --force-scope"
    )


def _not_built(task: str) -> Callable[[argparse.Namespace, Config], int]:
    def run(args: argparse.Namespace, cfg: Config) -> int:
        raise UsageError(f"`{' '.join(args.command_path)}` isn't built yet (task {task})")

    return run


def cmd_inventory(args: argparse.Namespace, cfg: Config) -> int:
    """Footage inventory over every 2026 event (a survey, so --scope doesn't narrow it)."""
    from owstudy.collect.catalog.inventory import pilot_label, run_inventory, write_inventory

    data = args.data_dir
    inv = run_inventory(data / "raw" / "reference", data / "interim" / "entities" / "aliases.csv", cfg.scope.pilot)
    out = data / "interim" / "inventory"
    paths = write_inventory(inv, out)
    s = inv.summary.set_index("scope")
    for label in (pilot_label(cfg.scope.pilot), "ALL 2026"):
        r = s.loc[label]
        print(
            f"{label}: {int(r.series)} series, {int(r.maps)} maps, {int(r.series_with_video)} with a POV video "
            f"({r.hours_one_pov:.1f} h of footage at one POV per series)"
        )
    counts = inv.videos.status.value_counts().sort_index()
    print("videos: " + ", ".join(f"{k} {v}" for k, v in counts.items()))
    print(f"wrote {len(paths)} files to {out}")
    return 0


HANDLERS: dict[tuple[str, ...], Callable[[argparse.Namespace, Config], int]] = {
    ("inventory",): cmd_inventory,
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="owstudy-collect", description="Collect and verify OWCS 2026 match data.")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG, help="settings file (default: %(default)s)")
    parser.add_argument("--scope", default="pilot", help="pilot, a region-stage key such as 'Asia/Stage 1/Korea', or all")
    parser.add_argument("--force-scope", action="store_true", help="allow a region-stage that isn't approved yet")
    parser.add_argument("--data-dir", type=Path, default=Path("data"), help="data folder (default: %(default)s)")
    parser.add_argument("-v", "--verbose", action="count", default=0)

    top = parser.add_subparsers(dest="cmd", metavar="COMMAND", required=True)
    groups: dict[str, argparse._SubParsersAction] = {}
    for path, help_text, task, setup in COMMANDS:
        if len(path) == 1:
            p = top.add_parser(path[0], help=help_text, description=help_text)
        else:
            if path[0] not in groups:
                g = top.add_parser(path[0], help=f"{path[0]} commands")
                groups[path[0]] = g.add_subparsers(dest="subcmd", metavar="SUBCOMMAND", required=True)
            p = groups[path[0]].add_parser(path[1], help=help_text, description=help_text)
        if setup is not None:
            setup(p)
        p.set_defaults(command_path=path, handler=HANDLERS.get(path, _not_built(task)))
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as e:  # argparse exits 2 on usage errors, 0 on --help
        return int(e.code or 0)
    try:
        cfg = load_config(args.config)
        args.scope_keys = resolve_scope(cfg, args.scope, args.force_scope)
        return int(args.handler(args, cfg) or 0)
    except CollectError as e:
        print(f"owstudy-collect: {e}", file=sys.stderr)
        return e.exit_code
    except KeyboardInterrupt:
        print("owstudy-collect: stopped", file=sys.stderr)
        return 130


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
