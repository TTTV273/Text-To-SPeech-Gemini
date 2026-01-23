from textual.app import App
from textual.containers import Container, Horizontal
from textual.widgets import Button, ContentSwitcher, Label

from tui.messages import FileSelected
from tui.screens.dashboard import Dashboard
from tui.screens.file_browser import FileBrowser
from tui.screens.voice_select import VoiceSelect


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
                    yield VoiceSelect(id="voice-select")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id

        if button_id == "btn-dashboard":
            self.query_one(ContentSwitcher).current = "dashboard"

        if button_id == "btn-new-job":
            self.query_one(ContentSwitcher).current = "new-job"

    def on_file_selected(self, message: FileSelected) -> None:
        selected_file = message.path

        self.notify(f"File selected: {selected_file}")

        self.query_one(ContentSwitcher).current = "voice-select"


if __name__ == "__main__":
    app = TTSApp()
    app.run()
