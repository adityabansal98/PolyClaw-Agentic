"""polyclaw init <name> — scaffolds a minimal working agent.

Usage:
    pip install polyclaw-agent-sdk
    polyclaw init my-agent
    cd my-agent
    python agent.py
"""

from __future__ import annotations

import argparse
import os
import sys

AGENT_TEMPLATE = '''"""My PolyClaw agent — scaffolded by `polyclaw init`."""

from polyclaw_sdk import PolyClawAgent


class {class_name}(PolyClawAgent):
    def decide(self):
        portfolio = self.client.get_portfolio()
        print(f"Cash: ${{portfolio.cash_balance:.2f}}, Equity: ${{portfolio.total_equity:.2f}}")

        # TODO: replace with your strategy logic
        # Example: buy 10 USDC of a token if cash > 100
        # if portfolio.cash_balance > 100:
        #     self.client.place_market_order(
        #         token_id="YOUR_TOKEN_ID",
        #         market_id="YOUR_MARKET_ID",
        #         side="BUY",
        #         usdc=10.0,
        #     )


if __name__ == "__main__":
    {class_name}(
        base_url="http://localhost:5000",
        token="YOUR_BEARER_TOKEN",
        interval_s=30.0,
    ).run()
'''

ENV_TEMPLATE = """POLYCLAW_BASE_URL=http://localhost:5000
POLYCLAW_BEARER_TOKEN=YOUR_BEARER_TOKEN
"""


def _to_class_name(name: str) -> str:
    return "".join(part.capitalize() for part in name.replace("-", "_").split("_")) + "Agent"


def cmd_init(args: argparse.Namespace) -> int:
    name = args.name
    directory = os.path.join(".", name)
    if os.path.exists(directory):
        print(f"Error: directory '{name}' already exists.", file=sys.stderr)
        return 1

    os.makedirs(directory)
    class_name = _to_class_name(name)

    with open(os.path.join(directory, "agent.py"), "w") as f:
        f.write(AGENT_TEMPLATE.format(class_name=class_name))
    with open(os.path.join(directory, ".env"), "w") as f:
        f.write(ENV_TEMPLATE)
    with open(os.path.join(directory, "requirements.txt"), "w") as f:
        f.write("polyclaw-agent-sdk>=0.1.0\n")

    print(f"Created {directory}/")
    print(f"  agent.py    — your agent ({class_name})")
    print(f"  .env        — config (set your bearer token)")
    print(f"  requirements.txt")
    print()
    print(f"Next steps:")
    print(f"  cd {name}")
    print(f"  pip install -r requirements.txt")
    print(f"  # Edit .env with your bearer token")
    print(f"  python agent.py")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="polyclaw", description="PolyClaw Agent SDK CLI")
    sub = parser.add_subparsers(dest="command")

    init_parser = sub.add_parser("init", help="Scaffold a new agent project")
    init_parser.add_argument("name", help="Agent project name (creates a directory)")

    args = parser.parse_args(argv)
    if args.command == "init":
        return cmd_init(args)

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
