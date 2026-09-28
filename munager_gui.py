from __future__ import annotations

import tkinter as tk
from tkinter import ttk
import tkinter.font as tkfont
from typing import Any, Callable, Iterable, Optional, Sequence, cast

try:
    from screeninfo import get_monitors
except Exception:
    get_monitors = None

try:
    from pynput import keyboard as _pk, mouse as _pm
except Exception:
    _pk = None
    _pm = None

import munager_net

CtrlEvent = Callable[["Ctrl"], Any]


class Ctrl:
    """Wrapper giving AHK-like .Text / .Value / .Enabled access to a widget."""

    def __init__(self, widget: tk.Widget, kind: str,
                 var: Optional[tk.Variable] = None) -> None:
        self.widget: tk.Widget = widget
        self.kind: str = kind
        self.var: Optional[tk.Variable] = var
        self._event: Optional[CtrlEvent] = None
        self._progress: Optional["ProgressBar"] = None
        self._items: list[Any] = []       # for DDL/ListBox 1-based Index

    @property
    def Text(self) -> str:
        if self.var is not None:
            return str(self.var.get())
        if self.kind == "edit":
            text = cast(tk.Text, self.widget)
            return text.get("1.0", "end-1c")
        if self.kind in ("text", "button"):
            return str(self.widget.cget("text"))
        return ""

    @Text.setter
    def Text(self, value: Any) -> None:
        if self.var is not None:
            self.var.set(value)
        elif self.kind == "edit":
            text = cast(tk.Text, self.widget)
            text.delete("1.0", "end")
            text.insert("1.0", str(value))
        elif self.kind in ("text", "button"):
            self.widget["text"] = str(value)

    @property
    def Value(self) -> Any:
        if self._progress is not None:
            return self._progress._value
        if self.var is not None:
            v = self.var.get()
            try:
                return int(v)
            except (ValueError, TypeError):
                return v
        return self.Text

    @Value.setter
    def Value(self, value: Any) -> None:
        if self._progress is not None:
            self._progress.set_value(value)
        elif self.var is not None:
            self.var.set(value)

    @property
    def Range(self) -> float:
        if self._progress is not None:
            return self._progress._range
        return 0.0

    @Range.setter
    def Range(self, value: float) -> None:
        if self._progress is not None:
            self._progress.set_range(value)

    def Opt(self, options: str) -> None:
        """AHK-style control option, used here to recolour a progress bar."""
        if self._progress is not None:
            for tok in options.split():
                if tok.startswith("c"):
                    self._progress.set_color(tok)

    def set_font(self, strike: bool = False, bold: bool = False) -> None:
        """AHK SetFont equivalent for Text/Button widgets."""
        for fname in ("TkDefaultFont", "TkTextFont", "TkMenuFont",
                      "TkHeadingFont", "TkCaptionFont", "TkFixedFont"):
            try:
                tkfont.nametofont(fname).configure(size=26)
            except tk.TclError:
                pass
        try:
            current = tkfont.Font(font=self.widget.cget("font"))
            current.configure(
                overstrike=strike,
                weight="bold" if bold else "normal")
            self.widget["font"] = current
        except tk.TclError:
            pass

    # ListView row operations (overridden by LVCtrl for real behaviour)
    def count(self) -> int:
        return 0

    def insert_row(self, pos: int, text: Any) -> None:
        raise TypeError("insert_row is only valid on a ListView control")

    def delete_row(self, pos: int) -> None:
        raise TypeError("delete_row is only valid on a ListView control")

    def get_text(self, row: int, col: int = 1) -> str:
        raise TypeError("get_text is only valid on a ListView control")

    def selected_row(self) -> int:
        """1-based index of the selected ListView row, or 0."""
        return 0

    def clear(self) -> None:
        raise TypeError("clear is only valid on a ListView control")

    def set_cell(self, row: int, col: int, text: Any) -> None:
        raise TypeError("set_cell is only valid on a ListView control")
    
    def insert_full(self, pos: int, values: list[Any]) -> None:
        raise TypeError("insert_full is only valid on a ListView control")

    def set_height(self, rows: int) -> None:
        raise TypeError("set_height is only valid on a ListView control")

    @property
    def Index(self) -> int:
        """1-based selected index for a DDL, else 0."""
        if self.var is not None and self._items:
            val = self.var.get()
            return (self._items.index(val) + 1) if val in self._items else 0
        return 0

    def on_change(self, cb: Callable[[], Any]) -> None:
        # DDL/combobox selection change
        self.widget.bind("<<ComboboxSelected>>", lambda e: cb())

    def fit_columns(self) -> None:
        raise TypeError("fit_columns is only valid on a ListView control")


class ProgressBar:
    _COLORS = {
        "cRed": "#e04040",
        "cYellow": "#e0c020",
        "cGreen": "#40c040",
        "cDefault": "#4060e0",
    }

    def __init__(self, master: tk.Widget, width: int, height: int,
                 range_max: float = 100.0) -> None:
        self.canvas: tk.Canvas = tk.Canvas(
            master, width=width, height=height, highlightthickness=1,
            highlightbackground="#808080", bg="#d9d9d9")
        self._w: int = width
        self._h: int = height
        self._range: float = range_max if range_max > 0 else 100.0
        self._value: float = 0.0
        self._color: str = self._COLORS["cDefault"]
        self._rect: int = self.canvas.create_rectangle(
            0, 0, 0, height, fill=self._color, width=0)
        # redraw fill whenever the canvas is actually resized (fill='x')
        self.canvas.bind("<Configure>", self._on_configure)

    def _on_configure(self, event: "tk.Event[Any]") -> None:
        self._w = event.width
        self._h = event.height
        self._redraw()

    def _redraw(self) -> None:
        fill_w = int(self._w * self._value / self._range)
        self.canvas.coords(self._rect, 0, 0, fill_w, self._h)

    def set_range(self, range_max: float) -> None:
        self._range = range_max if range_max > 0 else 100.0
        self._redraw()

    def set_value(self, value: float) -> None:
        self._value = max(0.0, min(self._range, float(value)))
        self._redraw()

    def set_color(self, opt: str) -> None:
        self._color = self._COLORS.get(opt, self._color)
        self.canvas.itemconfigure(self._rect, fill=self._color)


class Row:
    def __init__(self, owner: "Munager", frame: tk.Frame) -> None:
        self.owner = owner
        self.frame = frame

    def _pack(self, w: tk.Widget, expand: bool = False) -> None:
        w.pack(side="left", padx=2, expand=expand,
               fill="x" if expand else "none")

    def label(self, text: Any, width: int = 0) -> Ctrl:
        lbl = tk.Label(self.frame, text=str(text), font=self.owner._font(),
                       anchor="w")
        if width:
            lbl.config(width=width)
        self._pack(lbl, expand=not width)
        return Ctrl(lbl, "text")

    def button(self, text: Any, event: CtrlEvent) -> Ctrl:
        c: Ctrl
        btn = tk.Button(self.frame, text=str(text),
                        font=self.owner._font(),
                        command=lambda: event(c))
        self._pack(btn)
        c = Ctrl(btn, "button")
        c._event = event
        return c


class Munager:
    _root: Optional[tk.Tk] = None

    @classmethod
    def root(cls) -> tk.Tk:
        if cls._root is None:
            cls._root = tk.Tk()
            cls._root.withdraw()
            cls._pump()
        return cls._root

    @classmethod
    def _pump(cls) -> None:
        munager_net.pump()
        assert cls._root is not None
        cls._root.after(30, cls._pump)

    def __init__(self, name: str, vscroll: int = 0, font: int = 50,
                 bold: int = 0,
                 close: Optional[Callable[[], Any]] = None) -> None:
        self.win: tk.Toplevel = tk.Toplevel(Munager.root())
        self.win.title(name)
        self.font_size: int = font
        self._bold: int = bold
        # make combobox dropdown list use the same font size
        self.win.option_add("*TCombobox*Listbox.font",
                            ("TkDefaultFont", font))
        self._ctrls: dict[str, Ctrl] = {}
        self._followers: list["Munager"] = []
        self._close_cb: Optional[Callable[[], Any]] = close
        self.other: Optional["Munager"] = None
        self._hotkeys: list[Any] = []
        self._mouse: list[Any] = []

        # Scrollable body: canvas + inner frame.
        self.canvas: tk.Canvas = tk.Canvas(self.win, highlightthickness=0)
        self.vbar: ttk.Scrollbar = ttk.Scrollbar(
            self.win, orient="vertical", command=self._on_scroll)
        self.canvas.configure(yscrollcommand=self.vbar.set)
        self.vbar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)

        self.body: tk.Frame = tk.Frame(self.canvas)
        self._win_id: int = self.canvas.create_window(
            (0, 0), window=self.body, anchor="nw")
        self.body.bind("<Configure>", self._on_body_configure)
        self.canvas.bind(
            "<Configure>",
            lambda e: self.canvas.itemconfigure(self._win_id, width=e.width))

        # Mouse wheel — only when pointer is over THIS window's canvas.
        for w in (self.canvas, self.body):
            w.bind("<MouseWheel>", self._wheel)
            w.bind("<Button-4>", self._wheel)
            w.bind("<Button-5>", self._wheel)
        # ensure child widgets forward wheel to the canvas
        self.body.bind("<Enter>", lambda e: self.canvas.focus_set())

        self.win.protocol("WM_DELETE_WINDOW", self._closed)
        self.win.withdraw()

    # --- scroll linking (control drives display) ---
    def link_scroll(self, follower: "Munager") -> None:
        self._followers.append(follower)

    def _on_scroll(self, *args: str) -> None:
        self.canvas.yview(*args)
        top = self.canvas.yview()[0]
        for f in self._followers:
            f.canvas.yview_moveto(top)

    def _wheel(self, event: "tk.Event[Any]") -> str:
        if event.num == 5 or getattr(event, "delta", 0) < 0:
            self.canvas.yview_scroll(1, "units")
        elif event.num == 4 or getattr(event, "delta", 0) > 0:
            self.canvas.yview_scroll(-1, "units")
        top = self.canvas.yview()[0]
        for f in self._followers:
            f.canvas.yview_moveto(top)
        return "break"

    def _on_body_configure(self, _: Any) -> None:
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _closed(self) -> None:
        if self._close_cb:
            self._close_cb()
        else:
            self.win.destroy()

    def onClose(self, cb: Callable[[], Any]) -> None:
        self._close_cb = cb

    # --- fonts ---
    def _font(self, bold: Optional[int] = None) -> tuple[str, int, str]:
        b = self._bold if bold is None else bold
        return ("TkDefaultFont", self.font_size, "bold" if b else "normal")

    def bold(self) -> None:
        self._bold = 1

    def norm(self) -> None:
        self._bold = 0

    def size(self, s: int) -> None:
        self.font_size = s

    # --- window ops ---
    def _second_monitor_origin(self) -> Optional[tuple[int, int, int, int]]:
        if get_monitors is None:
            return None
        try:
            mons = get_monitors()
        except Exception:
            return None
        # prefer a monitor explicitly not primary
        for m in mons:
            if not getattr(m, "is_primary", False):
                return (m.x, m.y, m.width, m.height)
        # fallback: any monitor offset from origin
        for m in mons:
            if m.x != 0 or m.y != 0:
                return (m.x, m.y, m.width, m.height)
        return None

    def show(self, mode: int = 0) -> None:
        self.win.deiconify()
        self.win.update_idletasks()
        origin = self._second_monitor_origin()
        if mode == 1:  # maximize on second monitor
            if origin:
                x, y, w, h = origin
                self.win.geometry(f"{w}x{h}+{x}+{y}")
            else:
                try:
                    self.win.state("zoomed")
                except tk.TclError:
                    self.win.attributes("-zoomed", True)
        else:
            # autosize to content
            self.win.update_idletasks()
            req_w = self.body.winfo_reqwidth() + self.vbar.winfo_reqwidth() + 4
            req_h = self.body.winfo_reqheight() + 4
            sw = self.win.winfo_screenwidth()
            sh = self.win.winfo_screenheight()
            w = min(req_w, sw)
            h = min(req_h, sh - 60)
            if mode == -1 and origin:  # autosize on second monitor
                self.win.geometry(f"{w}x{h}+{origin[0]}+{origin[1]}")
            else:  # centered
                x = (sw - w) // 2
                y = (sh - h) // 2
                self.win.geometry(f"{w}x{h}+{x}+{y}")
        self._on_body_configure(None)

    def Hide(self) -> None:
        self.win.withdraw()

    def Show(self, mode: int = 0) -> None:
        self.show(mode)

    def Destroy(self) -> None:
        self.win.destroy()

    @property
    def Hwnd(self) -> int:
        return self.win.winfo_id()

    # --- display pairing (control drives a projector display window) ---
    def link_display(self, display: "Munager") -> None:
        """Register `display` as this control's projector mirror and link scroll."""
        self.other = display
        self.link_scroll(display)

    # --- hybrid global hotkeys (window binding + optional pynput global) ---
    def bind_key(self, sequence: str, handler: Callable[[], Any],
                 global_key: Optional[str] = None) -> None:
        """Bind a keyboard shortcut in-window, and globally if pynput allows.

        sequence   : Tk binding, e.g. '<Control-l>'
        global_key : pynput hotkey string, e.g. '<ctrl>+l' (optional)
        """
        self.win.bind_all(sequence, lambda e: handler(), add="+")
        if _pk is not None and global_key:
            self._start_global_hotkey(global_key, handler)

    def bind_mouse(self, button: str, handler: Callable[[], Any]) -> None:
        """Bind a mouse button in-window, and globally if pynput allows.

        button : 'middle' or 'right'
        """
        seq = {"middle": "<Button-2>", "right": "<Button-3>"}.get(button)
        if seq:
            self.win.bind_all(seq, lambda e: handler(), add="+")
        if _pm is not None:
            self._start_global_mouse(button, handler)

    def _start_global_hotkey(self, combo: str,
                             handler: Callable[[], Any]) -> None:
        def on_activate() -> None:
            self.win.after(0, handler)
        try:
            assert _pk is not None
            gh = _pk.GlobalHotKeys({combo: on_activate})
            gh.daemon = True
            gh.start()
            self._hotkeys.append(gh)
        except Exception:
            pass  # Accessibility not granted / unsupported: in-window still works

    def _start_global_mouse(self, button: str,
                            handler: Callable[[], Any]) -> None:
        assert _pm is not None
        want = {"middle": _pm.Button.middle,
                "right": _pm.Button.right}.get(button)

        def on_click(x: int, y: int, b: Any, pressed: bool) -> None:
            if pressed and b == want:
                self.win.after(0, handler)

        try:
            ml = _pm.Listener(on_click=on_click)
            ml.daemon = True
            ml.start()
            self._mouse.append(ml)
        except Exception:
            pass

    def __getitem__(self, name: str) -> Ctrl:
        return self._ctrls[name]

    def _register(self, name: Optional[str], ctrl: Ctrl) -> Ctrl:
        if name:
            self._ctrls[name] = ctrl
        return ctrl

    @staticmethod
    def _vname(options: str) -> Optional[str]:
        for tok in options.split():
            if tok.startswith("v") and len(tok) > 1:
                return tok[1:]
        return None

    # --- Add* helpers (AHK-compatible signatures) ---
    def AddText(self, options: str = "", text: Any = "",
                event: Optional[CtrlEvent] = None) -> Ctrl:
        name = self._vname(options)
        wraplength = 0
        for tok in options.split():
            if tok.startswith("w") and tok[1:].isdigit():
                wraplength = int(tok[1:])
        lbl = tk.Label(self.body, text=str(text), font=self._font(),
                       justify="left", anchor="w")
        if wraplength:
            lbl.config(wraplength=wraplength)
        if "wrap2" in options:
            # clamp height to 2 lines
            lbl.config(height=2)
        lbl.pack(fill="x", padx=4, pady=2)
        return self._register(name, Ctrl(lbl, "text"))

    def AddButton(self, options: str = "", text: Any = "",
                  event: Optional[CtrlEvent] = None) -> Ctrl:
        name = self._vname(options)
        cmd: str | Callable[[], Any] = (lambda: event(c)) if event else ""
        btn = tk.Button(self.body, text=str(text), font=self._font(),
                        command=cmd)
        btn.pack(fill="x", padx=4, pady=2)
        c = Ctrl(btn, "button")
        if event:
            c._event = event
        return self._register(name, c)

    def AddRow(self) -> "Row":
        """A horizontal container; add controls into it side-by-side."""
        frame = tk.Frame(self.body)
        frame.pack(fill="x", padx=4, pady=1)
        return Row(self, frame)

    def AddEdit(self, options: str = "", text: Any = "",
                event: Optional[CtrlEvent] = None) -> Ctrl:
        name = self._vname(options)
        rows = 1
        for tok in options.split():
            if tok.startswith("r") and tok[1:].isdigit():
                rows = int(tok[1:])
        disabled = "Disabled" in options
        txt = tk.Text(self.body, height=rows, font=self._font())
        if text:
            txt.insert("1.0", str(text))
        if disabled:
            txt.config(state="disabled")
        txt.pack(fill="x", padx=4, pady=2)
        return self._register(name, Ctrl(txt, "edit"))

    def AddUpDown(self, options: str = "", text: Any = 0,
                  event: Optional[CtrlEvent] = None) -> Ctrl:
        name = self._vname(options)
        lo, hi = 1, 5
        for tok in options.split():
            if tok.startswith("Range"):
                try:
                    lo, hi = (int(x) for x in tok[5:].split("-"))
                except ValueError:
                    pass
        disabled = "Disabled" in options
        var = tk.StringVar(value=str(text or lo))
        sp = tk.Spinbox(self.body, from_=lo, to=hi, textvariable=var,
                        font=self._font(), width=5)
        if disabled:
            sp.config(state="disabled")
        sp.pack(anchor="w", padx=4, pady=2)
        c = Ctrl(sp, "spin", var)
        if event:
            var.trace_add("write", lambda *_: event(c))
        return self._register(name, c)

    def AddDDL(self, options: str = "",
               items: Optional[Iterable[Any]] = None,
               event: Optional[CtrlEvent] = None) -> Ctrl:
        item_list: list[Any] = list(items or [])
        if "sort" in options:
            item_list = sorted(item_list)
        name = self._vname(options)
        var = tk.StringVar()
        style = ttk.Style()
        style_name = f"F{self.font_size}.TCombobox"
        style.configure(style_name, font=("TkDefaultFont", self.font_size))
        cb = ttk.Combobox(self.body, textvariable=var, values=item_list,
                          state="readonly", font=self._font(),
                          style=style_name)
        cb.pack(fill="x", padx=4, pady=2)
        c = Ctrl(cb, "ddl", var)
        c._items = item_list
        if event:
            cb.bind("<<ComboboxSelected>>", lambda e: event(c))
        return self._register(name, c)

    def AddListBox(self, options: str = "",
                   items: Optional[Iterable[Any]] = None,
                   event: Optional[CtrlEvent] = None) -> Ctrl:
        item_list: list[Any] = list(items or [])
        name = self._vname(options)
        rows = 3
        choose = 1
        for tok in options.split():
            if tok.startswith("r") and tok[1:].isdigit():
                rows = int(tok[1:])
            if tok.startswith("Choose"):
                choose = int(tok[6:])
        lb = tk.Listbox(self.body, height=rows, font=self._font(),
                        exportselection=False)
        for it in item_list:
            lb.insert("end", it)
        if item_list:
            lb.selection_set(choose - 1)
        lb.pack(fill="x", padx=4, pady=2)

        class LBCtrl(Ctrl):
            @property
            def Value(self) -> Any:
                sel = lb.curselection()
                return sel[0] + 1 if sel else 0

            @Value.setter
            def Value(self, value: Any) -> None:
                if self.var is not None:
                    self.var.set(value)

        c = LBCtrl(lb, "listbox")
        if event:
            lb.bind("<<ListboxSelect>>", lambda e: event(c))
        return self._register(name, c)

    def AddListView(self, options: str = "",
                    header: Optional[Sequence[str]] = None,
                    rows: Optional[Sequence[Sequence[Any]]] = None,
                    event: Optional[CtrlEvent] = None) -> Ctrl:
        header_list: list[str] = list(header or [])
        row_list: list[Sequence[Any]] = list(rows or [])
        name = self._vname(options)
        cols = [f"c{i}" for i in range(len(header_list))]
        tv = ttk.Treeview(self.body, columns=cols, show="headings",
                          height=min(20, max(3, len(row_list))))
        for i, h in enumerate(header_list):
            tv.heading(cols[i], text=h)
            tv.column(cols[i], width=120, stretch=True)
        for r in row_list:
            vals = r[1:] if len(r) == len(header_list) + 1 else r
            tv.insert("", "end", values=list(vals))
        tv.pack(fill="both", expand=True, padx=4, pady=2)

        header_len = len(header_list)

        style = ttk.Style(tv)
        font_spec = style.lookup("Treeview", "font") or "TkDefaultFont"
        fnt = tkfont.Font(font=font_spec)
        style.configure("Treeview",
                        rowheight=fnt.metrics("linespace") + 8)

        class LVCtrl(Ctrl):
            def ModifyCol(self, *_: Any) -> None:
                pass

            def Add(self, *vals: Any) -> None:
                v = vals[1:] if len(vals) == header_len + 1 else vals
                tv.insert("", "end", values=list(v))

            def count(self) -> int:
                return len(tv.get_children())

            def insert_row(self, pos: int, text: Any) -> None:
                """1-based insert; pos beyond end appends (AHK 2147483647)."""
                children = tv.get_children()
                index = min(max(pos - 1, 0), len(children))
                tv.insert("", index, values=[text])

            def delete_row(self, pos: int) -> None:
                """1-based delete."""
                children = tv.get_children()
                if 1 <= pos <= len(children):
                    tv.delete(children[pos - 1])

            def get_text(self, row: int, col: int = 1) -> str:
                """1-based row/col text."""
                children = tv.get_children()
                if 1 <= row <= len(children):
                    vals = tv.item(children[row - 1], "values")
                    if 1 <= col <= len(vals):
                        return str(vals[col - 1])
                return ""

            def selected_row(self) -> int:
                sel = tv.selection()
                if not sel:
                    return 0
                return tv.get_children().index(sel[0]) + 1

            def clear(self) -> None:
                for iid in tv.get_children():
                    tv.delete(iid)

            def set_cell(self, row: int, col: int, text: Any) -> None:
                children = tv.get_children()
                if 1 <= row <= len(children) and 1 <= col <= len(cols):
                    tv.set(children[row - 1], cols[col - 1], text)

            def insert_full(self, pos: int, values: list[Any]) -> None:
                children = tv.get_children()
                index = min(max(pos - 1, 0), len(children))
                tv.insert("", index, values=values)

            def set_height(self, rows: int) -> None:
                tv.configure(height=max(rows, 1))

            def fit_columns(self) -> None:
                """Resize each column to fit the widest header/cell shown."""
                f = tkfont.nametofont("TkDefaultFont")
                for col in cols:
                    w = f.measure(str(tv.heading(col, "text")))
                    for iid in tv.get_children(""):
                        w = max(w, f.measure(str(tv.set(iid, col))))
                    tv.column(col, width=w + 24, stretch=False)

        c = LVCtrl(tv, "listview")
        if event:
            tv.bind("<Double-1>", lambda e: event(c))
        return self._register(name, c)

    def AddProgress(self, options: str = "", value: int = 0) -> Ctrl:
        name = self._vname(options)
        width, height = 400, 40
        range_max = 100.0
        for tok in options.split():
            if tok.startswith("w") and tok[1:].isdigit():
                width = int(tok[1:])
            elif tok.startswith("h") and tok[1:].isdigit():
                height = int(tok[1:])
            elif tok.startswith("Range0-"):
                try:
                    range_max = float(tok[7:])
                except ValueError:
                    pass
        pb = ProgressBar(self.body, width, height, range_max)
        pb.canvas.pack(fill="x", padx=4, pady=4)
        pb.set_value(value)
        c = Ctrl(pb.canvas, "progress")
        c._progress = pb
        for tok in options.split():
            if tok.startswith("c"):
                pb.set_color(tok)
        return self._register(name, c)


def mainloop() -> None:
    Munager.root().mainloop()