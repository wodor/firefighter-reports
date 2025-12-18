import logging
import sys
from typing import Annotated, Optional

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
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Force dry run")] = False,
    permalink: Annotated[str, typer.Option(help="Process a single thread by its Slack permalink")] = "",
) -> None:
    setup_logging()
    settings = Settings()
    override_dry_run: Optional[bool] = True if dry_run else None
    effective_dry_run = settings.dry_run if override_dry_run is None else override_dry_run
    run_pipeline(settings=settings, dry_run=effective_dry_run, permalink=permalink or None)


if __name__ == "__main__":
    typer.run(main)

