from __future__ import annotations

import logging
import sys

from hihi.bot import Bot
from hihi.config import load_config


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    config = load_config()
    bot = Bot(config)
    try:
        bot.start()
    except KeyboardInterrupt:
        print("\nbye")
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
