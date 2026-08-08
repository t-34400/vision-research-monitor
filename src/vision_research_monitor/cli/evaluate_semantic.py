from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml

from ..classification.evaluation import evaluate
from ..config import load_academic, load_semantic, load_taxonomy, load_venues

ROOT = Path(__file__).resolve().parents[3]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Evaluate semantic classification against the lexical baseline"
    )
    parser.add_argument("--cases", type=Path, default=ROOT / "evaluation/semantic_cases.yaml")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    taxonomy = load_taxonomy(
        ROOT / "config/taxonomy.yaml", ROOT / "config/schemas/taxonomy.schema.json"
    )
    venues = load_venues(ROOT / "config/venues.yaml", ROOT / "config/schemas/venues.schema.json")
    academic = load_academic(
        ROOT / "config/academic.yaml",
        ROOT / "config/schemas/academic.schema.json",
        {venue["id"] for venue in venues["venues"]},
    )
    semantic = load_semantic(
        ROOT / "config/semantic.yaml",
        ROOT / "config/schemas/semantic.schema.json",
        {topic["id"] for topic in taxonomy["topics"]},
    )
    payload = yaml.safe_load(args.cases.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("cases"), list):
        raise SystemExit("Evaluation file must contain a cases list")
    result = evaluate(payload["cases"], taxonomy, academic, semantic)
    print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
