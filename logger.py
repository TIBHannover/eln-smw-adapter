import os
from datetime import datetime
import logging

class Logger:
    def __init__(self, log_dir="log"):
        self.start_time = datetime.now()  # Record the creation time of the logger instance
        self.log_dir = log_dir

        # Create the log directory if it doesn't exist
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)

        # Set up the logger
        self.logger = logging.getLogger('app')
        self.logger.setLevel(logging.INFO)  # Default log level is INFO
        self.update_log_file()  # Initialize the log file

    def update_log_file(self):
        log_filename = datetime.now().strftime("%Y-%m-%d.log")  # Use the current date for the log filename
        log_path = os.path.join(self.log_dir, log_filename)

        # Remove existing handlers before adding a new one
        if self.logger.handlers:
            self.logger.handlers.clear()

        # Add a file handler to the logger
        file_handler = logging.FileHandler(log_path)
        file_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s]: %(message)s"))
        self.logger.addHandler(file_handler)

    def log_message(self, level, message):
        # Dynamically get the logging method corresponding to the level
        log_method = getattr(self.logger, level.lower(), None)

        # If a valid log method exists, log the message, otherwise fallback to 'debug'
        if log_method: # error, warning, info
            log_method(message)
        else:
            self.logger.debug(message)

    # Log the runtime in milliseconds since the Logger instance was created
    def log_runtime(self):
        elapsed_time = datetime.now() - self.start_time
        elapsed_ms = int(elapsed_time.total_seconds() * 1000)  # Convert to milliseconds
        runtime_message = f"Runtime {elapsed_ms} ms"
        self.log_message('info', runtime_message)
