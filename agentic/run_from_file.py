"""CLI helper: python -m agentic.run_from_file <path_to_spec.json>"""
import json
import sys

from agentic.runner import AgenticRunner


def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: python -m agentic.run_from_file <path_to_spec.json>")
        sys.exit(1)

    with open(sys.argv[1], "r", encoding="utf-8") as f:
        spec = json.load(f)

    with AgenticRunner() as runner:
        result = runner.run(spec)
        print(json.dumps(result.model_dump(), indent=2))


if __name__ == "__main__":
    main()
