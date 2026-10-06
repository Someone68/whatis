import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Annotated
from urllib.parse import quote

import requests
import typer
import typer.rich_utils as ru
from bs4 import BeautifulSoup
from markdownify import markdownify as md
from rich import box, print
from rich.console import Console
from rich.markdown import Markdown
from rich.padding import Padding
from rich.table import Table

app = typer.Typer()
console = Console()

HISTORY_FILE = Path(typer.get_app_dir("what")) / "history.json"
HISTORY_LIMIT = 10
WIKIPEDIA_API = "https://en.wikipedia.org/w/rest.php/v1/"
USER_AGENT = "whatis wiki search/0.1 (https://github.com/Someone68/whatis)"
PANEL_WIDTH = min(Console().width, 120)
ru.MAX_WIDTH = PANEL_WIDTH

# stuff that doesnt need to be shown when viewing
SKIP_SECTIONS = {
    "See_also",
    "References",
    "Notes",
    "Citations",
    "Sources",
    "Bibliography",
    "Further_reading",
    "External_links",
    "Gallery",
}

# stuff that messes up article viewing
JUNK = [
    "style",
    "link",
    "meta",
    "script",
    "sup.mw-ref",
    "img",
    ".hatnote",
    ".shortdescription",
    ".mw-empty-elt",
    ".navbox",
    ".noprint",
    ".mw-references-wrap",
    ".gallery",
    ".infobox",
    ".sidebar",
    ".side-box",
    ".ambox",
    "span.Z3988",
]

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


def load_history() -> list[dict]:
    try:
        data = json.loads(HISTORY_FILE.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return []
    return [e for e in data if "query" in e]


def add_history(query: str, results: list[Result]) -> None:
    entries = [e for e in load_history() if e["query"] != query]
    entries.insert(
        0,
        {
            "query": query,
            "results": [
                {"title": r.title, "description": r.description} for r in results
            ],
        },
    )
    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    HISTORY_FILE.write_text(json.dumps(entries[:HISTORY_LIMIT], indent=2))


@app.command("is", help="Search Wikipedia and get a summary.")
def search(
    ctx: typer.Context,
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
    app_name = ctx.find_root().info_name
    q = " ".join(query)
    with console.status("Searching", spinner="dots"):
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
    add_history(q, results)
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
            f"[blue]{len(results) - idx if bottom_up else idx + 1}. [/blue][bold yellow]{result.title}[/bold yellow]"
            + (
                " [dim](top result)[/dim]"
                if idx == (len(results) - 1 if bottom_up else 0)
                else ""
            )
            + f"\n{result.description}",
        )
    print(table)
    print(
        Padding(
            f"[dim]Run [bold cyan]{app_name} show <number>[/bold cyan] to read an article.[/dim]",
            (0, 1),
        )
    )


def extract_content(html, keep_figures=True, strip_attrs=True):
    soup = BeautifulSoup(html, "html.parser")  # or "html.parser"
    body = soup.body

    if body is None:
        return
    # drop unwanted sections (subsections go with them)
    sections = [
        h.find_parent("section")
        for h in body.find_all("h2")
        if h.get("id") in SKIP_SECTIONS
    ]
    for s in sections:
        if s is None:
            continue
        s.decompose()

    for sel in JUNK:
        for el in body.select(sel):
            el.decompose()

    if not keep_figures:
        for el in body.select("figure"):
            el.decompose()

    if strip_attrs:  # remove Parsoid noise attributes
        for tag in body.find_all(True):
            for a in ("id", "about", "typeof", "data-mw", "rel"):
                tag.attrs.pop(a, None)

    return body.decode_contents()


def page(renderable) -> None:
    less = shutil.which("less")
    if not less or not console.is_terminal:
        console.print(renderable)
        return
    with console.capture() as cap:
        console.print(renderable)
    subprocess.run([less, "-RFX"], input=cap.get(), encoding="utf-8", check=False)


@app.command(help="View a Wikipedia article using its exact title.")
def view(
    title: Annotated[list[str], typer.Argument(help="Article title.")],
) -> None:
    t = " ".join(title)
    with console.status("Searching...", spinner="dots"):
        res = requests.get(
            WIKIPEDIA_API + f"page/{quote(t, safe='')}/html",
            headers={"User-Agent": USER_AGENT},
        )
        data = res.text
    if res.status_code == 404:
        print(
            f"[red]Could not find article with title[/red] [bold green]{t}[/bold green]."
        )
        raise typer.Exit(1)

    extracted_content = extract_content(data)
    if extracted_content is not None:
        page(Markdown(md(extracted_content)))


@app.command(
    help="Requires running a query command first. Views an article based on its number in the previous query."
)
def show(number: Annotated[int, typer.Argument(help="The query number to use.")]):
    history = load_history()
    if not history:
        print("[red]No previous query. Run [bold]what is <query>[/bold] first.[/red]")
        raise typer.Exit(1)
    if number not in range(1, len(history[0]["results"]) + 1):
        print("[red]Specified article number is not in range.[/red]")
        raise typer.Exit(1)
    target_title: str = history[0]["results"][number - 1]["title"]

    if type(target_title) is str:
        view(title=[target_title])
    else:
        print(
            "[red]Error with command history. Your query history file is most likely not valid.[/red]"
        )


if __name__ == "__main__":
    app()
