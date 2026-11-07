#!/usr/bin/env python3

import tkinter as tk
from tkinter import ttk

from rhyme_engine import (
    suggest_words,
    search_rhymes,
    FREQUENCY_CATEGORIES,
    WordNotFoundError,
    NoUsablePronunciationError,
)

COLORS = {
    "background": "#f3f5f8",
    "panel": "#ffffff",
    "sidebar": "#f8fafc",
    "text": "#202938",
    "muted": "#64748b",
    "border": "#dce2e9",
    "accent": "#2764a5",
    "accent_hover": "#194d86",
    "selected": "#e6eef8",
    "link": "#26704c",
    "link_hover": "#174c32",
}

RHYME_CATEGORIES = [
    ("Perfect / Normative", "perfect"),
    ("Light", "light"),
    ("Final Syllable", "final_syllable"),
    ("First Syllable", "first_syllable"),
    ("First Syllable Assonance", "first_syllable_assonance"),
    ("Back", "back"),
    ("Reverse", "reverse"),
    ("Reverse First Syllable", "reverse_first_syllable"),
    ("Homophone", None),
    ("Consonance", None),
    ("Double Consonance", None),
    ("Full Consonance", None),
    ("Assonance", None),
    ("Full Assonance", None),
    ("Full Assonance w/ End Cons", None),
    ("Sight", None),
    ("Half-double", None),
    ("Amphibraenic", None),
    ("Elided", None),
    ("Begins With", None),
    ("Ends With", None),
    ("Contains", None),
]

# Number of words inserted during each GUI update.
RENDER_BATCH_SIZE = 100

# Delay between batches, in milliseconds.
RENDER_DELAY_MS = 5


class RhymeApplication:

    def __init__(self, root):
        self.root = root
        self.root.title("Rhymesaurus — Rhyming Dictionary")
        self.root.geometry("1500x1000")
        self.root.minsize(750, 500)
        self.root.configure(bg=COLORS["background"])

        self.current_word = None
        self.current_rhyme_type = "perfect"

        self.suggestions = []
        self.suggestion_window = None
        self.suggestion_list = None

        self.word_tag_number = 0

        # Incremental-rendering state.
        self.render_after_id = None
        self.render_groups = []
        self.render_group_index = 0
        self.render_word_index = 0
        self.render_generation = 0
        self.rendered_word_count = 0
        self.render_total_words = 0

        self.setup_styles()
        self.build_interface()

    def setup_styles(self):
        style = ttk.Style()

        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        style.configure(
            "App.TFrame",
            background=COLORS["background"],
        )
        style.configure(
            "Panel.TFrame",
            background=COLORS["panel"],
        )
        style.configure(
            "Sidebar.TFrame",
            background=COLORS["sidebar"],
        )
        style.configure(
            "Heading.TLabel",
            background=COLORS["background"],
            foreground=COLORS["text"],
            font=("TkDefaultFont", 19, "bold"),
        )
        style.configure(
            "Subtitle.TLabel",
            background=COLORS["background"],
            foreground=COLORS["muted"],
            font=("TkDefaultFont", 9),
        )
        style.configure(
            "Section.TLabel",
            background=COLORS["panel"],
            foreground=COLORS["text"],
            font=("TkDefaultFont", 11, "bold"),
        )
        style.configure(
            "Muted.TLabel",
            background=COLORS["background"],
            foreground=COLORS["muted"],
            font=("TkDefaultFont", 9),
        )
        style.configure(
            "SidebarHeading.TLabel",
            background=COLORS["sidebar"],
            foreground=COLORS["text"],
            font=("TkDefaultFont", 10, "bold"),
        )
        style.configure(
            "Search.TEntry",
            padding=(9, 8),
            font=("TkDefaultFont", 13),
        )
        style.configure(
            "Accent.TButton",
            background=COLORS["accent"],
            foreground="#ffffff",
            padding=(18, 8),
            font=("TkDefaultFont", 10, "bold"),
            borderwidth=0,
        )
        style.map(
            "Accent.TButton",
            background=[
                ("active", COLORS["accent_hover"]),
                ("pressed", COLORS["accent_hover"]),
            ],
            foreground=[("disabled", "#ffffff")],
        )
        style.configure(
            "TCombobox",
            padding=5,
            font=("TkDefaultFont", 9),
        )
        style.configure(
            "TSeparator",
            background=COLORS["border"],
        )

    # --------------------------------------------------------
    # Main interface
    # --------------------------------------------------------

    def build_interface(self):
        outer = ttk.Frame(
            self.root,
            style="App.TFrame",
            padding=(22, 16, 22, 12),
        )
        outer.pack(fill="both", expand=True)

        header = ttk.Frame(outer, style="App.TFrame")
        header.pack(fill="x", pady=(0, 14))

        ttk.Label(
            header,
            text="RHYMESAURUS",
            style="Heading.TLabel",
        ).pack(anchor="w")

        ttk.Label(
            header,
            text="A rhyming dictionary",
            style="Subtitle.TLabel",
        ).pack(anchor="w", pady=(2, 0))

        search_area = ttk.Frame(outer, style="App.TFrame")
        search_area.pack(fill="x", pady=(0, 13))

        ttk.Label(
            search_area,
            text="WORD TO FIND",
            background=COLORS["background"],
            foreground=COLORS["muted"],
            font=("TkDefaultFont", 8, "bold"),
        ).pack(anchor="w", pady=(0, 5))

        search_row = ttk.Frame(search_area, style="App.TFrame")
        search_row.pack(fill="x")

        self.search_var = tk.StringVar()

        self.entry = ttk.Entry(
            search_row,
            textvariable=self.search_var,
            style="Search.TEntry",
        )
        self.entry.pack(side="left", fill="x", expand=True)

        self.entry.bind("<KeyRelease>", self.update_suggestions)
        self.entry.bind("<Down>", self.move_down)
        self.entry.bind("<Up>", self.move_up)
        self.entry.bind("<Return>", self.enter_search)
        self.entry.bind("<Escape>", self.hide_suggestions)

        self.search_button = ttk.Button(
            search_row,
            text="Search",
            style="Accent.TButton",
            command=self.search_from_entry,
        )
        self.search_button.pack(side="left", padx=(9, 0))

        ttk.Separator(outer).pack(fill="x", pady=(0, 14))

        content = ttk.Frame(outer, style="App.TFrame")
        content.pack(fill="both", expand=True)

        content.columnconfigure(0, weight=0)
        content.columnconfigure(1, weight=1)
        content.rowconfigure(0, weight=1)

        self.build_sidebar(content)
        self.build_results_panel(content)

        self.status_var = tk.StringVar(value="Ready")

        status = tk.Label(
            outer,
            textvariable=self.status_var,
            bg=COLORS["background"],
            fg=COLORS["muted"],
            font=("TkDefaultFont", 9),
            anchor="w",
            padx=2,
            pady=7,
        )
        status.pack(fill="x", side="bottom")

        self.entry.focus_set()

    # --------------------------------------------------------
    # Sidebar
    # --------------------------------------------------------

    def build_sidebar(self, parent):
        sidebar = ttk.Frame(
            parent,
            style="Sidebar.TFrame",
            padding=(12, 14),
        )
        sidebar.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        sidebar.configure(width=205)
        sidebar.grid_propagate(False)

        ttk.Label(
            sidebar,
            text="RHYME TYPE",
            style="SidebarHeading.TLabel",
        ).pack(anchor="w", pady=(0, 10))

        self.category_list = tk.Listbox(
            sidebar,
            font=("TkDefaultFont", 9),
            background=COLORS["sidebar"],
            foreground=COLORS["muted"],
            selectbackground=COLORS["accent"],
            selectforeground="#ffffff",
            highlightthickness=0,
            borderwidth=0,
            activestyle="none",
            exportselection=False,
            height=len(RHYME_CATEGORIES),
        )
        self.category_list.pack(fill="x")

        for label, rhyme_type in RHYME_CATEGORIES:
            self.category_list.insert("end", label)
            index = self.category_list.size() - 1

            if rhyme_type is not None:
                self.category_list.itemconfig(
                    index,
                    foreground=COLORS["accent"],
                )

        self.category_list.selection_set(0)
        self.category_list.bind(
            "<<ListboxSelect>>",
            self.category_selected,
        )

        ttk.Separator(sidebar).pack(fill="x", pady=14)

        ttk.Label(
            sidebar,
            text="MORE OPTIONS",
            style="SidebarHeading.TLabel",
        ).pack(anchor="w", pady=(0, 8))

        ttk.Label(
            sidebar,
            text=(
                "The first six rhyme types are now available. "
                "Additional rhyme types will be implemented "
                "in future versions."
            ),
            background=COLORS["sidebar"],
            foreground=COLORS["muted"],
            font=("TkDefaultFont", 9),
            wraplength=175,
            justify="left",
        ).pack(anchor="w")

    def category_selected(self, event=None):
        selection = self.category_list.curselection()

        if not selection:
            return

        index = selection[0]
        label, rhyme_type = RHYME_CATEGORIES[index]

        if rhyme_type is None:
            active_index = next(
                i for i, (_, kind) in enumerate(RHYME_CATEGORIES)
                if kind == self.current_rhyme_type
            )
            self.category_list.selection_clear(0, "end")
            self.category_list.selection_set(active_index)
            self.status_var.set(
                f"{label} has not been implemented yet."
            )
            return

        self.current_rhyme_type = rhyme_type

        if self.current_word:
            self.perform_search(self.current_word)
        else:
            self.cancel_rendering()
            self.results_heading.config(text=label)
            self.clear_results()
            self.insert_message(
                f"Enter a word to find {label.lower()}."
            )
            self.status_var.set(f"Rhyme type: {label}")

    # --------------------------------------------------------
    # Results panel
    # --------------------------------------------------------

    def build_results_panel(self, parent):
        panel = ttk.Frame(
            parent,
            style="Panel.TFrame",
            padding=(18, 16),
        )
        panel.grid(row=0, column=1, sticky="nsew")

        panel.columnconfigure(0, weight=1)
        panel.rowconfigure(2, weight=1)

        top = ttk.Frame(panel, style="Panel.TFrame")
        top.grid(row=0, column=0, sticky="ew")
        top.columnconfigure(0, weight=1)

        self.results_heading = ttk.Label(
            top,
            text="Find rhymes for a word",
            style="Section.TLabel",
        )
        self.results_heading.grid(row=0, column=0, sticky="w")

        filter_frame = ttk.Frame(top, style="Panel.TFrame")
        filter_frame.grid(row=0, column=1, sticky="e")

        ttk.Label(
            filter_frame,
            text="Frequency",
            background=COLORS["panel"],
            foreground=COLORS["muted"],
            font=("TkDefaultFont", 9),
        ).pack(side="left", padx=(0, 6))

        self.frequency_var = tk.StringVar(value="All words")

        self.frequency_options = {
            "All words": None,
            "Very common": 1,
            "Common": 2,
            "Less common": 5,
            "Broad vocabulary": 9,
        }

        self.frequency_box = ttk.Combobox(
            filter_frame,
            textvariable=self.frequency_var,
            values=list(self.frequency_options),
            state="readonly",
            width=17,
        )
        self.frequency_box.pack(side="left")
        self.frequency_box.bind(
            "<<ComboboxSelected>>",
            self.change_frequency,
        )

        ttk.Separator(panel).grid(
            row=1,
            column=0,
            sticky="ew",
            pady=(13, 12),
        )

        text_frame = ttk.Frame(panel, style="Panel.TFrame")
        text_frame.grid(row=2, column=0, sticky="nsew")
        text_frame.columnconfigure(0, weight=1)
        text_frame.rowconfigure(0, weight=1)

        self.results_text = tk.Text(
            text_frame,
            wrap="word",
            font=("TkDefaultFont", 10),
            background=COLORS["panel"],
            foreground=COLORS["text"],
            borderwidth=0,
            highlightthickness=0,
            padx=2,
            pady=2,
            spacing1=2,
            spacing3=3,
            cursor="arrow",
            state="disabled",
        )
        self.results_text.grid(row=0, column=0, sticky="nsew")

        scrollbar = ttk.Scrollbar(
            text_frame,
            orient="vertical",
            command=self.results_text.yview,
        )
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.results_text.configure(yscrollcommand=scrollbar.set)

        self.results_text.tag_configure(
            "word_heading",
            font=("TkDefaultFont", 14, "bold"),
            foreground=COLORS["text"],
            spacing1=4,
            spacing3=10,
        )
        self.results_text.tag_configure(
            "group_heading",
            font=("TkDefaultFont", 10, "bold"),
            foreground=COLORS["text"],
            spacing1=12,
            spacing3=5,
        )
        self.results_text.tag_configure(
            "empty_message",
            foreground=COLORS["muted"],
            font=("TkDefaultFont", 10),
        )

    # --------------------------------------------------------
    # Autocomplete
    # --------------------------------------------------------

    def update_suggestions(self, event=None):
        if event and event.keysym in (
            "Return", "Up", "Down", "Escape",
            "Left", "Right", "Shift_L", "Shift_R",
            "Control_L", "Control_R", "Alt_L", "Alt_R",
        ):
            return

        prefix = self.search_var.get().strip()
        self.suggestions = []

        if not prefix:
            self.hide_suggestions()
            return

        self.suggestions = suggest_words(prefix, limit=20)

        if not self.suggestions:
            self.hide_suggestions()
            return

        if self.suggestion_window is None:
            self.suggestion_window = tk.Toplevel(self.root)
            self.suggestion_window.overrideredirect(True)

            self.suggestion_list = tk.Listbox(
                self.suggestion_window,
                font=("TkDefaultFont", 11),
                background="#ffffff",
                foreground=COLORS["text"],
                selectbackground=COLORS["selected"],
                selectforeground=COLORS["accent"],
                highlightthickness=1,
                highlightbackground=COLORS["border"],
                borderwidth=0,
                activestyle="none",
                exportselection=False,
            )
            self.suggestion_list.pack(fill="both", expand=True)

            self.suggestion_list.bind(
                "<ButtonRelease-1>",
                self.choose_suggestion,
            )
            self.suggestion_list.bind(
                "<Return>",
                self.choose_suggestion,
            )
            self.suggestion_list.bind(
                "<Escape>",
                self.hide_suggestions,
            )

        self.suggestion_list.delete(0, "end")

        for item in self.suggestions:
            self.suggestion_list.insert("end", item["word"])

        self.root.update_idletasks()

        x = self.entry.winfo_rootx()
        y = self.entry.winfo_rooty() + self.entry.winfo_height()
        width = self.entry.winfo_width()
        height = min(8, len(self.suggestions)) * 25 + 4

        self.suggestion_window.geometry(
            f"{width}x{height}+{x}+{y}"
        )
        self.suggestion_window.deiconify()
        self.suggestion_window.lift()

    def hide_suggestions(self, event=None):
        if self.suggestion_window is not None:
            self.suggestion_window.withdraw()

        self.entry.focus_set()
        return "break"

    def move_down(self, event=None):
        if self.suggestion_window is not None:
            if self.suggestion_window.state() != "withdrawn":
                if self.suggestions:
                    self.suggestion_list.selection_clear(0, "end")
                    self.suggestion_list.selection_set(0)
                    self.suggestion_list.activate(0)
                    self.suggestion_list.focus_set()
                return "break"
        return None

    def move_up(self, event=None):
        if self.suggestion_window is not None:
            if self.suggestion_window.state() != "withdrawn":
                if self.suggestions:
                    last = len(self.suggestions) - 1
                    self.suggestion_list.selection_clear(0, "end")
                    self.suggestion_list.selection_set(last)
                    self.suggestion_list.activate(last)
                    self.suggestion_list.focus_set()
                return "break"
        return None

    def choose_suggestion(self, event=None):
        if self.suggestion_list is None:
            return "break"

        selection = self.suggestion_list.curselection()

        if not selection:
            return "break"

        word = self.suggestion_list.get(selection[0])
        self.search_var.set(word)
        self.hide_suggestions()
        self.perform_search(word)
        return "break"

    def enter_search(self, event=None):
        if self.suggestion_list is not None:
            try:
                if self.suggestion_list.focus_get() == self.suggestion_list:
                    return self.choose_suggestion()
            except tk.TclError:
                pass

        self.search_from_entry()
        return "break"

    def search_from_entry(self):
        word = self.search_var.get().strip()
        if word:
            self.hide_suggestions()
            self.perform_search(word)

    # --------------------------------------------------------
    # Search
    # --------------------------------------------------------

    def change_frequency(self, event=None):
        if self.current_word:
            self.perform_search(self.current_word)

    def active_category_label(self):
        for label, rhyme_type in RHYME_CATEGORIES:
            if rhyme_type == self.current_rhyme_type:
                return label
        return "Rhymes"

    def perform_search(self, word):
        self.hide_suggestions()
        self.current_word = word

        # Invalidate and cancel any previous rendering operation.
        self.cancel_rendering()
        self.clear_results()

        cutoff = self.frequency_options[self.frequency_var.get()]

        try:
            data = search_rhymes(
                word,
                max_frequency=cutoff,
                rhyme_type=self.current_rhyme_type,
            )
        except WordNotFoundError:
            self.results_heading.config(text=f"Word not found: {word}")
            self.insert_message("No matching word in the database.")
            self.status_var.set("No matching word in the database.")
            return
        except NoUsablePronunciationError:
            self.results_heading.config(
                text=f"No usable pronunciation for {word}"
            )
            self.insert_message("No rhyme search is available.")
            self.status_var.set("No rhyme search is available.")
            return

        category = self.active_category_label()

        self.results_heading.config(
            text=(
                f"{data['total_words']:,} {category.lower()} "
                f"rhymes for {word.upper()}"
            )
        )

        if not data["groups"]:
            self.insert_message("No rhymes found.")
            self.status_var.set("No results.")
            return

        self.results_text.configure(state="normal")
        self.insert_text(word.upper(), "word_heading")
        self.insert_text("\n")

        # Save the groups for incremental rendering.
        self.render_groups = data["groups"]
        self.render_group_index = 0
        self.render_word_index = 0
        self.rendered_word_count = 0
        self.render_total_words = data["total_words"]

        self.status_var.set(
            f"Displaying results: 0 of {self.render_total_words:,} words"
        )

        self.render_generation += 1
        generation = self.render_generation

        # Render the first batch immediately.
        self.render_next_batch(generation)

    # --------------------------------------------------------
    # Incremental rendering
    # --------------------------------------------------------

    def cancel_rendering(self):
        # Changing the generation also invalidates callbacks that
        # might already be queued.
        self.render_generation += 1

        if self.render_after_id is not None:
            try:
                self.root.after_cancel(self.render_after_id)
            except tk.TclError:
                pass

            self.render_after_id = None

        self.render_groups = []
        self.render_group_index = 0
        self.render_word_index = 0

    def render_next_batch(self, generation):
        if generation != self.render_generation:
            return

        self.render_after_id = None
        words_this_batch = 0

        while (
            self.render_group_index < len(self.render_groups)
            and words_this_batch < RENDER_BATCH_SIZE
        ):
            group = self.render_groups[self.render_group_index]
            words = group["words"]

            # Insert the syllable heading at the start of each group.
            if self.render_word_index == 0:
                syllables = group["syllables"]
                heading = (
                    f"{syllables} syllable"
                    f"{'s' if syllables != 1 else ''} words"
                )
                self.insert_text(heading + "\n", "group_heading")

            while (
                self.render_word_index < len(words)
                and words_this_batch < RENDER_BATCH_SIZE
            ):
                index = self.render_word_index
                item = words[index]
                spelling = item["word"]

                self.word_tag_number += 1
                tag = f"rhyme_{self.word_tag_number}"

                self.results_text.tag_configure(
                    tag,
                    foreground=COLORS["link"],
                    underline=True,
                )
                self.results_text.tag_bind(
                    tag,
                    "<Button-1>",
                    lambda event, w=spelling: self.click_rhyme(w),
                )
                self.results_text.tag_bind(
                    tag,
                    "<Enter>",
                    lambda event: self.results_text.configure(
                        cursor="hand2"
                    ),
                )
                self.results_text.tag_bind(
                    tag,
                    "<Leave>",
                    lambda event: self.results_text.configure(
                        cursor="arrow"
                    ),
                )

                self.insert_text(spelling, tag)

                if index < len(words) - 1:
                    self.insert_text(", ")

                self.render_word_index += 1
                self.rendered_word_count += 1
                words_this_batch += 1

            # Finish the group when all its words have been inserted.
            if self.render_word_index >= len(words):
                self.insert_text("\n\n")
                self.render_group_index += 1
                self.render_word_index = 0

        if generation != self.render_generation:
            return

        if self.render_group_index < len(self.render_groups):
            self.status_var.set(
                f"Displaying results: "
                f"{self.rendered_word_count:,} of "
                f"{self.render_total_words:,} words"
            )

            self.render_after_id = self.root.after(
                RENDER_DELAY_MS,
                lambda: self.render_next_batch(generation),
            )
        else:
            self.results_text.configure(state="disabled")
            self.status_var.set(
                f"Showing all {self.render_total_words:,} words"
                "  |  Click a word to search for its rhymes"
            )

    # --------------------------------------------------------
    # Text helpers
    # --------------------------------------------------------

    def click_rhyme(self, word):
        self.search_var.set(word)
        self.perform_search(word)

    def insert_text(self, text, tag=None):
        if tag:
            self.results_text.insert("end", text, tag)
        else:
            self.results_text.insert("end", text)

    def insert_message(self, message):
        self.results_text.configure(state="normal")
        self.results_text.insert(
            "end",
            message,
            "empty_message",
        )
        self.results_text.configure(state="disabled")

    def clear_results(self):
        self.results_text.configure(state="normal")
        self.results_text.delete("1.0", "end")
        self.results_text.configure(state="disabled")


def main():
    root = tk.Tk()
    RhymeApplication(root)
    root.mainloop()


if __name__ == "__main__":
    main()
