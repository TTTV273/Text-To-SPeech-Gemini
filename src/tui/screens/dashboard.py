from textual.containers import Container, Horizontal
from textual.widgets import DataTable, Label, Static


class Dashboard(Container):
    def compose(self):
        yield Label("Dashboard Overview")

        with Horizontal():
            yield Static("Stat 1")
            yield Static("Stat 2")
            yield Static("Stat 3")

        yield DataTable()

    def on_mount(self):
        table = self.query_one(DataTable)
        table.add_columns("ID", "File", "Status")
