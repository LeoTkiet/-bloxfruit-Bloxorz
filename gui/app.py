"""Main window: stage selection, manual play, solver buttons, metrics and solution replay."""
from __future__ import annotations

import queue
import sys
import threading
import time
import tkinter as tk
import traceback
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from . import theme
from .backend import (BRIDGE, FLOOR, FRAGILE, GOAL, HEAVY, SOFT, SOLVER_LABELS, SPLIT,
                      SPLIT_SWITCH, SWITCH, Backend, InvalidSolution, Trace, level_view,
                      keep_piece_order, load_backend, stage_description, state_view)
from .board_view import BoardView, Legend

STAGE_GROUPS = ("basic", "advanced", "split", "hard", "demo")   # play order of the levels/ sub-folders
# The stage list, in the order of the demo video; Open... still loads every other stage file.
DEMO_STAGES = ("demo/03_classic_stage1", "demo/04_fragile", "demo/05_soft_switch_bridge",
               "demo/06_heavy_switch", "split/01_split_intro", "demo/08_showcase",
               "advanced/02_fragile_band", "hard/01_grand_maze", "split/04_heavy_split_bridges",
               "demo/09_unsolvable")

ORIENTATION_TEXT = {"STANDING": "Standing", "HORIZONTAL": "Lying horizontally",
                    "VERTICAL": "Lying vertically"}
TILE_TEXT = {FLOOR: "Floor (island)", GOAL: "Goal hole (treasure)",
             FRAGILE: "Fragile tile - thin ice (breaks if Buggy stands on it)",
             BRIDGE: "Bridge", SOFT: "Soft switch", HEAVY: "Heavy switch",
             SPLIT_SWITCH: "Split switch"}
METRICS = (("algorithm", "Algorithm"), ("found", "Found"), ("solution_length", "Solution length"),
           ("path_cost", "Path cost"), ("expanded_nodes", "Expanded nodes"),
           ("search_time", "Search time"), ("peak_memory", "Peak memory"))
KEYMAP = {"UP": ("<Up>", "<w>", "<W>"), "DOWN": ("<Down>", "<s>", "<S>"),
          "LEFT": ("<Left>", "<a>", "<A>"), "RIGHT": ("<Right>", "<d>", "<D>"),
          SWITCH: ("<space>",)}


def _apply_style(root: tk.Tk) -> None:
    """Dark navy panels with light borders and gold accents, matching the pixel-art board."""
    root.configure(background=theme.PANEL)
    style = ttk.Style(root)
    style.theme_use("clam")
    style.configure(".", background=theme.PANEL, foreground=theme.BOARD_TEXT, font=theme.FONT,
                    bordercolor=theme.BORDER, lightcolor=theme.PANEL, darkcolor=theme.PANEL,
                    troughcolor=theme.DEEP, focuscolor=theme.GOLD)
    style.configure("TLabelframe", bordercolor=theme.BORDER, borderwidth=2, relief="solid")
    style.configure("TLabelframe.Label", foreground=theme.GOLD, font=theme.FONT_BOLD)
    style.configure("TButton", background=theme.BUTTON, lightcolor=theme.BUTTON,
                    darkcolor=theme.BUTTON, padding=(6, 3))
    style.map("TButton",
              background=[("disabled", theme.PANEL), ("pressed", theme.GOLD),
                          ("active", theme.BUTTON_HOVER)],
              foreground=[("disabled", theme.MUTED_TEXT), ("pressed", theme.INK)])
    style.map("TCombobox", fieldbackground=[("readonly", theme.DEEP)],
              foreground=[("readonly", theme.BOARD_TEXT)],
              selectbackground=[("readonly", theme.DEEP)],
              selectforeground=[("readonly", theme.BOARD_TEXT)])
    style.configure("TCombobox", background=theme.BUTTON, arrowcolor=theme.BOARD_TEXT)
    style.configure("TScrollbar", background=theme.BUTTON, lightcolor=theme.BUTTON,
                    darkcolor=theme.BUTTON, bordercolor=theme.PANEL, arrowcolor=theme.BOARD_TEXT)
    style.configure("Horizontal.TScale", background=theme.GOLD)
    root.option_add("*TCombobox*Listbox.background", theme.DEEP)
    root.option_add("*TCombobox*Listbox.foreground", theme.BOARD_TEXT)
    root.option_add("*TCombobox*Listbox.selectBackground", theme.GOLD)
    root.option_add("*TCombobox*Listbox.selectForeground", theme.INK)
    root.option_add("*TCombobox*Listbox.font", theme.FONT)


def find_stages(levels_dir: Path) -> list[Path]:
    """Every JSON stage under levels/, ordered by STAGE_GROUPS and then by file name."""
    def order(path: Path):
        group = path.relative_to(levels_dir).parts[0]
        rank = STAGE_GROUPS.index(group) if group in STAGE_GROUPS else len(STAGE_GROUPS)
        return rank, path.as_posix()
    return sorted(levels_dir.rglob("*.json"), key=order)


def demo_stages(levels_dir: Path) -> list[Path]:
    paths = (levels_dir / f"{name}.json" for name in DEMO_STAGES)
    return [path for path in paths if path.is_file()]


def _fmt_number(value) -> str:
    if value is None:
        return "–"
    if isinstance(value, float) and not value.is_integer():
        return f"{value:,.2f}"
    return f"{int(value):,}"


def _fmt_time(seconds) -> str:
    if seconds is None:
        return "–"
    return f"{seconds * 1000:,.1f} ms" if seconds < 1 else f"{seconds:,.2f} s"


def _fmt_bytes(size) -> str:
    if size is None:
        return "–"
    return f"{size / 1024:,.1f} KB" if size < 1024 ** 2 else f"{size / 1024 ** 2:,.2f} MB"


class App:
    def __init__(self, root: tk.Tk, backend: Backend, levels_dir: Path, stage: Path | None = None):
        self.root, self.backend = root, backend
        self.levels_dir = levels_dir
        self.stage_paths: list[Path] = demo_stages(levels_dir)
        self.path: Path | None = None
        self.level = self.lview = self.initial = self.state = None
        self.history: list = []               # previous states, for undo and the move counter
        self.view = None                      # what the board shows, split pieces kept in their slots
        self.game_over: str | None = None     # None | "win" | "lose"
        self.trace: Trace | None = None
        self.replay_index: int | None = None  # None while playing manually
        self.playing = False
        self._play_job = None
        self.solving: str | None = None
        self._solve_started = 0.0
        self._results: queue.Queue = queue.Queue()

        self._build()
        self._bind_keys()
        first = stage or (self.stage_paths[0] if self.stage_paths else None)
        if first is not None:
            self.load_stage(Path(first).resolve())
        else:
            self.status_var.set("No stages in levels/ - use Open... to load a stage file.")

    # ---- layout -------------------------------------------------------------------------------
    def _build(self) -> None:
        root = self.root
        root.title("Bloxorz Solver - CSC14003 Project 1")
        _apply_style(root)
        root.columnconfigure(0, weight=1)
        root.rowconfigure(0, weight=1)

        left = tk.Frame(root, background=theme.BG)
        left.grid(row=0, column=0, sticky="nsew")
        left.columnconfigure(0, weight=1)
        left.rowconfigure(2, weight=1)
        self.title_label = tk.Label(left, background=theme.BG, foreground=theme.GOLD,
                                    font=theme.FONT_TITLE, anchor="w")
        self.title_label.grid(row=0, column=0, sticky="ew", padx=18, pady=(12, 0))
        self.desc_label = tk.Label(left, background=theme.BG, foreground=theme.MUTED_TEXT,
                                   font=theme.FONT, anchor="w", justify="left")
        self.desc_label.grid(row=1, column=0, sticky="ew", padx=18)
        self.board = BoardView(left, on_hover=self._on_hover)
        self.board.grid(row=2, column=0, sticky="nsew")
        Legend(left).grid(row=3, column=0)
        tk.Label(left, background=theme.BG, foreground=theme.MUTED_TEXT, font=theme.FONT_SMALL,
                 text="Arrows / WASD: roll    Space: switch piece    Z: undo    R: restart    "
                      "Enter: next stage    P: play / pause replay\n"
                      "Drag: turn camera    Wheel: zoom    Q / E: turn left / right    "
                      "V or double-click: reset view").grid(row=4, column=0, pady=(4, 10))

        side = ttk.Frame(root, padding=(12, 10))
        side.grid(row=0, column=1, sticky="ns")

        box = ttk.LabelFrame(side, text="Game", padding=8)
        box.pack(fill="x")
        self.stage_box = ttk.Combobox(box, state="readonly", width=34,
                                      values=[self._stage_label(p) for p in self.stage_paths])
        self.stage_box.grid(row=0, column=0, columnspan=3, sticky="ew", pady=(0, 6))
        self.stage_box.bind("<<ComboboxSelected>>", self._on_stage_selected)
        self.new_btn = self._button(box, "New Game", self.new_game)
        self.restart_btn = self._button(box, "Restart", self.restart)
        self.open_btn = self._button(box, "Open...", self.open_stage)
        for i, btn in enumerate((self.new_btn, self.restart_btn, self.open_btn)):
            btn.grid(row=1, column=i, sticky="ew", padx=1)
            box.columnconfigure(i, weight=1)
        self.moves_var = tk.StringVar(value="Moves: 0")
        ttk.Label(box, textvariable=self.moves_var, font=theme.FONT_BOLD).grid(
            row=2, column=0, columnspan=2, sticky="w", pady=(6, 0))
        self.undo_btn = self._button(box, "Undo", self.undo)
        self.undo_btn.grid(row=2, column=2, sticky="ew", padx=1, pady=(6, 0))

        box = ttk.LabelFrame(side, text="Solvers", padding=8)
        box.pack(fill="x", pady=(8, 0))
        self.solver_btns: dict[str, ttk.Button] = {}
        for i, label in enumerate(SOLVER_LABELS):
            btn = self._button(box, f"Solve {label}", lambda name=label: self.run_solver(name))
            btn.grid(row=i // 3, column=i % 3, sticky="ew", padx=1, pady=1)
            self.solver_btns[label] = btn
        box.columnconfigure((0, 1, 2), weight=1)
        self.solver_status = tk.StringVar()
        ttk.Label(box, textvariable=self.solver_status, wraplength=270, justify="left").grid(
            row=2, column=0, columnspan=3, sticky="w", pady=(6, 0))

        box = ttk.LabelFrame(side, text="Result", padding=8)
        box.pack(fill="x", pady=(8, 0))
        self.metric_vars: dict[str, tk.StringVar] = {}
        for i, (key, text) in enumerate(METRICS):
            ttk.Label(box, text=text).grid(row=i, column=0, sticky="w")
            var = tk.StringVar(value="–")
            ttk.Label(box, textvariable=var, font=theme.FONT_BOLD).grid(
                row=i, column=1, sticky="e")
            self.metric_vars[key] = var
        box.columnconfigure(1, weight=1)

        box = ttk.LabelFrame(side, text="Solution replay", padding=8)
        box.pack(fill="both", expand=True, pady=(8, 0))
        box.columnconfigure(0, weight=1)
        box.rowconfigure(0, weight=1)
        self.moves_list = tk.Listbox(box, height=6, activestyle="none", exportselection=False,
                                     takefocus=0, font=theme.FONT, background=theme.DEEP,
                                     foreground=theme.BOARD_TEXT, selectbackground=theme.GOLD,
                                     selectforeground=theme.INK, highlightthickness=0,
                                     borderwidth=0)
        scroll = ttk.Scrollbar(box, command=self.moves_list.yview)
        self.moves_list.configure(yscrollcommand=scroll.set)
        self.moves_list.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")
        self.moves_list.bind("<<ListboxSelect>>", self._on_list_select)

        controls = ttk.Frame(box)
        controls.grid(row=1, column=0, columnspan=2, pady=(6, 0))
        self.replay_btns = [
            self._button(controls, "« Start", lambda: self._replay_jump(0), width=7),
            self._button(controls, "‹ Prev", lambda: self._replay_step(-1), width=7),
            self._button(controls, "Play", self.toggle_play, width=7),
            self._button(controls, "Next ›", lambda: self._replay_step(1), width=7),
            self._button(controls, "End »", lambda: self._replay_jump(-1), width=7),
        ]
        self.play_btn = self.replay_btns[2]
        for i, btn in enumerate(self.replay_btns):
            btn.grid(row=0, column=i, padx=1)
        speed = ttk.Frame(box)
        speed.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        self.speed_var = tk.DoubleVar(value=3.0)
        self.speed_text = tk.StringVar()
        ttk.Label(speed, text="Speed").pack(side="left")
        ttk.Scale(speed, from_=1, to=10, variable=self.speed_var, takefocus=0,
                  command=lambda _v: self._update_speed_text()).pack(
            side="left", fill="x", expand=True, padx=6)
        ttk.Label(speed, textvariable=self.speed_text, width=11).pack(side="left")
        self._update_speed_text()

        bar = ttk.Frame(root, padding=(10, 3))
        bar.grid(row=1, column=0, columnspan=2, sticky="ew")
        self.status_var = tk.StringVar()
        self.hover_var = tk.StringVar()
        ttk.Label(bar, textvariable=self.status_var).pack(side="left")
        ttk.Label(bar, textvariable=self.hover_var, foreground=theme.MUTED_TEXT).pack(side="right")
        self._clear_solution()
        self.board.focus_set()

    def _stage_label(self, path: Path) -> str:
        """`basic/01_horizontal_intro` for stages under levels/, the file name otherwise."""
        try:
            return path.relative_to(self.levels_dir).with_suffix("").as_posix()
        except ValueError:
            return path.stem

    @staticmethod
    def _button(parent, text, command, width=None) -> ttk.Button:
        # takefocus=False keeps Space/arrows from re-triggering the last clicked button.
        return ttk.Button(parent, text=text, command=command, width=width, takefocus=False)

    def _bind_keys(self) -> None:
        for key, sequences in KEYMAP.items():
            for seq in sequences:
                self.root.bind(seq, lambda e, k=key: self._key(e, lambda: self.move(k)))
        bindings = {self.undo: ("<z>", "<Z>", "<Control-z>", "<BackSpace>"),
                    self.restart: ("<r>", "<R>"), self.next_stage: ("<Return>",),
                    self.toggle_play: ("<p>", "<P>"),
                    lambda: self.board.orbit(-15): ("<q>", "<Q>"),
                    lambda: self.board.orbit(15): ("<e>", "<E>"),
                    self.board.reset_view: ("<v>", "<V>")}
        for handler, sequences in bindings.items():
            for seq in sequences:
                self.root.bind(seq, lambda e, h=handler: self._key(e, h))
        self.root.protocol("WM_DELETE_WINDOW", self.close)

    def _key(self, event, handler):
        if isinstance(event.widget, (str, ttk.Combobox, ttk.Entry, tk.Entry)):
            return None
        handler()
        return "break"

    # ---- stages -------------------------------------------------------------------------------
    def load_stage(self, path: Path) -> bool:
        try:
            level = self.backend.load_level(str(path))
            initial = self.backend.initial_state(level)
            lview = level_view(level, stage_description(path))
        except Exception as exc:  # show any loader/engine error instead of crashing the GUI
            messagebox.showerror("Cannot load stage", f"{path.name}\n\n{exc}")
            return False
        self._stop_play()
        self.path, self.level, self.lview, self.initial = path, level, lview, initial
        if path not in self.stage_paths:
            self.stage_paths.append(path)
            self.stage_box["values"] = [self._stage_label(p) for p in self.stage_paths]
        self.stage_box.current(self.stage_paths.index(path))
        self.title_label["text"] = lview.name
        self.desc_label["text"] = lview.description
        self._clear_solution()
        self.view = None
        self.restart()
        return True

    def new_game(self) -> None:
        if self.path is not None and not self.solving:
            self.load_stage(self.path)

    def open_stage(self) -> None:
        if self.solving:
            return
        name = filedialog.askopenfilename(title="Open stage", filetypes=[("Stage files", "*.json"),
                                                                        ("All files", "*.*")])
        if name:
            self.load_stage(Path(name).resolve())
        self.board.focus_set()

    def next_stage(self) -> None:
        if self.game_over != "win" or self.solving or self.path not in self.stage_paths:
            return
        i = self.stage_paths.index(self.path)
        if i + 1 < len(self.stage_paths):
            self.load_stage(self.stage_paths[i + 1])

    def restart(self) -> None:
        if self.level is None or self.solving:
            return
        self._stop_play()
        self.state, self.history, self.game_over = self.initial, [], None
        self.replay_index = None
        self.moves_list.selection_clear(0, "end")
        self.board.clear_banner()
        self.board.show(self.lview, self._state_view())
        self._update_info()

    def _on_stage_selected(self, _event) -> None:
        index = self.stage_box.current()
        if 0 <= index < len(self.stage_paths) and self.stage_paths[index] != self.path:
            self.load_stage(self.stage_paths[index])
        self.board.focus_set()

    # ---- manual play --------------------------------------------------------------------------
    def move(self, key: str) -> None:
        if self.level is None or self.solving or self.board.animating:
            return
        if self.replay_index is not None:
            self._leave_replay()
        if self.game_over:
            self.root.bell()
            return
        try:
            step = self.backend.successor_for(self.level, self.state, key)
        except Exception as exc:
            self._engine_error(exc)
            return
        if step is None:
            if key == SWITCH:
                return  # nothing to switch: the block is not split
            self.game_over = "lose"
            self.status_var.set(f"Illegal move {key.title()}: Buggy falls into the sea.")
            self.board.animate_fall(key, done=lambda: self.board.set_banner(
                "Buggy fell into the sea!",
                "Devil Fruit users can't swim. Press Z to undo the move or R to restart.", "lose"))
            return
        self.history.append(self.state)
        self.state = step[1]
        self.board.animate_to(self._state_view(), done=self._after_manual_move)
        self._update_info()

    def _after_manual_move(self) -> None:
        try:
            won = self.backend.is_goal(self.level, self.state)
        except Exception as exc:
            self._engine_error(exc)
            return
        if won:
            self.game_over = "win"
            moves = len(self.history)
            self.board.animate_sink(done=lambda: self.board.set_banner(
                "Stage complete!", f"Buggy reached the treasure in {moves} moves.  "
                                   "Enter: next stage  -  R: play again", "win"))

    def undo(self) -> None:
        if self.level is None or self.solving:
            return
        if self.replay_index is not None:
            self._leave_replay()
        if self.game_over == "lose":
            self.game_over = None          # the fatal move was never applied
        elif self.history:
            self.state = self.history.pop()
            self.game_over = None
        else:
            return
        self.board.clear_banner()
        self.board.show(self.lview, self._state_view())
        self._update_info()

    # ---- solvers ------------------------------------------------------------------------------
    def run_solver(self, label: str) -> None:
        solve = self.backend.solvers.get(label)
        if solve is None or self.level is None or self.solving:
            return
        self._stop_play()
        self.solving = label
        self._set_busy(True)
        self._solve_started = time.perf_counter()
        level, initial = self.level, self.initial

        def work():
            try:
                outcome, details = solve(level, initial), ""
            except Exception as exc:
                outcome, details = exc, traceback.format_exc()
            self._results.put((label, outcome, details))
        threading.Thread(target=work, daemon=True).start()
        self._poll_solver()

    def _poll_solver(self) -> None:
        try:
            label, outcome, details = self._results.get_nowait()
        except queue.Empty:
            elapsed = time.perf_counter() - self._solve_started
            self.solver_status.set(f"Running {self.solving}...  {elapsed:.1f} s")
            self.root.after(80, self._poll_solver)
            return
        self.solving = None
        self._set_busy(False)
        self.show_result(label, outcome, details)

    def show_result(self, label: str, outcome, details: str = "") -> None:
        if isinstance(outcome, BaseException):
            self.solver_status.set(f"{label} raised {type(outcome).__name__}: {outcome}")
            messagebox.showerror(f"{label} failed", details[-2000:] or str(outcome))
            return
        try:
            trace = self.backend.trace_solution(self.level, self.initial, outcome, label)
        except InvalidSolution as exc:
            self.solver_status.set(str(exc))
            messagebox.showerror("Invalid solution", str(exc))
            return
        except Exception as exc:
            self._engine_error(exc)
            return

        self.trace = trace
        self._show_metrics(trace)
        self.moves_list.delete(0, "end")
        self.restart()
        if not trace.found:
            self.moves_list.insert("end", "  (no solution)")
            self.solver_status.set(f"{label}: no path to the goal exists from the start.")
            expanded = _fmt_number(trace.metrics.get("expanded_nodes"))
            self.board.set_banner("No solution found",
                                  f"{label} expanded {expanded} states without reaching the goal.")
            return
        self.moves_list.insert("end", "  0. Start")
        for i, move in enumerate(trace.moves, 1):
            self.moves_list.insert("end", f"{i:>3}. {move}")
        message = f"{label}: found {len(trace.moves)} moves - replaying."
        if trace.warning:
            message += f"\nWarning: {trace.warning}"
        self.solver_status.set(message)
        self._goto(0)
        self.toggle_play()

    def _show_metrics(self, trace: Trace) -> None:
        m = trace.metrics
        values = {
            "algorithm": trace.algorithm,
            "found": "Yes" if trace.found else "No",
            "solution_length": _fmt_number(m.get("solution_length")) if trace.found else "–",
            "path_cost": _fmt_number(m.get("path_cost")) if trace.found else "–",
            "expanded_nodes": _fmt_number(m.get("expanded_nodes")),
            "search_time": _fmt_time(m.get("search_time")),
            "peak_memory": _fmt_bytes(m.get("peak_memory")),
        }
        for key, var in self.metric_vars.items():
            var.set(values[key])

    def _clear_solution(self) -> None:
        self.trace = None
        self.moves_list.delete(0, "end")
        for var in self.metric_vars.values():
            var.set("–")
        status = "Solvers start from the stage's start position."
        if self.backend.unavailable:
            status += "\nUnavailable: " + "; ".join(
                f"{label} ({why})" for label, why in self.backend.unavailable.items())
        self.solver_status.set(status)
        for label, btn in self.solver_btns.items():
            btn.state(["!disabled"] if self.backend.solvers.get(label) else ["disabled"])

    # ---- replay -------------------------------------------------------------------------------
    def toggle_play(self) -> None:
        if self.playing:
            self._stop_play()
            return
        if self.trace is None or not self.trace.found or self.solving:
            return
        if self.replay_index is None or self.replay_index >= len(self.trace.states) - 1:
            self._goto(0)
        self.playing = True
        self.play_btn["text"] = "Pause"
        self._play_job = self.root.after(self._delay_ms(), self._play_tick)

    def _play_tick(self) -> None:
        self._play_job = None
        if self.playing and self.replay_index is not None:
            self._goto(self.replay_index + 1, animate=True)

    def _stop_play(self) -> None:
        self.playing = False
        if self._play_job is not None:
            self.root.after_cancel(self._play_job)
            self._play_job = None
        self.play_btn["text"] = "Play"

    def _replay_step(self, delta: int) -> None:
        if self.trace is None or not self.trace.found:
            return
        self._stop_play()
        current = self.replay_index if self.replay_index is not None else 0
        self._goto(current + delta, animate=True)

    def _replay_jump(self, index: int) -> None:
        if self.trace is None or not self.trace.found:
            return
        self._stop_play()
        self._goto(index if index >= 0 else len(self.trace.states) - 1)

    def _goto(self, index: int, animate: bool = False) -> None:
        if self.trace is None or not self.trace.found or self.solving:
            return
        index = max(0, min(index, len(self.trace.states) - 1))
        previous, self.replay_index = self.replay_index, index
        self.state = self.trace.states[index]
        self.history = list(self.trace.states[:index])   # manual play can continue from here
        self.game_over = None
        self.board.clear_banner()
        self.moves_list.selection_clear(0, "end")
        self.moves_list.selection_set(index)
        self.moves_list.see(index)
        view = self._state_view()
        tween = animate and previous is not None and abs(index - previous) == 1
        if tween and not self.board.animating:
            self.board.animate_to(view, duration=self._anim_ms(), done=self._after_replay_step)
        else:
            self.board.show(self.lview, view)
            self._after_replay_step()
        self._update_info()

    def _after_replay_step(self) -> None:
        if self.replay_index is None or self.trace is None:
            return
        if self.replay_index == len(self.trace.states) - 1:
            self._stop_play()
            self.game_over = "win"
            title = f"Solved by {self.trace.algorithm}"
            cost = _fmt_number(self.trace.metrics.get("path_cost"))
            subtitle = f"{len(self.trace.moves)} moves  -  path cost {cost}"
            self.board.animate_sink(done=lambda: self.board.set_banner(title, subtitle, "win"))
        elif self.playing:
            self._play_job = self.root.after(self._delay_ms(), self._play_tick)

    def _leave_replay(self) -> None:
        self._stop_play()
        self.replay_index = None
        self.moves_list.selection_clear(0, "end")

    def _on_list_select(self, _event) -> None:
        selection = self.moves_list.curselection()
        if selection and self.trace is not None and self.trace.found:
            self._stop_play()
            self._goto(selection[0])
        self.board.focus_set()

    def _delay_ms(self) -> int:
        return int(1000 / self.speed_var.get())

    def _anim_ms(self) -> int:
        return min(240, int(self._delay_ms() * 0.7))

    def _update_speed_text(self) -> None:
        self.speed_text.set(f"{self.speed_var.get():.1f} moves/s")

    # ---- misc ---------------------------------------------------------------------------------
    def _set_busy(self, busy: bool) -> None:
        flag = ["disabled"] if busy else ["!disabled"]
        for btn in (self.new_btn, self.restart_btn, self.open_btn, self.undo_btn, *self.replay_btns):
            btn.state(flag)
        for label, btn in self.solver_btns.items():
            btn.state(flag if self.backend.solvers.get(label) else ["disabled"])
        self.stage_box.state(["disabled"] if busy else ["!disabled", "readonly"])

    def _state_view(self):
        """The view of self.state for the board, the head and the legs kept in their slots."""
        self.view = keep_piece_order(self.view, state_view(self.level, self.state))
        return self.view

    def _update_info(self) -> None:
        self.moves_var.set(f"Moves: {len(self.history)}")
        view = self._state_view()
        if view.orientation == SPLIT:
            marks = ["", ""]
            marks[view.active] = " (active)"
            text = (f"Bara Bara split: head {view.cells[0]}{marks[0]}, "
                    f"legs {view.cells[1]}{marks[1]}")
        else:
            cells = " + ".join(str(cell) for cell in view.cells)
            text = f"{ORIENTATION_TEXT.get(view.orientation, view.orientation)} on {cells}"
        self.status_var.set(text)

    def _on_hover(self, cell) -> None:
        if cell is None or self.lview is None:
            self.hover_var.set("")
            return
        kind = self.lview.tile(cell)
        text = f"{cell}  {TILE_TEXT.get(kind, kind)}"
        switch = self.lview.switches.get(cell)
        if switch is not None and switch.targets:
            text += f": splits into cubes at {switch.targets[0]} and {switch.targets[1]}"
        elif switch is not None:
            text += f": {switch.action} {len(switch.bridges)} bridge tile(s)"
        elif kind == BRIDGE:
            opened = cell in state_view(self.level, self.state).open_bridges
            text += " (open)" if opened else " (closed)"
        self.hover_var.set(text)

    def _engine_error(self, exc: Exception) -> None:
        messagebox.showerror("Engine error", f"{type(exc).__name__}: {exc}\n\n"
                                             f"{traceback.format_exc()[-1500:]}")

    def close(self) -> None:
        self._stop_play()
        self.board.cancel_animation()
        self.root.destroy()


def _enable_dpi_awareness() -> None:
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except (AttributeError, OSError):
            pass


def run(levels_dir: Path, stage: Path | None = None) -> None:
    _enable_dpi_awareness()
    backend = load_backend()
    root = tk.Tk()
    scale = root.winfo_fpixels("1i") / 96
    sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
    w, h = min(int(1280 * scale), int(sw * 0.92)), min(int(820 * scale), int(sh * 0.88))
    root.geometry(f"{w}x{h}+{(sw - w) // 2}+{max(0, (sh - h) // 3)}")
    root.minsize(int(900 * scale), int(640 * scale))
    App(root, backend, levels_dir, stage)
    root.mainloop()
