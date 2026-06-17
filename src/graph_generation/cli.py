"""CLI entry point — ``pipeline`` console script.

Usage:
    pipeline run all                       # full chain
    pipeline run <stage>                   # single stage
    pipeline run from:<stage>              # from this stage onward
    pipeline run --only <s1>,<s2>          # explicit list
    pipeline plan                          # print planned DAG, no run
    pipeline backup                        # ad-hoc manifest snapshot

A ``--config <path>`` flag overrides the default
``config/pipeline.toml`` (relative to the current working directory).
"""

from __future__ import annotations

import argparse
import shutil
import sys
from datetime import datetime
from pathlib import Path

from .config import load
from .stages.runner import Runner, planned_stages, print_plan


DEFAULT_CONFIG = Path("config/pipeline.toml")


def _add_config_arg(p: argparse.ArgumentParser) -> None:
    p.add_argument("--config", type=Path, default=DEFAULT_CONFIG,
                   help="path to pipeline.toml (default: ./config/pipeline.toml)")


def cmd_run(args: argparse.Namespace) -> int:
    cfg = load(args.config)
    # ``--layouts FMMM,kamada-kawai`` overrides ``[layouts].selected``
    # so a one-off invocation can run a sub-slice of the canonical
    # layout set without editing the TOML. Used by the parallel-
    # layouts dispatcher to spawn one subprocess per layout.
    layouts_filter = getattr(args, "layouts", None)
    if layouts_filter:
        from dataclasses import replace
        names = [s.strip() for s in layouts_filter.split(",") if s.strip()]
        cfg = replace(cfg, layouts=replace(
            cfg.layouts, selected=names, parallel_layouts=1))
    # ``--parallel-layouts N`` clamps the layout subprocess pool size
    # for this invocation without editing the TOML. Used by
    # ``run_pipeline.sh`` to auto-size against available memory: each
    # layout subprocess peaks around 2 GB RSS, so 12 of them on a
    # 16 GB WSL ceiling will OOM-kill systemd. The CLI rejects values
    # < 1 to keep the runner's serial-loop path well-defined.
    pl_override = getattr(args, "parallel_layouts", None)
    if pl_override is not None:
        if pl_override < 1:
            print(f"--parallel-layouts must be >= 1, got {pl_override}",
                  file=sys.stderr)
            return 2
        from dataclasses import replace
        cfg = replace(cfg, layouts=replace(
            cfg.layouts, parallel_layouts=pl_override))
    runner = Runner(cfg)
    target = args.target
    if args.only:
        runner.run_only([s.strip() for s in args.only.split(",") if s.strip()])
    elif target == "all":
        runner.run_all()
    elif target.startswith("from:"):
        runner.run_from(target.removeprefix("from:"))
    else:
        runner.run_only([target])
    return 0


def cmd_plan(args: argparse.Namespace) -> int:
    cfg = load(args.config)
    targets = None
    if args.only:
        targets = [s.strip() for s in args.only.split(",") if s.strip()]
    elif args.target and args.target != "all":
        targets = [args.target]
    print_plan(targets)
    return 0


def cmd_backup(args: argparse.Namespace) -> int:
    cfg = load(args.config)
    out = cfg.out_dir.expanduser().resolve()
    src = out / "manifest.csv"
    if not src.exists():
        print(f"no manifest at {src}", file=sys.stderr)
        return 1
    stamp = datetime.utcnow().strftime("%Y-%m-%dT%H-%M-%SZ")
    label = args.label or "snapshot"
    dst = out / f"manifest.csv.{stamp}-{label}.bak"
    shutil.copy2(src, dst)
    print(f"wrote {dst}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="pipeline")
    sub = p.add_subparsers(dest="cmd", required=True)

    pr = sub.add_parser("run", help="run pipeline stages")
    _add_config_arg(pr)
    pr.add_argument("target", nargs="?", default="all",
                    help="'all', a stage name, or 'from:<stage>'")
    pr.add_argument("--only", help="comma-separated explicit stage list")
    pr.add_argument("--layouts",
                    help="comma-separated layout names (overrides "
                         "[layouts].selected for this invocation)")
    pr.add_argument("--parallel-layouts", type=int, default=None,
                    dest="parallel_layouts",
                    help="override [layouts].parallel_layouts for this "
                         "invocation (>=1; auto-set by run_pipeline.sh "
                         "based on available RAM)")
    pr.set_defaults(func=cmd_run)

    pp = sub.add_parser("plan", help="print planned stages without running")
    _add_config_arg(pp)
    pp.add_argument("target", nargs="?", default="all")
    pp.add_argument("--only")
    pp.set_defaults(func=cmd_plan)

    pb = sub.add_parser("backup", help="ad-hoc manifest snapshot")
    _add_config_arg(pb)
    pb.add_argument("--label", default="", help="suffix on the snapshot filename")
    pb.set_defaults(func=cmd_backup)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
