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


def _today() -> str:
    import datetime as dt

    return dt.date.today().isoformat()


def _diff_summary(diff) -> str:
    counts = diff.change.value_counts()
    return ", ".join(f"{counts.get(k, 0)} {k}" for k in ("added", "removed", "changed"))


def cmd_refs_fetch(args: argparse.Namespace, cfg: Config) -> int:
    """Liquipedia downloads wait for the API key (T028); OWTV waits for its probe (T064-T066)."""
    from owstudy.collect.errors import RetrievalBlocked
    from owstudy.collect.refs.ratelimit import build_user_agent

    if args.source == "owtv":
        raise UsageError("the OWTV reader isn't built yet (task T066, after the OWTV probe and permission)")
    if not cfg.local.liquipedia_api_key or cfg.local.liquipedia_api_key.startswith("<"):
        raise RetrievalBlocked(
            "no Liquipedia API key yet: set liquipedia_api_key in configs/collect/local.yaml when Liquipedia "
            "sends it (requested 2026-11-16). Nothing was downloaded."
        )
    build_user_agent(cfg.local.user_agent_contact)  # refuses without a contact
    raise UsageError("downloading Liquipedia pages isn't built yet: task T028 finishes it now that the key is set")


def cmd_refs_import_sheet(args: argparse.Namespace, cfg: Config) -> int:
    """Parse the spreadsheet into a new dated snapshot and report what changed since the last one."""
    import shutil

    from owstudy.collect.refs.snapshot import diff_snapshots, list_snapshots, new_snapshot, write_diff_report
    from owstudy.collect.refs.spreadsheet import import_sheet

    if not args.path.exists():
        raise UsageError(f"spreadsheet not found: {args.path}")
    root = args.data_dir / "raw" / "reference"
    previous = list_snapshots("spreadsheet", root)
    folder = new_snapshot("spreadsheet", _today(), root)
    try:
        counts = import_sheet(args.path, folder)
    except Exception:
        shutil.rmtree(folder)  # a half-written snapshot is never left behind
        raise
    print(f"spreadsheet snapshot {folder}: {counts['series']} series, {counts['maps']} maps, {counts['bans']} bans")
    if previous:
        diff = diff_snapshots(previous[-1] / "sheet_series.csv", folder / "sheet_series.csv", ["series_key"],
                              ignore=["locator"])  # fmt: skip
        report = write_diff_report(diff, "spreadsheet", folder.name, args.data_dir / "interim" / "reports",
                                   ["series_key"])  # fmt: skip
        print(f"series since {previous[-1].name}: {_diff_summary(diff)} (details: {report})")
    return 0


def cmd_videos_list(args: argparse.Namespace, cfg: Config) -> int:
    """Snapshot the channel's video list (no downloads) and report new and removed videos."""
    from owstudy.collect.refs.snapshot import list_snapshots
    from owstudy.collect.refs.youtube_list import list_channel, load_videos

    root = args.data_dir / "raw" / "reference"
    previous = list_snapshots("youtube", root)
    folder = list_channel(root=root, date=_today())
    ids = {v["id"] for v in load_videos(folder)}
    print(f"youtube snapshot {folder}: {len(ids)} videos")
    if previous:
        old = {v["id"] for v in load_videos(previous[-1])}
        print(f"since {previous[-1].name}: {len(ids - old)} added, {len(old - ids)} removed")
    return 0


def cmd_catalog_build(args: argparse.Namespace, cfg: Config) -> int:
    from owstudy.collect.catalog.build import run_catalog

    run = run_catalog(args.data_dir, cfg, args.scope_keys)
    cat, links = run.catalog, run.links
    s, m = cat.series, cat.maps
    print(f"scope: {', '.join(args.scope_keys)}  (snapshots: "
          + ", ".join(f"{k} {v}" for k, v in sorted(cat.snapshots.items())) + ")")  # fmt: skip
    print(f"series: {len(s)} ({', '.join(f'{k} {v}' for k, v in s.status.value_counts().sort_index().items())}); "
          f"{int((~s.sources.str.contains(';')).sum())} listed by one source only")  # fmt: skip
    print(f"maps: {len(m)} ({', '.join(f'{k} {v}' for k, v in m.status.value_counts().sort_index().items())})")
    print(f"lineups: {len(cat.lineups)} player rows; patch-day series to check: {len(cat.patch_day)}")
    counts = links.status.value_counts().sort_index()
    print("videos: " + (", ".join(f"{k} {v}" for k, v in counts.items()) or "none"))
    linked = links[links.status == "linked"]
    print("links: " + ", ".join(f"{k} {int((linked.link_confidence == k).sum())}" for k in ("high", "medium", "low"))
          + f"; {int((linked.role == 'primary').sum())} series with a primary POV")  # fmt: skip
    print(f"alias proposals to review: {len(cat.proposals)} (data/interim/entities/aliases_proposed.csv)")
    print(f"wrote {len(run.paths)} files")
    return 0


def cmd_status(args: argparse.Namespace, cfg: Config) -> int:
    """Coverage per region-stage of the scope, from the last `catalog build`."""
    from owstudy.collect.catalog.inventory import coverage_status

    catalog_dir = args.data_dir / "interim" / "catalog"
    if not (catalog_dir / "series.csv").exists():
        raise UsageError("no catalog yet: run `owstudy-collect catalog build` first")
    table = coverage_status(catalog_dir)
    table = table[table.region_stage.isin(args.scope_keys)]
    if table.empty:
        print("nothing in the catalog for this scope yet")
        return 0
    print(table.to_string(index=False))
    return 0


HANDLERS: dict[tuple[str, ...], Callable[[argparse.Namespace, Config], int]] = {
    ("inventory",): cmd_inventory,
    ("refs", "fetch"): cmd_refs_fetch,
    ("refs", "import-sheet"): cmd_refs_import_sheet,
    ("videos", "list"): cmd_videos_list,
    ("catalog", "build"): cmd_catalog_build,
    ("status",): cmd_status,
}


def _add_global_options(parser: argparse.ArgumentParser, with_defaults: bool = True) -> None:
    def d(value):
        return {"default": value} if with_defaults else {}

    parser.add_argument("--config", type=Path, help="settings file (default: %s)" % DEFAULT_CONFIG,
                        **d(DEFAULT_CONFIG))
    parser.add_argument("--scope", help="pilot (default), a region-stage key such as 'Asia/Stage 1/Korea', or all",
                        **d("pilot"))
    parser.add_argument("--force-scope", action="store_true", help="allow a region-stage that isn't approved yet",
                        **d(False))
    parser.add_argument("--data-dir", type=Path, help="data folder (default: data)", **d(Path("data")))
    parser.add_argument("-v", "--verbose", action="count", **d(0))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="owstudy-collect", description="Collect and verify OWCS 2026 match data.")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    _add_global_options(parser)
    # The same options also work after the command (`catalog build --scope pilot`). There they
    # default to SUPPRESS so they only override what was given before the command when typed.
    shared = argparse.ArgumentParser(add_help=False, argument_default=argparse.SUPPRESS)
    _add_global_options(shared, with_defaults=False)

    top = parser.add_subparsers(dest="cmd", metavar="COMMAND", required=True)
    groups: dict[str, argparse._SubParsersAction] = {}
    for path, help_text, task, setup in COMMANDS:
        if len(path) == 1:
            p = top.add_parser(path[0], help=help_text, description=help_text, parents=[shared])
        else:
            if path[0] not in groups:
                g = top.add_parser(path[0], help=f"{path[0]} commands")
                groups[path[0]] = g.add_subparsers(dest="subcmd", metavar="SUBCOMMAND", required=True)
            p = groups[path[0]].add_parser(path[1], help=help_text, description=help_text, parents=[shared])
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
