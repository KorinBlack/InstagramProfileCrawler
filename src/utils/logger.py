"""
Logging module with rich formatting.
"""

from datetime import datetime
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich import print as rich_print


class Logger:
    """Rich-formatted logger for the application."""
    
    def __init__(self, name: str = "InstagramProfileCrawler"):
        self.console = Console()
        self.name = name
        self.level = "INFO"
    
    def info(self, message: str):
        """Log info message."""
        self._log("INFO", message)
    
    def success(self, message: str):
        """Log success message."""
        self._log("SUCCESS", message)
    
    def warning(self, message: str):
        """Log warning message."""
        self._log("WARNING", message)
    
    def error(self, message: str):
        """Log error message."""
        self._log("ERROR", message)
    
    def debug(self, message: str):
        """Log debug message."""
        self._log("DEBUG", message)
    
    def _log(self, level: str, message: str):
        """Internal log method."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        if level == "INFO":
            self.console.print(f"[cyan]{timestamp} [bold cyan]{self.name}[/] {message}")
        elif level == "SUCCESS":
            self.console.print(f"[green][✓] {timestamp} {message}")
        elif level == "WARNING":
            self.console.print(f"[yellow][⚠] {timestamp} {message}")
        elif level == "ERROR":
            self.console.print(f"[red][✗] {timestamp} {message}")
        elif level == "DEBUG":
            self.console.print(f"[magenta][?] {timestamp} {message}")
    
    def print_header(self, title: str, subtitle: str = ""):
        """Print a formatted header."""
        text = Text()
        text.append(title, style="bold cyan")
        if subtitle:
            text.append(f"\n{subtitle}", style="dim")
        
        self.console.print(Panel(text, title=f"[bold]🚀 {title}[/]", border_style="cyan"))
    
    def print_progress(self, current: int, total: int, message: str = ""):
        """Print progress indicator."""
        percentage = (current / total * 100) if total > 0 else 0
        bar = "█" * int(percentage / 2) + "░" * (50 - int(percentage / 2))
        
        self.console.print(
            f"\r[{bar}] {current}/{total} ({percentage:.1f}%) {message}",
            end=""
        )
    
    def print_table(self, data: list, title: str = ""):
        """Print data in a table."""
        if not data:
            return
        
        table = Table(show_header=True, header_style="bold cyan")
        
        if title:
            self.console.print(f"\n[bold cyan]{title}[/]")
        
        # Auto-detect columns
        if isinstance(data[0], dict):
            columns = data[0].keys()
            for col in columns:
                table.add_column(str(col), style="cyan")
            
            for row in data:
                table.add_row(*[str(row.get(col, '')) for col in columns])
        else:
            for item in data:
                table.add_row(str(item))
        
        self.console.print(table)
    
    def clear_screen(self):
        """Clear terminal screen."""
        self.console.clear()
    
    def print_stats(self, title: str, stats: dict):
        """Print statistics in a formatted way."""
        self.console.print(
            Panel(
                Text("\n".join([
                    f"[bold cyan]{title}[/]",
                    ""
                ] + [f"[dim]{k}: {v}[/]" for k, v in stats.items()]),
                title="📊 Statistics",
                border_style="green"
            )
        ))


def print_success(message: str):
    """Print success message."""
    rich_print(f"[green][✓] {message}")


def print_error(message: str):
    """Print error message."""
    rich_print(f"[red][✗] {message}")


def print_warning(message: str):
    """Print warning message."""
    rich_print(f"[yellow][⚠] {message}")


def print_info(message: str):
    """Print info message."""
    rich_print(f"[cyan]ℹ {message}")
