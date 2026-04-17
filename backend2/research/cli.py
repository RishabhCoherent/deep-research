"""Command-line interface for the research system."""

import typer
import asyncio
import uuid
from typing import Optional
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from research.core.state import create_initial_state
from research.graph.nodes import a1_node, a2_node
from research.core.types import RunState, IntentKind, SubQuestion, QuestionCategory

app = typer.Typer(help="Multi-Agent Senior Analyst Research System")
console = Console()


@app.command()
def debug_a1(
    query: str,
    no_interactive: bool = typer.Option(False, "--no-interactive", help="Skip user interaction"),
    pick: Optional[int] = typer.Option(None, "--pick", help="Auto-pick Nth variant (1-based)")
):
    """Debug Agent 1 - Query Refiner node."""
    
    async def run_debug():
        # Create initial state
        run_id = str(uuid.uuid4())
        state = create_initial_state(run_id, query)
        
        # Configure node
        config = {}
        if no_interactive and pick:
            config["configurable"] = {"auto_pick": pick}
        
        console.print(Panel(f"Debug Agent 1: {query}", style="bold blue"))
        
        try:
            # Run the node
            result = await a1_node(state, config=config)
            
            # Display results
            console.print("\n[bold green]Agent 1 Results:[/bold green]")
            console.print(f"Intent: {result['intent']}")
            console.print(f"Chosen Query: {result['chosen_query']}")
            
            console.print("\n[bold]All Variants (sorted by score):[/bold]")
            for i, variant in enumerate(result['query_variants'], 1):
                console.print(f"\n{i}. {variant.variant.text}")
                console.print(f"   Angle: {variant.variant.angle}")
                console.print(f"   Score: {variant.composite:.1f}")
                console.print(f"   Reason: {variant.reason}")
            
        except Exception as e:
            console.print(f"[bold red]Error:[/bold red] {e}")
            raise typer.Exit(1)
    
    asyncio.run(run_debug())


@app.command(name="debug-a2")
def debug_a2(
    query: str,
    intent: str = typer.Option("market_sizing", "--intent", help="IntentKind value"),
    original_query: Optional[str] = typer.Option(None, "--original-query", help="Original raw query"),
):
    """Debug Agent 2 - Question Generator node standalone."""

    async def run_debug():
        from research.crews.a2_question_generator.crew import run_a2
        intent_kind = IntentKind(intent)
        raw = original_query or query

        console.print(Panel(f"Debug Agent 2 — intent={intent_kind}", style="bold blue"))
        console.print(f"[dim]Chosen query:[/dim] {query}\n")

        try:
            result = await run_a2(
                chosen_query=query,
                intent=intent_kind,
                original_query=raw,
            )

            table = Table(title=f"Sub-Questions ({len(result.questions)} total)",
                          show_lines=True)
            table.add_column("#", style="cyan", width=3)
            table.add_column("Score", style="yellow", width=6)
            table.add_column("Cat", style="magenta", width=12)
            table.add_column("Src", style="dim", width=10)
            table.add_column("Question", style="white")

            for i, sq in enumerate(result.questions, 1):
                table.add_row(
                    str(i),
                    f"{sq.composite:.2f}",
                    sq.category.value,
                    sq.source,
                    sq.text,
                )
            console.print(table)

        except Exception as e:
            console.print(f"[bold red]Error:[/bold red] {e}")
            raise typer.Exit(1)

    asyncio.run(run_debug())


@app.command(name="debug-a3")
def debug_a3(
    query: str,
    intent: str = typer.Option("market_sizing", "--intent"),
    sub_questions: Optional[str] = typer.Option(
        None, "--sub-questions",
        help="Comma-separated list of sub-question texts (max 8). Uses a default set if omitted."
    ),
):
    """Debug Agent 3 - Topic Researcher node standalone (requires ANTHROPIC + TAVILY keys)."""

    async def run_debug():
        from research.crews.a3_topic_researcher.crew import run_a3
        from research.core.types import SubQuestion, QuestionCategory

        intent_kind = IntentKind(intent)

        if sub_questions:
            sq_list = []
            for i, sq_text in enumerate(sub_questions.split(",")[:8], 1):
                comp = round(0.6 * 8.0 + 0.4 * 7.0, 2)
                sq_list.append(SubQuestion(
                    text=sq_text.strip(), category=QuestionCategory.SIZE,
                    source="cli", info_value=8.0, answerability=7.0,
                    composite=comp, reason="CLI-provided question."
                ))
        else:
            comp = round(0.6 * 8.0 + 0.4 * 7.0, 2)
            sq_list = [
                SubQuestion(text=f"What is the 2026 global market size for: {query}?",
                            category=QuestionCategory.SIZE, source="cli",
                            info_value=8.0, answerability=7.0, composite=comp,
                            reason="Default sizing question."),
            ]

        console.print(Panel(f"Debug Agent 3 — intent={intent_kind}", style="bold blue"))
        console.print(f"[dim]Query:[/dim] {query}")
        console.print(f"[dim]Sub-questions:[/dim] {len(sq_list)}\n")

        try:
            result = await run_a3(
                chosen_query=query,
                intent=intent_kind,
                sub_questions=sq_list,
            )
            console.print(f"\n[bold green]✔ Agent 3 done[/bold green]")
            console.print(f"  Claims: {len(result.claims)}")
            console.print(f"  Narrative: {len(result.narrative.split())} words")
            console.print(f"  Scratchpad obs: {len(result.scratchpad_writes)}")
            console.print(f"\n[bold]Narrative:[/bold]\n{result.narrative[:800]}…")
        except Exception as e:
            console.print(f"[bold red]Error:[/bold red] {e}")
            raise typer.Exit(1)

    asyncio.run(run_debug())


@app.command()
def run(
    query: str,
    budget: float = typer.Option(3.0, "--budget", help="Budget limit in USD"),
    no_interactive: bool = typer.Option(False, "--no-interactive", help="Skip user interaction"),
    pick: Optional[int] = typer.Option(None, "--pick", help="Auto-pick Nth variant (1-based)"),
    use_opus: bool = typer.Option(False, "--use-opus", help="Use Opus model for deep reasoning"),
    debate: bool = typer.Option(False, "--debate", help="Enable AutoGen validator debate"),
    out: Optional[str] = typer.Option("./out", "--out", help="Output directory"),
    format: str = typer.Option("md", "--format", help="Output format: md, json")
):
    """Run A1 → A2 pipeline (Agents 3-8 stubbed)."""

    async def run_pipeline():
        run_id = str(uuid.uuid4())
        state = create_initial_state(run_id, query)

        config: dict = {}
        if no_interactive and pick:
            config["configurable"] = {"auto_pick": pick}

        console.print(Panel(f"Research Pipeline  run_id={run_id[:8]}…  budget=${budget:.2f}",
                            style="bold blue"))

        # A1 — Query Refiner
        console.print("\n[cyan]▶ A1 refiner…[/cyan]")
        a1_patch = await a1_node(state, config=config)
        state.update(a1_patch)
        console.print(f"[green]✔ A1[/green]  intent={state['intent']}  "
                      f"chosen={state['chosen_query'][:60]}…")

        # A2 — Question Generator
        console.print("\n[cyan]▶ A2 questions…[/cyan]")
        a2_patch = await a2_node(state)
        state.update(a2_patch)
        console.print(f"[green]✔ A2[/green]  {len(state['sub_questions'])} sub-questions generated")

        console.print("\n[dim]Agents 3–8 not yet implemented.[/dim]")
        console.print("\n[bold]Sub-questions:[/bold]")
        for i, sq in enumerate(state["sub_questions"], 1):
            console.print(f"  {i:2}. [{sq.composite:.2f}] {sq.text}")

    asyncio.run(run_pipeline())


if __name__ == "__main__":
    app()
