import typer


app = typer.Typer(help="Science Fiction Library Manager CLI")


@app.command()
def hello(name: str = "reader") -> None:
    """Simple sanity command for the CLI."""
    typer.echo(f"Hello, {name}!")


@app.command()
def health() -> None:
    """Basic health check for wiring/testing."""
    typer.echo("ok")
