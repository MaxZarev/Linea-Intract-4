import sys

from loguru import logger


def setup():
    logger.remove()
    logger.add(
        sys.stdout,
        colorize=True,
        format="<light-cyan>{time:DD-MM HH:mm:ss}</light-cyan> | <level> {level: <8} </level> {file}:{function}:{line} | {message}",
        level="DEBUG",
    )

    logger.add("logs/logs.log", rotation="1 day", retention="7 days", level="DEBUG")
