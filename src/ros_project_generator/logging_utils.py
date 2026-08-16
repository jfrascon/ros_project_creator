import logging


def create_logger(
    name: str, use_console_log: bool = True, log_file: str = '', log_level: str = 'DEBUG'
) -> logging.Logger:
    """Create a standard logger with optional console and file handlers."""
    logger_name = name.strip()
    if not logger_name:
        raise ValueError('Logger name must be a non-empty string')

    log_file = log_file.strip()
    log_level = log_level.strip()
    if not log_level:
        raise ValueError(f"Log level for logger '{logger_name}' must be a non-empty string")

    level = getattr(logging, log_level.upper(), None)
    if not isinstance(level, int):
        raise ValueError(f"Invalid log level '{log_level}' for logger '{logger_name}'")

    logger = logging.getLogger(logger_name)
    logger.setLevel(level)
    logger.handlers.clear()
    logger.propagate = False
    logger.disabled = False

    if not use_console_log and not log_file:
        logger.disabled = True
        return logger

    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

    if use_console_log:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(level)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger
