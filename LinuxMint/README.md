# Bookmark Manager

A lightweight Python/Tkinter application for organizing, launching and tracking bookmarks (websites, files or commands).

<img width="785" height="97" alt="billede" src="https://github.com/user-attachments/assets/ec4761f1-0b8e-42d8-b4f6-721535905679" />

## Description

Bookmark Manager allows you to:

* Create and manage nested categories of bookmarks
* Launch bookmarks in a selected browser (Edge, Firefox, Chrome or the system default)
* Search bookmarks with suggestion/autocomplete support
* Import and export bookmarks to/from JSON for backup or sharing
* Track usage statistics (how often each bookmark is launched)
* Drag-and-drop reorder of bookmark entries
* Completely free to use and modify (public domain)

## Features

* Nested folder/category structure for bookmarks
* Bookmark types: URL, file path, command
* Select preferred browser for each bookmark category or entry
* Search bar with suggestions as you type
* Export all bookmarks + stats to JSON; import to restore or share
* Usage log (e.g., last launched timestamp, launch count)
* Easy drag-and-drop interface for rearranging bookmarks
* Simple, clear UI built with Tkinter
 
<img width="783" height="253" alt="billede" src="https://github.com/user-attachments/assets/5ae1c6f4-17fd-4852-b581-bcf2c78d0ad2" />

## Installation (Windows)

### Prerequisites

* Python 3.8 or newer installed (use official installer from python.org)
* “Add Python to PATH” option enabled during installation
* (Optional) Virtual environment recommended

### Steps

1. Open a Command Prompt (cmd.exe) or PowerShell.
2. Clone or download this project repository (for example):

   ```powershell
   git clone https://github.com/your-username/bookmark-manager.git
   cd bookmark-manager
   ```
3. (Optional) Create and activate a virtual environment:

   ```powershell
   python -m venv venv
   .\venv\Scripts\activate
   ```
4. Install required dependencies (if any – e.g., additional Python packages):

   ```powershell
   pip install -r requirements.txt
   ```

   *If you have no extra dependencies, you may skip this step.*
5. Run the application:

   ```powershell
   python main.py
   ```

   *(Replace `main.py` with the actual entry-point filename if different.)*

## Usage

* Use the menu to add a new bookmark or category.
* Select a bookmark and choose “Launch” to open it in the configured browser/file/command.
* Use the search box to quickly find bookmarks by name or keyword.
* Export your bookmarks (with usage stats) via the File → Export menu.
* Import bookmarks from a JSON file via File → Import (overwrites or merges).
* View usage statistics for each bookmark in the “Statistics” tab/menu.
* Drag and drop bookmarks or categories to change their order.

Have fun

Knud ;O)

