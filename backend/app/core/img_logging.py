
import logging
import sys

def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler("app.log", encoding='utf-8')
        ]
    )
    logger = logging.getLogger("diplom3d")
    logger.setLevel(logging.DEBUG)
    return logger

logger = setup_logging()
