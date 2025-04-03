import logging


class ColoredFormatter(logging.Formatter):
    # Define colors for different log levels.
    COLORS = {
        "DEBUG": "\033[1;94m",  # bold blue
        "INFO": "\033[1;92m",  # bold green
        "WARNING": "\033[1;93m",  # bold yellow
        "ERROR": "\033[1;91m",  # bold red
        "CRITICAL": "\033[1;95m",  # bold magenta
    }
    RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        sep: str = "|"
        date_format: str = "%Y-%m-%d %H:%M:%S"
        log_color: str = self.COLORS.get(record.levelname, self.RESET)
        log_fmt: str = (
            f"\033[92m%(asctime)s.%(msecs)03d\033[0m"
            f" {sep} {log_color}%(levelname)-8s{self.RESET}"
            f" {sep} \033[96m%(name)s:%(module)s:%(funcName)s:%(lineno)d\033[0m"
            f" - {log_color}%(message)s{self.RESET}"
        )
        formatter = logging.Formatter(fmt=log_fmt, datefmt=date_format)
        return formatter.format(record=record)
