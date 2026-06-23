"""CLI entry point for the local FastAPI server."""

import uvicorn

from .config import API_HOST, API_PORT


def main() -> None:
    uvicorn.run("vehicle_valuation.api:app", host=API_HOST, port=API_PORT, reload=False)


if __name__ == "__main__":
    main()
