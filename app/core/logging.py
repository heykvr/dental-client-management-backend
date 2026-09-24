import logging


def setup_logging(environment: str) -> None:
    logging.basicConfig(
        level=logging.DEBUG if environment == "development" else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    # Third-party libraries are very chatty at DEBUG
    for noisy in ("pymongo", "asyncio", "httpx", "httpcore", "anthropic"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
