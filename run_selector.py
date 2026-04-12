from __future__ import annotations

import argparse
import json

from polyclaw.pipeline import SelectionPipeline


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="PolyClaw: Polymarket bet selection framework (top 5 picks per category)."
    )
    parser.add_argument(
        "--input",
        type=str,
        default="data/sample_markets.json",
        help="Path to JSON markets payload.",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="data/selection_output.json",
        help="Path to write selection output JSON.",
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Print output JSON to stdout.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()

    pipeline = SelectionPipeline()
    results = pipeline.run_from_file(args.input)
    pipeline.write_output(args.output, results)

    if args.pretty:
        print(json.dumps(pipeline.to_output_dict(results), indent=2))


if __name__ == "__main__":
    main()
