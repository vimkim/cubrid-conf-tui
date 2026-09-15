"""Complete limited-offline application boundary."""

import os
from collections.abc import Mapping

from rich.text import Text
from textual import events, on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.fuzzy import Matcher
from textual.screen import ModalScreen
from textual.widgets import Footer, Input, OptionList, Static
from textual.widgets.option_list import Option

from .document import (
    Assignment,
    ConfigurationDocument,
    ConfigurationError,
    editing_target,
    validate_value,
)


class ValueInput(Input):
    def _on_paste(self, event: events.Paste) -> None:
        try:
            validate_value(event.text)
        except ConfigurationError as error:
            event.stop()
            event.prevent_default()
            self.screen.query_one("#save-status", Static).update(str(error))
        else:
            super()._on_paste(event)


class ValueEditor(ModalScreen[str | None]):
    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("ctrl+r", "remove_override", "Remove override"),
    ]

    def __init__(self, document: ConfigurationDocument, assignment: Assignment) -> None:
        super().__init__()
        self.document = document
        self.assignment = assignment

    def compose(self) -> ComposeResult:
        yield Static(f"{self.document.path} — [common] only", markup=False)
        yield Static(
            f"{self.assignment.name}\nPrevious assignment: {self.assignment.value}\n"
            "Defaults: unavailable\nType / constraints: unavailable\n"
            "Client / server observations: unavailable\n"
            "Activation requirements: unavailable\nLimited validation",
            id="details",
            markup=False,
        )
        yield ValueInput(self.assignment.value, id="value")
        yield Static(
            "Enter saves • Ctrl+R removes override • Esc cancels",
            id="save-status",
            markup=False,
        )
        yield Footer()

    def on_mount(self) -> None:
        self.query_one(Input).focus()

    @on(Input.Submitted, "#value")
    def save_value(self) -> None:
        try:
            message = self.document.save(
                self.assignment.name, self.query_one(Input).value
            )
        except (ConfigurationError, OSError, UnicodeError) as error:
            self.query_one("#save-status", Static).update(str(error))
        else:
            self.dismiss(message)

    def action_cancel(self) -> None:
        self.dismiss(None)

    def action_remove_override(self) -> None:
        try:
            message = self.document.remove_override(self.assignment.name)
        except (ConfigurationError, OSError, UnicodeError) as error:
            self.query_one("#save-status", Static).update(str(error))
        else:
            self.dismiss(message)


class ConfigurationApp(App[None]):
    CSS = """
    #target, #mode, #status { height: auto; }
    OptionList { height: 1fr; }
    ValueEditor { background: $surface; padding: 1 2; }
    ValueEditor Static { height: auto; }
    """
    BINDINGS = [Binding("ctrl+q", "quit", "Quit")]

    def __init__(self, *, environment: Mapping[str, str] | None = None) -> None:
        super().__init__()
        self.environment = dict(os.environ if environment is None else environment)
        self.document: ConfigurationDocument | None = None
        self.error = ""
        try:
            self.document = ConfigurationDocument(editing_target(self.environment))
        except (ConfigurationError, OSError, UnicodeError) as error:
            self.error = str(error)

    def compose(self) -> ComposeResult:
        yield Static(
            f"{self.document.path} — [common] only"
            if self.document
            else "Configuration unavailable",
            id="target",
            markup=False,
        )
        yield Static(
            "Limited offline editing • existing common assignments only\n"
            "Metadata and runtime observations unavailable • limited validation",
            id="mode",
            markup=False,
        )
        yield Input(
            placeholder="Fuzzy search; Enter opens selected setting", id="search"
        )
        yield OptionList(id="settings")
        yield Static(self.error, id="status", markup=False)
        yield Footer()

    def on_mount(self) -> None:
        self.refresh_settings()
        self.query_one(Input).focus()

    @on(Input.Changed, "#search")
    def refresh_settings(self) -> None:
        options = self.query_one(OptionList)
        options.clear_options()
        if self.document:
            query = self.query_one("#search", Input).value
            matcher = Matcher(query, case_sensitive=False)
            matches = [
                (matcher.match(name) if query else 1.0, assignment)
                for name, assignment in self.document.assignments.items()
            ]
            for score, assignment in sorted(matches, key=lambda item: -item[0]):
                if score > 0:
                    options.add_option(
                        Option(
                            Text(f"{assignment.name} = {assignment.value}"),
                            id=assignment.name.lower(),
                        )
                    )
            options.highlighted = 0 if options.option_count else None

    @on(Input.Submitted, "#search")
    @on(OptionList.OptionSelected)
    def open_editor(self) -> None:
        options = self.query_one(OptionList)
        if self.document and options.highlighted is not None:
            name = options.get_option_at_index(options.highlighted).id
            if name is not None:
                self.push_screen(
                    ValueEditor(self.document, self.document.assignments[name]),
                    self.editor_closed,
                )

    def editor_closed(self, message: str | None) -> None:
        if message:
            options = self.query_one(OptionList)
            selection = options.highlighted
            self.refresh_settings()
            options.highlighted = (
                min(selection or 0, options.option_count - 1)
                if options.option_count
                else None
            )
            self.query_one("#status", Static).update(message)
        self.query_one("#search", Input).focus()
