from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from ..config import load_linking
from ..linking.linker import EntityLinker
from ..models import to_iso8601
from ..runtime import RuntimePaths, display_path
from ..storage import JsonDocumentStore, JsonlItemStore


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Link related research items across sources")
    parser.add_argument("--config", type=Path, default=Path("config/linking.yaml"))
    parser.add_argument(
        "--config-schema", type=Path, default=Path("config/schemas/linking.schema.json")
    )
    parser.add_argument("--work-root", type=Path)
    parser.add_argument("--items", type=Path)
    parser.add_argument("--output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    paths = RuntimePaths.resolve(args.work_root)
    items_path = args.items or paths.items
    output_path = args.output or paths.entities / "links.json"
    config = load_linking(args.config, args.config_schema)
    items = JsonlItemStore(items_path).load_items()
    generated_at = to_iso8601(datetime.now(UTC))
    result = EntityLinker(config).link(items, generated_at=generated_at)
    JsonDocumentStore(output_path).save(result.to_dict())
    print(
        json.dumps(
            {
                "items": len(items),
                "links": len(result.edges),
                "entities": len(result.entities),
                "output": display_path(output_path),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
