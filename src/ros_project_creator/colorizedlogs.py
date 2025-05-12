#!/usr/bin/env python3

import logging

# Check if colorama is installed
try:
    from colorama import Fore, Style, init
    init(autoreset=True)  # Initialize colorama (required for Windows)
except ImportError:
    raise ImportError("The 'colorama' package is required for colored logging. Install it using 'pip install colorama'.")


class ColorizedLogger:
    """Logger class that supports colored console output and file logging."""

    class ColoredFormatter(logging.Formatter):
        """Custom formatter to add colors to log messages based on log level."""
        COLORS = {
            logging.DEBUG: Fore.BLUE,
            logging.INFO: Fore.GREEN,
            logging.WARNING: Fore.YELLOW,
            logging.ERROR: Fore.RED,
            logging.CRITICAL: Fore.RED + Style.BRIGHT,
        }

        SHORT_LEVEL_NAMES = {
            "DEBUG": "DBG",
            "INFO": "INF",
            "WARNING": "WRN",
            "ERROR": "ERR",
            "CRITICAL": "CRT",
        }

        def format(self, record):
            # Store the original level name
            original_levelname = record.levelname

            # Replace with the three-letter abbreviation if available
            record.levelname = self.SHORT_LEVEL_NAMES.get(record.levelname, record.levelname)

            log_color = self.COLORS.get(record.levelno, Fore.WHITE)
            log_message = super().format(record)

            # Restore the original level name for any further processing
            record.levelname = original_levelname

            return log_color + log_message + Style.RESET_ALL

    @staticmethod
    def __assert_non_empty(item, error_msg: str) -> None:
        if not item:  # Covers empty strings, lists, dicts, sets, None, etc.
            raise Exception(error_msg)

    @staticmethod
    def __generate_unique_logger_name(base_name: str) -> str:
        """
        Generates a unique logger name by incrementing a counter.
        """

        base_name = base_name.strip()
        ColorizedLogger.__assert_non_empty(base_name, "Base name for the logger must be a non-empty str")

        existing_loggers = logging.Logger.manager.loggerDict.keys()
        unique_name = base_name
        counter = 1

        while unique_name in existing_loggers:
            unique_name = f"{base_name}_{counter}"
            counter += 1

        return unique_name

    def __init__(
        self, name: str = "colorizedlogs", use_console_log: bool = True, log_file: str = "", log_level: str = "DEBUG"
    ):
        """
        Initializes a custom logger with optional console and file logging.

        Args:
            name (str): The logger's name.
            use_console_log (bool): Enable logging to the console.
            log_file (str): Path to a log file (empty string disables file logging).
            log_level (str): The minimum logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
        """
        name = ColorizedLogger.__generate_unique_logger_name(name)

        log_file = log_file.strip()  # it could be empty if no logging to file is required.

        log_level = log_level.strip()
        ColorizedLogger.__assert_non_empty(log_level,
                                           f"The level for the logger '{name}' must be a non-empty str")

        self.logger = logging.getLogger(name)

        # Convert str level to logging module level. Raise exception if log_level is invalid.
        self.logger.setLevel(getattr(logging, log_level.upper()))

        # Clear existing handlers only for this logger (avoid affecting root logger).
        self.logger.handlers.clear()

        # If neither console nor file logging is enabled, disable the logger.
        if not use_console_log and not log_file:
            self.logger.disabled = True
            return

        log_format = '%(asctime)s - %(levelname)s - %(message)s'

        if use_console_log:
            console_handler = logging.StreamHandler()
            console_handler.setLevel(log_level)
            console_handler.setFormatter(self.ColoredFormatter(log_format))
            self.logger.addHandler(console_handler)

        if log_file:
            file_handler = logging.FileHandler(log_file)
            file_handler.setLevel(log_level)
            file_handler.setFormatter(logging.Formatter(log_format))
            self.logger.addHandler(file_handler)

    def debug(self, msg: str) -> None:
        self.logger.debug(msg)

    def info(self, msg: str) -> None:
        self.logger.info(msg)

    def warning(self, msg: str) -> None:
        self.logger.warning(msg)

    def error(self, msg: str) -> None:
        self.logger.error(msg)

    def critical(self, msg: str) -> None:
        self.logger.critical(msg)
