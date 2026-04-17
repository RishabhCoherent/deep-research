"""Tool for interactive user selection with Rich prompts."""

from typing import List, Optional
import asyncio
from rich.console import Console
from rich.prompt import Prompt
from rich.panel import Panel
from rich.table import Table


class AskUserTool:
    """Interactive user selection tool using Rich."""
    
    def __init__(self):
        self.console = Console()
    
    def ask_sync(
        self, 
        question: str, 
        options: List[str], 
        hints: Optional[List[str]] = None
    ) -> str:
        """Ask user to select from options synchronously."""
        self.console.print(Panel(question, style="bold blue"))
        
        # Create table for options
        table = Table(show_header=False, box=None)
        table.add_column("No.", style="cyan", width=3)
        table.add_column("Option", style="white")
        if hints:
            table.add_column("Score", style="yellow", width=20)
        
        for i, option in enumerate(options, 1):
            row = [str(i), option]
            if hints and i <= len(hints):
                row.append(hints[i-1])
            table.add_row(*row)
        
        self.console.print(table)
        
        # Get user input
        while True:
            try:
                choice = Prompt.ask(
                    "Select option [1-4]",
                    default="1",
                    show_choices=False,
                    console=self.console
                )
                choice_num = int(choice)
                if 1 <= choice_num <= len(options):
                    return options[choice_num - 1]
                else:
                    self.console.print(f"[red]Please enter a number between 1 and {len(options)}[/red]")
            except ValueError:
                self.console.print("[red]Please enter a valid number[/red]")
    
    async def ask_async(
        self, 
        question: str, 
        options: List[str], 
        hints: Optional[List[str]] = None
    ) -> str:
        """Ask user to select from options asynchronously."""
        # For now, just call sync version
        # In a real async context, you might want to use a different approach
        return self.ask_sync(question, options, hints)


# Global instance
ask_user = AskUserTool()
