

import os
import sys
import asyncio
import logging
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Custom business/test logger
custom_logger = logging.getLogger("custom_test_logger")
custom_logger.setLevel(logging.INFO)

if not custom_logger.handlers:
    file_handler = logging.FileHandler("custom_test.log")
    file_handler.setFormatter(logging.Formatter("[CUSTOM TEST] %(asctime)s | %(message)s"))
    custom_logger.addHandler(file_handler)

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(logging.Formatter("🔹 [CUSTOM TEST LOG] %(asctime)s | %(message)s"))
    custom_logger.addHandler(stream_handler)


class LogsManager:
    """Manage log file creation and writing"""
    
    def __init__(self, folder_name="logs"):
        # Create folder if it doesn't exist
        os.makedirs(folder_name, exist_ok=True)

        current_datetime = datetime.now()
        self.text_file_name = os.path.join(
            folder_name,
            f"logs_{current_datetime.strftime('%Y%m%d_%H%M%S')}.txt"
        )
    
    def store_logs(self, text: str):
        """Store logs to file"""
        try:
            with open(self.text_file_name, "a", encoding='utf-8') as f:
                f.write(f'\n{text}\n\n')
        except Exception as e:
            logger.error(f"Failed to write to log file: {e}")