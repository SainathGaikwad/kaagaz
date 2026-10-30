"""Command line.

    kaagaz read samples/register_en_clean.png            # real model (needs MODEL_API_KEY in .env)
    kaagaz read samples/*.jpg --as-of 2026-10-31 --out out/results.csv
    kaagaz read page.jpg --fake                           # samples' ground truth, no network
    kaagaz read page.jpg --replay                         # recorded answers only, no network, no key
    kaagaz order samples/court_order_sample.pdf           # replay a court order against the engine
    kaagaz check                                          # is the key there, does the API answer (lists models)

Every real call is recorded under kaagaz_cache/ (request text, image hashes, the answer). No key is ever written.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from .images import load_many
from .model import FakeModel, MuseSpark, ReplayCache, load_api_key
from .orders import replay_order
from .pipeline import run

SAMPLES = Path(__file__).resolve().parent.parent / "samples"
CACHE = Path("kaagaz_cache")


def make_model(args) -> object:
    if getattr(args, "fake", False):
        return FakeModel.from_samples(SAMPLES)
    cache = ReplayCache(args.cache) if args.cache else None
    return MuseSpark(model=args.model, cache=cache, replay_only=getattr(args, "replay", False))


def cmd_read(args) -> int:
    model = make_model(args)
    pages = load_many(args.pages)
    as_of = date.fromisoformat(args.as_of) if args.as_of else date.today()
    rep = run(model, pages, as_of=as_of, audit=not args.no_audit)
    for name, pr in rep.pages:
        print(f"page {name}: kind={pr.page_kind} lang={pr.language or '-'} rows={len(pr.rows)}"
              + (" (from cache)" if pr.from_cache else ""))
    print()
    w = max([len(r.identifier) for r in rep.results] + [10])
    print(f"{'identifier':{w}}  {'read':9}  {'status':24}  {'eligible':10}  notes")
    for r in rep.results:
        read = "accepted" if r.verdict.accepted else "CHECK"
        note = "; ".join(r.verdict.reasons) if not r.verdict.accepted else (r.reasons[0][:90] if r.reasons else "")
        print(f"{r.identifier:{w}}  {read:9}  {r.status:24}  {r.eligible_on or '-':10}  {note}")
    print()
    print("summary:", ", ".join(f"{k} {v}" for k, v in sorted(rep.counts().items())),
          f"| accepted {len(rep.accepted)} / {len(rep.results)} rows",
          f"| model calls {rep.usage.calls} (cached {rep.usage.cached}), tokens in {rep.usage.input_tokens} out {rep.usage.output_tokens}, {rep.usage.seconds:.1f}s")
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(rep.csv(), encoding="utf-8")
        out.with_suffix(".memos.txt").write_text(rep.memos(), encoding="utf-8")
        out.with_suffix(".read.json").write_text(json.dumps(
            [{"page": n, "page_kind": pr.page_kind, "rows": [r.to_dict() for r in pr.rows]} for n, pr in rep.pages],
            ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"wrote {out}, {out.with_suffix('.memos.txt')}, {out.with_suffix('.read.json')}")
    return 0


def cmd_order(args) -> int:
    model = make_model(args)
    pages = [b for _, b in load_many([args.order])]
    rep = replay_order(model, pages)
    print(f"court: {rep.court or '-'} | case: {rep.case_reference or '-'} | order date: {rep.order_date or '-'}")
    print(f"charges: {', '.join(c['act'] + ' ' + c['section'] for c in rep.charges) or '-'}")
    for ck in rep.checks:
        print(f"  {ck.act} {ck.section}: {ck.status} {ck.note}")
    print(f"custody from: {rep.custody_start or '-'} | first-time: {rep.first_time_offender} | other cases: {rep.other_cases_pending} | s.479 discussed: {rep.section_479_invoked}")
    print(f"court decided: {rep.decision}  \"{rep.decision_quote}\"")
    print(f"engine says:   {rep.engine_status}" + (f" (eligible from {rep.engine_eligible_on})" if rep.engine_eligible_on else ""))
    for r in rep.engine_reasons:
        print("  -", r)
    print(f"verdict: {rep.verdict} - {rep.verdict_note}")
    print(f"model calls {rep.usage.calls} (cached {rep.usage.cached}), tokens in {rep.usage.input_tokens} out {rep.usage.output_tokens}")
    if args.out:
        Path(args.out).write_text(json.dumps(rep.to_dict(), ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"wrote {args.out}")
    return 0


def cmd_check(args) -> int:
    import os
    key = load_api_key()
    if not key:
        print("no MODEL_API_KEY found: copy .env.example to .env and put the key there (never in chat).")
        return 1
    base_url = os.environ.get("KAAGAZ_BASE_URL", args.base_url)
    model = args.model or os.environ.get("KAAGAZ_MODEL", "muse-spark-1.3")
    print(f"key found ({len(key)} characters). Provider: {base_url}")
    from openai import OpenAI
    client = OpenAI(base_url=base_url, api_key=key, timeout=60)
    try:
        models = client.models.list()
        ids = sorted(m.id for m in models.data)
        print(f"model list: {len(ids)} models" + (": " + ", ".join(ids[:40]) if ids else ""))
        if ids:
            print(f"model '{model}':", "present" if model in ids else "NOT in the list (set KAAGAZ_MODEL to one above)")
    except Exception as e:
        print("note: could not list models (some providers don't expose it):", type(e).__name__, str(e)[:160])
    # The real readiness test: a one-token generation. models.list succeeds even when billing/credits are not set up,
    # so only an actual completion tells us the account can run. This is the call that returns 402 if billing is unresolved.
    print(f"probing a 1-token generation on '{model}' ...")
    try:
        r = client.chat.completions.create(model=model, messages=[{"role": "user", "content": "Reply with the single word: ok"}], max_tokens=5)
        print("READY - model replied:", repr((r.choices[0].message.content or "").strip()[:40]))
        return 0
    except Exception as e:
        print("NOT READY -", type(e).__name__, str(e)[:260])
        return 2


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="kaagaz", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", default=None, help="model id (default muse-spark-1.3 or KAAGAZ_MODEL)")
    ap.add_argument("--base-url", default="https://api.meta.ai/v1")
    ap.add_argument("--cache", default=str(CACHE), help="directory for recorded answers ('' to disable)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("read", help="read register pages and assess every row")
    r.add_argument("pages", nargs="+")
    r.add_argument("--as-of", default=None, help="assessment date YYYY-MM-DD (default today)")
    r.add_argument("--out", default=None, help="write results CSV (+ .memos.txt, .read.json) here")
    r.add_argument("--no-audit", action="store_true", help="skip the second (audit) read")
    r.add_argument("--fake", action="store_true", help="no network: answers from samples/*.truth.json")
    r.add_argument("--replay", action="store_true", help="no network: recorded answers only")
    r.set_defaults(func=cmd_read)

    o = sub.add_parser("order", help="replay a court order against the engine")
    o.add_argument("order")
    o.add_argument("--out", default=None)
    o.add_argument("--fake", action="store_true")
    o.add_argument("--replay", action="store_true")
    o.set_defaults(func=cmd_order)

    c = sub.add_parser("check", help="verify the key and the API connection")
    c.set_defaults(func=cmd_check)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
