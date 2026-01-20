import logging
import os

class LogService:
    def __init__(self, log_file="spotdl_debug.log"):
        self.gui_callback = None
        
        # Setup File Logging
        logging.basicConfig(
            filename=log_file,
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
    def set_gui_callback(self, callback):
        """Sets a callback function (str) -> None for GUI updates."""
        self.gui_callback = callback
        
    def log(self, message: str):
        """Logs to file and GUI."""
        logging.info(message)
        if self.gui_callback:
            self.gui_callback(message)
            
    def info(self, message: str):
        self.log(message)
        
    def error(self, message: str):
        self.log(f"ERROR: {message}")
