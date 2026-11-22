import logging
import os
from logging.handlers import TimedRotatingFileHandler

NOME_LOGGER = "gestor_identidades_ad"


def setup_logger(name=NOME_LOGGER, arquivo="gestor_identidades_ad.log", console=True, nivel=logging.INFO):
    """Log com rotação diária em arquivo e saída no console.

    arquivo=None desliga o arquivo; console=False desliga o console.
    """
    logger = logging.getLogger(name)
    logger.setLevel(nivel)

    # Impede handlers duplicados
    if logger.handlers:
        return logger

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    if arquivo:
        # Diretório de logs
        log_dir = os.getenv("LOG_DIR") or "logs"
        os.makedirs(log_dir, exist_ok=True)

        # Handler de arquivo rotativo
        file_handler = TimedRotatingFileHandler(
            os.path.join(log_dir, arquivo), when="midnight", interval=1, encoding="utf-8"
        )
        file_handler.suffix = "%Y-%m-%d"
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    if console:
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    if not logger.handlers:
        logger.addHandler(logging.NullHandler())

    return logger
