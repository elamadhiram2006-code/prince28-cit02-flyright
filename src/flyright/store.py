import json
import logging
from pathlib import Path

logger = logging.getLogger("flyright")


class Store:
    def __init__(self, data_file: Path):
        self.data_file = data_file
        self.records = []

    def load(self):
        if not self.data_file.exists():
            logger.error("Data file not found")
            self.records = []
            return

        with self.data_file.open("r", encoding="utf-8") as file:
            self.records = json.load(file)

        logger.info("records loaded", extra={"records": len(self.records)})

    def get_all(self):
        return self.records

    def get_by_id(self, document_id: str):
        for record in self.records:
            if record["id"] == document_id:
                return record

        return None
