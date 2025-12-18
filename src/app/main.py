import logging
import sys
from typing import Optional

import typer

from .config import Settings
from .runner import run_pipeline

def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler("firefighter.log"),
        ],
        force=True,
    )


def main(
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Force dry run: print blocks instead of posting to Slack",
        is_flag=True,
    ),
    no_dry_run: bool = typer.Option(
        False,
        "--no-dry-run",
        help="Force posting to Slack even if DRY_RUN env is true",
        is_flag=True,
    ),
) -> None:
    if dry_run and no_dry_run:
        raise typer.BadParameter("Choose only one of --dry-run or --no-dry-run")

    setup_logging()
    settings = Settings()
    override_dry_run: Optional[bool] = True if dry_run else False if no_dry_run else None
    effective_dry_run = settings.dry_run if override_dry_run is None else override_dry_run
    run_pipeline(settings=settings, dry_run=effective_dry_run)


if __name__ == "__main__":
    typer.run(main)

