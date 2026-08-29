"""
RESQ - Operator console.

OWNER: Partner D (System Core).

    python main.py --ui

A Tk desktop window. Tk ships with Python, so this adds no dependency and the
core stays installable with nothing but a clone - which is the rule the rest of
the project follows and the reason a web framework was not used.

DESIGN NOTE - the one rule this file obeys above all others:

    EVERY BUTTON CALLS A REAL ENGINE METHOD.

Nothing here fakes a display, nudges a status, or writes to the world. The
buttons call engine.inject_* and then the screen redraws from whatever the
world actually says. If the engine did not do it, the operator does not see it.
That is what makes the demo evidence rather than theatre, and it is why the
audit log below the tables always agrees with the tables above it.

The simulation is driven by Tk's own `after` timer on the main thread. No
threads, no locks: a tick either happens between redraws or it does not, and the
screen can never catch the world half-updated.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, ttk
from typing import Optional

from .audit import AuditLog
from .engine import Engine, EngineConfig
from .models import IncidentStatus, IncidentType, NodeKind, UnitStatus, UnitType
from .scenarios import ALL_SCENARIOS, collect_metrics
from .adapters.partner_a import SeverityPrioritizer
from .adapters.partner_b import AllocationDispatcher
from .adapters.partner_c import DijkstraRouter
from .stubs.naive import BfsRouter, FifoPrioritizer, FirstFreeDispatcher

# How fast one simulated tick arrives, per speed setting. Real milliseconds.
SPEEDS = {"0.5x": 1200, "1x": 600, "2x": 300, "4x": 150, "Max": 20}

# Status -> colour. Kept blunt and high contrast; the instructor reads this
# from across a room, not from a laptop screen.
INCIDENT_COLOURS = {
    "REPORTED": "#7a5c00",
    "QUEUED": "#8a3b00",
    "ASSIGNED": "#1d4f91",
    "ON_SCENE": "#0b6b4f",
    "TRANSPORTING": "#4a2a8a",
    "RESOLVED": "#2f5d2f",
    "FAILED": "#8c1d13",
}
UNIT_COLOURS = {
    "AVAILABLE": "#2f5d2f",
    "EN_ROUTE": "#1d4f91",
    "ON_SCENE": "#0b6b4f",
    "TRANSPORTING": "#4a2a8a",
    "RETURNING": "#5a5a5a",
    "OUT_OF_SERVICE": "#8c1d13",
}


class OperatorConsole:
    """The whole window. One class so state is easy to follow while defending it."""

    def __init__(self, root: tk.Tk, repository=None) -> None:
        self.root = root
        self.repository = repository
        self.engine: Optional[Engine] = None
        self.running = False
        self._after_id = None
        self._logged = 0  # how many audit records we have already shown

        root.title("RESQ - Operator Console")
        root.geometry("1280x860")
        root.minsize(1060, 700)

        self._build_toolbar()
        self._build_tables()
        self._build_injection_panel()
        self._build_bottom()

        self.load_scenario()

    # ==================================================================
    # LAYOUT
    # ==================================================================

    def _build_toolbar(self) -> None:
        bar = ttk.Frame(self.root, padding=(10, 8))
        bar.pack(fill="x")

        ttk.Label(bar, text="Scenario").pack(side="left")
        self.scenario_var = tk.StringVar(value=list(ALL_SCENARIOS)[0])
        picker = ttk.Combobox(bar, textvariable=self.scenario_var, width=13,
                              state="readonly", values=list(ALL_SCENARIOS))
        picker.pack(side="left", padx=(6, 4))
        picker.bind("<<ComboboxSelected>>", lambda _e: self.load_scenario())

        ttk.Label(bar, text="Components").pack(side="left", padx=(10, 4))
        self.components_var = tk.StringVar(value="real")
        chooser = ttk.Combobox(bar, textvariable=self.components_var, width=9,
                               state="readonly", values=["real", "baseline"])
        chooser.pack(side="left")
        chooser.bind("<<ComboboxSelected>>", lambda _e: self.load_scenario())

        ttk.Button(bar, text="Load / Reset",
                   command=self.load_scenario).pack(side="left", padx=6)

        ttk.Separator(bar, orient="vertical").pack(side="left", fill="y", padx=10)

        self.play_button = ttk.Button(bar, text="Start", width=8,
                                      command=self.toggle_running)
        self.play_button.pack(side="left", padx=2)
        ttk.Button(bar, text="Step", width=6,
                   command=self.step_once).pack(side="left", padx=2)

        ttk.Label(bar, text="Speed").pack(side="left", padx=(12, 4))
        self.speed_var = tk.StringVar(value="1x")
        ttk.Combobox(bar, textvariable=self.speed_var, width=6, state="readonly",
                     values=list(SPEEDS)).pack(side="left")

        ttk.Separator(bar, orient="vertical").pack(side="left", fill="y", padx=10)

        self.clock_label = ttk.Label(bar, text="00:00:00",
                                     font=("Consolas", 20, "bold"))
        self.clock_label.pack(side="left")
        self.tick_label = ttk.Label(bar, text="tick 0", foreground="#555")
        self.tick_label.pack(side="left", padx=(8, 0))

        self.status_label = ttk.Label(bar, text="", foreground="#1d4f91")
        self.status_label.pack(side="right")

    def _build_tables(self) -> None:
        panes = ttk.Frame(self.root, padding=(10, 0))
        panes.pack(fill="both", expand=True)
        panes.columnconfigure(0, weight=3)
        panes.columnconfigure(1, weight=2)
        panes.rowconfigure(0, weight=1)

        # --- incidents ------------------------------------------------
        left = ttk.LabelFrame(panes, text="Incidents", padding=6)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 6))

        columns = ("id", "type", "at", "status", "unit", "waited", "why")
        self.incident_table = ttk.Treeview(left, columns=columns,
                                           show="headings", height=12)
        for name, title, width in (
            ("id", "Incident", 72), ("type", "Type", 78), ("at", "Node", 50),
            ("status", "Status", 100), ("unit", "Unit", 48),
            ("waited", "Waited", 58), ("why", "Latest reason", 300),
        ):
            self.incident_table.heading(name, text=title)
            self.incident_table.column(
                name, width=width, minwidth=40, stretch=(name == "why"),
                anchor="w" if name == "why" else "center")
        self.incident_table.pack(fill="both", expand=True, side="left")
        scroll = ttk.Scrollbar(left, orient="vertical",
                               command=self.incident_table.yview)
        scroll.pack(side="right", fill="y")
        self.incident_table.configure(yscrollcommand=scroll.set)
        for status, colour in INCIDENT_COLOURS.items():
            self.incident_table.tag_configure(status, foreground=colour)
        # Double-click a call to open its decision chain in the audit tab.
        self.incident_table.bind("<Double-1>", self._on_incident_double_click)

        # --- units ----------------------------------------------------
        right = ttk.LabelFrame(panes, text="Response units", padding=6)
        right.grid(row=0, column=1, sticky="nsew")

        columns = ("id", "type", "status", "node", "incident", "busy")
        self.unit_table = ttk.Treeview(right, columns=columns,
                                       show="headings", height=12)
        for name, title, width in (
            ("id", "Unit", 46), ("type", "Type", 96), ("status", "Status", 104),
            ("node", "At", 44), ("incident", "Incident", 68), ("busy", "Busy", 46),
        ):
            self.unit_table.heading(name, text=title)
            self.unit_table.column(name, width=width, minwidth=36,
                                   stretch=(name == "status"), anchor="center")
        self.unit_table.pack(fill="both", expand=True)
        for status, colour in UNIT_COLOURS.items():
            self.unit_table.tag_configure(status, foreground=colour)

    def _build_injection_panel(self) -> None:
        """
        The instructor's controls. Every one calls an engine method directly.
        Grouped by what they break so nobody has to hunt during the demo.
        """
        outer = ttk.LabelFrame(
            self.root,
            text="Failure injection  -  these call the engine, nothing is faked",
            padding=8,
        )
        outer.pack(fill="x", padx=10, pady=8)

        # --- roads ----------------------------------------------------
        roads = ttk.Frame(outer)
        roads.pack(fill="x", pady=2)
        ttk.Label(roads, text="Road", width=8).pack(side="left")
        self.road_a = ttk.Combobox(roads, width=6, state="readonly")
        self.road_a.pack(side="left", padx=2)
        ttk.Label(roads, text="<->").pack(side="left")
        self.road_b = ttk.Combobox(roads, width=6, state="readonly")
        self.road_b.pack(side="left", padx=2)
        ttk.Button(roads, text="Close road",
                   command=self.close_road).pack(side="left", padx=(6, 2))
        ttk.Button(roads, text="Restore road",
                   command=self.restore_road).pack(side="left", padx=2)
        ttk.Label(roads, text="Traffic").pack(side="left", padx=(16, 4))
        self.traffic_var = tk.StringVar(value="3.0")
        ttk.Combobox(roads, textvariable=self.traffic_var, width=5,
                     state="readonly",
                     values=["1.0", "1.5", "2.0", "3.0", "5.0"]).pack(side="left")
        ttk.Button(roads, text="Set traffic",
                   command=self.set_traffic).pack(side="left", padx=6)

        # --- resources ------------------------------------------------
        resources = ttk.Frame(outer)
        resources.pack(fill="x", pady=2)
        ttk.Label(resources, text="Unit", width=8).pack(side="left")
        self.unit_picker = ttk.Combobox(resources, width=8, state="readonly")
        self.unit_picker.pack(side="left", padx=2)
        ttk.Button(resources, text="Disable unit",
                   command=self.disable_unit).pack(side="left", padx=6)

        ttk.Label(resources, text="Hospital").pack(side="left", padx=(16, 4))
        self.hospital_picker = ttk.Combobox(resources, width=8, state="readonly")
        self.hospital_picker.pack(side="left", padx=2)
        ttk.Button(resources, text="Fill hospital",
                   command=self.fill_hospital).pack(side="left", padx=6)

        # --- new demand -----------------------------------------------
        demand = ttk.Frame(outer)
        demand.pack(fill="x", pady=2)
        ttk.Label(demand, text="New call", width=8).pack(side="left")
        self.spawn_node = ttk.Combobox(demand, width=6, state="readonly")
        self.spawn_node.pack(side="left", padx=2)
        self.spawn_type = ttk.Combobox(
            demand, width=12, state="readonly",
            values=[t.value for t in IncidentType])
        self.spawn_type.set(IncidentType.MEDICAL.value)
        self.spawn_type.pack(side="left", padx=2)
        ttk.Button(demand, text="Spawn critical incident",
                   command=self.spawn_incident).pack(side="left", padx=6)
        ttk.Button(demand, text="Spawn burst of 5",
                   command=self.spawn_burst).pack(side="left", padx=2)

    def _build_bottom(self) -> None:
        """
        Two tabs: the live log, and the audit view.

        The audit tab is the answer to "why did it send that unit". Double-click
        any incident in the table above and it opens here, showing that call's
        complete decision chain - who decided what, when, on what grounds, and
        which options were turned down. Reading it should never require opening
        a terminal or the source.
        """
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.notebook = notebook

        # --- tab 1: the live decision log ------------------------------
        log_tab = ttk.Frame(notebook, padding=6)
        notebook.add(log_tab, text="  Decision log  ")
        self.log_box = tk.Text(log_tab, height=10, wrap="none",
                               font=("Consolas", 9), background="#12151b",
                               foreground="#d6dae2", insertbackground="#d6dae2")
        self.log_box.pack(fill="both", expand=True, side="left")
        log_scroll = ttk.Scrollbar(log_tab, orient="vertical",
                                   command=self.log_box.yview)
        log_scroll.pack(side="right", fill="y")
        self.log_box.configure(yscrollcommand=log_scroll.set, state="disabled")

        # --- tab 2: the audit view -------------------------------------
        audit_tab = ttk.Frame(notebook, padding=6)
        notebook.add(audit_tab, text="  Audit: why did it do that?  ")
        self.audit_tab = audit_tab
        audit_tab.columnconfigure(1, weight=1)
        audit_tab.rowconfigure(1, weight=1)

        ttk.Label(audit_tab, text="Incident",
                  font=("", 9, "bold")).grid(row=0, column=0, sticky="w")
        header = ttk.Frame(audit_tab)
        header.grid(row=0, column=1, sticky="ew", padx=(10, 0))
        self.audit_title = ttk.Label(header, text="Pick an incident on the left",
                                     font=("", 10, "bold"))
        self.audit_title.pack(side="left")
        ttk.Button(header, text="Export as text",
                   command=self.export_chain).pack(side="right")
        ttk.Button(header, text="Refresh",
                   command=self._refresh_audit).pack(side="right", padx=6)

        self.audit_list = tk.Listbox(audit_tab, width=14, exportselection=False,
                                     font=("Consolas", 10))
        self.audit_list.grid(row=1, column=0, sticky="ns", pady=(6, 0))
        self.audit_list.bind("<<ListboxSelect>>", self._on_audit_pick)

        self.audit_box = tk.Text(audit_tab, wrap="word", font=("Consolas", 9),
                                 background="#12151b", foreground="#d6dae2",
                                 insertbackground="#d6dae2", padx=8, pady=6)
        self.audit_box.grid(row=1, column=1, sticky="nsew", padx=(10, 0),
                            pady=(6, 0))
        audit_scroll = ttk.Scrollbar(audit_tab, orient="vertical",
                                     command=self.audit_box.yview)
        audit_scroll.grid(row=1, column=2, sticky="ns", pady=(6, 0))
        self.audit_box.configure(yscrollcommand=audit_scroll.set,
                                 state="disabled")

        # Colour the chain so the shape of a decision reads at a glance.
        for tag, colour in (("head", "#8ab4f8"), ("who", "#c7a4ff"),
                            ("why", "#d6dae2"), ("rejected", "#f0897c"),
                            ("ok", "#7ddba1")):
            self.audit_box.tag_configure(tag, foreground=colour)
        self.audit_box.tag_configure("head", font=("Consolas", 10, "bold"),
                                     foreground="#8ab4f8")

        self.audit_incident: Optional[str] = None

    # ==================================================================
    # SIMULATION CONTROL
    # ==================================================================

    def _components(self):
        """
        Which three components this run uses.

        Defaults to the real implementations - the console is what the
        instructor drives, so it must show the system as it actually is.
        Switching to "baseline" reloads with the naive stubs, which makes the
        before/after comparison something that can be demonstrated live rather
        than only quoted from a table.
        """
        if self.components_var.get() == "baseline":
            return FifoPrioritizer(), FirstFreeDispatcher(), BfsRouter()
        return SeverityPrioritizer(), AllocationDispatcher(), DijkstraRouter()

    def load_scenario(self) -> None:
        """Build a fresh engine for the chosen scenario. Also the reset button."""
        self.pause()
        key = self.scenario_var.get()
        scenario = ALL_SCENARIOS[key]()
        prioritizer, dispatcher, router = self._components()

        if self.repository is not None:
            self.repository.start_run(
                scenario=key, prioritizer=prioritizer.name,
                dispatcher=dispatcher.name, router=router.name,
                notes="operator console",
            )

        self.engine = Engine(
            world=scenario.world,
            prioritizer=prioritizer,
            dispatcher=dispatcher,
            router=router,
            config=EngineConfig(tick_seconds=30.0),
            audit=AuditLog(echo=False),
            repository=self.repository,
        )
        for incident in scenario.incidents:
            self.engine.schedule_incident(incident)

        # Scenario events are timed injections. Keep them so a plain run still
        # reproduces, but the operator can fire anything by hand at any moment.
        self._timed_events = sorted(scenario.events, key=lambda e: e[0])

        self._logged = 0
        self._clear_log()
        self._populate_pickers()
        self._say(f"Loaded {scenario.name} - {self.components_var.get()} components")
        self.refresh()

    def toggle_running(self) -> None:
        self.pause() if self.running else self.play()

    def play(self) -> None:
        if self.engine is None or self.running:
            return
        self.running = True
        self.play_button.configure(text="Pause")
        self._schedule_next_tick()

    def pause(self) -> None:
        self.running = False
        if hasattr(self, "play_button"):
            self.play_button.configure(text="Start")
        if self._after_id is not None:
            self.root.after_cancel(self._after_id)
            self._after_id = None

    def step_once(self) -> None:
        """Advance exactly one tick. The demo's most useful button - it lets a
        question be asked between two states of the world."""
        self.pause()
        self._advance()

    def _schedule_next_tick(self) -> None:
        if not self.running:
            return
        delay = SPEEDS.get(self.speed_var.get(), 600)
        self._after_id = self.root.after(delay, self._run_tick)

    def _run_tick(self) -> None:
        if not self.running:
            return
        self._advance()
        self._schedule_next_tick()

    def _advance(self) -> None:
        """One tick of the real engine, plus any scenario-timed injections."""
        if self.engine is None:
            return
        if self.engine._is_finished():
            self.pause()
            self._say("Scenario complete - press Load / Reset to run again")
            self._finish_run()
            return

        while self._timed_events and self._timed_events[0][0] <= self.engine.now:
            self._timed_events.pop(0)[1](self.engine)

        self.engine.tick()
        self.refresh()

    def _finish_run(self) -> None:
        if self.repository is None or self.engine is None:
            return
        metrics = collect_metrics(self.engine, self.scenario_var.get())
        self.repository.finish_run(
            sim_seconds=self.engine.now, ticks=self.engine.tick_count,
            resolved=metrics.resolved, failed=metrics.failed,
        )

    # ==================================================================
    # INJECTION HANDLERS  -  each one is a direct engine call
    # ==================================================================

    def close_road(self) -> None:
        a, b = self.road_a.get(), self.road_b.get()
        if self.engine and a and b:
            self.engine.inject_close_road(a, b)
            self._say(f"Closed {a} <-> {b}")
            self.refresh()

    def restore_road(self) -> None:
        a, b = self.road_a.get(), self.road_b.get()
        if self.engine and a and b:
            self.engine.inject_restore_road(a, b)
            self._say(f"Re-opened {a} <-> {b}")
            self.refresh()

    def set_traffic(self) -> None:
        a, b = self.road_a.get(), self.road_b.get()
        if self.engine and a and b:
            multiplier = float(self.traffic_var.get())
            self.engine.inject_traffic(a, b, multiplier)
            self._say(f"Traffic {a} <-> {b} set to x{multiplier}")
            self.refresh()

    def disable_unit(self) -> None:
        unit_id = self.unit_picker.get()
        if self.engine and unit_id:
            self.engine.inject_disable_unit(unit_id)
            self._say(f"{unit_id} taken out of service")
            self.refresh()

    def fill_hospital(self) -> None:
        node_id = self.hospital_picker.get()
        if self.engine and node_id:
            self.engine.inject_fill_hospital(node_id)
            self._say(f"{node_id} marked full")
            self.refresh()

    def spawn_incident(self) -> None:
        node = self.spawn_node.get()
        if not (self.engine and node):
            return
        incident_type = IncidentType(self.spawn_type.get())
        self.engine.inject_spawn_incident(
            node_id=node,
            incident_type=incident_type,
            required_unit=_unit_for(incident_type),
            victims=3,
            requires_transport=incident_type in (IncidentType.MEDICAL,
                                                 IncidentType.ACCIDENT),
        )
        self._say(f"Spawned {incident_type.value} at {node}")
        self.refresh()

    def spawn_burst(self) -> None:
        """Five calls at once - the 'demand exceeds resources' demo step."""
        if self.engine is None:
            return
        nodes = [n for n, node in self.engine.world.nodes.items()
                 if node.kind == NodeKind.INTERSECTION][:5]
        for index, node in enumerate(nodes):
            incident_type = (IncidentType.MEDICAL if index % 2 == 0
                             else IncidentType.ACCIDENT)
            self.engine.inject_spawn_incident(
                node_id=node, incident_type=incident_type,
                required_unit=_unit_for(incident_type),
                victims=2, requires_transport=True,
            )
        self._say(f"Spawned a burst of {len(nodes)} calls")
        self.refresh()

    # ==================================================================
    # REDRAW  -  always reads the world, never remembers it
    # ==================================================================

    def refresh(self) -> None:
        if self.engine is None:
            return
        self._draw_clock()
        self._draw_incidents()
        self._draw_units()
        self._draw_new_log_lines()
        self._refresh_audit_list()
        if self.audit_incident:
            self._refresh_audit()

    def _draw_clock(self) -> None:
        total = int(self.engine.now)
        self.clock_label.configure(
            text=f"{total // 3600:02d}:{total % 3600 // 60:02d}:{total % 60:02d}")
        self.tick_label.configure(text=f"tick {self.engine.tick_count}")

    def _draw_incidents(self) -> None:
        table = self.incident_table
        table.delete(*table.get_children())

        incidents = list(self.engine.world.incidents.values())
        # waiting calls first, then active, then closed - the operator cares
        # about what still needs a decision
        order = {IncidentStatus.QUEUED: 0, IncidentStatus.REPORTED: 1,
                 IncidentStatus.ASSIGNED: 2, IncidentStatus.ON_SCENE: 3,
                 IncidentStatus.TRANSPORTING: 4, IncidentStatus.FAILED: 5,
                 IncidentStatus.RESOLVED: 6}
        incidents.sort(key=lambda i: (order.get(i.status, 9), i.reported_at))

        for incident in incidents:
            if incident.status in (IncidentStatus.RESOLVED, IncidentStatus.FAILED):
                waited = "-"
            else:
                waited = f"{self.engine.now - incident.reported_at:.0f}s"
            reason = (incident.failure_reason or incident.severity_rationale
                      or self._latest_reason(incident.incident_id))
            table.insert(
                "", "end",
                values=(incident.incident_id, incident.incident_type.value,
                        incident.node_id, incident.status.value,
                        incident.assigned_unit_id or "-", waited, reason),
                tags=(incident.status.value,),
            )

    def _latest_reason(self, incident_id: str) -> str:
        records = self.engine.audit.for_incident(incident_id)
        return records[-1].rationale if records else ""

    def _draw_units(self) -> None:
        table = self.unit_table
        table.delete(*table.get_children())
        for unit in sorted(self.engine.world.units.values(),
                           key=lambda u: u.unit_id):
            busy = (f"{unit.total_busy_seconds / self.engine.now * 100:.0f}%"
                    if self.engine.now else "0%")
            table.insert(
                "", "end",
                values=(unit.unit_id, unit.unit_type.value, unit.status.value,
                        unit.current_node, unit.assigned_incident_id or "-", busy),
                tags=(unit.status.value,),
            )

    def _draw_new_log_lines(self) -> None:
        """Append only what is new, so the log does not flicker or rewind."""
        records = self.engine.audit.all()
        if len(records) <= self._logged:
            return
        self.log_box.configure(state="normal")
        for record in records[self._logged:]:
            self.log_box.insert("end", record.as_line() + "\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")
        self._logged = len(records)

    def _clear_log(self) -> None:
        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.configure(state="disabled")
        self.audit_incident = None
        self.audit_list.delete(0, "end")
        self._write_audit([("why", "Pick an incident on the left, or "
                                   "double-click one in the table above.\n")])
        self.audit_title.configure(text="Pick an incident on the left")

    # ==================================================================
    # AUDIT VIEW  -  "why did it send that unit"
    # ==================================================================

    def _on_incident_double_click(self, _event=None) -> None:
        """Double-click a row above to open its decision chain below."""
        selection = self.incident_table.selection()
        if not selection:
            return
        incident_id = self.incident_table.item(selection[0], "values")[0]
        self.open_audit(incident_id)

    def open_audit(self, incident_id: str) -> None:
        """Show one incident's chain and bring the audit tab to the front."""
        self.audit_incident = incident_id
        self._refresh_audit()
        self.notebook.select(self.audit_tab)

        # keep the list selection in step with what is displayed
        for index in range(self.audit_list.size()):
            if self.audit_list.get(index) == incident_id:
                self.audit_list.selection_clear(0, "end")
                self.audit_list.selection_set(index)
                self.audit_list.see(index)
                break

    def _on_audit_pick(self, _event=None) -> None:
        selection = self.audit_list.curselection()
        if selection:
            self.audit_incident = self.audit_list.get(selection[0])
            self._refresh_audit()

    def _refresh_audit_list(self) -> None:
        """Keep the incident list current without disturbing the selection."""
        if self.engine is None:
            return
        wanted = sorted(self.engine.world.incidents)
        current = list(self.audit_list.get(0, "end"))
        if wanted == current:
            return
        selected = self.audit_incident
        self.audit_list.delete(0, "end")
        for incident_id in wanted:
            self.audit_list.insert("end", incident_id)
        if selected in wanted:
            index = wanted.index(selected)
            self.audit_list.selection_set(index)

    def _refresh_audit(self) -> None:
        """Rebuild the chain for whichever incident is currently selected."""
        if self.engine is None or not self.audit_incident:
            return

        incident_id = self.audit_incident
        records = self.engine.audit.for_incident(incident_id)
        incident = self.engine.world.incidents.get(incident_id)

        if incident is not None:
            summary = (f"{incident_id}  -  {incident.incident_type.value} at "
                       f"{incident.node_id}, {incident.victims} victim(s)  -  "
                       f"{incident.status.value}")
        else:
            summary = f"{incident_id}  -  not yet reported"
        self.audit_title.configure(text=summary)

        if not records:
            self._write_audit([("why", f"No decisions recorded for "
                                       f"{incident_id} yet.\n")])
            return

        lines = [("head", f"Decision chain for {incident_id}\n"),
                 ("why", "=" * 78 + "\n")]

        if incident is not None and incident.severity_rationale:
            lines.append(("ok", f"Severity: {incident.severity_rationale}\n\n"))

        for record in records:
            stamp = f"[{record.sim_time:7.0f}s] "
            lines.append(("who", f"{stamp}{record.component}  {record.action}\n"))
            if record.chosen:
                lines.append(("ok", f"{'':>11}chose {record.chosen}\n"))
            if record.rationale:
                lines.append(("why", f"{'':>11}{record.rationale}\n"))
            if record.error and record.error != "NONE":
                lines.append(("rejected", f"{'':>11}error: {record.error}\n"))
            for candidate in record.considered:
                lines.append((
                    "rejected",
                    f"{'':>11}  rejected {candidate.get('option_id')}: "
                    f"{candidate.get('reason')}\n"))
            lines.append(("why", "\n"))

        if incident is not None:
            closing = []
            if incident.response_seconds is not None:
                closing.append(f"responded in {incident.response_seconds:.0f}s")
            if incident.destination_hospital:
                closing.append(f"transported to {incident.destination_hospital}")
            if incident.failure_reason:
                closing.append(f"failed: {incident.failure_reason}")
            if closing:
                lines.append(("head", "Outcome: " + "; ".join(closing) + "\n"))

        self._write_audit(lines)

    def _write_audit(self, parts) -> None:
        self.audit_box.configure(state="normal")
        self.audit_box.delete("1.0", "end")
        for tag, text in parts:
            self.audit_box.insert("end", text, tag)
        self.audit_box.configure(state="disabled")

    def chain_as_text(self, incident_id: str) -> str:
        """The same chain as plain text - for the report, and for export."""
        records = self.engine.audit.for_incident(incident_id)
        out = [f"Decision chain for {incident_id}", "=" * 78]
        incident = self.engine.world.incidents.get(incident_id)
        if incident is not None:
            out.append(f"{incident.incident_type.value} at {incident.node_id}, "
                       f"{incident.victims} victim(s), "
                       f"status {incident.status.value}")
            if incident.severity_rationale:
                out.append(f"Severity: {incident.severity_rationale}")
            out.append("")
        for record in records:
            out.append(record.as_line())
            for candidate in record.considered:
                out.append(f"{'':>13}   rejected {candidate.get('option_id')}: "
                           f"{candidate.get('reason')}")
        return "\n".join(out) + "\n"

    def export_chain(self) -> None:
        """Save the displayed chain as readable text."""
        if self.engine is None or not self.audit_incident:
            self._say("Pick an incident first")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            initialfile=f"{self.audit_incident}_decision_chain.txt",
            filetypes=[("Text file", "*.txt"), ("All files", "*.*")],
            title=f"Export {self.audit_incident}",
        )
        if not path:
            return
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(self.chain_as_text(self.audit_incident))
        self._say(f"Exported {self.audit_incident} to {path}")

    def _populate_pickers(self) -> None:
        """Fill the dropdowns from the world, so the operator can only pick
        things that actually exist."""
        world = self.engine.world
        nodes = sorted(world.nodes)
        intersections = sorted(n for n, node in world.nodes.items()
                               if node.kind == NodeKind.INTERSECTION)

        self.road_a.configure(values=nodes)
        self.road_b.configure(values=nodes)
        self.unit_picker.configure(values=sorted(world.units))
        self.hospital_picker.configure(values=sorted(world.hospitals))
        self.spawn_node.configure(values=intersections)

        # Sensible defaults: the bottleneck road the sample city was built
        # around, so "close a road" does something visible on the first click.
        if "N06" in nodes and "N07" in nodes:
            self.road_a.set("N06")
            self.road_b.set("N07")
        elif len(nodes) >= 2:
            self.road_a.set(nodes[0])
            self.road_b.set(nodes[1])
        if world.units:
            self.unit_picker.set(sorted(world.units)[0])
        if world.hospitals:
            self.hospital_picker.set(sorted(world.hospitals)[0])
        if intersections:
            self.spawn_node.set(intersections[0])

    def _say(self, message: str) -> None:
        self.status_label.configure(text=message)


def _unit_for(incident_type: IncidentType) -> UnitType:
    """Which kind of unit a hand-spawned call asks for."""
    return {
        IncidentType.MEDICAL: UnitType.AMBULANCE,
        IncidentType.ACCIDENT: UnitType.AMBULANCE,
        IncidentType.FIRE: UnitType.FIRE_TRUCK,
        IncidentType.HAZMAT: UnitType.HAZMAT_TEAM,
        IncidentType.RESCUE: UnitType.RESCUE_VAN,
    }.get(incident_type, UnitType.AMBULANCE)


def launch(repository=None) -> None:
    """Entry point used by `python main.py --ui`."""
    root = tk.Tk()
    try:
        ttk.Style().theme_use("vista")
    except tk.TclError:
        pass  # any platform default is fine
    console = OperatorConsole(root, repository=repository)

    def on_close() -> None:
        console.pause()
        console._finish_run()
        if repository is not None:
            repository.close()
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_close)
    root.mainloop()
