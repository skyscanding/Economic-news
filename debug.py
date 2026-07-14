"""
Convenience runner for manual debugging.

Two ways to use it — CLI flags override the CONFIG defaults below:

    python debug.py                                  # use the defaults below
    python debug.py --sections Technology World      # only these sections
    python debug.py --vendors Reuters Bloomberg      # only these vendors
    python debug.py --key AIza... --model gemini-3-flash-preview
    python debug.py --no-open                        # write file, don't launch browser
    python debug.py --list                           # show available sources and exit

Precedence for the API key: --key wins, else the API_KEY below, else the
GEMINI_API_KEY environment variable / .env file; if none exist, ranking
degrades to keyword scoring (still produces a page).
"""
import argparse
import os
import sys

# Windows consoles default to cp1252 and choke on £, curly quotes, etc. in
# headlines. Force UTF-8 so printing the selected list never crashes.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# ============================= CONFIG — EDIT ME =============================
API_KEY = ""          # paste a Gemini key here, or "" to use .env / env var
MODEL = ""            # "" = default (gemini-3.5-flash). Alt: "gemini-3-flash-preview"

# Which sources to fetch. None = all. Names are case-insensitive.
VENDORS = None        # e.g. ["Reuters", "Bloomberg"]  |  None = every vendor
SECTIONS = None       # e.g. ["Technology", "World"]   |  None = every section

OPEN_BROWSER = True   # open the rendered HTML when finished
# ===========================================================================

from newsagent.feeds import ALL_FEEDS, SECTIONS as ALL_SECTIONS

ALL_VENDORS = sorted({f.vendor for f in ALL_FEEDS})


def _parse_args(argv=None):
    p = argparse.ArgumentParser(
        description="Debug runner for the news agent (flags override CONFIG).")
    p.add_argument("--key", default=None, metavar="GEMINI_KEY",
                   help="Gemini API key (overrides API_KEY / env / .env)")
    p.add_argument("--model", default=None, metavar="NAME",
                   help="ranking model, e.g. gemini-3-flash-preview")
    p.add_argument("--vendors", nargs="*", default=None, metavar="V",
                   help=f"subset of vendors {ALL_VENDORS}")
    p.add_argument("--sections", nargs="*", default=None, metavar="S",
                   help=f"subset of sections {list(ALL_SECTIONS)}")
    open_grp = p.add_mutually_exclusive_group()
    open_grp.add_argument("--open", dest="open", action="store_true", default=None,
                          help="open the rendered HTML (default)")
    open_grp.add_argument("--no-open", dest="open", action="store_false",
                          help="write the file but don't launch a browser")
    p.add_argument("--list", action="store_true",
                   help="list available vendors/sections and exit")
    return p.parse_args(argv)


def _resolve(name_list, valid, kind):
    """Case-insensitively validate a --vendors/--sections list; warn on unknowns."""
    if name_list is None:
        return None
    lut = {v.lower(): v for v in valid}
    out, bad = [], []
    for n in name_list:
        (out if n.lower() in lut else bad).append(lut.get(n.lower(), n))
    if bad:
        print(f"  ! unknown {kind}: {bad}  (valid: {list(valid)})", file=sys.stderr)
    return out or None


def main(argv=None) -> None:
    args = _parse_args(argv)

    if args.list:
        print("Vendors :", ALL_VENDORS)
        print("Sections:", list(ALL_SECTIONS))
        return

    # CLI flag > CONFIG constant for each setting.
    key = args.key or API_KEY
    model = args.model or MODEL
    vendors = _resolve(args.vendors if args.vendors is not None else VENDORS,
                       ALL_VENDORS, "vendor")
    sections = _resolve(args.sections if args.sections is not None else SECTIONS,
                        ALL_SECTIONS, "section")
    open_browser = OPEN_BROWSER if args.open is None else args.open

    # Apply key/model to the environment BEFORE Config reads them.
    if key:
        os.environ["GEMINI_API_KEY"] = key
    if model:
        os.environ["GEMINI_MODEL"] = model

    # Import after env is set so Config.load() sees the overrides.
    from newsagent.config import Config
    from newsagent.main import run

    cfg = Config.load()
    print("=" * 68)
    print("  NEWS AGENT - debug run")
    print("-" * 68)
    print(f"  Gemini key : {'set (' + cfg.gemini_api_key[:6] + '...)' if cfg.gemini_api_key else 'NOT set -> keyword fallback'}")
    print(f"  Model      : {cfg.gemini_model}")
    print(f"  Vendors    : {vendors or 'ALL ' + str(ALL_VENDORS)}")
    print(f"  Sections   : {sections or 'ALL ' + str(list(ALL_SECTIONS))}")
    print(f"  Open browser: {open_browser}")
    print("=" * 68)

    path = run(vendors=vendors, sections=sections, no_open=not open_browser)
    print(f"\n[done] wrote {path}")


if __name__ == "__main__":
    main()
