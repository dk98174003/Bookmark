# -*- coding: utf-8 -*-
import json
import os
import subprocess
import sys
import tkinter as tk
import webbrowser
from copy import deepcopy
from tkinter import Menu, Toplevel, messagebox, filedialog
from tkinter import ttk

APP_TITLE = "Bookmarks Manager"
DEFAULT_GEOMETRY = "860x50"
MIN_WIDTH = 700
FIXED_HEIGHT = 50
SORT_BY_USAGE = "usage"
SORT_BY_NAME = "name"
BROWSERS = ("LastUsed", "Edge", "Firefox", "Chrome", "Default")

root = None
menu = None
extra_menu = None
sort_menu = None
context_menu = None
browser_var = None
search_var = None
search_entry = None
search_button = None
icon_path = None

sort_mode = SORT_BY_USAGE
bookmarks = {}
usage = {}


def get_app_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def safe_iconbitmap(window: tk.Misc) -> None:
    if icon_path and os.path.exists(icon_path):
        try:
            window.iconbitmap(icon_path)
        except Exception:
            pass


APP_DIR = get_app_dir()
BOOKMARKS_FILE = os.path.join(APP_DIR, "bookmarks.json")
USAGE_FILE = os.path.join(APP_DIR, "usage.json")
GEOMETRY_FILE = os.path.join(APP_DIR, "window_geometry.txt")


# -----------------------------
# Persistence and validation
# -----------------------------
def load_json_file(path: str, default):
    if not os.path.exists(path):
        return deepcopy(default)
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except json.JSONDecodeError as exc:
        messagebox.showerror("Load Error", f"Could not load '{os.path.basename(path)}':\n{exc}")
        return deepcopy(default)
    except OSError as exc:
        messagebox.showerror("Load Error", f"Could not read '{os.path.basename(path)}':\n{exc}")
        return deepcopy(default)


def save_json_file(path: str, data) -> bool:
    try:
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=4, ensure_ascii=False)
        return True
    except OSError as exc:
        messagebox.showerror("Save Error", f"Could not write '{os.path.basename(path)}':\n{exc}")
        return False


def save_bookmarks() -> bool:
    return save_json_file(BOOKMARKS_FILE, bookmarks)


def save_usage() -> bool:
    return save_json_file(USAGE_FILE, usage)


def load_bookmarks():
    data = load_json_file(BOOKMARKS_FILE, {})
    if not isinstance(data, dict):
        messagebox.showerror("Load Error", "Bookmarks file must contain a JSON object at the top level.")
        return {}
    return normalize_bookmark_tree(data)


def load_usage():
    data = load_json_file(USAGE_FILE, {})
    if not isinstance(data, dict):
        return {}
    return data


def normalize_bookmark_tree(node):
    if not isinstance(node, dict):
        return {}

    normalized = {}
    for key, value in node.items():
        if not isinstance(key, str):
            key = str(key)
        if isinstance(value, dict):
            normalized[key] = normalize_bookmark_tree(value)
        else:
            normalized[key] = str(value)
    return normalized


def sync_usage_structure(bookmark_node, usage_node):
    if not isinstance(usage_node, dict):
        usage_node = {}

    for key in list(usage_node.keys()):
        if key not in bookmark_node:
            del usage_node[key]

    for key, value in bookmark_node.items():
        if isinstance(value, dict):
            usage_node[key] = sync_usage_structure(value, usage_node.get(key, {}))
        else:
            entry = usage_node.get(key)
            if not isinstance(entry, dict):
                entry = {}
            entry["count"] = int(entry.get("count", 0) or 0)
            entry["last_browser"] = entry.get("last_browser")
            usage_node[key] = entry

    return usage_node


def load_geometry():
    if not os.path.exists(GEOMETRY_FILE):
        return None
    try:
        with open(GEOMETRY_FILE, "r", encoding="utf-8") as handle:
            value = handle.read().strip()
        return value or None
    except OSError:
        return None


def save_geometry(geometry: str) -> None:
    try:
        with open(GEOMETRY_FILE, "w", encoding="utf-8") as handle:
            handle.write(geometry)
    except OSError as exc:
        messagebox.showerror("Save Error", f"Could not save window geometry:\n{exc}")


# -----------------------------
# Tree helpers
# -----------------------------
def get_node_by_path(data: dict, path: tuple):
    node = data
    for key in path:
        if not isinstance(node, dict) or key not in node:
            return None
        node = node[key]
    return node


def get_parent_dict(data: dict, path: tuple):
    if not path:
        return None
    if len(path) == 1:
        return data
    return get_node_by_path(data, path[:-1])


def get_all_category_paths(data=None, current_path=()):
    if data is None:
        data = bookmarks
    paths = []
    for key, value in data.items():
        if isinstance(value, dict):
            new_path = current_path + (key,)
            paths.append(new_path)
            paths.extend(get_all_category_paths(value, new_path))
    return paths


def get_all_bookmark_paths(data=None, current_path=()):
    if data is None:
        data = bookmarks
    result = []
    for key, value in data.items():
        new_path = current_path + (key,)
        if isinstance(value, dict):
            result.extend(get_all_bookmark_paths(value, new_path))
        else:
            result.append((" > ".join(new_path), new_path))
    return result


def get_bookmark_link(path: tuple):
    value = get_node_by_path(bookmarks, path)
    return value if isinstance(value, str) else None


def delete_node_by_path(data: dict, path: tuple) -> bool:
    parent = get_parent_dict(data, path)
    if parent is None:
        return False
    if path[-1] not in parent:
        return False
    del parent[path[-1]]
    return True


def ensure_usage_entry(path: tuple):
    node = usage
    for key in path[:-1]:
        child = node.get(key)
        if not isinstance(child, dict):
            child = {}
            node[key] = child
        node = child

    entry = node.get(path[-1])
    if not isinstance(entry, dict):
        entry = {"count": 0, "last_browser": None}
        node[path[-1]] = entry

    entry["count"] = int(entry.get("count", 0) or 0)
    entry["last_browser"] = entry.get("last_browser")
    return entry


def sum_all_usage(node) -> int:
    if not isinstance(node, dict):
        return 0
    if "count" in node:
        return int(node.get("count", 0) or 0)
    return sum(sum_all_usage(value) for value in node.values())


def get_usage_sum(path: tuple) -> int:
    node = usage
    for key in path:
        if not isinstance(node, dict):
            return 0
        node = node.get(key, {})
    return sum_all_usage(node)


def is_descendant_path(parent_path: tuple, child_path: tuple) -> bool:
    return len(child_path) >= len(parent_path) and child_path[:len(parent_path)] == parent_path


# -----------------------------
# Opening links / commands
# -----------------------------
def browser_executable(browser_name: str):
    if os.name != "nt":
        return None

    lookup = {
        "Chrome": [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        ],
        "Firefox": [
            r"C:\Program Files\Mozilla Firefox\firefox.exe",
            r"C:\Program Files (x86)\Mozilla Firefox\firefox.exe",
        ],
        "Edge": [
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        ],
    }

    for candidate in lookup.get(browser_name, []):
        if os.path.exists(candidate):
            return candidate
    return None


def is_url(value: str) -> bool:
    text = value.lower().strip()
    return text.startswith("http://") or text.startswith("https://")


def open_url(link: str, browser_name: str):
    if browser_name in ("Default", "LastUsed"):
        webbrowser.open(link)
        return

    executable = browser_executable(browser_name)
    if executable:
        subprocess.Popen([executable, link])
        return

    webbrowser.open(link)


def open_path_or_command(link: str):
    link = link.strip()

    if os.path.exists(link):
        if os.name == "nt":
            os.startfile(link)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", link])
        else:
            subprocess.Popen(["xdg-open", link])
        return

    subprocess.Popen(link, shell=True)


def open_link_with_browser(link: str, browser_name: str):
    try:
        if is_url(link):
            open_url(link, browser_name)
        else:
            open_path_or_command(link)
    except Exception as exc:
        messagebox.showerror("Open Error", f"Could not open:\n{link}\n\nReason:\n{exc}")


def record_usage_and_open(link: str, path: tuple):
    entry = ensure_usage_entry(path)

    selected = browser_var.get()
    if selected == "LastUsed":
        used_browser = entry.get("last_browser") or "Default"
    else:
        used_browser = selected

    entry["count"] = int(entry.get("count", 0) or 0) + 1
    entry["last_browser"] = used_browser

    save_usage()
    update_menu()
    open_link_with_browser(link, used_browser)


# -----------------------------
# Menu building
# -----------------------------
def sorted_keys_for_menu(items: dict, current_path: tuple):
    if sort_mode == SORT_BY_USAGE:
        return sorted(items.keys(), key=lambda key: get_usage_sum(current_path + (key,)), reverse=True)
    return sorted(items.keys(), key=lambda key: key.lower())


def build_bookmarks_menu(parent_menu: Menu, items: dict, current_path=()):
    for name in sorted_keys_for_menu(items, current_path):
        value = items[name]
        new_path = current_path + (name,)
        if isinstance(value, dict):
            submenu = Menu(parent_menu, tearoff=0)
            build_bookmarks_menu(submenu, value, new_path)
            parent_menu.add_cascade(label=name, menu=submenu)
        else:
            parent_menu.add_command(
                label=name,
                command=lambda link=value, path=new_path: record_usage_and_open(link, path),
            )


def update_menu():
    menu.delete(0, tk.END)
    build_bookmarks_menu(menu, bookmarks)
    menu.add_separator()
    menu.add_cascade(label="Tools", menu=extra_menu)
    menu.add_cascade(label="Sort", menu=sort_menu)


# -----------------------------
# Small UI helpers
# -----------------------------
def position_child_window(window: Toplevel, width: int, height: int):
    x = root.winfo_x() + 40
    y = root.winfo_y() + 40
    window.geometry(f"{width}x{height}+{x}+{y}")


def set_option_menu(variable: tk.StringVar, menu_parent, values, default_value):
    if not values:
        values = [default_value]
    variable.set(default_value)
    return tk.OptionMenu(menu_parent, variable, *values)


def path_to_label(path: tuple) -> str:
    return " > ".join(path)


def category_option_list(include_none=True):
    values = [path_to_label(path) for path in get_all_category_paths()]
    if include_none:
        return ["None", *values]
    return values


# -----------------------------
# CRUD windows
# -----------------------------
def add_category_window():
    window = Toplevel(root)
    safe_iconbitmap(window)
    window.title("Add Category / Subcategory")
    position_child_window(window, 430, 160)

    tk.Label(window, text="Parent Category (or None):").grid(row=0, column=0, padx=10, pady=8, sticky="w")
    parent_var = tk.StringVar(window)
    parent_menu = set_option_menu(parent_var, window, category_option_list(True), "None")
    parent_menu.grid(row=0, column=1, padx=10, pady=8, sticky="ew")

    tk.Label(window, text="New Category Name:").grid(row=1, column=0, padx=10, pady=8, sticky="w")
    name_entry = tk.Entry(window)
    name_entry.grid(row=1, column=1, padx=10, pady=8, sticky="ew")
    name_entry.focus_set()

    def save_category_action():
        new_name = name_entry.get().strip()
        if not new_name:
            messagebox.showwarning("Invalid Input", "Category name is required.")
            return

        selected_parent = parent_var.get()
        if selected_parent == "None":
            target_bm = bookmarks
            target_usage = usage
        else:
            parent_path = tuple(selected_parent.split(" > "))
            target_bm = get_node_by_path(bookmarks, parent_path)
            target_usage = get_node_by_path(usage, parent_path)
            if not isinstance(target_bm, dict) or not isinstance(target_usage, dict):
                messagebox.showerror("Add Error", "Selected parent category is invalid.")
                return

        if new_name in target_bm:
            messagebox.showwarning("Exists", "An item with that name already exists there.")
            return

        target_bm[new_name] = {}
        target_usage[new_name] = {}

        if save_bookmarks() and save_usage():
            update_menu()
            window.destroy()

    tk.Button(window, text="Add Category", command=save_category_action).grid(row=2, column=1, padx=10, pady=10, sticky="e")
    window.columnconfigure(1, weight=1)


def add_bookmark_window():
    window = Toplevel(root)
    safe_iconbitmap(window)
    window.title("Add Bookmark")
    position_child_window(window, 560, 190)

    tk.Label(window, text="Category (or None):").grid(row=0, column=0, padx=10, pady=8, sticky="w")
    parent_var = tk.StringVar(window)
    parent_menu = set_option_menu(parent_var, window, category_option_list(True), "None")
    parent_menu.grid(row=0, column=1, padx=10, pady=8, sticky="ew")

    tk.Label(window, text="Bookmark Name:").grid(row=1, column=0, padx=10, pady=8, sticky="w")
    name_entry = tk.Entry(window)
    name_entry.grid(row=1, column=1, padx=10, pady=8, sticky="ew")

    tk.Label(window, text="URL / Command:").grid(row=2, column=0, padx=10, pady=8, sticky="w")
    link_entry = tk.Entry(window)
    link_entry.grid(row=2, column=1, padx=10, pady=8, sticky="ew")

    name_entry.focus_set()

    def save_bookmark_action():
        name = name_entry.get().strip()
        link = link_entry.get().strip()
        if not name or not link:
            messagebox.showwarning("Invalid Input", "Both bookmark name and URL/command are required.")
            return

        selected_parent = parent_var.get()
        if selected_parent == "None":
            target_bm = bookmarks
            target_usage = usage
        else:
            parent_path = tuple(selected_parent.split(" > "))
            target_bm = get_node_by_path(bookmarks, parent_path)
            target_usage = get_node_by_path(usage, parent_path)
            if not isinstance(target_bm, dict) or not isinstance(target_usage, dict):
                messagebox.showerror("Add Error", "Selected category is invalid.")
                return

        if name in target_bm:
            messagebox.showwarning("Exists", "An item with that name already exists there.")
            return

        target_bm[name] = link
        target_usage[name] = {"count": 0, "last_browser": None}

        if save_bookmarks() and save_usage():
            update_menu()
            window.destroy()

    tk.Button(window, text="Add Bookmark", command=save_bookmark_action).grid(row=3, column=1, padx=10, pady=10, sticky="e")
    window.columnconfigure(1, weight=1)


def delete_bookmark_window():
    bookmark_items = get_all_bookmark_paths()
    if not bookmark_items:
        messagebox.showwarning("No Bookmarks", "There are no bookmarks to delete.")
        return

    window = Toplevel(root)
    safe_iconbitmap(window)
    window.title("Delete Bookmark")
    position_child_window(window, 500, 130)

    tk.Label(window, text="Select Bookmark:").grid(row=0, column=0, padx=10, pady=8, sticky="w")
    options = [display for display, _ in bookmark_items]
    selected_var = tk.StringVar(window)
    option_menu = set_option_menu(selected_var, window, options, options[0])
    option_menu.grid(row=0, column=1, padx=10, pady=8, sticky="ew")

    def delete_action():
        chosen = selected_var.get()
        selected_path = next((path for display, path in bookmark_items if display == chosen), None)
        if selected_path is None:
            return
        delete_node_by_path(bookmarks, selected_path)
        delete_node_by_path(usage, selected_path)
        if save_bookmarks() and save_usage():
            update_menu()
            window.destroy()

    tk.Button(window, text="Delete", command=delete_action).grid(row=1, column=1, padx=10, pady=10, sticky="e")
    window.columnconfigure(1, weight=1)


def delete_category_window():
    categories = get_all_category_paths()
    if not categories:
        messagebox.showwarning("No Categories", "There are no categories to delete.")
        return

    window = Toplevel(root)
    safe_iconbitmap(window)
    window.title("Delete Category")
    position_child_window(window, 500, 130)

    tk.Label(window, text="Select Category:").grid(row=0, column=0, padx=10, pady=8, sticky="w")
    options = [path_to_label(path) for path in categories]
    selected_var = tk.StringVar(window)
    option_menu = set_option_menu(selected_var, window, options, options[0])
    option_menu.grid(row=0, column=1, padx=10, pady=8, sticky="ew")

    def delete_action():
        path = tuple(selected_var.get().split(" > "))
        delete_node_by_path(bookmarks, path)
        delete_node_by_path(usage, path)
        if save_bookmarks() and save_usage():
            update_menu()
            window.destroy()

    tk.Button(window, text="Delete Category", command=delete_action).grid(row=1, column=1, padx=10, pady=10, sticky="e")
    window.columnconfigure(1, weight=1)


def edit_bookmark_window():
    bookmark_items = get_all_bookmark_paths()
    if not bookmark_items:
        messagebox.showwarning("No Bookmarks", "There are no bookmarks to edit.")
        return

    selector = Toplevel(root)
    safe_iconbitmap(selector)
    selector.title("Select Bookmark to Edit")
    position_child_window(selector, 520, 130)

    tk.Label(selector, text="Select Bookmark:").grid(row=0, column=0, padx=10, pady=8, sticky="w")
    options = [display for display, _ in bookmark_items]
    selected_var = tk.StringVar(selector)
    option_menu = set_option_menu(selected_var, selector, options, options[0])
    option_menu.grid(row=0, column=1, padx=10, pady=8, sticky="ew")

    def open_editor():
        selected_path = next((path for display, path in bookmark_items if display == selected_var.get()), None)
        if selected_path is None:
            return

        current_link = get_bookmark_link(selected_path)
        current_name = selected_path[-1]
        current_category = path_to_label(selected_path[:-1]) if len(selected_path) > 1 else "None"

        editor = Toplevel(root)
        safe_iconbitmap(editor)
        editor.title("Edit Bookmark")
        position_child_window(editor, 560, 220)

        tk.Label(editor, text="Category (or None):").grid(row=0, column=0, padx=10, pady=8, sticky="w")
        parent_var = tk.StringVar(editor)
        parent_options = category_option_list(True)
        parent_menu = set_option_menu(
            parent_var,
            editor,
            parent_options,
            current_category if current_category in parent_options else "None",
        )
        parent_menu.grid(row=0, column=1, padx=10, pady=8, sticky="ew")

        tk.Label(editor, text="Bookmark Name:").grid(row=1, column=0, padx=10, pady=8, sticky="w")
        name_entry = tk.Entry(editor)
        name_entry.insert(0, current_name)
        name_entry.grid(row=1, column=1, padx=10, pady=8, sticky="ew")

        tk.Label(editor, text="URL / Command:").grid(row=2, column=0, padx=10, pady=8, sticky="w")
        link_entry = tk.Entry(editor)
        link_entry.insert(0, current_link or "")
        link_entry.grid(row=2, column=1, padx=10, pady=8, sticky="ew")

        def save_action():
            new_name = name_entry.get().strip()
            new_link = link_entry.get().strip()
            if not new_name or not new_link:
                messagebox.showwarning("Invalid Input", "Both name and URL/command are required.")
                return

            selected_parent = parent_var.get()
            new_parent_path = () if selected_parent == "None" else tuple(selected_parent.split(" > "))
            target_bm = bookmarks if not new_parent_path else get_node_by_path(bookmarks, new_parent_path)
            target_usage = usage if not new_parent_path else get_node_by_path(usage, new_parent_path)
            if not isinstance(target_bm, dict) or not isinstance(target_usage, dict):
                messagebox.showerror("Edit Error", "Selected destination category is invalid.")
                return

            old_parent_bm = get_parent_dict(bookmarks, selected_path)
            old_parent_usage = get_parent_dict(usage, selected_path)
            old_usage_entry = deepcopy(old_parent_usage.get(selected_path[-1], {"count": 0, "last_browser": None}))
            old_value = old_parent_bm.get(selected_path[-1])

            same_target = selected_path[:-1] == new_parent_path and selected_path[-1] == new_name
            if not same_target and new_name in target_bm:
                messagebox.showwarning("Exists", "A bookmark with that name already exists in the destination category.")
                return

            del old_parent_bm[selected_path[-1]]
            old_parent_usage.pop(selected_path[-1], None)

            target_bm[new_name] = new_link
            target_usage[new_name] = old_usage_entry

            if save_bookmarks() and save_usage():
                update_menu()
                editor.destroy()
                selector.destroy()
            else:
                target_bm.pop(new_name, None)
                target_usage.pop(new_name, None)
                old_parent_bm[selected_path[-1]] = old_value
                old_parent_usage[selected_path[-1]] = old_usage_entry

        tk.Button(editor, text="Save Changes", command=save_action).grid(row=3, column=1, padx=10, pady=10, sticky="e")
        editor.columnconfigure(1, weight=1)

    tk.Button(selector, text="Edit", command=open_editor).grid(row=1, column=1, padx=10, pady=10, sticky="e")
    selector.columnconfigure(1, weight=1)


def edit_category_window():
    categories = get_all_category_paths()
    if not categories:
        messagebox.showwarning("No Categories", "There are no categories to edit.")
        return

    selector = Toplevel(root)
    safe_iconbitmap(selector)
    selector.title("Edit Category")
    position_child_window(selector, 500, 130)

    tk.Label(selector, text="Select Category:").grid(row=0, column=0, padx=10, pady=8, sticky="w")
    options = [path_to_label(path) for path in categories]
    selected_var = tk.StringVar(selector)
    option_menu = set_option_menu(selected_var, selector, options, options[0])
    option_menu.grid(row=0, column=1, padx=10, pady=8, sticky="ew")

    def open_editor():
        path = tuple(selected_var.get().split(" > "))
        current_name = path[-1]

        editor = Toplevel(root)
        safe_iconbitmap(editor)
        editor.title("Rename Category")
        position_child_window(editor, 420, 130)

        tk.Label(editor, text="New Category Name:").grid(row=0, column=0, padx=10, pady=8, sticky="w")
        name_entry = tk.Entry(editor)
        name_entry.insert(0, current_name)
        name_entry.grid(row=0, column=1, padx=10, pady=8, sticky="ew")

        def save_action():
            new_name = name_entry.get().strip()
            if not new_name:
                messagebox.showwarning("Invalid Input", "Category name is required.")
                return

            parent_bm = bookmarks if len(path) == 1 else get_node_by_path(bookmarks, path[:-1])
            parent_usage = usage if len(path) == 1 else get_node_by_path(usage, path[:-1])

            if new_name != current_name and new_name in parent_bm:
                messagebox.showwarning("Exists", "A category or bookmark with that name already exists at this level.")
                return

            parent_bm[new_name] = parent_bm.pop(current_name)
            parent_usage[new_name] = parent_usage.pop(current_name, {})

            if save_bookmarks() and save_usage():
                update_menu()
                editor.destroy()
                selector.destroy()

        tk.Button(editor, text="Save Changes", command=save_action).grid(row=1, column=1, padx=10, pady=10, sticky="e")
        editor.columnconfigure(1, weight=1)

    tk.Button(selector, text="Edit", command=open_editor).grid(row=1, column=1, padx=10, pady=10, sticky="e")
    selector.columnconfigure(1, weight=1)


def move_item_window():
    movable_items = []
    for display, path in get_all_bookmark_paths():
        movable_items.append((f"Bookmark: {display}", "bookmark", path))
    for path in get_all_category_paths():
        movable_items.append((f"Category: {path_to_label(path)}", "category", path))

    if not movable_items:
        messagebox.showwarning("No Items", "There are no bookmarks or categories to move.")
        return

    window = Toplevel(root)
    safe_iconbitmap(window)
    window.title("Move Bookmark / Category")
    position_child_window(window, 640, 160)

    item_map = {label: (node_type, path) for label, node_type, path in movable_items}

    tk.Label(window, text="Select item to move:").grid(row=0, column=0, padx=10, pady=8, sticky="w")
    item_var = tk.StringVar(window)
    item_options = list(item_map.keys())
    item_menu = set_option_menu(item_var, window, item_options, item_options[0])
    item_menu.grid(row=0, column=1, padx=10, pady=8, sticky="ew")

    tk.Label(window, text="Destination category (or None):").grid(row=1, column=0, padx=10, pady=8, sticky="w")
    dest_var = tk.StringVar(window)
    dest_menu = set_option_menu(dest_var, window, category_option_list(True), "None")
    dest_menu.grid(row=1, column=1, padx=10, pady=8, sticky="ew")

    def move_action():
        selected_item = item_var.get()
        item_type, old_path = item_map[selected_item]
        destination = dest_var.get()
        new_parent_path = () if destination == "None" else tuple(destination.split(" > "))

        if item_type == "category":
            if new_parent_path == old_path or is_descendant_path(old_path, new_parent_path):
                messagebox.showerror("Move Error", "You cannot move a category into itself or one of its subcategories.")
                return

        if item_type == "bookmark" and old_path[:-1] == new_parent_path:
            window.destroy()
            return
        if item_type == "category" and old_path[:-1] == new_parent_path:
            window.destroy()
            return

        target_bm = bookmarks if not new_parent_path else get_node_by_path(bookmarks, new_parent_path)
        target_usage = usage if not new_parent_path else get_node_by_path(usage, new_parent_path)
        if not isinstance(target_bm, dict) or not isinstance(target_usage, dict):
            messagebox.showerror("Move Error", "Destination category is invalid.")
            return

        source_parent_bm = get_parent_dict(bookmarks, old_path)
        source_parent_usage = get_parent_dict(usage, old_path)
        name = old_path[-1]

        if name in target_bm:
            messagebox.showerror("Move Error", f"An item named '{name}' already exists in the destination.")
            return

        target_bm[name] = source_parent_bm.pop(name)
        target_usage[name] = source_parent_usage.pop(
            name,
            {} if item_type == "category" else {"count": 0, "last_browser": None},
        )

        if save_bookmarks() and save_usage():
            update_menu()
            window.destroy()

    tk.Button(window, text="Move", command=move_action).grid(row=2, column=1, padx=10, pady=10, sticky="e")
    window.columnconfigure(1, weight=1)


# -----------------------------
# Manage / reorder window
# -----------------------------
def manage_bookmarks_window():
    window = Toplevel(root)
    safe_iconbitmap(window)
    window.title("Manage Bookmarks")
    position_child_window(window, 680, 450)

    tree = ttk.Treeview(window, columns=("node_type", "path"), show="tree")
    tree.pack(fill="both", expand=True, side="left")

    button_frame = tk.Frame(window)
    button_frame.pack(side="right", fill="y", padx=6, pady=6)

    original_links = {path: get_bookmark_link(path) for _, path in get_all_bookmark_paths()}

    def populate(parent_id, data, current_path=()):
        for key, value in data.items():
            path = current_path + (key,)
            node_type = "category" if isinstance(value, dict) else "bookmark"
            item_id = tree.insert(parent_id, "end", text=key, values=(node_type, path_to_label(path)))
            if isinstance(value, dict):
                populate(item_id, value, path)

    populate("", bookmarks)

    def move_selected(direction: int):
        selection = tree.selection()
        if not selection:
            return
        item_id = selection[0]
        parent_id = tree.parent(item_id)
        index = tree.index(item_id)
        new_index = index + direction
        if new_index < 0:
            return
        sibling_count = len(tree.get_children(parent_id))
        if new_index >= sibling_count:
            return
        tree.move(item_id, parent_id, new_index)

    def rebuild_node(item_id):
        item = tree.item(item_id)
        name = item["text"]
        values = item.get("values", [])
        node_type = values[0] if values else "bookmark"

        if node_type == "bookmark":
            original_path_label = values[1] if len(values) > 1 else name
            original_path = tuple(original_path_label.split(" > ")) if original_path_label else (name,)
            return name, original_links.get(original_path, "")

        category_data = {}
        for child_id in tree.get_children(item_id):
            child_name, child_value = rebuild_node(child_id)
            category_data[child_name] = child_value
        return name, category_data

    def save_reorder():
        new_tree = {}
        for top_item in tree.get_children(""):
            name, value = rebuild_node(top_item)
            new_tree[name] = value

        bookmarks.clear()
        bookmarks.update(new_tree)
        sync_usage_structure(bookmarks, usage)

        if save_bookmarks() and save_usage():
            update_menu()
            window.destroy()

    tk.Button(button_frame, text="Move Up", command=lambda: move_selected(-1)).pack(fill="x", pady=4)
    tk.Button(button_frame, text="Move Down", command=lambda: move_selected(1)).pack(fill="x", pady=4)
    tk.Button(button_frame, text="Save Changes", command=save_reorder).pack(fill="x", pady=8)


# -----------------------------
# Import / export / stats / search
# -----------------------------
def export_to_json():
    filename = filedialog.asksaveasfilename(
        defaultextension=".json",
        filetypes=[("JSON files", "*.json")]
    )
    if not filename:
        return
    try:
        with open(filename, "w", encoding="utf-8") as handle:
            json.dump(bookmarks, handle, indent=4, ensure_ascii=False)
        messagebox.showinfo("Export", "Bookmarks exported successfully.")
    except OSError as exc:
        messagebox.showerror("Export Error", f"Could not export bookmarks:\n{exc}")


def merge_bookmark_dict(source: dict, destination: dict):
    for key, value in source.items():
        if isinstance(value, dict) and isinstance(destination.get(key), dict):
            merge_bookmark_dict(value, destination[key])
        else:
            destination[key] = deepcopy(value)


def import_from_json():
    filename = filedialog.askopenfilename(filetypes=[("JSON files", "*.json")])
    if not filename:
        return

    try:
        with open(filename, "r", encoding="utf-8") as handle:
            imported = json.load(handle)
        if not isinstance(imported, dict):
            raise ValueError("Imported JSON must contain an object at the top level.")
        imported = normalize_bookmark_tree(imported)
        merge_bookmark_dict(imported, bookmarks)
        sync_usage_structure(bookmarks, usage)
        if save_bookmarks() and save_usage():
            update_menu()
            messagebox.showinfo("Import", "Bookmarks imported successfully.")
    except Exception as exc:
        messagebox.showerror("Import Error", f"Failed to import bookmarks:\n{exc}")


def show_usage_stats():
    window = Toplevel(root)
    safe_iconbitmap(window)
    window.title("Usage Statistics")
    position_child_window(window, 500, 360)

    text = tk.Text(window, wrap="none")
    text.pack(fill="both", expand=True)

    def write_stats(bookmark_node, usage_node, prefix=""):
        for key, value in bookmark_node.items():
            current_label = f"{prefix}{key}"
            if isinstance(value, dict):
                total = sum_all_usage(usage_node.get(key, {})) if isinstance(usage_node, dict) else 0
                text.insert(tk.END, f"[Category] {current_label} - total usage: {total}\n")
                write_stats(value, usage_node.get(key, {}) if isinstance(usage_node, dict) else {}, current_label + " > ")
            else:
                entry = usage_node.get(key, {}) if isinstance(usage_node, dict) else {}
                text.insert(tk.END, f"    {current_label} - usage: {int(entry.get('count', 0) or 0)}\n")

    write_stats(bookmarks, usage)
    text.config(state="disabled")


def search_bookmarks(query: str):
    query = query.strip().lower()
    if not query:
        return

    matches = [
        (display, path)
        for display, path in get_all_bookmark_paths()
        if query in display.lower()
    ]

    if not matches:
        messagebox.showinfo("Search", f"No bookmarks found for '{query}'.")
        return

    popup = Menu(root, tearoff=0)
    for display, path in matches:
        popup.add_command(
            label=display,
            command=lambda chosen_path=path: record_usage_and_open(
                get_bookmark_link(chosen_path), chosen_path
            )
        )

    popup.post(
        search_button.winfo_rootx(),
        search_button.winfo_rooty() + search_button.winfo_height()
    )


# -----------------------------
# App lifecycle
# -----------------------------
def show_context_menu(event):
    context_menu.post(event.x_root, event.y_root)


def force_compact_height():
    root.update_idletasks()
    width = root.winfo_width()
    x = root.winfo_x()
    y = root.winfo_y()
    root.geometry(f"{width}x{FIXED_HEIGHT}+{x}+{y}")
    root.minsize(MIN_WIDTH, FIXED_HEIGHT)
    root.maxsize(10000, FIXED_HEIGHT)


def on_closing():
    root.update_idletasks()
    width = root.winfo_width()
    x = root.winfo_x()
    y = root.winfo_y()
    save_geometry(f"{width}x{FIXED_HEIGHT}+{x}+{y}")
    root.destroy()


def set_sort_mode(mode: str):
    global sort_mode
    sort_mode = mode
    update_menu()


def do_search():
    search_bookmarks(search_var.get())
    search_var.set("")


def build_ui():
    global menu, extra_menu, sort_menu, context_menu
    global browser_var, search_var, search_entry, search_button

    menu = Menu(root)
    root.config(menu=menu)

    extra_menu = Menu(menu, tearoff=0)
    extra_menu.add_command(label="Import Bookmarks", command=import_from_json)
    extra_menu.add_command(label="Export Bookmarks", command=export_to_json)
    extra_menu.add_separator()
    extra_menu.add_command(label="Manage Bookmarks", command=manage_bookmarks_window)
    extra_menu.add_command(label="Usage Stats", command=show_usage_stats)

    sort_menu = Menu(menu, tearoff=0)
    sort_menu.add_command(label="Sort by Usage", command=lambda: set_sort_mode(SORT_BY_USAGE))
    sort_menu.add_command(label="Sort by Name", command=lambda: set_sort_mode(SORT_BY_NAME))

    context_menu = Menu(root, tearoff=0)
    context_menu.add_command(label="Add Bookmark", command=add_bookmark_window)
    context_menu.add_command(label="Add Category", command=add_category_window)
    context_menu.add_command(label="Edit Bookmark", command=edit_bookmark_window)
    context_menu.add_command(label="Edit Category", command=edit_category_window)
    context_menu.add_command(label="Delete Bookmark", command=delete_bookmark_window)
    context_menu.add_command(label="Delete Category", command=delete_category_window)
    context_menu.add_command(label="Move Bookmark / Category", command=move_item_window)

    root.bind("<Button-3>", show_context_menu)

    content_frame = tk.Frame(root)
    content_frame.pack(side="top", fill="x", padx=8, pady=2)

    tk.Label(content_frame, text="Browser:").grid(row=0, column=0, padx=(0, 4), pady=0, sticky="w")

    browser_var = tk.StringVar(root, value="LastUsed")
    browser_menu = tk.OptionMenu(content_frame, browser_var, *BROWSERS)
    browser_menu.config(width=8, padx=2, pady=0, highlightthickness=0)
    browser_menu.grid(row=0, column=1, padx=(0, 10), pady=0, sticky="w")

    search_var = tk.StringVar()
    search_entry = tk.Entry(content_frame, textvariable=search_var, width=18)
    search_entry.grid(row=0, column=2, padx=(0, 4), pady=0, ipady=0, sticky="w")
    search_entry.bind("<Return>", lambda event: do_search())

    search_button = tk.Button(content_frame, text="Search", command=do_search, padx=4, pady=0)
    search_button.grid(row=0, column=3, padx=(0, 8), pady=0, ipadx=0, ipady=0, sticky="w")

    tk.Label(
        content_frame,
        text="@Knud Schroder",
        fg="gray"
    ).grid(row=0, column=4, padx=(8, 0), pady=0, sticky="e")

    content_frame.columnconfigure(4, weight=1)


def main():
    global root, bookmarks, usage, icon_path

    root = tk.Tk()
    root.title(APP_TITLE)

    saved_geometry = load_geometry()
    root.geometry(saved_geometry if saved_geometry else DEFAULT_GEOMETRY)
    root.minsize(MIN_WIDTH, FIXED_HEIGHT)

    icon_path = os.path.join(APP_DIR, "bookmark.ico")
    safe_iconbitmap(root)

    build_ui()

    bookmarks = load_bookmarks()
    usage = sync_usage_structure(bookmarks, load_usage())
    save_usage()
    update_menu()

    force_compact_height()

    root.protocol("WM_DELETE_WINDOW", on_closing)
    root.mainloop()


if __name__ == "__main__":
    main()