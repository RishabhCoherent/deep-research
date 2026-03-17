"""
CLI entry point for the multi-layer research agent.

Usage:
    python run_research.py "Global Electric Vehicle Battery Market"
    python run_research.py "AI in Drug Discovery" --max-layer 2
    python run_research.py "Semiconductor Supply Chain" --output-dir results/
"""

import argparse
import asyncio
import logging
import sys
import os

# Force UTF-8 output on Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

from config import set_model_tier, get_model_tier, MODEL_TIERS
from research_agent import run_all_layers
from research_agent.cli import print_report, save_report


def main():
    parser = argparse.ArgumentParser(
        description="Multi-Layer Research Agent — Progressive market research analysis",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run_research.py "Global Electric Vehicle Battery Market"
  python run_research.py "AI in Drug Discovery" --max-layer 2
  python run_research.py "Semiconductor Supply Chain" --output-dir results/
  python run_research.py "mRNA Therapeutics Market" --verbose

Layers:
  0  Baseline     — Single LLM prompt, no research
  1  Research     — Web search + source gathering + synthesis
  2  Analysis     — Cross-reference + frameworks + gap-filling
  3  Expert       — Assumption challenging + contrarian views + expert synthesis
        """,
    )
    parser.add_argument("topic", help="Market research topic to analyze")
    parser.add_argument("--max-layer", type=int, default=3, choices=[0, 1, 2, 3],
                        help="Maximum layer to run (default: 3 = all layers)")
    parser.add_argument("--output-dir", default="outputs",
                        help="Directory to save output files (default: outputs/)")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Enable verbose logging")
    parser.add_argument("--no-save", action="store_true",
                        help="Don't save output files, only print to console")
    parser.add_argument("--model", default="standard",
                        choices=list(MODEL_TIERS.keys()),
                        help="Model tier: standard (gpt-4o), premium (gpt-4.1), "
                             "budget (gpt-4o-mini), reasoning (o4-mini)")

    args = parser.parse_args()

    # Set model tier
    set_model_tier(args.model)

    # Configure logging
    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)-5s | %(message)s",
        datefmt="%H:%M:%S",
    )
    # Suppress noisy libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)
    logging.getLogger("aiohttp").setLevel(logging.WARNING)

    # Progress callback for console
    def progress(layer, status, message):
        icons = {0: "[0]", 1: "[1]", 2: "[2]", 3: "[3]"}
        icon = icons.get(layer, "[*]")
        if status == "start":
            print(f"\n  {icon} Layer {layer}: {message}")
        elif status == "done":
            print(f"    > {message}")
        elif status == "complete":
            print(f"\n  [*] {message}")

    # Run
    tier_info = get_model_tier()
    print(f"\n  +------------------------------------------------------+")
    print(f"  |  Multi-Layer Research Agent                           |")
    print(f"  |  Topic: {args.topic[:45]:<45}  |")
    print(f"  |  Layers: 0 -> {args.max_layer}  |  Model: {tier_info:<23}  |")
    print(f"  +------------------------------------------------------+")

    report = asyncio.run(run_all_layers(
        topic=args.topic,
        max_layer=args.max_layer,
        progress_callback=progress,
    ))

    # Print full report
    print_report(report)

    # Save if requested
    if not args.no_save:
        json_path = save_report(report, args.output_dir)
        print(f"\n  Output saved to: {args.output_dir}/")
        print(f"  Comparison JSON: {json_path}")


if __name__ == "__main__":
    main()
