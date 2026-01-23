from textual.containers import Container, Horizontal
from textual.widgets import Button, Label


class VoiceCard(Container):
    def __init__(self, voice_name, voice_style):
        super().__init__()
        self.voice_name = voice_name
        self.voice_style = voice_style

    def compose(self):
        yield Label(self.voice_name)
        yield Label(self.voice_style)
        yield Button("Preview")
        yield Button("Select")


class VoiceSelect(Container):
    def compose(self):
        yield Label("Select a Voice")
        with Horizontal():
            yield VoiceCard("Kore", "Firm")
            yield VoiceCard("Puck", "Upbeat")
            yield VoiceCard("Zephyr", "Bright")
