from textual.message import Message


class FileSelected(Message):
    def __init__(self, path: str) -> None:
        self.path = path
        super().__init__()
