# -*- coding: utf-8 -*-
"""
Bookmark Manager (Tkinter)

Key improvements vs original:
- Fix: usage counter could be incremented without being written back to the usage tree.
- Cross-platform opening:
  - URLs open via `webbrowser`
  - Files open via OS default opener (Windows/macOS/Linux)
  - Commands run via subprocess
- Safer JSON writes (atomic replace) to avoid corrupt files after a crash.
- Suggestion listbox positioning fixed (uses widget-relative coords).
- Reduced globals (state kept in a small App class), fewer unused imports.

Files created next to where you start the program (current working directory):
- bookmarks.json
- usage.json
- window_geometry.txt
"""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
import webbrowser
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple, Union

import tkinter as tk
from tkinter import Menu, messagebox, Toplevel, Label, Entry, Button, StringVar, OptionMenu, filedialog
from tkinter import ttk


JsonDict = Dict[str, Any]
PathTuple = Tuple[str, ...]


def get_data_dir() -> Path:
    # Keep original behavior: data files are in the current working directory.
    return Path.cwd()


def atomic_write_text(path: Path, text: str, encoding: str = "utf-8") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", delete=False, dir=str(path.parent), encoding=encoding) as tf:
        tf.write(text)
        tmp_name = tf.name
    os.replace(tmp_name, path)


def atomic_write_json(path: Path, data: Any) -> None:
    atomic_write_text(path, json.dumps(data, indent=4, ensure_ascii=False), encoding="utf-8")


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        messagebox.showerror("Load Error", f"Could not load {path.name}: {e}")
        return default
    except Exception as e:
        messagebox.showerror("Load Error", f"Could not read {path.name}: {e}")
        return default


def is_url(s: str) -> bool:
    s = s.strip().lower()
    return s.startswith("http://") or s.startswith("https://")


def open_file_default(path: Path) -> None:
    """
    Open a file with the OS default application (cross-platform).
    """
    try:
        if sys.platform.startswith("win"):
            os.startfile(str(path))  # type: ignore[attr-defined]
            return
        if sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
            return
        subprocess.Popen(["xdg-open", str(path)])
    except Exception as e:
        messagebox.showerror("Error", f"Could not open file '{path}': {e}")


def ensure_usage_leaf(node: JsonDict, key: str) -> JsonDict:
    """
    Ensure node[key] is a usage leaf: {"count": int, "last_browser": str|None}
    Return the leaf dict.
    """
    if key not in node or not isinstance(node.get(key), dict) or "count" not in node[key]:
        node[key] = {"count": 0, "last_browser": None}
    else:
        node[key].setdefault("count", 0)
        node[key].setdefault("last_browser", None)
    return node[key]


def ensure_usage_category(node: JsonDict, key: str) -> JsonDict:
    """
    Ensure node[key] is a dict category.
    """
    if key not in node or not isinstance(node.get(key), dict) or "count" in node[key]:
        node[key] = {}
    return node[key]


def sync_usage_structure(bookmarks: JsonDict, usage: JsonDict) -> JsonDict:
    """
    Ensure usage tree matches bookmarks tree shape.
    """
    # Remove usage keys that no longer exist in bookmarks
    for k in list(usage.keys()):
        if k not in bookmarks:
            usage.pop(k, None)

    for k, v in bookmarks.items():
        if isinstance(v, dict):
            ensure_usage_category(usage, k)
            sync_usage_structure(v, usage[k])
        else:
            ensure_usage_leaf(usage, k)

    return usage


def get_category_by_path(data: JsonDict, path: PathTuple) -> JsonDict:
    node: JsonDict = data
    for key in path:
        node = node.get(key, {})
        if not isinstance(node, dict):
            return {}
    return node


def get_bookmark_by_path(bookmarks: JsonDict, path: PathTuple) -> Optional[str]:
    node: JsonDict = bookmarks
    for key in path[:-1]:
        nxt = node.get(key)
        if not isinstance(nxt, dict):
            return None
        node = nxt
    val = node.get(path[-1])
    return val if isinstance(val, str) else None


def get_all_category_paths(data: JsonDict, current: PathTuple = ()) -> List[PathTuple]:
    paths: List[PathTuple] = []
    for k, v in data.items():
        if isinstance(v, dict):
            new_p = current + (k,)
            paths.append(new_p)
            paths.extend(get_all_category_paths(v, new_p))
    return paths


def get_all_bookmark_paths(data: JsonDict, current: PathTuple = ()) -> List[Tuple[str, PathTuple]]:
    out: List[Tuple[str, PathTuple]] = []
    for k, v in data.items():
        if isinstance(v, dict):
            out.extend(get_all_bookmark_paths(v, current + (k,)))
        else:
            display = " > ".join(current + (k,))
            out.append((display, current + (k,)))
    return out


def sum_all_usage(node: Any) -> int:
    if isinstance(node, dict):
        if "count" in node:
            return int(node.get("count", 0))
        return sum(sum_all_usage(v) for v in node.values())
    return 0


@dataclass
class AppPaths:
    data_dir: Path
    bookmarks_file: Path
    usage_file: Path
    geometry_file: Path
    theme_file: Path
    icon_path: Path


class BookmarkApp:
    def __init__(self) -> None:
        self.paths = self._init_paths()
        self.theme_mode: str = self.load_theme() or "light"
        self.sort_mode: str = "usage"

        self.bookmarks: JsonDict = {}
        self.usage: JsonDict = {}

        self.root = tk.Tk()
        self.root.withdraw()  # prevent flicker and WM geometry nudges on startup
        self.root.title("Bookmarks Manager")
        self._apply_geometry()

        self._apply_icon()

        self.menu = Menu(self.root)
        self.root.config(menu=self.menu)

        self.extra_menu = Menu(self.menu, tearoff=0)
        self.sort_menu = Menu(self.menu, tearoff=0)
        self.context_menu = Menu(self.root, tearoff=0)

        # Theme
        self.theme_var = tk.BooleanVar(self.root, value=(self.theme_mode == "dark"))
        self.style = ttk.Style(self.root)
        try:
            self._ttk_theme_default = self.style.theme_use()
        except Exception:
            self._ttk_theme_default = None

        self.browser_var = StringVar(self.root, value="LastUsed")
        self.search_var = StringVar()

        self.search_entry: Optional[tk.Entry] = None
        self.search_button: Optional[tk.Button] = None
        self.suggestion_listbox: Optional[tk.Listbox] = None

        self._build_ui()
        self._apply_theme()
        self._load_data()
        self.update_menu()

        self.root.bind("<Button-3>", self._show_context_menu)
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

        # Show the window only after UI + theme is ready (reduces flicker)
        self.root.update_idletasks()
        self.root.deiconify()
        self._schedule_geometry_stabilization()

    def _init_paths(self) -> AppPaths:
        data_dir = get_data_dir()
        project_dir = Path(__file__).resolve().parent
        return AppPaths(
            data_dir=data_dir,
            bookmarks_file=data_dir / "bookmarks.json",
            usage_file=data_dir / "usage.json",
            geometry_file=data_dir / "window_geometry.txt",
            theme_file=data_dir / "ui_theme.txt",
            icon_path=project_dir / "it4home.ico",
        )

    def _apply_icon(self) -> None:
        if self.paths.icon_path.exists():
            try:
                self.root.iconbitmap(str(self.paths.icon_path))
            except Exception:
                pass

    def _apply_geometry(self) -> None:
        geom = self.load_geometry()
        self._desired_geometry = geom or None

        if geom:
            self.root.geometry(geom)
        else:
            self.root.geometry("600x200")

        self.root.minsize(600, 40)

    def _stabilize_geometry(self) -> None:
        """Re-apply saved geometry after the WM maps the window.

        Some Linux window managers (and Wayland/X11 combinations) can nudge the
        window by a couple of pixels when restoring geometry.
        """
        geom = getattr(self, "_desired_geometry", None)
        if not geom:
            return
        try:
            self.root.update_idletasks()
            self.root.geometry(geom)
        except Exception:
            pass

    @staticmethod
    def _parse_geometry(geom: str) -> tuple[int, int, int, int] | None:
        """Parse 'WxH+X+Y' (and variants with -X/-Y) into ints."""
        m = re.match(r"^(\d+)x(\d+)([+-]\d+)([+-]\d+)$", geom.strip())
        if not m:
            return None
        w = int(m.group(1))
        h = int(m.group(2))
        x = int(m.group(3))
        y = int(m.group(4))
        return w, h, x, y

    def _on_first_configure(self, event: tk.Event | None = None) -> None:
        """One-time hook to counter small WM 'nudge' after first map.

        Some WMs adjust the final position after mapping. We re-apply the saved
        geometry once more a bit later, but only if the delta is tiny (1-5px).
        """
        if getattr(self, "_did_first_configure_fix", False):
            return
        self._did_first_configure_fix = True
        # remove the binding so we only schedule once
        try:
            bind_id = getattr(self, "_configure_bind_id", None)
            if bind_id:
                self.root.unbind("<Configure>", bind_id)
                self._configure_bind_id = None
        except Exception:
            pass
        # wait a bit longer than the initial stabilization so the WM has settled
        self.root.after(250, self._final_geometry_fix)

    def _final_geometry_fix(self) -> None:
        desired = getattr(self, "_desired_geometry", None)
        if not desired:
            return

        cur = self.root.wm_geometry()
        d = self._parse_geometry(desired)
        c = self._parse_geometry(cur)
        if not d or not c:
            # best effort: just re-apply once
            try:
                self.root.geometry(desired)
                self.root.after(120, lambda: self.root.geometry(desired))
            except Exception:
                pass
            return

        dw, dh, dx, dy = d
        cw, ch, cx, cy = c

        # Only correct tiny shifts; don't fight the user's position.
        if abs(cx - dx) <= 5 and abs(cy - dy) <= 5 and cw == dw and ch == dh and (cy != dy):
            try:
                self.root.geometry(desired)
                self.root.after(120, lambda: self.root.geometry(desired))
            except Exception:
                pass

    def _schedule_geometry_stabilization(self) -> None:
        if getattr(self, "_desired_geometry", None):
            # Apply immediately once (best effort), then a few more times after
            # the window is mapped to counter tiny WM nudges (eg. 1-2 px).
            self._stabilize_geometry()
            self.root.after(0, self._stabilize_geometry)
            self.root.after(120, self._stabilize_geometry)
            self.root.after(350, self._stabilize_geometry)

            # One-time <Configure> hook: if the WM shifts the window right after
            # mapping, correct it once more (but only for tiny deltas).
            try:
                self._did_first_configure_fix = False
                self._configure_bind_id = self.root.bind("<Configure>", self._on_first_configure, add="+")
            except Exception:
                pass

    def _build_ui(self) -> None:
        # Tools
        self.extra_menu.add_command(label="Import Bookmarks", command=self.import_from_json)
        self.extra_menu.add_command(label="Export Bookmarks", command=self.export_to_json)
        self.extra_menu.add_separator()
        self.extra_menu.add_command(label="Manage Bookmarks", command=self.manage_bookmarks_window)
        self.extra_menu.add_command(label="Usage Stats", command=self.show_usage_stats)

        self.extra_menu.add_separator()
        self.extra_menu.add_checkbutton(label="Dark mode", variable=self.theme_var, command=self.toggle_theme)

        # Sort
        self.sort_menu.add_command(label="Sort by Usage", command=lambda: self.set_sort_mode("usage"))
        self.sort_menu.add_command(label="Sort by Name", command=lambda: self.set_sort_mode("name"))

        # Context menu
        self.context_menu.add_command(label="Add Bookmark", command=self.add_bookmark_window)
        self.context_menu.add_command(label="Add Category", command=self.add_category_window)
        self.context_menu.add_command(label="Edit Bookmark", command=self.edit_bookmark_window)
        self.context_menu.add_command(label="Edit Category", command=self.edit_category_window)
        self.context_menu.add_command(label="Delete Bookmark", command=self.delete_bookmark_window)
        self.context_menu.add_command(label="Delete Category", command=self.delete_category_window)
        self.context_menu.add_command(label="Move Bookmark/Category", command=self.move_item_window)

        # Bottom bar
        browser_frame = tk.Frame(self.root)
        browser_frame.pack(side="bottom", fill="x")

        tk.Label(browser_frame, text="Browser:").pack(side="left", padx=(10, 2), pady=5)
        OptionMenu(browser_frame, self.browser_var, "LastUsed", "Edge", "Firefox", "Chrome", "Default").pack(
            side="left", pady=5
        )

        # Search
        self.search_var.trace_add("write", self.update_suggestions)
        self.search_entry = tk.Entry(browser_frame, textvariable=self.search_var, width=20)
        self.search_entry.pack(side="left", padx=(10, 2), pady=5)
        self.search_button = tk.Button(
            browser_frame,
            text="Search",
            command=lambda: (self.search_bookmarks(self.search_var.get()), self.search_var.set("")),
        )
        self.search_button.pack(side="left", padx=5, pady=5)

        tk.Label(browser_frame, text="@Knud Schrøder (it4home.dk)", fg="gray").pack(side="right", padx=(2, 10), pady=5)

    # -------------------------
    # Persistence
    # -------------------------

    def _load_data(self) -> None:
        self.bookmarks = load_json(self.paths.bookmarks_file, {})
        if not isinstance(self.bookmarks, dict):
            messagebox.showerror("Load Error", "bookmarks.json must contain a JSON object at the top level.")
            self.bookmarks = {}

        self.usage = load_json(self.paths.usage_file, {})
        if not isinstance(self.usage, dict):
            self.usage = {}

        sync_usage_structure(self.bookmarks, self.usage)
        self.save_usage()

    def save_bookmarks(self) -> None:
        atomic_write_json(self.paths.bookmarks_file, self.bookmarks)

    def save_usage(self) -> None:
        atomic_write_json(self.paths.usage_file, self.usage)

    def load_geometry(self) -> Optional[str]:
        if not self.paths.geometry_file.exists():
            return None
        try:
            return self.paths.geometry_file.read_text(encoding="utf-8").strip()
        except Exception:
            return None

    def save_geometry(self, geometry: str) -> None:
        try:
            atomic_write_text(self.paths.geometry_file, geometry, encoding="utf-8")
        except Exception:
            pass


    # -------------------------
    # Theme (light/dark)
    # -------------------------

    def load_theme(self) -> Optional[str]:
        if not self.paths.theme_file.exists():
            return None
        try:
            val = self.paths.theme_file.read_text(encoding="utf-8").strip().lower()
            if val in ("dark", "light"):
                return val
        except Exception:
            pass
        return None

    def save_theme(self, mode: str) -> None:
        try:
            atomic_write_text(self.paths.theme_file, mode, encoding="utf-8")
        except Exception:
            pass

    def toggle_theme(self) -> None:
        self.theme_mode = "dark" if bool(self.theme_var.get()) else "light"
        self.save_theme(self.theme_mode)
        self._apply_theme()

    def _apply_theme(self) -> None:
        theme = self._get_theme_palette()
        try:
            self.root.configure(bg=theme["bg"])
        except Exception:
            pass

        self._style_menu(self.menu, theme)
        self._style_menu(self.extra_menu, theme)
        self._style_menu(self.sort_menu, theme)
        self._style_menu(self.context_menu, theme)

        self._apply_theme_recursive(self.root, theme)
        self._style_ttk(theme)

    def _get_theme_palette(self) -> Dict[str, str]:
        if self.theme_mode == "dark":
            return {
                "bg": "#2b2b2b",
                "fg": "#e6e6e6",
                "muted_fg": "#b0b0b0",
                "entry_bg": "#3c3f41",
                "entry_fg": "#ffffff",
                "list_bg": "#3c3f41",
                "list_fg": "#ffffff",
                "select_bg": "#5c5c5c",
                "select_fg": "#ffffff",
                "button_bg": "#3c3f41",
                "button_fg": "#ffffff",
            }
        return {
            "bg": "#ffffff",
            "fg": "#000000",
            "muted_fg": "#666666",
            "entry_bg": "#ffffff",
            "entry_fg": "#000000",
            "list_bg": "#ffffff",
            "list_fg": "#000000",
            "select_bg": "#cfe8ff",
            "select_fg": "#000000",
            "button_bg": "#f0f0f0",
            "button_fg": "#000000",
        }

    def _apply_theme_recursive(self, widget: tk.Misc, theme: Dict[str, str]) -> None:
        for child in widget.winfo_children():
            self._style_widget(child, theme)
            self._apply_theme_recursive(child, theme)

    def _style_widget(self, w: tk.Misc, theme: Dict[str, str]) -> None:
        # Containers
        if isinstance(w, (tk.Tk, tk.Toplevel, tk.Frame, tk.LabelFrame, tk.Canvas)):
            try:
                w.configure(bg=theme["bg"])
            except Exception:
                pass

        # Labels
        if isinstance(w, tk.Label):
            try:
                fg_raw = w.cget("fg")
                fg_norm = str(fg_raw).strip().lower()

                # Preserve explicit "muted" labels
                if fg_norm in ("gray", "grey"):
                    fg_use = theme["muted_fg"]
                else:
                    # Fix common case: label kept the default black fg when switching to dark mode
                    if self.theme_mode == "dark" and fg_norm in ("black", "#000000", "systemwindowtext", "windowtext", "systemtext"):
                        fg_use = theme["fg"]
                    # ...and the reverse if a label was forced to white while switching back to light
                    elif self.theme_mode == "light" and fg_norm in ("white", "#ffffff"):
                        fg_use = theme["fg"]
                    else:
                        fg_use = fg_raw if fg_raw else theme["fg"]

                w.configure(bg=theme["bg"], fg=fg_use)
            except Exception:
                pass

        # Buttons & OptionMenu's Menubutton
        if isinstance(w, (tk.Button, tk.Menubutton)):
            try:
                w.configure(
                    bg=theme["button_bg"],
                    fg=theme["button_fg"],
                    activebackground=theme["select_bg"],
                    activeforeground=theme["select_fg"],
                )
            except Exception:
                pass

        # Entries / Text
        if isinstance(w, tk.Entry):
            try:
                w.configure(
                    bg=theme["entry_bg"],
                    fg=theme["entry_fg"],
                    insertbackground=theme["entry_fg"],
                    disabledbackground=theme["entry_bg"],
                    disabledforeground=theme["muted_fg"],
                )
            except Exception:
                pass

        if isinstance(w, tk.Text):
            try:
                w.configure(
                    bg=theme["entry_bg"],
                    fg=theme["entry_fg"],
                    insertbackground=theme["entry_fg"],
                )
            except Exception:
                pass

        # Listbox
        if isinstance(w, tk.Listbox):
            try:
                w.configure(
                    bg=theme["list_bg"],
                    fg=theme["list_fg"],
                    selectbackground=theme["select_bg"],
                    selectforeground=theme["select_fg"],
                )
            except Exception:
                pass

        # Scrollbars
        if isinstance(w, tk.Scrollbar):
            try:
                w.configure(bg=theme["bg"], troughcolor=theme["bg"], activebackground=theme["select_bg"])
            except Exception:
                pass

    def _style_menu(self, menu: Menu, theme: Dict[str, str]) -> None:
        # Menu styling is platform/theme dependent; some systems ignore these options.
        try:
            menu.configure(
                background=theme["bg"],
                foreground=theme["fg"],
                activebackground=theme["select_bg"],
                activeforeground=theme["select_fg"],
            )
        except Exception:
            pass

    def _style_ttk(self, theme: Dict[str, str]) -> None:
        try:
            # Use a theme that supports color changes better on many platforms
            if self.theme_mode == "dark":
                try:
                    self.style.theme_use("clam")
                except Exception:
                    pass
            elif self._ttk_theme_default:
                try:
                    self.style.theme_use(self._ttk_theme_default)
                except Exception:
                    pass

            self.style.configure(
                "Treeview",
                background=theme["list_bg"],
                fieldbackground=theme["list_bg"],
                foreground=theme["list_fg"],
            )
            self.style.map(
                "Treeview",
                background=[("selected", theme["select_bg"])],
                foreground=[("selected", theme["select_fg"])],
            )
            self.style.configure(
                "Treeview.Heading",
                background=theme["bg"],
                foreground=theme["fg"],
            )
        except Exception:
            pass

    def _style_window(self, win: Toplevel) -> None:
        theme = self._get_theme_palette()
        try:
            win.configure(bg=theme["bg"])
        except Exception:
            pass
        self._apply_theme_recursive(win, theme)
        self._style_ttk(theme)

    # -------------------------
    # Menu building
    # -------------------------

    def set_sort_mode(self, mode: str) -> None:
        self.sort_mode = mode
        self.update_menu()

    def get_usage_sum(self, path: PathTuple) -> int:
        node: Any = self.usage
        for key in path:
            if not isinstance(node, dict):
                return 0
            node = node.get(key, {})
        return sum_all_usage(node)

    def build_bookmarks_menu(self, parent_menu: Menu, items: JsonDict, current_path: PathTuple = ()) -> None:
        if self.sort_mode == "usage":
            sorted_keys = sorted(items.keys(), key=lambda k: self.get_usage_sum(current_path + (k,)), reverse=True)
        else:
            sorted_keys = sorted(items.keys(), key=lambda k: k.lower())

        for name in sorted_keys:
            value = items[name]
            new_path = current_path + (name,)
            if isinstance(value, dict):
                submenu = Menu(parent_menu, tearoff=0)
                self.build_bookmarks_menu(submenu, value, new_path)
                parent_menu.add_cascade(label=name, menu=submenu)
            else:
                if not isinstance(value, str):
                    messagebox.showerror(
                        "Invalid Bookmark", f"Bookmark '{' > '.join(new_path)}' has invalid link: {value}"
                    )
                    continue
                parent_menu.add_command(label=name, command=lambda link=value, p=new_path: self.record_usage_and_open(link, p))

    def update_menu(self) -> None:
        self.menu.delete(0, tk.END)
        self.build_bookmarks_menu(self.menu, self.bookmarks)
        self.menu.add_separator()
        self.menu.add_cascade(label="Tools", menu=self.extra_menu)
        self.menu.add_cascade(label="Sort", menu=self.sort_menu)

    # -------------------------
    # Opening links / commands
    # -------------------------

    def _open_with_named_browser(self, url: str, browser_used: str) -> None:
        """
        Uses webbrowser module. If a named browser is not available, falls back to default.
        """
        if browser_used in ("Default", "LastUsed", None, ""):
            webbrowser.open(url, new=2)
            return

        # Map selection names to likely system browser names.
        candidates = {
            "Chrome": ["google-chrome", "chrome", "chromium", "chromium-browser"],
            "Firefox": ["firefox"],
            "Edge": ["microsoft-edge", "msedge"],
        }.get(browser_used, [])

        controller = None
        for name in candidates:
            try:
                controller = webbrowser.get(name)
                break
            except webbrowser.Error:
                continue

        if controller is None:
            # Fallback: default browser
            webbrowser.open(url, new=2)
        else:
            controller.open(url, new=2)

    def open_target(self, target: str, browser_used: str) -> None:
        target = target.strip()
        if not target:
            return

        if is_url(target):
            try:
                self._open_with_named_browser(target, browser_used)
            except Exception as e:
                messagebox.showerror("Browser Error", f"Could not open URL: {e}")
            return

        p = Path(target)
        if p.exists():
            open_file_default(p.resolve())
            return

        # Treat as command
        try:
            # If user pasted a quoted command, keep it; shlex splits safely on Linux/macOS.
            args = shlex.split(target) if not sys.platform.startswith("win") else target
            subprocess.Popen(args, shell=isinstance(args, str))
        except Exception as e:
            messagebox.showerror("Error", f"Could not run command '{target}': {e}")

    def _get_usage_leaf_by_path(self, path: PathTuple) -> JsonDict:
        """
        Ensure and return the usage leaf node for this bookmark path.
        """
        node: JsonDict = self.usage
        for key in path[:-1]:
            node = ensure_usage_category(node, key)
        return ensure_usage_leaf(node, path[-1])

    def record_usage_and_open(self, target: str, path: PathTuple) -> None:
        entry = self._get_usage_leaf_by_path(path)
        entry["count"] = int(entry.get("count", 0)) + 1

        sel = self.browser_var.get()
        if sel == "LastUsed":
            used = entry.get("last_browser") or "Default"
            entry["last_browser"] = used
        else:
            used = sel
            entry["last_browser"] = used

        self.save_usage()
        self.update_menu()
        self.open_target(target, used)

    # -------------------------
    # Search suggestions
    # -------------------------

    def update_suggestions(self, *_: Any) -> None:
        query = self.search_var.get().strip().lower()
        if self.suggestion_listbox is not None:
            self.suggestion_listbox.destroy()
            self.suggestion_listbox = None
        if not query or self.search_entry is None:
            return

        matches = [(display, path) for display, path in get_all_bookmark_paths(self.bookmarks) if query in display.lower()]
        if not matches:
            return

        lb = tk.Listbox(self.root, height=min(len(matches), 6))
        self.suggestion_listbox = lb

        # place() uses coordinates relative to parent, so use winfo_x/y not winfo_rootx/y.
        x = self.search_entry.winfo_x()
        y = self.search_entry.winfo_y() + self.search_entry.winfo_height()
        lb.place(x=x, y=y)

        for display, _ in matches:
            lb.insert(tk.END, display)

        def on_select(evt: Any) -> None:
            w: tk.Listbox = evt.widget
            idx = w.curselection()
            if not idx:
                return
            sel_display = w.get(idx[0])
            for d, p in matches:
                if d == sel_display:
                    link = get_bookmark_by_path(self.bookmarks, p)
                    if link is not None:
                        self.record_usage_and_open(link, p)
                    break
            self.search_var.set("")
            w.destroy()
            self.suggestion_listbox = None

        lb.bind("<<ListboxSelect>>", on_select)

    # -------------------------
    # Tools: stats, manage, import/export
    # -------------------------

    def show_usage_stats(self) -> None:
        stat_win = Toplevel(self.root)
        self._style_window(stat_win)
        stat_win.title("Usage Statistics")
        self._set_child_icon(stat_win)
        stat_win.geometry(f"400x300+{self.root.winfo_x()+50}+{self.root.winfo_y()+50}")
        text = tk.Text(stat_win, wrap="none")
        text.pack(fill="both", expand=True)

        def recurse(bm_dict: JsonDict, usage_dict: JsonDict, prefix: str = "") -> None:
            for k, v in bm_dict.items():
                new_prefix = prefix + k
                if isinstance(v, dict):
                    cusage = sum_all_usage(usage_dict.get(k, {}))
                    text.insert(tk.END, f"[Category] {new_prefix} - total usage: {cusage}\n")
                    recurse(v, usage_dict.get(k, {}), new_prefix + " > ")
                else:
                    uentry = usage_dict.get(k, {"count": 0})
                    text.insert(tk.END, f"   {new_prefix} - usage: {uentry.get('count', 0)}\n")

        recurse(self.bookmarks, self.usage)
        text.config(state="disabled")

    def manage_bookmarks_window(self) -> None:
        mgr_win = Toplevel(self.root)
        self._style_window(mgr_win)
        mgr_win.title("Manage Bookmarks")
        self._set_child_icon(mgr_win)
        mgr_win.geometry(f"500x400+{self.root.winfo_x()+50}+{self.root.winfo_y()+50}")

        tree = ttk.Treeview(mgr_win)
        tree.pack(fill="both", expand=True, side="left")

        btn_frame = tk.Frame(mgr_win)
        btn_frame.pack(side="right", fill="y")

        def populate(parent: str, data: JsonDict, path: PathTuple = ()) -> None:
            for k, v in data.items():
                node_id = tree.insert(parent, "end", text=k, values=list(path + (k,)))
                if isinstance(v, dict):
                    populate(node_id, v, path + (k,))

        populate("", self.bookmarks)

        # Build link map from current bookmarks (not from a stale file read)
        all_bms = get_all_bookmark_paths(self.bookmarks)
        path_link_map: Dict[PathTuple, str] = {}
        for _, p in all_bms:
            link = get_bookmark_by_path(self.bookmarks, p)
            if link is not None:
                path_link_map[p] = link

        def move_item_up() -> None:
            sel = tree.selection()
            if not sel:
                return
            item = sel[0]
            parent = tree.parent(item)
            index = tree.index(item)
            if index > 0:
                tree.move(item, parent, index - 1)

        def move_item_down() -> None:
            sel = tree.selection()
            if not sel:
                return
            item = sel[0]
            parent = tree.parent(item)
            index = tree.index(item)
            tree.move(item, parent, index + 1)

        def rebuild_data() -> JsonDict:
            def traverse(node_id: str) -> Union[JsonDict, str]:
                children = tree.get_children(node_id)
                if not children:
                    # leaf
                    values = tuple(tree.item(node_id, "values"))
                    return path_link_map.get(values, "")
                cat: JsonDict = {}
                for child in children:
                    name = tree.item(child, "text")
                    cat[name] = traverse(child)
                return cat

            new_data: JsonDict = {}
            for top in tree.get_children(""):
                name = tree.item(top, "text")
                new_data[name] = traverse(top)
            return new_data

        def save_reorder() -> None:
            new_bm = rebuild_data()
            self.bookmarks.clear()
            self.bookmarks.update(new_bm)
            self.save_bookmarks()
            sync_usage_structure(self.bookmarks, self.usage)
            self.save_usage()
            self.update_menu()
            mgr_win.destroy()

        Button(btn_frame, text="Move Up", command=move_item_up).pack(pady=5)
        Button(btn_frame, text="Move Down", command=move_item_down).pack(pady=5)
        Button(btn_frame, text="Save Changes", command=save_reorder).pack(pady=5)

    def export_to_json(self) -> None:
        filename = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON files", "*.json")])
        if not filename:
            return
        try:
            atomic_write_json(Path(filename), self.bookmarks)
            messagebox.showinfo("Export", "Bookmarks exported successfully.")
        except Exception as e:
            messagebox.showerror("Export Error", f"Failed to export: {e}")

    def import_from_json(self) -> None:
        filename = filedialog.askopenfilename(filetypes=[("JSON files", "*.json")])
        if not filename:
            return
        try:
            imported = load_json(Path(filename), {})
            if not isinstance(imported, dict):
                raise ValueError("Imported JSON must be an object (dict).")

            def merge(src: JsonDict, dest: JsonDict) -> None:
                for k, v in src.items():
                    if k not in dest:
                        dest[k] = v
                    else:
                        if isinstance(v, dict) and isinstance(dest.get(k), dict):
                            merge(v, dest[k])
                        else:
                            dest[k] = v

            merge(imported, self.bookmarks)
            self.save_bookmarks()
            sync_usage_structure(self.bookmarks, self.usage)
            self.save_usage()
            self.update_menu()
            messagebox.showinfo("Import", "Bookmarks imported successfully.")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to import: {e}")

    def search_bookmarks(self, query: str) -> None:
        query = query.strip().lower()
        if not query:
            messagebox.showinfo("Search", "Please enter text to search.")
            return
        matches = [(display, path) for display, path in get_all_bookmark_paths(self.bookmarks) if query in display.lower()]
        if not matches:
            messagebox.showinfo("Search", f"No bookmarks found for '{query}'.")
            return
        popup = Menu(self.root, tearoff=0)

        for display, path in matches:
            def open_found(p: PathTuple = path) -> None:
                link = get_bookmark_by_path(self.bookmarks, p)
                if link is not None:
                    self.record_usage_and_open(link, p)

            popup.add_command(label=display, command=open_found)

        if self.search_button is not None:
            x = self.search_button.winfo_rootx()
            y = self.search_button.winfo_rooty() + self.search_button.winfo_height()
            popup.post(x, y)

    # -------------------------
    # CRUD windows
    # -------------------------

    def _set_child_icon(self, win: tk.Toplevel) -> None:
        if self.paths.icon_path.exists():
            try:
                win.iconbitmap(str(self.paths.icon_path))
            except Exception:
                pass

    def add_category_window(self) -> None:
        def save_category() -> None:
            parent_sel = parent_var.get()
            new_cat = cat_entry.get().strip()
            if not new_cat:
                messagebox.showwarning("Invalid Input", "Category name is required!")
                return

            if parent_sel == "None":
                if new_cat in self.bookmarks:
                    messagebox.showwarning("Exists", "A top-level category with this name already exists!")
                    return
                self.bookmarks[new_cat] = {}
                ensure_usage_category(self.usage, new_cat)
            else:
                parent_path = tuple(parent_sel.split(" > "))
                parent_cat = get_category_by_path(self.bookmarks, parent_path)
                parent_usage = get_category_by_path(self.usage, parent_path)
                if new_cat in parent_cat:
                    messagebox.showwarning("Exists", "A category with this name already exists here!")
                    return
                parent_cat[new_cat] = {}
                ensure_usage_category(parent_usage, new_cat)

            self.save_bookmarks()
            self.save_usage()
            self.update_menu()
            cat_window.destroy()

        cat_window = Toplevel(self.root)

        self._style_window(cat_window)
        cat_window.title("Add Category / Subcategory")
        self._set_child_icon(cat_window)
        cat_window.geometry(f"400x150+{self.root.winfo_x()+50}+{self.root.winfo_y()+50}")

        Label(cat_window, text="Parent Category (or None):").grid(row=0, column=0, padx=10, pady=5, sticky="w")
        parent_options = ["None"] + [" > ".join(p) for p in get_all_category_paths(self.bookmarks)]
        parent_var = StringVar(cat_window, value="None")
        OptionMenu(cat_window, parent_var, *parent_options).grid(row=0, column=1, padx=10, pady=5, sticky="ew")

        Label(cat_window, text="New Category Name:").grid(row=1, column=0, padx=10, pady=5, sticky="w")
        cat_entry = Entry(cat_window)
        cat_entry.grid(row=1, column=1, padx=10, pady=5, sticky="ew")

        Button(cat_window, text="Add Category", command=save_category).grid(row=2, column=1, padx=10, pady=10, sticky="e")
        cat_window.columnconfigure(1, weight=1)

    def add_bookmark_window(self) -> None:
        def save_new_bookmark() -> None:
            sel = parent_var.get()
            name = name_entry.get().strip()
            link = url_entry.get().strip()
            if not name or not link:
                messagebox.showwarning("Invalid Input", "Both Name and URL/Command are required!")
                return

            if sel == "None":
                if name in self.bookmarks:
                    messagebox.showwarning("Exists", "A top-level item with this name already exists!")
                    return
                self.bookmarks[name] = link
                ensure_usage_leaf(self.usage, name)
            else:
                cat_path = tuple(sel.split(" > "))
                category = get_category_by_path(self.bookmarks, cat_path)
                category_usage = get_category_by_path(self.usage, cat_path)
                if name in category:
                    messagebox.showwarning("Exists", "An item with this name already exists here!")
                    return
                category[name] = link
                ensure_usage_leaf(category_usage, name)

            self.save_bookmarks()
            self.save_usage()
            self.update_menu()
            add_window.destroy()

        add_window = Toplevel(self.root)

        self._style_window(add_window)
        add_window.title("Add Bookmark")
        self._set_child_icon(add_window)
        add_window.geometry(f"500x180+{self.root.winfo_x()+50}+{self.root.winfo_y()+50}")

        Label(add_window, text="Select Category (or None):").grid(row=0, column=0, padx=10, pady=5, sticky="w")
        parent_options = ["None"] + [" > ".join(p) for p in get_all_category_paths(self.bookmarks)]
        parent_var = StringVar(add_window, value="None")
        OptionMenu(add_window, parent_var, *parent_options).grid(row=0, column=1, padx=10, pady=5, sticky="ew")

        Label(add_window, text="Bookmark Name:").grid(row=1, column=0, padx=10, pady=5, sticky="w")
        name_entry = Entry(add_window)
        name_entry.grid(row=1, column=1, padx=10, pady=5, sticky="ew")

        Label(add_window, text="URL / Command:").grid(row=2, column=0, padx=10, pady=5, sticky="w")
        url_entry = Entry(add_window, width=60)
        url_entry.grid(row=2, column=1, padx=10, pady=5, sticky="ew")

        Button(add_window, text="Add Bookmark", command=save_new_bookmark).grid(row=3, column=1, padx=10, pady=10, sticky="e")
        add_window.columnconfigure(1, weight=1)

    def delete_bookmark_window(self) -> None:
        bm_list = get_all_bookmark_paths(self.bookmarks)
        if not bm_list:
            messagebox.showwarning("No Bookmarks", "There are no bookmarks to delete.")
            return

        del_window = Toplevel(self.root)

        self._style_window(del_window)
        del_window.title("Delete Bookmark")
        self._set_child_icon(del_window)
        del_window.geometry(f"450x130+{self.root.winfo_x()+50}+{self.root.winfo_y()+50}")

        Label(del_window, text="Select Bookmark to Delete:").grid(row=0, column=0, padx=10, pady=5, sticky="w")
        options = [display for display, _ in bm_list]
        selected_var = StringVar(del_window, value=options[0])
        OptionMenu(del_window, selected_var, *options).grid(row=0, column=1, padx=10, pady=5, sticky="ew")

        def delete_selected() -> None:
            sel_display = selected_var.get()
            for display, path in bm_list:
                if display != sel_display:
                    continue
                if len(path) == 1:
                    self.bookmarks.pop(path[0], None)
                    self.usage.pop(path[0], None)
                else:
                    parent = get_category_by_path(self.bookmarks, path[:-1])
                    parent.pop(path[-1], None)
                    usage_parent = get_category_by_path(self.usage, path[:-1])
                    usage_parent.pop(path[-1], None)
                break

            self.save_bookmarks()
            self.save_usage()
            self.update_menu()
            del_window.destroy()

        Button(del_window, text="Delete", command=delete_selected).grid(row=1, column=1, padx=10, pady=10, sticky="e")
        del_window.columnconfigure(1, weight=1)

    def delete_category_window(self) -> None:
        cat_paths = get_all_category_paths(self.bookmarks)
        if not cat_paths:
            messagebox.showwarning("No Categories", "There are no categories to delete.")
            return

        win = Toplevel(self.root)

        self._style_window(win)
        win.title("Delete Category")
        self._set_child_icon(win)
        win.geometry(f"450x130+{self.root.winfo_x()+50}+{self.root.winfo_y()+50}")

        Label(win, text="Select Category to Delete:").grid(row=0, column=0, padx=10, pady=5, sticky="w")
        options = [" > ".join(p) for p in cat_paths]
        selected_var = StringVar(win, value=options[0])
        OptionMenu(win, selected_var, *options).grid(row=0, column=1, padx=10, pady=5, sticky="ew")

        def delete_category() -> None:
            path = tuple(selected_var.get().split(" > "))
            self._delete_category_by_path(self.bookmarks, path)
            self._delete_category_by_path(self.usage, path)
            self.save_bookmarks()
            self.save_usage()
            self.update_menu()
            win.destroy()

        Button(win, text="Delete Category", command=delete_category).grid(row=1, column=1, padx=10, pady=10, sticky="e")
        win.columnconfigure(1, weight=1)

    def _delete_category_by_path(self, data: JsonDict, path: PathTuple) -> None:
        if not path:
            return
        if len(path) == 1:
            data.pop(path[0], None)
            return
        parent = get_category_by_path(data, path[:-1])
        parent.pop(path[-1], None)

    def edit_bookmark_window(self) -> None:
        bm_list = get_all_bookmark_paths(self.bookmarks)
        if not bm_list:
            messagebox.showwarning("No Bookmarks", "There are no bookmarks to edit.")
            return

        select_window = Toplevel(self.root)

        self._style_window(select_window)
        select_window.title("Select Bookmark to Edit")
        self._set_child_icon(select_window)
        select_window.geometry(f"450x130+{self.root.winfo_x()+50}+{self.root.winfo_y()+50}")

        Label(select_window, text="Select Bookmark to Edit:").grid(row=0, column=0, padx=10, pady=5, sticky="w")
        options = [display for display, _ in bm_list]
        selected_var = StringVar(select_window, value=options[0])
        OptionMenu(select_window, selected_var, *options).grid(row=0, column=1, padx=10, pady=5, sticky="ew")

        def open_edit_form() -> None:
            sel_display = selected_var.get()
            old_path: Optional[PathTuple] = None
            for display, path in bm_list:
                if display == sel_display:
                    old_path = path
                    break
            if old_path is None:
                return

            current_link = get_bookmark_by_path(self.bookmarks, old_path) or ""
            current_category = "None" if len(old_path) == 1 else " > ".join(old_path[:-1])
            current_name = old_path[-1]

            edit_window = Toplevel(self.root)

            self._style_window(edit_window)
            edit_window.title("Edit Bookmark")
            self._set_child_icon(edit_window)
            edit_window.geometry(f"500x200+{self.root.winfo_x()+50}+{self.root.winfo_y()+50}")

            Label(edit_window, text="Select Category (or None):").grid(row=0, column=0, padx=10, pady=5, sticky="w")
            parent_options = ["None"] + [" > ".join(p) for p in get_all_category_paths(self.bookmarks)]
            new_parent_var = StringVar(edit_window, value=current_category if current_category in parent_options else "None")
            OptionMenu(edit_window, new_parent_var, *parent_options).grid(row=0, column=1, padx=10, pady=5, sticky="ew")

            Label(edit_window, text="Bookmark Name:").grid(row=1, column=0, padx=10, pady=5, sticky="w")
            name_entry = Entry(edit_window)
            name_entry.insert(0, current_name)
            name_entry.grid(row=1, column=1, padx=10, pady=5, sticky="ew")

            Label(edit_window, text="URL / Command:").grid(row=2, column=0, padx=10, pady=5, sticky="w")
            url_entry = Entry(edit_window, width=60)
            url_entry.insert(0, current_link)
            url_entry.grid(row=2, column=1, padx=10, pady=5, sticky="ew")

            def save_edited_bookmark() -> None:
                new_cat_str = new_parent_var.get()
                new_name = name_entry.get().strip()
                new_link = url_entry.get().strip()
                if not new_name or not new_link:
                    messagebox.showwarning("Invalid Input", "Name and URL/command are required!")
                    return

                # Extract old usage leaf
                old_usage = self._pop_usage_leaf(old_path)

                # Remove old bookmark
                self._delete_bookmark_by_path(old_path)

                # Add to new location
                if new_cat_str == "None":
                    target_bm = self.bookmarks
                    target_usage = self.usage
                else:
                    new_cat_path = tuple(new_cat_str.split(" > "))
                    target_bm = get_category_by_path(self.bookmarks, new_cat_path)
                    target_usage = get_category_by_path(self.usage, new_cat_path)

                if new_name in target_bm:
                    messagebox.showwarning("Exists", "A bookmark with this name already exists in that category!")
                    # restore old item
                    self._set_bookmark_by_path(old_path, current_link)
                    self._set_usage_leaf_by_path(old_path, old_usage)
                    return

                target_bm[new_name] = new_link
                target_usage[new_name] = old_usage

                self.save_bookmarks()
                self.save_usage()
                self.update_menu()
                edit_window.destroy()
                select_window.destroy()

            Button(edit_window, text="Save Changes", command=save_edited_bookmark).grid(row=3, column=1, padx=10, pady=10, sticky="e")
            edit_window.columnconfigure(1, weight=1)

        Button(select_window, text="Edit", command=open_edit_form).grid(row=1, column=1, padx=10, pady=10, sticky="e")
        select_window.columnconfigure(1, weight=1)

    def _delete_bookmark_by_path(self, path: PathTuple) -> None:
        if len(path) == 1:
            self.bookmarks.pop(path[0], None)
            return
        parent = get_category_by_path(self.bookmarks, path[:-1])
        parent.pop(path[-1], None)

    def _set_bookmark_by_path(self, path: PathTuple, link: str) -> None:
        if len(path) == 1:
            self.bookmarks[path[0]] = link
            return
        parent = get_category_by_path(self.bookmarks, path[:-1])
        parent[path[-1]] = link

    def _pop_usage_leaf(self, path: PathTuple) -> JsonDict:
        if len(path) == 1:
            return self.usage.pop(path[0], {"count": 0, "last_browser": None})
        parent = get_category_by_path(self.usage, path[:-1])
        return parent.pop(path[-1], {"count": 0, "last_browser": None})

    def _set_usage_leaf_by_path(self, path: PathTuple, leaf: JsonDict) -> None:
        if len(path) == 1:
            self.usage[path[0]] = leaf
            return
        parent = get_category_by_path(self.usage, path[:-1])
        parent[path[-1]] = leaf

    def edit_category_window(self) -> None:
        cat_paths = get_all_category_paths(self.bookmarks)
        if not cat_paths:
            messagebox.showwarning("No Categories", "There are no categories to edit.")
            return

        select_window = Toplevel(self.root)

        self._style_window(select_window)
        select_window.title("Edit Category")
        self._set_child_icon(select_window)
        select_window.geometry(f"450x130+{self.root.winfo_x()+50}+{self.root.winfo_y()+50}")

        Label(select_window, text="Select Category to Edit:").grid(row=0, column=0, padx=10, pady=5, sticky="w")
        options = [" > ".join(p) for p in cat_paths]
        selected_var = StringVar(select_window, value=options[0])
        OptionMenu(select_window, selected_var, *options).grid(row=0, column=1, padx=10, pady=5, sticky="ew")

        def open_category_edit() -> None:
            path = tuple(selected_var.get().split(" > "))
            current_name = path[-1]

            edit_window = Toplevel(self.root)

            self._style_window(edit_window)
            edit_window.title("Rename Category")
            self._set_child_icon(edit_window)
            edit_window.geometry(f"400x120+{self.root.winfo_x()+50}+{self.root.winfo_y()+50}")

            Label(edit_window, text="New Category Name:").grid(row=0, column=0, padx=10, pady=5, sticky="w")
            name_entry = Entry(edit_window)
            name_entry.insert(0, current_name)
            name_entry.grid(row=0, column=1, padx=10, pady=5, sticky="ew")

            def save_edited_category() -> None:
                new_name = name_entry.get().strip()
                if not new_name:
                    messagebox.showwarning("Invalid Input", "Category name is required!")
                    return

                parent_bm = self.bookmarks if len(path) == 1 else get_category_by_path(self.bookmarks, path[:-1])
                parent_usage = self.usage if len(path) == 1 else get_category_by_path(self.usage, path[:-1])

                if new_name in parent_bm:
                    messagebox.showwarning("Exists", "A category with this name already exists at this level!")
                    return

                value_bm = parent_bm.pop(path[-1], {})
                parent_bm[new_name] = value_bm

                value_usage = parent_usage.pop(path[-1], {})
                parent_usage[new_name] = value_usage

                self.save_bookmarks()
                self.save_usage()
                self.update_menu()
                edit_window.destroy()
                select_window.destroy()

            Button(edit_window, text="Save Changes", command=save_edited_category).grid(row=1, column=1, padx=10, pady=10, sticky="e")
            edit_window.columnconfigure(1, weight=1)

        Button(select_window, text="Edit", command=open_category_edit).grid(row=1, column=1, padx=10, pady=10, sticky="e")
        select_window.columnconfigure(1, weight=1)

    def move_item_window(self) -> None:
        move_win = Toplevel(self.root)
        self._style_window(move_win)
        move_win.title("Move Bookmark/Category")
        self._set_child_icon(move_win)
        move_win.geometry(f"600x150+{self.root.winfo_x()+50}+{self.root.winfo_y()+50}")

        movable_items: List[Tuple[str, str, PathTuple]] = []
        for display, path in get_all_bookmark_paths(self.bookmarks):
            movable_items.append(("Bookmark: " + display, "bookmark", path))
        for path in get_all_category_paths(self.bookmarks):
            movable_items.append(("Category: " + " > ".join(path), "category", path))

        if not movable_items:
            messagebox.showwarning("No Items", "There are no bookmarks or categories to move.")
            move_win.destroy()
            return

        item_mapping = {item[0]: (item[1], item[2]) for item in movable_items}

        Label(move_win, text="Select item to move:").grid(row=0, column=0, padx=10, pady=5, sticky="w")
        item_var = StringVar(move_win, value=list(item_mapping.keys())[0])
        OptionMenu(move_win, item_var, *list(item_mapping.keys())).grid(row=0, column=1, padx=10, pady=5, sticky="ew")

        Label(move_win, text="Select destination category (or 'None'):").grid(row=1, column=0, padx=10, pady=5, sticky="w")
        dest_options = ["None"] + [" > ".join(p) for p in get_all_category_paths(self.bookmarks)]
        dest_var = StringVar(move_win, value="None")
        OptionMenu(move_win, dest_var, *dest_options).grid(row=1, column=1, padx=10, pady=5, sticky="ew")

        def move_selected() -> None:
            selected_item = item_var.get()
            item_type, old_path = item_mapping[selected_item]
            dest_sel = dest_var.get()

            if dest_sel == "None":
                new_parent_bm = self.bookmarks
                new_parent_usage = self.usage
            else:
                new_parent_path = tuple(dest_sel.split(" > "))
                new_parent_bm = get_category_by_path(self.bookmarks, new_parent_path)
                new_parent_usage = get_category_by_path(self.usage, new_parent_path)

            name = old_path[-1]
            if name in new_parent_bm:
                messagebox.showerror("Move Error", f"An item with name '{name}' already exists in destination.")
                return

            if item_type == "bookmark":
                link = get_bookmark_by_path(self.bookmarks, old_path)
                if link is None:
                    return
                self._delete_bookmark_by_path(old_path)
                old_usage = self._pop_usage_leaf(old_path)
                new_parent_bm[name] = link
                new_parent_usage[name] = old_usage
            else:
                # category
                old_parent_bm = self.bookmarks if len(old_path) == 1 else get_category_by_path(self.bookmarks, old_path[:-1])
                old_parent_usage = self.usage if len(old_path) == 1 else get_category_by_path(self.usage, old_path[:-1])
                cat_bm = old_parent_bm.pop(name, {})
                cat_usage = old_parent_usage.pop(name, {})
                new_parent_bm[name] = cat_bm
                new_parent_usage[name] = cat_usage

            self.save_bookmarks()
            self.save_usage()
            self.update_menu()
            move_win.destroy()

        Button(move_win, text="Move", command=move_selected).grid(row=2, column=1, padx=10, pady=10, sticky="e")
        move_win.columnconfigure(1, weight=1)

    # -------------------------
    # Window closing
    # -------------------------

    def on_closing(self) -> None:
        # Save the *exact* window-manager geometry string.
        # This prevents "drift" (eg. moving down each restart) caused by mixing
        # winfo_* coordinates with wm geometry coordinates.
        self.root.update_idletasks()
        geom = self.root.wm_geometry()
        if geom:
            self.save_geometry(geom)
        self.root.destroy()

    def _show_context_menu(self, event: tk.Event) -> None:
        self.context_menu.post(event.x_root, event.y_root)

    def run(self) -> None:
        self.root.mainloop()


def main() -> None:
    app = BookmarkApp()
    app.run()


if __name__ == "__main__":
    main()
