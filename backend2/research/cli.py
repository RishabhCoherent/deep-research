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
    query: Optional[str] = typer.Argument(None, help="Research query (required unless --resume)"),
    budget: float = typer.Option(3.0, "--budget", help="Budget limit in USD"),
    no_interactive: bool = typer.Option(False, "--no-interactive", help="Skip user interaction"),
    pick: Optional[int] = typer.Option(None, "--pick", help="Auto-pick Nth variant (1-based)"),
    out: Optional[str] = typer.Option("./out", "--out", help="Output directory for the Markdown brief"),
    resume: Optional[str] = typer.Option(None, "--resume",
        help="Resume a previously-saved run by its thread_id. The graph picks "
             "up from the last completed node (LangGraph SqliteSaver checkpoints "
             "after every node). Run `... runs` to see saved runs."),
):
    """Run the full A0 -> A8 pipeline and write a Markdown brief.

    Checkpointing: the graph saves state to backend2/.checkpoints.db after
    EVERY node completes. If a node crashes (or you Ctrl-C), re-run with
    `--resume <thread_id>` and the graph picks up from the last successful
    node — so an a5 failure doesn't waste a3 + a4's work.
    """

    async def run_pipeline():
        from pathlib import Path
        from research.graph.build import build_graph, open_async_checkpointer
        from research.report.markdown_renderer import render_to_file

        if resume:
            run_id = resume
            # When resuming, LangGraph reads state from the checkpoint DB; we
            # don't need to construct an initial_state. Pass `None` to ainvoke
            # so it picks up where the saved state left off.
            initial_state = None
            console.print(Panel(
                f"Resuming run thread_id={run_id[:8]}...",
                style="bold yellow",
            ))
        else:
            if not query:
                console.print("[bold red]Error:[/bold red] either provide a query or use --resume <thread_id>")
                raise typer.Exit(2)
            run_id = str(uuid.uuid4())
            initial_state = create_initial_state(run_id, query)
            console.print(Panel(
                f"Research Pipeline  thread_id={run_id}  budget=${budget:.2f}\n"
                f"(saved after every node; resume with --resume {run_id})",
                style="bold blue",
            ))

        configurable: dict = {"thread_id": run_id}
        if no_interactive and pick:
            configurable["auto_pick"] = pick
        config = {"configurable": configurable, "recursion_limit": 50}

        # Open the async SQLite checkpointer for the duration of the run.
        # AsyncSqliteSaver writes checkpoints after every node completes.
        async with open_async_checkpointer() as saver:
            graph = build_graph(checkpointer=saver)

            console.print("\n[cyan]> Running A0 -> A8 (may take several minutes)...[/cyan]")
            try:
                final_state = await graph.ainvoke(initial_state, config=config)
            except Exception as e:
                console.print(f"[bold red]Pipeline error:[/bold red] {e}")
                console.print(
                    f"[yellow]State has been checkpointed up to the last completed node. "
                    f"Resume with: --resume {run_id}[/yellow]"
                )
                raise typer.Exit(1)

        # Summary
        console.print("\n[bold green]✔ Pipeline complete[/bold green]")
        console.print(f"  intent:           {final_state.get('intent')}")
        console.print(f"  chosen query:     {final_state.get('chosen_query', '')[:80]}")
        console.print(f"  sub-questions:    {len(final_state.get('sub_questions', []))}")
        console.print(f"  topic claims:     {len(final_state.get('topic_claims', []))}")
        console.print(f"  market claims:    {len(final_state.get('market_claims', []))}")
        console.print(f"  news claims:      {len(final_state.get('news_claims', []))}")
        console.print(f"  validated claims: {len(final_state.get('validated_claims', []))}")
        console.print(f"  conflicts:        {len(final_state.get('conflicts', []))}")
        console.print(f"  causations:       {len(final_state.get('causations', []))}")

        # Write brief
        out_dir = Path(out or "./out")
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"brief_{run_id[:8]}.md"
        render_to_file(final_state, str(out_path))
        console.print(f"\n[bold]Brief written:[/bold] {out_path}")

    asyncio.run(run_pipeline())


@app.command(name="runs")
def list_runs_cmd(
    limit: int = typer.Option(20, "--limit", help="Max runs to list (most recent first)"),
):
    """List checkpointed runs with their latest reached node and topic.

    Use the printed thread_id with `run --resume <thread_id>` to pick up.
    """
    from research.graph.build import list_checkpointed_runs

    runs = list_checkpointed_runs(limit=limit)
    if not runs:
        console.print("[dim]No checkpointed runs found.[/dim]")
        return
    table = Table(title=f"Checkpointed runs (showing {len(runs)})", show_lines=False)
    table.add_column("thread_id", style="cyan", no_wrap=True)
    table.add_column("latest_node", style="yellow")
    table.add_column("topic", style="white")
    table.add_column("ts", style="dim")
    for r in runs:
        table.add_row(
            r["thread_id"][:12] + "...",
            r.get("latest_node", "?"),
            (r.get("topic") or "")[:60],
            (r.get("ts") or "")[:19],
        )
    console.print(table)


if __name__ == "__main__":
    app()
