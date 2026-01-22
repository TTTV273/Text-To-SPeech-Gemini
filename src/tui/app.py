from textual.app import App
from textual.widgets import Label, Button
from textual.containers import Container, Horizontal


class TTSApp(App):
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
