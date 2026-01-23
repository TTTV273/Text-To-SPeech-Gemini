from textual.containers import Container
from textual.widgets import DirectoryTree, Label


class FileBrowser(Container):
    def compose(self):
        yield Label("Select a Markdown File", classes="screen-title")
        # Đường dẫn mặc định là thư mục hiện tại
        yield DirectoryTree("./")

    def on_directory_tree_file_selected(self, event: DirectoryTree.FileSelected):
        """Hàm này chạy khi user chọn một file"""
        selected_file = event.path
        # Tạm thời mình chỉ in ra console để test thôi
        self.notify(f"Selected: {selected_file}")
