from textual.app import App
from textual.containers import Container, Horizontal
from textual.widgets import Button, ContentSwitcher, Label

from tui.screens.dashboard import Dashboard
from tui.screens.file_browser import FileBrowser


class TTSApp(App):
    CSS_PATH = "styles/app.tcss"

    def compose(self):
        with Horizontal():
            with Container(id="sidebar"):
                yield Label("Menu")
                yield Button("Dashboard", id="btn-dashboard")
                yield Button("New Job", id="btn-new-job")

            with Container(id="main-content"):
                with ContentSwitcher(initial="dashboard"):
                    yield Dashboard(id="dashboard")
                    yield FileBrowser(id="new-job")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id

        if button_id == "btn-dashboard":
            self.query_one(ContentSwitcher).current = "dashboard"

        if button_id == "btn-new-job":
            self.query_one(ContentSwitcher).current = "new-job"


if __name__ == "__main__":
    app = TTSApp()
    app.run()
