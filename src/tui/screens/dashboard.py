from textual.containers import Container
from textual.widgets import Label


class Dashboard(Container):
    def compose(self):
        yield Label("This is Dashboard Widget")
