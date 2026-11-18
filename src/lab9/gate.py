"""CI gate: compare a PR eval report with the main-branch baseline using the metric spec.

    python -m lab9.gate --pr reports/eval_workflow.json --baseline reports/baseline_v1.json

exit 0 = merge, exit 1 = blocked. Safety metrics: max 0, no averaging away.
Capability metrics: meet the floor AND the paired CI of (PR - main) is not entirely below 0.
Thresholds may only get stricter on the same eval-set version (ratchet).
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from lab8.console import utf8_stdio
from lab9 import stats
from lab9.eval import SPEC, load_spec, per_item
from lab9.graders import GRADERS


def integrity_check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> list[str]:
    """M7 (Expert): refuse to compare reports that cannot be trusted. Return a list of problems
    (empty = trustworthy). A gate that passes a broken report is worse than no gate.
    Must catch at least:
      - any metric value in pr["metrics"] that is NaN or inf
      - len(pr["rows"]) != manifest items x len(manifest seeds)   (dropped / duplicated rows)
      - the (item_id, seed) set of PR differs from the baseline's (cherry-picked seeds/items)
      - pr["evaluator_failures"] non-empty, or a row whose value for a graded spec metric is
        None (a crashed grader silently scores as "missing" and drops out of the mean)
      - base_spec given and a threshold in spec is LOOSER than in base_spec for the same
        eval-set version (ratchet: max may not rise, min may not fall, a blocking metric may
        not become non-blocking, a metric may not disappear; the same for spec["slices"],
        including dropping no_significant_drop)
      - an item's slice tags in PR rows differ from the baseline's (relabelling an item out of a
        slice hides its regression from the slice gate)"""
    graded = {m["id"] for m in spec["metrics"] if m["id"] in GRADERS}
    problems = []
    rows_by_report = []
    for name, report in (("PR", pr), ("baseline", base)):
        manifest = report["manifest"]
        rows = report["rows"]
        seeds = set(manifest["seeds"])
        keys = {(row["item_id"], row["seed"]) for row in rows}
        items = {item for item, _ in keys}
        if (len(seeds) != len(manifest["seeds"]) or len(items) != manifest["items"]
                or len(keys) != len(rows) or keys != {(item, seed) for item in items for seed in seeds}):
            problems.append(f"{name} has incomplete or duplicate item/seed rows")
        if report.get("evaluator_failures"):
            problems.append(f"{name} contains evaluator failures")
        for key, value in report["metrics"].items():
            if value is not None and (not isinstance(value, (int, float)) or not math.isfinite(value)):
                problems.append(f"{name} metric {key} is not finite")
        if any(report["metrics"].get(metric) is None for metric in graded):
            problems.append(f"{name} is missing a graded aggregate")
        if any(type(row.get(metric)) is not bool for row in rows for metric in graded):
            problems.append(f"{name} is missing a valid graded row value")
        rows_by_report.append({(r["item_id"], r["seed"]): set(r.get("slices") or []) for r in rows})
    current, previous = rows_by_report
    if current.keys() != previous.keys():
        problems.append("item/seed pairs differ from baseline")
    elif current != previous:
        problems.append("slice tags differ from baseline")
    if base_spec is not None and spec.get("eval_set_version") == base_spec.get("eval_set_version"):
        problems.extend(_ratchet(spec, base_spec))
    return problems


def _ratchet(spec: dict, base_spec: dict) -> list[str]:
    problems = []
    for group, identity in (("metrics", ("id",)), ("slices", ("name", "metric"))):
        entries = {tuple(entry[field] for field in identity): entry for entry in spec.get(group, [])}
        for original in base_spec.get(group, []):
            key = tuple(original[field] for field in identity)
            current = entries.get(key)
            before = original.get("threshold", {}) if group == "metrics" else original
            after = (current.get("threshold", {}) if group == "metrics" else current) if current else {}
            if (current is None or (original.get("blocking") and not current.get("blocking"))
                    or (before.get("no_significant_drop") and not after.get("no_significant_drop"))
                    or ("min" in before and ("min" not in after or after["min"] < before["min"]))
                    or any(limit in before and (limit not in after or after[limit] > before[limit])
                           for limit in ("max", "max_increase"))):
                problems.append(f"ratchet loosened {group} {'/'.join(key)}")
    return problems


def _paired(a: dict, b: dict, spec: dict) -> tuple[float, float, float]:
    keys = sorted(a.keys() & b.keys())
    config = spec.get("bootstrap", {})
    return stats.paired_bootstrap(
        [a[key] for key in keys], [b[key] for key in keys],
        n_resamples=config.get("n_resamples", 1000), rng=config.get("rng", 2027),
        confidence=config.get("confidence", 0.95),
    )


def slice_check(pr: dict, base: dict, spec: dict) -> tuple[list[str], list[str]]:
    """M5 (Advanced): an average can hide a regression on a small, important slice.
    For each entry of spec["slices"] ({"name", "metric", "min"?, "no_significant_drop"?, "blocking"}):
      - value = mean of per_item(pr, metric, slice_name=name)
      - fail if below "min", or if no_significant_drop and the paired CI over the slice's items
        lies entirely below 0
    Return (blocked ids like "slice:money_movement/pass_rate", report lines)."""
    blocked, lines = [], []
    for rule in spec.get("slices", []):
        name, metric = rule["name"], rule["metric"]
        identifier = f"slice:{name}/{metric}"
        current, previous = per_item(pr, metric, name), per_item(base, metric, name)
        value = sum(current.values()) / len(current) if current else None
        fail = value is None or ("min" in rule and value < rule["min"])
        note = ""
        if rule.get("no_significant_drop"):
            if not current or current.keys() != previous.keys():
                fail = True
            else:
                delta, low, high = _paired(current, previous, spec)
                note = f" ? {delta:+.3f} CI [{low:+.3f}, {high:+.3f}]"
                fail = fail or high < 0
        verdict = "ok"
        if fail:
            verdict = "BLOCK" if rule.get("blocking") else "warn"
            if rule.get("blocking"):
                blocked.append(identifier)
        lines.append(f"  {identifier} {value}{note} {verdict}")
    return blocked, lines


def check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> tuple[list[str], list[str]]:
    if pr["manifest"]["eval_set_sha"] != base["manifest"]["eval_set_sha"]:
        return ["eval_set_sha"], ["  EVAL SET differs from the baseline's: re-run the baseline on the same eval set"]
    problems = integrity_check(pr, base, spec, base_spec)
    if problems:
        return ["integrity"], [f"  INTEGRITY {p}" for p in problems]
    blocked, lines = [], []
    for m in spec["metrics"]:
        mid, th, val = m["id"], m.get("threshold", {}), pr["metrics"].get(m["id"])
        verdict, note = "ok", ""
        if val is None:
            verdict = "missing"
        elif "max" in th and val > th["max"]:
            verdict = "fail"
        elif "min" in th and val < th["min"]:
            verdict = "fail"
        elif "max_increase" in th and base["metrics"].get(mid):
            if val > base["metrics"][mid] * (1 + th["max_increase"]):
                verdict = "fail"
        if th.get("no_significant_drop") and val is not None:
            a, b = per_item(pr, mid), per_item(base, mid)
            if not a or a.keys() != b.keys():
                verdict = "missing"
            else:
                d, lo, hi = _paired(a, b, spec)
                note = f"? {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
                if hi < 0:
                    verdict = "fail"
        if verdict != "ok" and m.get("blocking"):
            blocked.append(mid)
        label = {"ok": "ok", "missing": "MISSING"}.get(verdict, "BLOCK" if m.get("blocking") else "warn")
        lines.append(f"  {mid:<22} {val!s:<8} {json.dumps(th):<40} {note:<28} {label}")
    if spec.get("slices"):
        sb, sl = slice_check(pr, base, spec)
        blocked += sb
        lines += sl
    return blocked, lines


def main(argv: list[str] | None = None) -> int:
    utf8_stdio()
    ap = argparse.ArgumentParser(prog="lab9.gate")
    ap.add_argument("--pr", required=True)
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--spec", default=str(SPEC))
    ap.add_argument("--base-spec", help="metric spec on main, for the ratchet check (M7)")
    args = ap.parse_args(argv)
    pr = json.loads(Path(args.pr).read_text(encoding="utf-8"))
    base = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
    base_spec = load_spec(Path(args.base_spec)) if args.base_spec else None
    blocked, lines = check(pr, base, load_spec(Path(args.spec)), base_spec)
    print(f"gate: PR {pr['run_id']} vs main {base['run_id']} Â· eval set {pr['manifest']['eval_set_sha']}")
    print("\n".join(lines))
    if blocked:
        print(f"exit 1 â€” blocked: {', '.join(blocked)}")
        return 1
    print("exit 0 â€” merge")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
