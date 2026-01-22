from textual.app import App
from textual.containers import Container, Horizontal
from textual.widgets import Button, Label


class TTSApp(App):
    CSS_PATH = "styles/app.tcss"

    def compose(self):
        with Horizontal():
            with Container(id="sidebar"):
                yield Label("Menu")
                yield Button("Dashboard")
                yield Button("New Job")

            with Container(id="main-content"):
                yield Label("Welcome to Gemini TTS")


if __name__ == "__main__":
    app = TTSApp()
    app.run()
