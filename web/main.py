"""Browser entry point. tools/build_web.py packs this with the drachewut
package for pygbag, which runs it on CPython compiled to WebAssembly."""

import asyncio

import pygame

from drachewut.client import Application


async def main():
    pygame.init()
    await Application().main()


asyncio.run(main())
