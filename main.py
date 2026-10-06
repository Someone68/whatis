import time

import requests
import typer
from rich import box, print
from rich.console import Console
from rich.padding import Padding
from rich.panel import Panel

app = typer.Typer()
console = Console()


class Result:
    def __init__(self, key: str, title: str, excerpt: str) -> None:
        self.key = key
        self.title = title
        self.excerpt = excerpt


@app.command()
def search(query: str) -> None:
    with console.status("Loading", spinner="dots"):
        time.sleep(0.5)
    print(
        Padding(
            f"[bold cyan]5[/bold cyan] results for [bold green]{query}[/bold green]", 1
        )
    )
    print(
        Panel.fit(
            "[bold blue]Result 1[/bold blue]\nExcerpt 1 (this is some kinda long text that will take up some space)",
            box=box.HORIZONTALS,
        )
    )


if __name__ == "__main__":
    app()
