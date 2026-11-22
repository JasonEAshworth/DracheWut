"""Locations of the game's bundled files."""

from pathlib import Path

ASSETS = Path(__file__).resolve().parent / "assets"


def asset(*parts: str) -> str:
    """Absolute path to a bundled asset, independent of the working directory."""
    return str(ASSETS.joinpath(*parts))
