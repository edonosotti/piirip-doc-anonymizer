from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .handlers import HANDLERS
from .playbooks import load_playbook


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="piirip",
        description="Redact PII from documents (%s) using Presidio." % ", ".join(sorted(HANDLERS)),
    )
    p.add_argument("files", nargs="*", type=Path, help="documents to anonymize")
    p.add_argument("-p", "--playbook", default="default",
                   help="'default', 'all', or path to a YAML playbook listing Presidio entities")
    p.add_argument("-o", "--output-dir", type=Path,
                   help="write results here (default: next to input, as NAME.redacted.EXT)")
    p.add_argument("--in-place", action="store_true", help="overwrite the input files")
    p.add_argument("-l", "--language", default="en", help="document language (default: en)")
    p.add_argument("-m", "--model", default="en_core_web_lg", help="spaCy model (default: en_core_web_lg)")
    p.add_argument("-t", "--threshold", type=float, help="minimum confidence score (default: 0.35)")
    p.add_argument("--generic", action="store_true", help="replace with <REDACTED> instead of <ENTITY_TYPE>")
    p.add_argument("--pdf-style", choices=["box", "placeholder"], default="box",
                   help="PDF redaction style: black 'box' (default) or text 'placeholder' like <PERSON>")
    p.add_argument("--list-entities", action="store_true", help="list entities of the chosen playbook and exit")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.files and not args.list_entities:
        build_parser().error("no input files")
    try:
        playbook = load_playbook(args.playbook)
        from .engine import Redactor

        redactor = Redactor(playbook, args.language, args.model, args.threshold, label=not args.generic,
                            pdf_style=args.pdf_style)
    except Exception as e:  # noqa: BLE001
        print(f"error: {e}", file=sys.stderr)
        return 2

    if args.list_entities:
        print("\n".join(redactor.entities))
        return 0

    rc = 0
    for src in args.files:
        handler = HANDLERS.get(src.suffix.lower())
        if not src.is_file() or handler is None:
            reason = "not found" if not src.is_file() else f"unsupported format '{src.suffix}'"
            print(f"skip {src}: {reason}", file=sys.stderr)
            rc = 1
            continue
        if args.in_place:
            dst = src.with_name(f"{src.stem}.tmp{src.suffix}")
            final = src
        else:
            out_dir = args.output_dir or src.parent
            out_dir.mkdir(parents=True, exist_ok=True)
            dst = final = out_dir / f"{src.stem}.redacted{src.suffix}"
        before = redactor.count
        try:
            handler(src, dst, redactor)
            if dst != final:
                dst.replace(final)
        except Exception as e:  # noqa: BLE001
            print(f"fail {src}: {e}", file=sys.stderr)
            dst.unlink(missing_ok=True)
            rc = 1
            continue
        print(f"{src} -> {final} ({redactor.count - before} redactions)")
    return rc


if __name__ == "__main__":
    sys.exit(main())
