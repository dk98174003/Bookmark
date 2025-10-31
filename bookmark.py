# -*- coding: utf-8 -*-
import tkinter as tk
from tkinter import Menu, messagebox, Toplevel, Label, Entry, Button, StringVar, OptionMenu, filedialog
from tkinter import ttk  # for Treeview
import subprocess
import json
import os
import sys
import re

def get_data_dir():
    # Use current working directory for JSON files
    return os.getcwd()

DATA_DIR = get_data_dir()
BOOKMARKS_FILE = os.path.join(DATA_DIR, "bookmarks.json")
GEOMETRY_FILE = os.path.join(DATA_DIR, "window_geometry.txt")
USAGE_FILE = os.path.join(DATA_DIR, "usage.json")

sort_mode = "usage"

def load_bookmarks():
    if os.path.exists(BOOKMARKS_FILE):
        try:
            with open(BOOKMARKS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            messagebox.showerror("Load Error", f"Could not load bookmarks: {e}")
            return {}
    return {}

def save_bookmarks():
    with open(BOOKMARKS_FILE, "w", encoding="utf-8") as f:
        json.dump(bookmarks, f, indent=4)

def load_usage():
    if os.path.exists(USAGE_FILE):
        try:
            with open(USAGE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            messagebox.showerror("Load Error", f"Could not load usage data: {e}")
            return {}
    return {}

def save_usage():
    with open(USAGE_FILE, "w", encoding="utf-8") as f:
        json.dump(usage, f, indent=4)

def sync_usage_structure(bm_dict, usage_dict):
    for key in list(usage_dict.keys()):
        if key not in bm_dict:
            del usage_dict[key]
    for key, value in bm_dict.items():
        if isinstance(value, dict):
            if key not in usage_dict or not isinstance(usage_dict.get(key), dict):
                usage_dict[key] = {}
            sync_usage_structure(value, usage_dict[key])
        else:
            if key not in usage_dict or not isinstance(usage_dict.get(key), dict):
                usage_dict[key] = {"count": 0, "last_browser": None}
            else:
                if "count" not in usage_dict[key]:
                    usage_dict[key]["count"] = 0
                if "last_browser" not in usage_dict[key]:
                    usage_dict[key]["last_browser"] = None
    return usage_dict

def get_usage_entry(path):
    node = usage
    for key in path:
        node = node.get(key)
        if node is None:
            return None
    return node

def sum_all_usage(node):
    if isinstance(node, dict):
        if "count" in node:
            return node["count"]
        else:
            total = 0
            for val in node.values():
                total += sum_all_usage(val)
            return total
    return 0

def get_usage_sum(path):
    node = usage
    for key in path:
        node = node.get(key, {})
    return sum_all_usage(node)

def open_link_with_browser(link, browser_used):
    if link.lower().startswith("http://") or link.lower().startswith("https://"):
        try:
            if browser_used == "Chrome":
                path = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
                if not os.path.exists(path):
                    path = r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
                subprocess.Popen([path, link])
            elif browser_used == "Firefox":
                path = r"C:\Program Files\Mozilla Firefox\firefox.exe"
                if not os.path.exists(path):
                    path = r"C:\Program Files (x86)\Mozilla Firefox\firefox.exe"
                subprocess.Popen([path, link])
            elif browser_used == "Edge":
                path = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
                if not os.path.exists(path):
                    path = r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"
                subprocess.Popen([path, link])
            else:
                os.startfile(link)
        except Exception as e:
            messagebox.showerror("Browser Error", f"Could not open URL with {browser_used}: {e}")
    else:
        if os.path.exists(link):
            try:
                os.startfile(link)
                return
            except Exception as e:
                messagebox.showerror("Error", f"Could not open file '{link}': {e}")
                return
        try:
            subprocess.Popen(link, shell=True)
        except Exception as e:
            messagebox.showerror("Error", f"Could not run command '{link}': {e}")

def record_usage_and_open(link, path):
    entry = get_usage_entry(path)
    if entry is None:
        entry = {"count": 0, "last_browser": None}
    entry["count"] += 1
    sel = browser_var.get()
    if sel == "LastUsed":
        if entry["last_browser"]:
            used_browser = entry["last_browser"]
        else:
            used_browser = "Default"
            entry["last_browser"] = used_browser
    else:
        used_browser = sel
        entry["last_browser"] = used_browser
    save_usage()
    update_menu()
    open_link_with_browser(link, used_browser)

def get_all_category_paths(data, current_path=()):
    paths = []
    for key, value in data.items():
        if isinstance(value, dict):
            new_path = current_path + (key,)
            paths.append(new_path)
            paths.extend(get_all_category_paths(value, new_path))
    return paths

def get_all_bookmark_paths(data, current_path=()):
    bms = []
    for key, value in data.items():
        if isinstance(value, dict):
            bms.extend(get_all_bookmark_paths(value, current_path + (key,)))
        else:
            display = " > ".join(current_path + (key,))
            bms.append((display, current_path + (key,)))
    return bms

def get_category_by_path(data, path):
    for key in path:
        data = data.get(key, {})
    return data

def get_bookmark_by_path(bm, path):
    for key in path[:-1]:
        bm = bm.get(key, {})
    return bm.get(path[-1])

def delete_category_by_path(data, path):
    if len(path) == 1:
        if path[0] in data:
            del data[path[0]]
    else:
        parent = get_category_by_path(data, path[:-1])
        if path[-1] in parent:
            del parent[path[-1]]

def add_category_window():
    def save_category():
        parent_sel = parent_var.get()
        new_cat = cat_entry.get().strip()
        if not new_cat:
            messagebox.showwarning("Invalid Input", "Category name is required!")
            return
        if parent_sel == "None":
            if new_cat in bookmarks:
                messagebox.showwarning("Exists", "A top-level category with this name already exists!")
                return
            bookmarks[new_cat] = {}
            usage[new_cat] = {}
        else:
            parent_path = tuple(parent_sel.split(" > "))
            parent_cat = get_category_by_path(bookmarks, parent_path)
            parent_usage = get_category_by_path(usage, parent_path)
            if new_cat in parent_cat:
                messagebox.showwarning("Exists", "A category with this name already exists here!")
                return
            parent_cat[new_cat] = {}
            parent_usage[new_cat] = {}
        save_bookmarks()
        save_usage()
        update_menu()
        cat_window.destroy()

    cat_window = Toplevel(root)
    cat_window.iconbitmap(icon_path)
    cat_window.title("Add Category / Subcategory")
    cat_window.geometry("400x150+" + str(root.winfo_x() + 50) + "+" + str(root.winfo_y() + 50))
    Label(cat_window, text="Parent Category (or None):").grid(row=0, column=0, padx=10, pady=5, sticky="w")
    parent_options = ["None"] + [" > ".join(path) for path in get_all_category_paths(bookmarks)]
    parent_var = StringVar(cat_window)
    parent_var.set("None")
    OptionMenu(cat_window, parent_var, *parent_options).grid(row=0, column=1, padx=10, pady=5, sticky="ew")
    Label(cat_window, text="New Category Name:").grid(row=1, column=0, padx=10, pady=5, sticky="w")
    cat_entry = Entry(cat_window)
    cat_entry.grid(row=1, column=1, padx=10, pady=5, sticky="ew")
    Button(cat_window, text="Add Category", command=save_category).grid(row=2, column=1, padx=10, pady=10, sticky="e")
    cat_window.columnconfigure(1, weight=1)

def add_bookmark_window():
    def save_new_bookmark():
        sel = parent_var.get()
        name = name_entry.get().strip()
        link = url_entry.get().strip()
        if not name or not link:
            messagebox.showwarning("Invalid Input", "Both Name and URL/Command are required!")
            return
        if sel == "None":
            if name in bookmarks:
                messagebox.showwarning("Exists", "A top-level item with this name already exists!")
                return
            bookmarks[name] = link
            usage[name] = {"count": 0, "last_browser": None}
        else:
            cat_path = tuple(sel.split(" > "))
            category = get_category_by_path(bookmarks, cat_path)
            category_usage = get_category_by_path(usage, cat_path)
            if name in category:
                messagebox.showwarning("Exists", "An item with this name already exists here!")
                return
            category[name] = link
            category_usage[name] = {"count": 0, "last_browser": None}
        save_bookmarks()
        save_usage()
        update_menu()
        add_window.destroy()

    add_window = Toplevel(root)
    add_window.iconbitmap(icon_path)
    add_window.title("Add Bookmark")
    add_window.geometry("500x180+" + str(root.winfo_x() + 50) + "+" + str(root.winfo_y() + 50))
    Label(add_window, text="Select Category (or None):").grid(row=0, column=0, padx=10, pady=5, sticky="w")
    parent_options = ["None"] + [" > ".join(path) for path in get_all_category_paths(bookmarks)]
    parent_var = StringVar(add_window)
    parent_var.set("None")
    OptionMenu(add_window, parent_var, *parent_options).grid(row=0, column=1, padx=10, pady=5, sticky="ew")
    Label(add_window, text="Bookmark Name:").grid(row=1, column=0, padx=10, pady=5, sticky="w")
    name_entry = Entry(add_window)
    name_entry.grid(row=1, column=1, padx=10, pady=5, sticky="ew")
    Label(add_window, text="URL / Command:").grid(row=2, column=0, padx=10, pady=5, sticky="w")
    url_entry = Entry(add_window, width=60)
    url_entry.grid(row=2, column=1, padx=10, pady=5, sticky="ew")
    Button(add_window, text="Add Bookmark", command=save_new_bookmark).grid(row=3, column=1, padx=10, pady=10, sticky="e")
    add_window.columnconfigure(1, weight=1)

def delete_bookmark_window():
    bm_list = get_all_bookmark_paths(bookmarks)
    if not bm_list:
        messagebox.showwarning("No Bookmarks", "There are no bookmarks to delete.")
        return
    del_window = Toplevel(root)
    del_window.iconbitmap(icon_path)
    del_window.title("Delete Bookmark")
    del_window.geometry("450x130+" + str(root.winfo_x() + 50) + "+" + str(root.winfo_y() + 50))
    Label(del_window, text="Select Bookmark to Delete:").grid(row=0, column=0, padx=10, pady=5, sticky="w")
    options = [display for display, _ in bm_list]
    selected_var = StringVar(del_window)
    selected_var.set(options[0])
    OptionMenu(del_window, selected_var, *options).grid(row=0, column=1, padx=10, pady=5, sticky="ew")

    def delete_selected():
        sel_display = selected_var.get()
        for display, path in bm_list:
            if display == sel_display:
                if len(path) == 1:
                    del bookmarks[path[0]]
                    usage.pop(path[0], None)
                else:
                    parent = get_category_by_path(bookmarks, path[:-1])
                    del parent[path[-1]]
                    usage_parent = get_category_by_path(usage, path[:-1])
                    usage_parent.pop(path[-1], None)
                break
        save_bookmarks()
        save_usage()
        update_menu()
        del_window.destroy()

    Button(del_window, text="Delete", command=delete_selected).grid(row=1, column=1, padx=10, pady=10, sticky="e")
    del_window.columnconfigure(1, weight=1)

def delete_category_window():
    cat_paths = get_all_category_paths(bookmarks)
    if not cat_paths:
        messagebox.showwarning("No Categories", "There are no categories to delete.")
        return
    cat_del_window = Toplevel(root)
    cat_del_window.iconbitmap(icon_path)
    cat_del_window.title("Delete Category")
    cat_del_window.geometry("450x130+" + str(root.winfo_x() + 50) + "+" + str(root.winfo_y() + 50))
    Label(cat_del_window, text="Select Category to Delete:").grid(row=0, column=0, padx=10, pady=5, sticky="w")
    options = [" > ".join(path) for path in cat_paths]
    selected_var = StringVar(cat_del_window)
    selected_var.set(options[0])
    OptionMenu(cat_del_window, selected_var, *options).grid(row=0, column=1, padx=10, pady=5, sticky="ew")

    def delete_category():
        sel = selected_var.get()
        path = tuple(sel.split(" > "))
        delete_category_by_path(bookmarks, path)
        delete_category_by_path(usage, path)
        save_bookmarks()
        save_usage()
        update_menu()
        cat_del_window.destroy()

    Button(cat_del_window, text="Delete Category", command=delete_category).grid(row=1, column=1, padx=10, pady=10, sticky="e")
    cat_del_window.columnconfigure(1, weight=1)

def edit_bookmark_window():
    bm_list = get_all_bookmark_paths(bookmarks)
    if not bm_list:
        messagebox.showwarning("No Bookmarks", "There are no bookmarks to edit.")
        return
    select_window = Toplevel(root)
    select_window.iconbitmap(icon_path)
    select_window.title("Select Bookmark to Edit")
    select_window.geometry("450x130+" + str(root.winfo_x() + 50) + "+" + str(root.winfo_y() + 50))
    Label(select_window, text="Select Bookmark to Edit:").grid(row=0, column=0, padx=10, pady=5, sticky="w")
    options = [display for display, _ in bm_list]
    selected_var = StringVar(select_window)
    selected_var.set(options[0])
    OptionMenu(select_window, selected_var, *options).grid(row=0, column=1, padx=10, pady=5, sticky="ew")

    def open_edit_form():
        sel_display = selected_var.get()
        old_path = None
        current_link = ""
        current_category = "None"
        current_name = ""
        for display, path in bm_list:
            if display == sel_display:
                old_path = path
                break
        if old_path is None:
            return
        if len(old_path) == 1:
            current_link = bookmarks[old_path[0]]
            current_name = old_path[0]
        else:
            parent_path = old_path[:-1]
            parent = get_category_by_path(bookmarks, parent_path)
            current_link = parent[old_path[-1]]
            current_category = " > ".join(parent_path) if parent_path else "None"
            current_name = old_path[-1]

        edit_window = Toplevel(root)
        edit_window.iconbitmap(icon_path)
        edit_window.title("Edit Bookmark")
        edit_window.geometry("500x200+" + str(root.winfo_x() + 50) + "+" + str(root.winfo_y() + 50))

        Label(edit_window, text="Select Category (or None):").grid(row=0, column=0, padx=10, pady=5, sticky="w")
        parent_options = ["None"] + [" > ".join(path) for path in get_all_category_paths(bookmarks)]
        new_parent_var = StringVar(edit_window)
        if current_category in parent_options:
            new_parent_var.set(current_category)
        else:
            new_parent_var.set("None")
        OptionMenu(edit_window, new_parent_var, *parent_options).grid(row=0, column=1, padx=10, pady=5, sticky="ew")

        Label(edit_window, text="Bookmark Name:").grid(row=1, column=0, padx=10, pady=5, sticky="w")
        name_entry = Entry(edit_window)
        name_entry.insert(0, current_name)
        name_entry.grid(row=1, column=1, padx=10, pady=5, sticky="ew")

        Label(edit_window, text="URL / Command:").grid(row=2, column=0, padx=10, pady=5, sticky="w")
        url_entry = Entry(edit_window, width=60)
        url_entry.insert(0, current_link)
        url_entry.grid(row=2, column=1, padx=10, pady=5, sticky="ew")

        def save_edited_bookmark():
            new_cat_str = new_parent_var.get()
            new_name = name_entry.get().strip()
            new_link = url_entry.get().strip()
            if not new_name or not new_link:
                messagebox.showwarning("Invalid Input", "Name and URL/command are required!")
                return
            if len(old_path) == 1:
                del bookmarks[old_path[0]]
                old_usage = usage.pop(old_path[0], {"count":0, "last_browser":None})
            else:
                parent = get_category_by_path(bookmarks, old_path[:-1])
                del parent[old_path[-1]]
                usage_parent = get_category_by_path(usage, old_path[:-1])
                old_usage = usage_parent.pop(old_path[-1], {"count":0, "last_browser":None})

            if new_cat_str == "None":
                target_bookmarks = bookmarks
                target_usage = usage
            else:
                new_cat_path = tuple(new_cat_str.split(" > "))
                target_bookmarks = get_category_by_path(bookmarks, new_cat_path)
                target_usage = get_category_by_path(usage, new_cat_path)

            if new_name in target_bookmarks:
                messagebox.showwarning("Exists", "A bookmark with this name already exists in that category!")
                if len(old_path) == 1:
                    bookmarks[old_path[0]] = current_link
                    usage[old_path[0]] = old_usage
                else:
                    parent = get_category_by_path(bookmarks, old_path[:-1])
                    parent[old_path[-1]] = current_link
                    usage_parent = get_category_by_path(usage, old_path[:-1])
                    usage_parent[old_path[-1]] = old_usage
                return
            target_bookmarks[new_name] = new_link
            target_usage[new_name] = old_usage

            save_bookmarks()
            save_usage()
            update_menu()
            edit_window.destroy()
            select_window.destroy()

        Button(edit_window, text="Save Changes", command=save_edited_bookmark).grid(row=3, column=1, padx=10, pady=10, sticky="e")
        edit_window.columnconfigure(1, weight=1)

    Button(select_window, text="Edit", command=open_edit_form).grid(row=1, column=1, padx=10, pady=10, sticky="e")
    select_window.columnconfigure(1, weight=1)

def edit_category_window():
    cat_paths = get_all_category_paths(bookmarks)
    if not cat_paths:
        messagebox.showwarning("No Categories", "There are no categories to edit.")
        return
    select_window = Toplevel(root)
    select_window.iconbitmap(icon_path)
    select_window.title("Edit Category")
    select_window.geometry("450x130+" + str(root.winfo_x() + 50) + "+" + str(root.winfo_y() + 50))
    Label(select_window, text="Select Category to Edit:").grid(row=0, column=0, padx=10, pady=5, sticky="w")
    options = [" > ".join(path) for path in cat_paths]
    selected_var = StringVar(select_window)
    selected_var.set(options[0])
    OptionMenu(select_window, selected_var, *options).grid(row=0, column=1, padx=10, pady=5, sticky="ew")

    def open_category_edit():
        sel = selected_var.get()
        path = tuple(sel.split(" > "))
        current_name = path[-1]

        edit_window = Toplevel(root)
        edit_window.iconbitmap(icon_path)
        edit_window.title("Rename Category")
        edit_window.geometry("400x120+" + str(root.winfo_x() + 50) + "+" + str(root.winfo_y() + 50))

        Label(edit_window, text="New Category Name:").grid(row=0, column=0, padx=10, pady=5, sticky="w")
        name_entry = Entry(edit_window)
        name_entry.insert(0, current_name)
        name_entry.grid(row=0, column=1, padx=10, pady=5, sticky="ew")

        def save_edited_category():
            new_name = name_entry.get().strip()
            if not new_name:
                messagebox.showwarning("Invalid Input", "Category name is required!")
                return
            parent_bm = bookmarks if len(path) == 1 else get_category_by_path(bookmarks, path[:-1])
            parent_usage = usage if len(path) == 1 else get_category_by_path(usage, path[:-1])
            if new_name in parent_bm:
                messagebox.showwarning("Exists", "A category with this name already exists at this level!")
                return
            value_bm = parent_bm[path[-1]]
            del parent_bm[path[-1]]
            parent_bm[new_name] = value_bm

            value_usage = parent_usage.get(path[-1], {})
            del parent_usage[path[-1]]
            parent_usage[new_name] = value_usage

            save_bookmarks()
            save_usage()
            update_menu()
            edit_window.destroy()
            select_window.destroy()

        Button(edit_window, text="Save Changes", command=save_edited_category).grid(row=1, column=1, padx=10, pady=10, sticky="e")
        edit_window.columnconfigure(1, weight=1)

    Button(select_window, text="Edit", command=open_category_edit).grid(row=1, column=1, padx=10, pady=10, sticky="e")
    select_window.columnconfigure(1, weight=1)

def move_item_window():
    move_win = Toplevel(root)
    move_win.iconbitmap(icon_path)
    move_win.title("Move Bookmark/Category")
    move_win.geometry("600x150+" + str(root.winfo_x() + 50) + "+" + str(root.winfo_y() + 50))

    movable_items = []
    for display, path in get_all_bookmark_paths(bookmarks):
        movable_items.append(("Bookmark: " + display, "bookmark", path))
    for path in get_all_category_paths(bookmarks):
        movable_items.append(("Category: " + " > ".join(path), "category", path))

    if not movable_items:
        messagebox.showwarning("No Items", "There are no bookmarks or categories to move.")
        move_win.destroy()
        return

    item_mapping = {item[0]: (item[1], item[2]) for item in movable_items}

    Label(move_win, text="Select item to move:").grid(row=0, column=0, padx=10, pady=5, sticky="w")
    item_var = StringVar(move_win)
    item_var.set(list(item_mapping.keys())[0])
    OptionMenu(move_win, item_var, *list(item_mapping.keys())).grid(row=0, column=1, padx=10, pady=5, sticky="ew")

    Label(move_win, text="Select destination category (or 'None'):").grid(row=1, column=0, padx=10, pady=5, sticky="w")
    dest_options = ["None"] + [" > ".join(path) for path in get_all_category_paths(bookmarks)]
    dest_var = StringVar(move_win)
    dest_var.set("None")
    OptionMenu(move_win, dest_var, *dest_options).grid(row=1, column=1, padx=10, pady=5, sticky="ew")

    def move_selected():
        selected_item = item_var.get()
        item_type, old_path = item_mapping[selected_item]
        dest_sel = dest_var.get()
        if dest_sel == "None":
            new_parent_dict = bookmarks
            new_usage_dict = usage
        else:
            new_parent_path = tuple(dest_sel.split(" > "))
            new_parent_dict = get_category_by_path(bookmarks, new_parent_path)
            new_usage_dict = get_category_by_path(usage, new_parent_path)

        if item_type == "bookmark":
            if len(old_path) == 1:
                old_parent = bookmarks
                old_usage_parent = usage
            else:
                old_parent = get_category_by_path(bookmarks, old_path[:-1])
                old_usage_parent = get_category_by_path(usage, old_path[:-1])
            item_name = old_path[-1]
            if item_name in new_parent_dict:
                messagebox.showerror("Move Error", f"An item with name '{item_name}' already exists in destination.")
                return
            new_parent_dict[item_name] = old_parent[item_name]
            del old_parent[item_name]
            new_usage_dict[item_name] = old_usage_parent.get(item_name, {"count": 0, "last_browser": None})
            if item_name in old_usage_parent:
                del old_usage_parent[item_name]
        elif item_type == "category":
            if len(old_path) == 1:
                old_parent = bookmarks
                old_usage_parent = usage
            else:
                old_parent = get_category_by_path(bookmarks, old_path[:-1])
                old_usage_parent = get_category_by_path(usage, old_path[:-1])
            cat_name = old_path[-1]
            if cat_name in new_parent_dict:
                messagebox.showerror("Move Error", f"A category named '{cat_name}' already exists in destination.")
                return
            new_parent_dict[cat_name] = old_parent[cat_name]
            del old_parent[cat_name]
            new_usage_dict[cat_name] = old_usage_parent.get(cat_name, {})
            if cat_name in old_usage_parent:
                del old_usage_parent[cat_name]
        else:
            messagebox.showerror("Move Error", "Unknown item type.")
            return
        save_bookmarks()
        save_usage()
        update_menu()
        move_win.destroy()

    Button(move_win, text="Move", command=move_selected).grid(row=2, column=1, padx=10, pady=10, sticky="e")
    move_win.columnconfigure(1, weight=1)

menu_references = {}

def build_bookmarks_menu(parent_menu, items, current_path=()):
    if sort_mode == "usage":
        sorted_keys = sorted(items.keys(),
                             key=lambda k: get_usage_sum(current_path + (k,)),
                             reverse=True)
    else:
        sorted_keys = sorted(items.keys(), key=lambda k: k.lower())

    for name in sorted_keys:
        value = items[name]
        new_path = current_path + (name,)
        if isinstance(value, dict):
            submenu = Menu(parent_menu, tearoff=0)
            build_bookmarks_menu(submenu, value, new_path)
            parent_menu.add_cascade(label=name, menu=submenu)
        else:
            if not isinstance(value, str):
                messagebox.showerror("Invalid Bookmark",
                                     f"Bookmark '{' > '.join(new_path)}' has invalid link: {value}")
                continue
            parent_menu.add_command(
                label=name,
                command=lambda link=value, p=new_path: record_usage_and_open(link, p)
            )
            menu_references[new_path] = (parent_menu, parent_menu.index("end"))

def update_menu():
    menu.delete(0, tk.END)
    menu_references.clear()

    build_bookmarks_menu(menu, bookmarks)
    menu.add_separator()

    menu.add_cascade(label="Tools", menu=extra_menu)
    menu.add_cascade(label="Sort", menu=sort_menu)

suggestion_listbox = None

def update_suggestions(event=None):
    global suggestion_listbox
    query = search_var.get().strip().lower()
    if suggestion_listbox:
        suggestion_listbox.destroy()
        suggestion_listbox = None
    if not query:
        return
    matches = []
    all_bms = get_all_bookmark_paths(bookmarks)
    for display, path in all_bms:
        if query in display.lower():
            matches.append((display, path))
    if matches:
        suggestion_listbox = tk.Listbox(root, height=min(len(matches), 6))
        x = search_entry.winfo_rootx()
        y = search_entry.winfo_rooty() + search_entry.winfo_height()
        suggestion_listbox.place(x=x, y=y)
        for display, _ in matches:
            suggestion_listbox.insert(tk.END, display)

        def on_select(evt):
            w = evt.widget
            idx = w.curselection()
            if not idx:
                return
            sel_display = w.get(idx[0])
            for d, p in matches:
                if d == sel_display:
                    link = get_bookmark_by_path(bookmarks, p)
                    record_usage_and_open(link, p)
                    break
            search_var.set("")
            w.destroy()

        suggestion_listbox.bind("<<ListboxSelect>>", on_select)

def show_usage_stats():
    stat_win = Toplevel(root)
    stat_win.iconbitmap(icon_path)
    stat_win.title("Usage Statistics")
    stat_win.geometry("400x300+" + str(root.winfo_x() + 50) + "+" + str(root.winfo_y() + 50))
    text = tk.Text(stat_win, wrap="none")
    text.pack(fill="both", expand=True)

    def recurse_stats(bm_dict, usage_dict, path_prefix=""):
        for k, v in bm_dict.items():
            new_prefix = path_prefix + k
            if isinstance(v, dict):
                cusage = sum_all_usage(usage_dict.get(k, {}))
                text.insert(tk.END, f"[Category] {new_prefix} - total usage: {cusage}\n")
                recurse_stats(v, usage_dict.get(k, {}), new_prefix + " > ")
            else:
                uentry = usage_dict.get(k, {"count": 0})
                text.insert(tk.END, f"   {new_prefix} - usage: {uentry['count']}\n")

    recurse_stats(bookmarks, usage)
    text.config(state="disabled")

def manage_bookmarks_window():
    mgr_win = Toplevel(root)
    mgr_win.iconbitmap(icon_path)
    mgr_win.title("Manage Bookmarks")
    mgr_win.geometry("500x400+" + str(root.winfo_x() + 50) + "+" + str(root.winfo_y() + 50))

    tree = ttk.Treeview(mgr_win)
    tree.pack(fill="both", expand=True, side="left")

    btn_frame = tk.Frame(mgr_win)
    btn_frame.pack(side="right", fill="y")

    def populate_tree(parent, data, path=()):
        for k, v in data.items():
            node_id = tree.insert(parent, "end", text=k, values=[*path, k])
            if isinstance(v, dict):
                populate_tree(node_id, v, path + (k,))

    populate_tree("", bookmarks)

    def move_item_up():
        sel = tree.selection()
        if not sel:
            return
        item = sel[0]
        parent = tree.parent(item)
        index = tree.index(item)
        if index > 0:
            tree.move(item, parent, index-1)

    def move_item_down():
        sel = tree.selection()
        if not sel:
            return
        item = sel[0]
        parent = tree.parent(item)
        index = tree.index(item)
        tree.move(item, parent, index+1)

    all_bms = get_all_bookmark_paths(load_bookmarks())
    path_link_map = {}
    for _, p in all_bms:
        link = get_bookmark_by_path(bookmarks, p)
        path_link_map[p] = link

    def rebuild_data():
        def traverse(node_id):
            children = tree.get_children(node_id)
            if not children:
                text_val = tree.item(node_id, "text")
                return text_val
            else:
                cat_dict = {}
                for c in children:
                    sub_result = traverse(c)
                    child_text = tree.item(c, "text")
                    if isinstance(sub_result, dict):
                        cat_dict[child_text] = sub_result
                    elif isinstance(sub_result, str):
                        cat_dict[child_text] = bookmarks_lookup(child_text, c)
                return cat_dict

        def bookmarks_lookup(text_val, node_id):
            full_path = tree.item(node_id, "values")
            full_path = tuple(full_path)
            return path_link_map.get(full_path, "")

        new_data = {}
        for top_item in tree.get_children(""):
            res = traverse(top_item)
            cat_name = tree.item(top_item, "text")
            if isinstance(res, dict):
                new_data[cat_name] = res
            else:
                new_data[cat_name] = bookmarks_lookup(cat_name, top_item)
        return new_data

    def save_reorder():
        new_bm = rebuild_data()
        bookmarks.clear()
        bookmarks.update(new_bm)
        save_bookmarks()
        sync_usage_structure(bookmarks, usage)
        save_usage()
        update_menu()
        mgr_win.destroy()

    Button(btn_frame, text="Move Up", command=move_item_up).pack(pady=5)
    Button(btn_frame, text="Move Down", command=move_item_down).pack(pady=5)
    Button(btn_frame, text="Save Changes", command=save_reorder).pack(pady=5)

def export_to_json():
    filename = filedialog.asksaveasfilename(defaultextension=".json",
                                            filetypes=[("JSON files","*.json")])
    if not filename:
        return
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(bookmarks, f, indent=4)
    messagebox.showinfo("Export", "Bookmarks exported successfully.")

def import_from_json():
    filename = filedialog.askopenfilename(filetypes=[("JSON files","*.json")])
    if not filename:
        return
    try:
        with open(filename, "r", encoding="utf-8") as f:
            imported = json.load(f)
        def merge_dict(src, dest):
            for k, v in src.items():
                if k not in dest:
                    dest[k] = v
                else:
                    if isinstance(v, dict) and isinstance(dest[k], dict):
                        merge_dict(v, dest[k])
                    else:
                        dest[k] = v
        merge_dict(imported, bookmarks)
        save_bookmarks()
        sync_usage_structure(bookmarks, usage)
        save_usage()
        update_menu()
        messagebox.showinfo("Import", "Bookmarks imported successfully.")
    except Exception as e:
        messagebox.showerror("Error", f"Failed to import: {e}")

def search_bookmarks(query):
    query = query.strip().lower()
    if not query:
        messagebox.showinfo("Search", "Please enter text to search.")
        return
    all_bms = get_all_bookmark_paths(bookmarks)
    matches = [(display, path) for display, path in all_bms if query in display.lower()]
    if not matches:
        messagebox.showinfo("Search", f"No bookmarks found for '{query}'.")
        return
    popup = Menu(root, tearoff=0)
    for display, path in matches:
        def open_found(p=path):
            link = get_bookmark_by_path(bookmarks, p)
            record_usage_and_open(link, p)
        popup.add_command(label=display, command=open_found)
    x = search_button.winfo_rootx()
    y = search_button.winfo_rooty() + search_button.winfo_height()
    popup.post(x, y)

def show_context_menu(event):
    context_menu.post(event.x_root, event.y_root)

def load_geometry():
    if os.path.exists(GEOMETRY_FILE):
        with open(GEOMETRY_FILE, "r", encoding="utf-8") as f:
            return f.read().strip()
    return None

def save_geometry(geometry):
    with open(GEOMETRY_FILE, "w", encoding="utf-8") as f:
        f.write(geometry)

def on_closing():
    root.update_idletasks()
    geom = root.winfo_geometry()
    m = re.match(r"(\d+)x(\d+)\+(\d+)\+(\d+)", geom)
    if m:
        width, height, x, y = map(int, m.groups())
        height += 20
        geom = f"{width}x{height}+{x}+{y}"
    save_geometry(geom)
    root.destroy()

def main():
    global root, menu, bookmarks, usage
    global browser_var, search_var, search_entry, search_button
    global extra_menu, sort_menu, context_menu, icon_path

    root = tk.Tk()
    root.title("Bookmarks Manager")

    saved_geom = load_geometry()
    if saved_geom:
        root.geometry(saved_geom)
    else:
        root.geometry("600x200")
    root.minsize(600, 40)

    # --- FIX ICON PATH HERE ---
    PROJECT_PATH = os.path.dirname(os.path.abspath(__file__))
    icon_path = os.path.join(PROJECT_PATH, "it4home.ico")
    if os.path.exists(icon_path):
        try:
            root.iconbitmap(icon_path)
        except Exception:
            pass

    menu = Menu(root)
    root.config(menu=menu)

    extra_menu = Menu(menu, tearoff=0)
    extra_menu.add_command(label="Import Bookmarks", command=import_from_json)
    extra_menu.add_command(label="Export Bookmarks", command=export_to_json)
    extra_menu.add_separator()
    extra_menu.add_command(label="Manage Bookmarks", command=manage_bookmarks_window)
    extra_menu.add_command(label="Usage Stats", command=show_usage_stats)

    sort_menu = Menu(menu, tearoff=0)
    def set_sort_mode(mode):
        global sort_mode
        sort_mode = mode
        update_menu()
    sort_menu.add_command(label="Sort by Usage", command=lambda: set_sort_mode("usage"))
    sort_menu.add_command(label="Sort by Name",  command=lambda: set_sort_mode("name"))

    context_menu = Menu(root, tearoff=0)
    context_menu.add_command(label="Add Bookmark", command=add_bookmark_window)
    context_menu.add_command(label="Add Category", command=add_category_window)
    context_menu.add_command(label="Edit Bookmark", command=edit_bookmark_window)
    context_menu.add_command(label="Edit Category", command=edit_category_window)
    context_menu.add_command(label="Delete Bookmark", command=delete_bookmark_window)
    context_menu.add_command(label="Delete Category", command=delete_category_window)
    context_menu.add_command(label="Move Bookmark/Category", command=move_item_window)
    root.bind("<Button-3>", show_context_menu)

    browser_var = StringVar(root)
    browser_var.set("LastUsed")
    browser_frame = tk.Frame(root)
    browser_frame.pack(side="bottom", fill="x")

    browser_label = tk.Label(browser_frame, text="Browser:")
    browser_label.pack(side="left", padx=(10, 2), pady=5)
    browser_menu = OptionMenu(browser_frame, browser_var, "LastUsed", "Edge", "Firefox", "Chrome", "Default")
    browser_menu.pack(side="left", pady=5)

    search_var = StringVar()
    search_var.trace("w", update_suggestions)
    search_entry = tk.Entry(browser_frame, textvariable=search_var, width=20)
    search_entry.pack(side="left", padx=(10, 2), pady=5)
    search_button = tk.Button(browser_frame, text="Search",
                              command=lambda: (search_bookmarks(search_var.get()), search_var.set("")))
    search_button.pack(side="left", padx=5, pady=5)

    info_label = tk.Label(browser_frame, text="\u0040Knud Schr\u00F8der (it4home.dk)", fg="gray")
    info_label.pack(side="right", padx=(2, 10), pady=5)

    global bookmarks
    bookmarks = load_bookmarks()
    global usage
    usage = load_usage()
    usage = sync_usage_structure(bookmarks, usage)
    save_usage()
    update_menu()

    root.protocol("WM_DELETE_WINDOW", on_closing)
    root.mainloop()

if __name__ == '__main__':
    main()
