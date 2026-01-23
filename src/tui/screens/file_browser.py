from textual.containers import Container
from textual.widgets import DirectoryTree, Label

from tui.messages import FileSelected


class FileBrowser(Container):
    def compose(self):
        yield Label("Select a Markdown File", classes="screen-title")
        # Đường dẫn mặc định là thư mục hiện tại
        yield DirectoryTree("./")

    def on_directory_tree_file_selected(self, event: DirectoryTree.FileSelected):
        """Hàm này chạy khi user chọn một file"""
        selected_file = str(event.path)

        self.post_message(FileSelected(selected_file))
