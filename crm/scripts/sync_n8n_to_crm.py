"""Continuously sync n8n car_listings rows into the local CRM database."""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime

from import_n8n_listings import import_rows


def timestamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--interval-seconds", type=int, default=60)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--skip-images", action="store_true")
    parser.add_argument("--once", action="store_true")
    return parser.parse_args()


async def run_once(args: argparse.Namespace) -> dict[str, int]:
    result = await import_rows(
        limit=args.limit,
        skip_images=args.skip_images,
        refresh_existing=False,
    )
    print(f"[CRM SYNC] {timestamp()} {result}", flush=True)
    return result


async def main() -> None:
    args = parse_args()
    if args.interval_seconds < 10:
        raise ValueError("--interval-seconds must be at least 10")

    while True:
        try:
            await run_once(args)
        except Exception as error:
            print(f"[CRM SYNC] {timestamp()} failed: {error}", flush=True)

        if args.once:
            break

        await asyncio.sleep(args.interval_seconds)


if __name__ == "__main__":
    asyncio.run(main())
