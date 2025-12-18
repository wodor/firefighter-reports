from typing import Optional

import typer

from .config import Settings
from .runner import run_pipeline

app = typer.Typer(add_completion=False, no_args_is_help=True)


@app.command()
def run(
    dry_run: Optional[bool] = typer.Option(
        None,
        "--dry-run/--no-dry-run",
        help="Print blocks instead of posting to Slack; defaults to DRY_RUN env",
    )
) -> None:
    settings = Settings()
    effective_dry_run = settings.dry_run if dry_run is None else dry_run
    run_pipeline(settings=settings, dry_run=effective_dry_run)


if __name__ == "__main__":
    app()

