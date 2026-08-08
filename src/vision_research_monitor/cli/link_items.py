from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from ..config import load_linking
from ..linking.linker import EntityLinker
from ..models import to_iso8601
from ..storage import JsonDocumentStore, JsonlItemStore


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Link related research items across sources")
    parser.add_argument("--config", type=Path, default=Path("config/linking.yaml"))
    parser.add_argument("--config-schema", type=Path, default=Path("config/schemas/linking.schema.json"))
    parser.add_argument("--items", type=Path, default=Path("data/items"))
    parser.add_argument("--output", type=Path, default=Path("data/entities/links.json"))
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = load_linking(args.config, args.config_schema)
    items = JsonlItemStore(args.items).load_items()
    generated_at = to_iso8601(datetime.now(timezone.utc))
    result = EntityLinker(config).link(items, generated_at=generated_at)
    JsonDocumentStore(args.output).save(result.to_dict())
    print(
        json.dumps(
            {
                "items": len(items),
                "links": len(result.edges),
                "entities": len(result.entities),
                "output": str(args.output),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
