"""Complete application: discovery, common editing and truthful observations."""

import os
from collections.abc import Mapping
from pathlib import Path

from rich.text import Text
from textual import events, on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.fuzzy import Matcher
from textual.screen import ModalScreen
from textual.widgets import Footer, Input, OptionList, Static
from textual.widgets.option_list import Option

from .discovery import Discovery, Parameter, discover, registry_candidates
from .document import (
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

    def __init__(
        self,
        document: ConfigurationDocument,
        name: str,
        parameter: Parameter | None = None,
        details: str = "",
    ) -> None:
        super().__init__()
        self.document = document
        self.parameter_name = name
        self.assignment = document.assignments.get(name.lower())
        self.details = details
        self.parameter = parameter

    def compose(self) -> ComposeResult:
        yield Static(f"{self.document.path} — [common] only", markup=False)
        previous = self.assignment.value if self.assignment is not None else "<absent>"
        yield Static(
            f"{self.parameter_name}\nPrevious assignment: {previous}\n"
            f"{self.details}\nType / constraints: unavailable\n"
            "Activation requirements: unavailable\nLimited validation",
            id="details",
            markup=False,
        )
        yield ValueInput(self.assignment.value if self.assignment else "", id="value")
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
            if self.parameter and not self.parameter.common_supported:
                raise ConfigurationError(
                    "Parameter is not supported in [common]; removal remains available."
                )
            message = self.document.save(
                self.parameter_name,
                self.query_one(Input).value,
                allow_insert=self.parameter is not None
                and self.parameter.common_supported,
            )
        except (ConfigurationError, OSError, UnicodeError) as error:
            self.query_one("#save-status", Static).update(str(error))
        else:
            self.dismiss(message)

    def action_cancel(self) -> None:
        self.dismiss(None)

    def action_remove_override(self) -> None:
        try:
            message = self.document.remove_override(self.parameter_name)
        except (ConfigurationError, OSError, UnicodeError) as error:
            self.query_one("#save-status", Static).update(str(error))
        else:
            self.dismiss(message)


class DatabasePicker(ModalScreen[str | None]):
    BINDINGS = [Binding("escape", "offline", "Offline")]

    def __init__(self, candidates: list[str], diagnostic: str) -> None:
        super().__init__()
        self.candidates = candidates
        self.diagnostic = diagnostic

    def compose(self) -> ComposeResult:
        yield Static(
            "Registry candidates (availability unverified) • Esc for offline",
            id="picker-title",
            markup=False,
        )
        yield Static(self.diagnostic, markup=False)
        yield OptionList(
            *(Option(Text(name), id=name) for name in self.candidates), id="databases"
        )
        yield Footer()

    def on_mount(self) -> None:
        self.query_one(OptionList).focus()
        self.query_one(OptionList).highlighted = 0 if self.candidates else None

    @on(OptionList.OptionSelected)
    def select_database(self, event: OptionList.OptionSelected) -> None:
        event.stop()
        self.dismiss(event.option.id)

    def action_offline(self) -> None:
        self.dismiss(None)


class ConfigurationApp(App[None]):
    CSS = """
    #target, #mode, #status { height: auto; }
    #status { max-height: 8; overflow-y: auto; }
    OptionList { height: 1fr; }
    ValueEditor { background: $surface; padding: 1 2; }
    ValueEditor Static { height: auto; }
    """
    BINDINGS = [
        Binding("ctrl+q", "quit", "Quit"),
        Binding("ctrl+d", "choose_database", "Database", priority=True),
        Binding("ctrl+f", "refresh_discovery", "Refresh observations", priority=True),
        Binding("escape", "cancel_discovery", "Cancel discovery"),
    ]

    def __init__(
        self,
        *,
        environment: Mapping[str, str] | None = None,
        database: str | None = None,
    ) -> None:
        super().__init__()
        self.environment = dict(os.environ if environment is None else environment)
        self.database = database
        self.discovery = Discovery()
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
        if self.database and self.document:
            self.discover_database()
        elif self.document:
            candidates, diagnostic = registry_candidates(self.environment)
            self.query_one("#mode", Static).update(
                "Limited offline editing • existing common assignments only\n"
                + diagnostic
            )
            if candidates:
                self.push_screen(
                    DatabasePicker(candidates, diagnostic), self.database_selected
                )

    def action_choose_database(self) -> None:
        if len(self.screen_stack) == 1 and self.document:
            candidates, diagnostic = registry_candidates(self.environment)
            self.push_screen(
                DatabasePicker(candidates, diagnostic), self.database_selected
            )

    def database_selected(self, database: str | None) -> None:
        self.action_cancel_discovery()
        self.database = database
        self.discovery = Discovery()
        self.refresh_settings()
        if database:
            self.discover_database()
        self.query_one("#search", Input).focus()

    def action_cancel_discovery(self) -> None:
        self.workers.cancel_group(self, "discovery")
        self.query_one("#mode", Static).update(
            "Discovery cancelled • Limited offline editing; "
            "retained observations unchanged"
        )

    def action_refresh_discovery(self) -> None:
        if self.database and len(self.screen_stack) == 1:
            self.discover_database()

    @work(exclusive=True, group="discovery")
    async def discover_database(self) -> None:
        assert self.database is not None
        self.query_one("#mode", Static).update(
            f"Discovering {self.database} • offline editing available"
        )
        self.discovery = await discover(self.environment, self.database)
        label = (
            "Incomplete discovery" if self.discovery.diagnostics else "Live discovery"
        )
        self.query_one("#mode", Static).update(
            f"{label} • {self.database} • metadata unavailable • limited validation"
        )
        self.query_one("#status", Static).update("\n".join(self.discovery.diagnostics))
        self.refresh_settings()

    def parameter_details(self, name: str) -> str:
        parameter = self.discovery.parameters.get(name)
        details = (
            []
            if parameter
            else ["Defaults: unavailable", "Client / server observations: unavailable"]
        )
        for role in ("C", "S"):
            observation = parameter.observations.get(role) if parameter else None
            details.append(
                f"{role}: {observation.value or '<empty>'} • "
                f"default: {observation.default or '<empty>'} • "
                f"default difference: {'yes' if observation.differs else 'no'}"
                if observation
                else f"{role}: unavailable"
            )
        if self.document and self.database:
            section_database = Path(self.database.split("@", 1)[0]).name
            overrides = self.document.database_assignments.get(section_database, {})
            if name in overrides:
                details.append(
                    f"Database override [@{section_database}]: {overrides[name]}"
                )
        variable = "CUBRID_" + name.upper()
        if variable in self.environment:
            details.append(
                f"Local environment {variable}={self.environment[variable]} "
                "(server environment unknown)"
            )
        return "\n".join(details)

    @on(Input.Changed, "#search")
    def refresh_settings(self) -> None:
        options = self.query_one(OptionList)
        options.clear_options()
        if self.document:
            query = self.query_one("#search", Input).value
            matcher = Matcher(query, case_sensitive=False)
            catalog = {
                name: Parameter(assignment.name)
                for name, assignment in self.document.assignments.items()
            }
            catalog.update(self.discovery.parameters)
            matches = [
                (matcher.match(name) if query else 1.0, parameter)
                for name, parameter in catalog.items()
            ]
            for score, parameter in sorted(matches, key=lambda item: -item[0]):
                if score > 0:
                    options.add_option(
                        Option(
                            Text(
                                f"{parameter.name} = "
                                + (
                                    self.document.assignments[
                                        parameter.name.lower()
                                    ].value
                                    if parameter.name.lower()
                                    in self.document.assignments
                                    else "<no common assignment>"
                                )
                            ),
                            id=parameter.name.lower(),
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
                    ValueEditor(
                        self.document,
                        (
                            self.document.assignments[name].name
                            if name in self.document.assignments
                            else self.discovery.parameters[name].name
                        ),
                        self.discovery.parameters.get(name),
                        self.parameter_details(name),
                    ),
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
