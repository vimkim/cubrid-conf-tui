"""Complete application: discovery, common editing and truthful observations."""

import os
from collections.abc import Callable, Mapping, Sequence
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
from .metadata import MetadataCatalog, discover_metadata
from .validation import (
    configuration_default_text,
    configuration_text_description,
    describe_assignment,
    parse_boolean_text,
    replace_scalar_preserving_quotes,
    unquote_configuration_text,
    validate_configuration_value,
    validation_description,
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
        Binding("space", "toggle_boolean", "Toggle", show=False),
    ]

    def __init__(
        self,
        document: ConfigurationDocument,
        name: str,
        parameter: Parameter | None = None,
        details: str = "",
        parameter_lookup: Callable[[str], Parameter | None] | None = None,
    ) -> None:
        super().__init__()
        self.document = document
        self.parameter_name = name
        self.assignment = document.assignments.get(name.lower())
        self.details = details
        self.parameter = parameter
        self.parameter_lookup = parameter_lookup

    def compose(self) -> ComposeResult:
        yield Static(f"{self.document.path} — [common] only", markup=False)
        metadata = self.parameter.metadata if self.parameter else None
        previous = describe_assignment(
            self.assignment.value if self.assignment is not None else None, metadata
        )
        yield Static(
            f"{self.parameter_name}\nPrevious assignment: {previous}\n"
            f"{self.details}\n"
            + (
                validation_description(metadata) + "\n"
                if metadata
                else "Type / constraints: unavailable\n"
            )
            + "Activation requirements: unavailable\nLimited validation",
            id="details",
            markup=False,
        )
        if self.is_boolean:
            yield OptionList(
                Option(Text("yes"), id="yes"),
                Option(Text("no"), id="no"),
                Option(Text("default"), id="default"),
                id="boolean-values",
            )
        else:
            yield ValueInput(
                self.assignment.value if self.assignment else "", id="value"
            )
        yield Static(
            "Enter saves • Ctrl+R removes override • Esc cancels",
            id="save-status",
            markup=False,
        )
        yield Footer()

    def on_mount(self) -> None:
        if self.is_boolean:
            selector = self.query_one("#boolean-values", OptionList)
            selector.highlighted = self.initial_boolean_selection
            selector.focus()
        else:
            self.query_one(Input).focus()

    @property
    def is_boolean(self) -> bool:
        return bool(
            self.parameter
            and self.parameter.metadata
            and self.parameter.metadata.type_name == "boolean"
        )

    @property
    def initial_boolean_selection(self) -> int | None:
        if self.assignment:
            scalar, _ = unquote_configuration_text(self.assignment.value)
            scalar = scalar.lower()
            if scalar == "default":
                return 2
            parsed = parse_boolean_text(self.assignment.value)
            if parsed is not None:
                return 0 if parsed else 1
            return None
        metadata = self.parameter.metadata if self.parameter else None
        default_text = configuration_default_text(metadata) if metadata else None
        default = parse_boolean_text(default_text) if default_text else None
        if default is None:
            return None
        return 0 if default else 1

    @on(Input.Submitted, "#value")
    def save_value(self) -> None:
        self._save(self.query_one(Input).value)

    @on(OptionList.OptionSelected, "#boolean-values")
    def save_boolean(self, event: OptionList.OptionSelected) -> None:
        event.stop()
        if event.option.id is not None:
            original = self.assignment.value if self.assignment else None
            self._save(replace_scalar_preserving_quotes(original, event.option.id))

    def _save(self, value: str) -> None:
        try:
            validate_value(value)
            parameter = (
                self.parameter_lookup(self.parameter_name)
                if self.parameter_lookup
                else self.parameter
            )
            if parameter and not parameter.common_supported:
                reason = (
                    "obsolete"
                    if parameter.metadata and parameter.metadata.obsolete
                    else "not supported in [common]"
                )
                raise ConfigurationError(
                    f"Parameter is {reason}; removal remains available."
                )
            outcome = (
                validate_configuration_value(parameter.metadata, value)
                if parameter and parameter.metadata
                else None
            )
            message = self.document.save(
                self.parameter_name,
                value,
                allow_insert=parameter is not None and parameter.common_supported,
            )
            limitations = (
                outcome.limitations
                if outcome
                else ("type and parameter constraints are unavailable",)
            )
            message += (
                " Limited validation: "
                + "; ".join(limitations)
                + ". A saved value does not prove CUBRID startup acceptance."
            )
        except (ConfigurationError, OSError, UnicodeError) as error:
            self.query_one("#save-status", Static).update(str(error))
        else:
            self.dismiss(message)

    def action_toggle_boolean(self) -> None:
        if self.is_boolean:
            selector = self.query_one("#boolean-values", OptionList)
            selector.highlighted = 1 if selector.highlighted == 0 else 0

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
    #mode, #status { max-height: 8; overflow-y: auto; }
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
        metadata_command: Sequence[str] | None = None,
        metadata_timeout: float = 10.0,
    ) -> None:
        super().__init__()
        self.environment = dict(os.environ if environment is None else environment)
        self.database = database
        self.metadata_command = tuple(metadata_command) if metadata_command else None
        self.metadata_timeout = metadata_timeout
        self.discovery = Discovery()
        self.metadata = MetadataCatalog()
        self.metadata_pending = True
        self.live_pending = bool(database)
        self.registry_diagnostic = ""
        self.document: ConfigurationDocument | None = None
        self.error = ""
        try:
            self.document = ConfigurationDocument(editing_target(self.environment))
        except (ConfigurationError, OSError, UnicodeError) as error:
            self.error = str(error)
            self.metadata_pending = False
            self.live_pending = False

    def compose(self) -> ComposeResult:
        yield Static(
            f"{self.document.path} — [common] only"
            if self.document
            else "Configuration unavailable",
            id="target",
            markup=False,
        )
        yield Static(
            (
                "Discovering offline catalog • existing settings remain editable"
                if self.metadata_pending
                else "Limited offline editing • existing common assignments only\n"
                "Metadata and runtime observations unavailable • limited validation"
            ),
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
        if self.document:
            self.discover_catalog()
        if self.database and self.document:
            self.discover_database()
        elif self.document:
            candidates, diagnostic = registry_candidates(self.environment)
            self.registry_diagnostic = diagnostic
            self.update_mode()
            if candidates:
                self.push_screen(
                    DatabasePicker(candidates, diagnostic), self.database_selected
                )

    def action_choose_database(self) -> None:
        if len(self.screen_stack) == 1 and self.document:
            candidates, diagnostic = registry_candidates(self.environment)
            self.registry_diagnostic = diagnostic
            self.push_screen(
                DatabasePicker(candidates, diagnostic), self.database_selected
            )

    def database_selected(self, database: str | None) -> None:
        self.workers.cancel_group(self, "live-discovery")
        self.database = database
        self.discovery = Discovery()
        self.live_pending = bool(database)
        self.refresh_settings()
        if database:
            self.discover_database()
        self.query_one("#search", Input).focus()

    def action_cancel_discovery(self) -> None:
        self.workers.cancel_group(self, "live-discovery")
        self.workers.cancel_group(self, "metadata-discovery")
        self.metadata_pending = False
        self.live_pending = False
        self.query_one("#mode", Static).update(
            "Discovery cancelled • Limited offline editing; "
            "retained observations unchanged"
        )

    def action_refresh_discovery(self) -> None:
        if self.database and len(self.screen_stack) == 1:
            self.discover_database()

    @work(exclusive=True, group="metadata-discovery")
    async def discover_catalog(self) -> None:
        self.metadata_pending = True
        self.update_mode()
        try:
            self.metadata = await discover_metadata(
                self.environment, self.metadata_command, self.metadata_timeout
            )
        finally:
            self.metadata_pending = False
        self.update_mode()
        self.refresh_settings()

    @work(exclusive=True, group="live-discovery")
    async def discover_database(self) -> None:
        assert self.database is not None
        self.live_pending = True
        self.update_mode()
        try:
            self.discovery = await discover(self.environment, self.database)
        finally:
            self.live_pending = False
        self.update_mode()
        self.refresh_settings()

    def update_mode(self) -> None:
        if self.metadata_pending or self.live_pending:
            work = []
            if self.metadata_pending:
                work.append("offline catalog")
            if self.live_pending and self.database:
                work.append(self.database)
            label = "Discovering " + " and ".join(work)
            if self.metadata_pending and not self.live_pending:
                label = "Limited offline editing • " + label
        elif self.database:
            label = (
                "Incomplete discovery"
                if self.discovery.diagnostics
                else "Live discovery"
            ) + f" • {self.database}"
            label += (
                " • Supported offline catalog"
                if self.metadata.supported
                else " • offline catalog unavailable"
            )
        elif self.metadata.supported:
            label = "Supported offline catalog • no database required"
        else:
            label = "Limited offline editing • existing common assignments only"
        label += " • limited validation"
        if self.metadata.diagnostics:
            label += "\n" + "\n".join(self.metadata.diagnostics)
        if self.registry_diagnostic:
            label += "\n" + self.registry_diagnostic
        self.query_one("#mode", Static).update(label)
        self.query_one("#status", Static).update("\n".join(self.discovery.diagnostics))

    def combined_parameters(self) -> dict[str, Parameter]:
        combined: dict[str, Parameter] = {}
        if self.document:
            combined.update(
                {
                    name: Parameter(assignment.name)
                    for name, assignment in self.document.assignments.items()
                }
            )
        for name, metadata in self.metadata.parameters.items():
            if metadata.obsolete and name not in combined:
                continue
            parameter = combined.setdefault(name, Parameter(metadata.name))
            parameter.metadata = metadata
        for name, live in self.discovery.parameters.items():
            live_metadata = self.metadata.parameters.get(name)
            if live_metadata and live_metadata.obsolete and name not in combined:
                continue
            parameter = combined.setdefault(name, Parameter(live.name))
            parameter.observations = live.observations
            if live_metadata:
                parameter.metadata = live_metadata
        return combined

    def current_parameter(self, name: str) -> Parameter | None:
        return self.combined_parameters().get(name.lower())

    def parameter_details(self, name: str) -> str:
        parameter = self.combined_parameters().get(name)
        details = (
            []
            if parameter and (parameter.metadata or parameter.observations)
            else ["Defaults: unavailable", "Client / server observations: unavailable"]
        )
        metadata = parameter.metadata if parameter else None
        if metadata:
            roles = "/".join(
                role
                for present, role in (
                    (metadata.client, "client"),
                    (metadata.server, "server"),
                )
                if present
            )
            if not roles:
                roles = "role flags unavailable"
            classification = "hidden" if metadata.hidden else "ordinary"
            if metadata.obsolete:
                classification += " • obsolete"
            details.extend(
                [
                    f"{metadata.name} • {classification} • {roles}",
                    f"Raw compiled default ({metadata.type_name}): "
                    f"{metadata.default.display()}",
                    f"Raw lower constraint: {metadata.lower.display()}",
                    f"Raw upper constraint: {metadata.upper.display()}",
                    configuration_text_description(metadata),
                    metadata.provenance.cpu_derived,
                    f"Artifact: {metadata.provenance.artifact.path} • "
                    f"{metadata.provenance.artifact.role} • "
                    f"{metadata.provenance.artifact.mode}",
                    f"SHA-256: {metadata.provenance.artifact.sha256}",
                    f"Build ID: {metadata.provenance.artifact.build_id}",
                    "Custom validation callbacks: "
                    + ("present" if metadata.has_custom_callbacks else "absent"),
                    f"Compatibility: {metadata.provenance.compatibility.layout} • "
                    f"{metadata.provenance.compatibility.evidence}",
                ]
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
            catalog = self.combined_parameters()
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
                            else self.combined_parameters()[name].name
                        ),
                        self.combined_parameters().get(name),
                        self.parameter_details(name),
                        self.current_parameter,
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
