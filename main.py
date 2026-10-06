import re
from typing import Annotated

import requests
import typer
import typer.rich_utils as ru
from bs4 import BeautifulSoup
from rich import box, print
from rich.console import Console
from rich.padding import Padding
from rich.table import Table

app = typer.Typer()
console = Console()

WIKIPEDIA_API = "https://en.wikipedia.org/w/rest.php/v1/"
USER_AGENT = "whatis wiki search/0.1 (https://github.com/Someone68/whatis)"
PANEL_WIDTH = min(Console().width, 120)
ru.MAX_WIDTH = PANEL_WIDTH

# ts some bs i found online and tweaked :sob:
SENTENCE_END = re.compile(
    r"(?<!\b[A-Z])(?<!\be\.g)(?<!\bi\.e)(?<!\bc)(?<!\bSt)(?<!\bDr)(?<!\bMr)(?<!\bMrs)(?<!\bvs)"
    r"[.!?][\"')\]]*(?=\s+[A-Z0-9\"'(])"
)


class Result:
    def __init__(self, title: str, description: str) -> None:
        self.title = title
        self.description = description


def get_first_sentence(html: str):
    soup = BeautifulSoup(html, "html.parser")
    lead = soup.find("section", attrs={"data-mw-section-id": "0"}) or soup
    for p in lead.find_all("p"):
        if p.find_parent(["table", "figure"]):
            continue
        for tag in p.select(
            "sup.reference, style, .mw-empty-elt, [style*='display:none']"
        ):
            tag.decompose()
        text = re.sub(r"\s+", " ", p.get_text()).strip()
        if text:
            m = SENTENCE_END.search(text)
            return text[: m.end()] if m else text
    return ""


@app.command()
def search(
    query: Annotated[list[str], typer.Argument(..., help="Search query.")],
    num_results: Annotated[
        int, typer.Option("--num-results", "-n", help="The number of results to show.")
    ] = 3,
    bottom_up: Annotated[
        bool,
        typer.Option(
            "--bottom-up/--top-up",
            "-b",
            help="Whether the most relevant result should be at the bottom.",
        ),
    ] = True,
    quick: Annotated[
        bool,
        typer.Option(
            "--quick/--no-quick",
            "-q/-w",
            help="Whether to use a shorter description for results that are not the most relevant. Speeds up search time by around half a second.",
        ),
    ] = True,
) -> None:
    q = " ".join(query)
    with console.status("Loading", spinner="dots"):
        results = [
            # Result(
            #     "Result 1",
            #     "Description 1 (this is some kinda long text that will take up some space and some more and im just adding more text here so i can see if it overflows)",
            # ),
            # Result(
            #     "Result 2",
            #     "Description 2 (this is some kinda long text that will take up some space and some more and im just adding more text here so i can see if it overflows)",
            # ),
        ]
        res = requests.get(
            WIKIPEDIA_API + "search/page",
            headers={"User-Agent": USER_AGENT},
            params={
                "q": f'{q} -incategory:"All_disambiguation_pages"',
                "limit": num_results,
            },
        )
        data = res.json()

        for idx, page in enumerate(data["pages"]):
            if quick and idx == 0 or not quick:
                res_content = requests.get(
                    WIKIPEDIA_API + f"page/{page['title']}/html",
                    headers={"User-Agent": USER_AGENT},
                )
                first_sentence = get_first_sentence(str(res_content.text))
                results.append(Result(page["title"], first_sentence))
                continue
            results.append(
                Result(
                    page["title"],
                    page["description"]
                    if page["description"]
                    else "[red]No short description found.[/red]",
                )
            )
    print(
        Padding(
            f"Showing [bold cyan]{min(num_results, len(results))}[/bold cyan] results for [bold green]{q}[/bold green]",
            1,
        )
    )

    table = Table(
        box=box.HORIZONTALS, show_header=False, show_lines=True, width=PANEL_WIDTH
    )

    table.add_column()
    for idx, result in enumerate(reversed(results) if bottom_up else results):
        table.add_row(
            f"[bold yellow]{result.title}[/bold yellow]"
            + (
                " [dim](top result)[/dim]"
                if idx == (len(results) - 1 if bottom_up else 0)
                else ""
            )
            + f"\n{result.description}",
        )
    print(table)


if __name__ == "__main__":
    app()
