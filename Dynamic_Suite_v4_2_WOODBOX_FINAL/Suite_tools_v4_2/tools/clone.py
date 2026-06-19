#!/usr/bin/env python3
"""
Dynamic Suite - Cloning tool (v4.2)

Supports two modes:

A) Prefix mode (conservative literal replace):
  python tools/clone.py --src-prefix ds_w1_ --dst-prefixes ds_w2_,ds_w3_ --in-dir ./DS --out-dir ./DS_out --match ds_w1_

B) Module mode (recommended, user-friendly):
  # DS: clone w1 -> w2..w8
  python tools/clone.py --module ds --from 1 --to 2-8 --in-dir ./DS --out-dir ./DS_out

  # DC: clone zone01 -> zone02..04
  python tools/clone.py --module dc --from 1 --to 2-4 --in-dir ./DC --out-dir ./DC_out

  # DV: clone vmc -> vmc02 (optional / future multi-VMC)
  python tools/clone.py --module dv --from 1 --to 2 --in-dir ./DV --out-dir ./DV_out

Design goals:
- Conservative replacements (prefix mode replaces only the exact prefix).
- Module mode maps numbers to canonical prefixes:
    dc_zone01_ / dc_zone02_
    ds_w1_ / ds_w2_
    dv_vmc_ / dv_vmc02_
- No changes to common files unless they match the prefix token.
- Produces a JSON report of files created and replacements applied.

Notes:
- This tool only clones YAML/text files so you can include them as packages.
- To migrate user configuration values, use the module backup/restore scripts.
"""
import argparse
import re
import json
from pathlib import Path

TEXT_EXTS = {".yaml", ".yml", ".md", ".txt"}

def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="strict")

def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")

def parse_to_spec(s: str):
    """
    Parse --to like:
      "2" -> [2]
      "2,3,5" -> [2,3,5]
      "2-8" -> [2..8]
      "2-4,7,9-10" -> [...]
    """
    s = s.strip()
    if not s:
        return []
    out = []
    parts = [p.strip() for p in s.split(",") if p.strip()]
    for p in parts:
        m = re.match(r"^(\d+)\s*-\s*(\d+)$", p)
        if m:
            a = int(m.group(1)); b = int(m.group(2))
            if b < a:
                raise ValueError(f"Invalid range '{p}' (end < start)")
            out.extend(list(range(a, b+1)))
        else:
            if not re.match(r"^\d+$", p):
                raise ValueError(f"Invalid --to token '{p}'")
            out.append(int(p))
    # unique, preserve order
    seen=set()
    uniq=[]
    for n in out:
        if n not in seen:
            seen.add(n); uniq.append(n)
    return uniq

def module_prefix(module: str, n_from: int, n_to: int):
    module = module.lower()
    if module == "dc":
        # zone01..zone08 etc
        return f"dc_zone{n_from:02d}_", f"dc_zone{n_to:02d}_", f"dc_zone{n_from:02d}_"
    if module == "ds":
        return f"ds_w{n_from}_", f"ds_w{n_to}_", f"ds_w{n_from}_"
    if module == "dv":
        # current canonical is dv_vmc_ for first, then dv_vmc02_ ...
        src = "dv_vmc_" if n_from == 1 else f"dv_vmc{n_from:02d}_"
        dst = "dv_vmc_" if n_to == 1 else f"dv_vmc{n_to:02d}_"
        return src, dst, src
    raise ValueError("module must be one of: dc, ds, dv")

def clone_once(src_prefix: str, dst_prefix: str, in_dir: Path, out_dir: Path, match: str, dry_run: bool):
    created = []
    skipped = []
    replacements_total = 0

    for p in in_dir.rglob("*"):
        if p.is_dir():
            continue
        rel = p.relative_to(in_dir)

        # Only clone matching files (relative path contains match token) if provided
        if match and (match not in str(rel)):
            continue

        # Only clone text-like files
        if p.suffix.lower() not in TEXT_EXTS:
            continue

        out_rel_str = str(rel).replace(src_prefix, dst_prefix)
        out_rel = Path(out_rel_str)
        out_path = out_dir / out_rel

        txt = read_text(p)
        new_txt = txt.replace(src_prefix, dst_prefix)

        # If nothing changed and filename didn't change, skip
        if new_txt == txt and out_path == (out_dir / rel):
            skipped.append(str(rel))
            continue

        if not dry_run:
            write_text(out_path, new_txt)

        replacements_total += txt.count(src_prefix)
        created.append({"src": str(rel), "dst": str(out_rel)})

    return created, skipped, replacements_total

def main():
    ap = argparse.ArgumentParser()
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--module", choices=["dc","ds","dv"], help="Module mode (recommended)")
    mode.add_argument("--src-prefix", help="Prefix mode: prefix to replace, e.g., dc_zone01_ or ds_w1_")

    ap.add_argument("--from", dest="n_from", type=int, default=1, help="Module mode: source index (dc zone, ds window, dv vmc). Default 1.")
    ap.add_argument("--to", dest="n_to", default="", help="Module mode: destination spec, e.g., 2-8 or 2,3,4")
    ap.add_argument("--dst-prefixes", help="Prefix mode: comma-separated destination prefixes")

    ap.add_argument("--in-dir", required=True, help="Input directory (extracted module)")
    ap.add_argument("--out-dir", required=False, default="", help="Output directory (default: <in-dir>_out)")
    ap.add_argument("--per-dst-subdir", action="store_true", help="If set, create one subfolder per destination prefix inside out-dir")
    ap.add_argument("--match", default="", help="Only clone files whose relative path contains this token (recommended)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    in_dir = Path(args.in_dir).resolve()
    if args.out_dir:
        out_dir = Path(args.out_dir).resolve()
    else:
        out_dir = in_dir.parent / (in_dir.name + "_out")
    out_dir.mkdir(parents=True, exist_ok=True)

    report = {
        "mode": "module" if args.module else "prefix",
        "module": args.module or "",
        "src_prefix": "",
        "dst_prefixes": [],
        "in_dir": str(in_dir),
        "out_dir": str(out_dir),
        "match": args.match,
        "dry_run": args.dry_run,
        "runs": [],
    }

    if args.module:
        if not args.n_to:
            raise SystemExit("--to is required in module mode (e.g., 2-8)")
        dst_nums = parse_to_spec(args.n_to)
        if not dst_nums:
            raise SystemExit("No destination numbers parsed from --to")
        # Determine src prefix from module/from
        for n in dst_nums:
            src_prefix, dst_prefix, default_match = module_prefix(args.module, args.n_from, n)
            match = args.match or default_match
            run_out_dir = (out_dir / dst_prefix.rstrip("_")) if args.per_dst_subdir else out_dir
            run_out_dir.mkdir(parents=True, exist_ok=True)
            created, skipped, repl = clone_once(src_prefix, dst_prefix, in_dir, run_out_dir, match, args.dry_run)
            report["src_prefix"] = src_prefix
            report["dst_prefixes"].append(dst_prefix)
            report["runs"].append({
                "dst_prefix": dst_prefix,
                "created_count": len(created),
                "skipped_count": len(skipped),
                "replacements_total": repl,
                "created": created[:200],
                "skipped": skipped[:200],
            })
    else:
        if not args.src_prefix:
            raise SystemExit("--src-prefix is required in prefix mode")
        if not args.dst_prefixes:
            raise SystemExit("--dst-prefixes is required in prefix mode")
        dst_prefixes = [x.strip() for x in args.dst_prefixes.split(",") if x.strip()]
        if not dst_prefixes:
            raise SystemExit("No dst prefixes provided")
        report["src_prefix"] = args.src_prefix
        report["dst_prefixes"] = dst_prefixes

        for dst in dst_prefixes:
            run_out_dir = (out_dir / dst.rstrip("_")) if args.per_dst_subdir else out_dir
            run_out_dir.mkdir(parents=True, exist_ok=True)
            created, skipped, repl = clone_once(args.src_prefix, dst, in_dir, run_out_dir, args.match, args.dry_run)
            report["runs"].append({
                "dst_prefix": dst,
                "created_count": len(created),
                "skipped_count": len(skipped),
                "replacements_total": repl,
                "created": created[:200],
                "skipped": skipped[:200],
            })

    report_path = out_dir / "clone_report.json"
    if not args.dry_run:
        report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    main()
