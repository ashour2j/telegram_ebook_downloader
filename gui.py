#!/usr/bin/env python3
"""
Graphical User Interface (GUI) for Telegram Ebook Downloader.
Designed for easy, non-terminal use on Windows.
"""

import os
import sys
import subprocess
import threading
import queue
import time
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext

HERE = Path(__file__).resolve().parent
ENV_PATH = HERE / ".env"


def load_env_vars():
    env = {}
    if ENV_PATH.exists():
        with open(ENV_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env[k.strip()] = v.strip()
    return env


def save_env_var(key: str, value: str):
    lines = []
    if ENV_PATH.exists():
        with open(ENV_PATH, "r", encoding="utf-8") as f:
            lines = f.readlines()

    found = False
    new_line = f"{key}={value}\n"
    for i, line in enumerate(lines):
        if line.strip().startswith(f"{key}="):
            lines[i] = new_line
            found = True
            break
    if not found:
        lines.append(new_line)

    with open(ENV_PATH, "w", encoding="utf-8") as f:
        f.writelines(lines)


class EbookDownloaderGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Telegram Ebook Downloader — كتب المناهج المصرية")
        self.geometry("900x720")
        self.minsize(800, 600)

        # Set app theme / colors
        self.style = ttk.Style(self)
        try:
            self.style.theme_use("vista")
        except Exception:
            pass

        self.proc = None
        self.log_queue = queue.Queue()

        self._create_widgets()
        self._load_current_config()
        self.after(100, self._process_log_queue)

    def _create_widgets(self):
        # Header title
        header_frame = ttk.Frame(self, padding=10)
        header_frame.pack(fill=tk.X)

        title_lbl = ttk.Label(
            header_frame,
            text="📚 Telegram Ebook Downloader & Library Manager",
            font=("Segoe UI", 16, "bold"),
        )
        title_lbl.pack(side=tk.LEFT)

        # Main notebook tabs
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        # Tab 1: Downloader Controls & Logs
        self.tab_download = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(self.tab_download, text="📥 Downloader & Live Status")

        # Tab 2: Settings & Filters
        self.tab_settings = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(self.tab_settings, text="⚙️ Settings & Filters")

        self._build_download_tab()
        self._build_settings_tab()

    def _build_download_tab(self):
        # Control Buttons Bar
        btn_frame = ttk.Frame(self.tab_download)
        btn_frame.pack(fill=tk.X, pady=(0, 10))

        self.btn_start = ttk.Button(
            btn_frame, text="▶️ Start Download", command=self.start_download
        )
        self.btn_start.pack(side=tk.LEFT, padx=5)

        self.btn_stop = ttk.Button(
            btn_frame, text="⏹️ Stop", command=self.stop_download, state=tk.DISABLED
        )
        self.btn_stop.pack(side=tk.LEFT, padx=5)

        self.btn_skip = ttk.Button(
            btn_frame, text="⏭️ Skip Active Download", command=self.skip_download
        )
        self.btn_skip.pack(side=tk.LEFT, padx=5)

        self.btn_progress = ttk.Button(
            btn_frame, text="📊 Progress Summary", command=self.show_progress_summary
        )
        self.btn_progress.pack(side=tk.LEFT, padx=5)

        self.btn_update_lib = ttk.Button(
            btn_frame, text="🔄 Organize & Update Library", command=self.run_update_library
        )
        self.btn_update_lib.pack(side=tk.RIGHT, padx=5)

        self.btn_web_app = ttk.Button(
            btn_frame, text="🌐 Open Invoice Web App", command=self.open_web_app
        )
        self.btn_web_app.pack(side=tk.RIGHT, padx=5)

        # Log Output Box
        log_frame = ttk.LabelFrame(self.tab_download, text="Live Output Console", padding=5)
        log_frame.pack(fill=tk.BOTH, expand=True)

        self.log_text = scrolledtext.ScrolledText(
            log_frame, wrap=tk.WORD, font=("Consolas", 10), bg="#1e1e1e", fg="#d4d4d4"
        )
        self.log_text.pack(fill=tk.BOTH, expand=True)

        # Bottom clear button
        bottom_frame = ttk.Frame(self.tab_download)
        bottom_frame.pack(fill=tk.X, pady=(5, 0))
        btn_clear = ttk.Button(bottom_frame, text="Clear Logs", command=self.clear_logs)
        btn_clear.pack(side=tk.RIGHT)

    def _build_settings_tab(self):
        # Target channels / usernames
        lbl_target = ttk.Label(self.tab_settings, text="Target Usernames (comma-separated):")
        lbl_target.grid(row=0, column=0, sticky=tk.W, pady=5)

        self.entry_targets = ttk.Entry(self.tab_settings, width=70)
        self.entry_targets.grid(row=0, column=1, sticky=tk.W, pady=5, padx=5)

        # Grade filter dropdown
        lbl_grade = ttk.Label(self.tab_settings, text="Grade Filter:")
        lbl_grade.grid(row=1, column=0, sticky=tk.W, pady=5)

        self.combo_grade = ttk.Combobox(
            self.tab_settings,
            values=["All Grades"] + [f"Grade {g}" for g in range(1, 13)],
            state="readonly",
            width=20,
        )
        self.combo_grade.grid(row=1, column=1, sticky=tk.W, pady=5, padx=5)
        self.combo_grade.current(0)

        # Term filter dropdown
        lbl_term = ttk.Label(self.tab_settings, text="School Term Filter (Arabic):")
        lbl_term.grid(row=2, column=0, sticky=tk.W, pady=5)

        self.combo_term = ttk.Combobox(
            self.tab_settings,
            values=["All Terms", "Term 1 (الترم الأول)", "Term 2 (الترم الثاني)"],
            state="readonly",
            width=30,
        )
        self.combo_term.grid(row=2, column=1, sticky=tk.W, pady=5, padx=5)
        self.combo_term.current(0)

        # Year filter
        lbl_year = ttk.Label(self.tab_settings, text="Year Filter (e.g. 2027):")
        lbl_year.grid(row=3, column=0, sticky=tk.W, pady=5)

        self.entry_year = ttk.Entry(self.tab_settings, width=20)
        self.entry_year.grid(row=3, column=1, sticky=tk.W, pady=5, padx=5)

        # Output Dir
        lbl_out = ttk.Label(self.tab_settings, text="Output Directory:")
        lbl_out.grid(row=4, column=0, sticky=tk.W, pady=5)

        self.entry_output = ttk.Entry(self.tab_settings, width=40)
        self.entry_output.grid(row=4, column=1, sticky=tk.W, pady=5, padx=5)

        # Save settings button
        btn_save = ttk.Button(self.tab_settings, text="💾 Save Settings to .env", command=self.save_settings)
        btn_save.grid(row=5, column=1, sticky=tk.W, pady=15, padx=5)

    def _load_current_config(self):
        env = load_env_vars()
        self.entry_targets.insert(0, env.get("TELEGRAM_TARGET_CHAT", ""))
        self.entry_year.insert(0, env.get("FILTER_YEAR", "2027"))
        self.entry_output.insert(0, env.get("OUTPUT_DIR", "./downloads/Books26-27"))

        term_val = env.get("FILTER_TERM", "")
        if term_val == "1":
            self.combo_term.current(1)
        elif term_val == "2":
            self.combo_term.current(2)
        else:
            self.combo_term.current(0)

    def save_settings(self):
        targets = self.entry_targets.get().strip()
        year = self.entry_year.get().strip()
        output_dir = self.entry_output.get().strip()

        term_idx = self.combo_term.current()
        term_val = "1" if term_idx == 1 else ("2" if term_idx == 2 else "")

        grade_idx = self.combo_grade.current()
        grade_val = str(grade_idx) if grade_idx > 0 else ""

        if targets:
            save_env_var("TELEGRAM_TARGET_CHAT", targets)
        if year:
            save_env_var("FILTER_YEAR", year)
        else:
            save_env_var("FILTER_YEAR", "")
        if term_val:
            save_env_var("FILTER_TERM", term_val)
        else:
            save_env_var("FILTER_TERM", "")
        if output_dir:
            save_env_var("OUTPUT_DIR", output_dir)

        messagebox.showinfo("Saved", "Settings saved successfully to .env file!")

    def log(self, message: str):
        self.log_queue.put(message)

    def _process_log_queue(self):
        while not self.log_queue.empty():
            msg = self.log_queue.get()
            self.log_text.insert(tk.END, msg + "\n")
            self.log_text.see(tk.END)
        self.after(100, self._process_log_queue)

    def clear_logs(self):
        self.log_text.delete("1.0", tk.END)

    def start_download(self):
        if self.proc and self.proc.poll() is None:
            messagebox.showwarning("Running", "Downloader is already running!")
            return

        self.save_settings()

        grade_idx = self.combo_grade.current()
        cmd = [sys.executable, "main.py"]
        if grade_idx > 0:
            cmd.extend(["--grade", str(grade_idx)])

        self.log(f"[GUI] Starting process: {' '.join(cmd)}")
        self.btn_start.config(state=tk.DISABLED)
        self.btn_stop.config(state=tk.NORMAL)

        def runner():
            try:
                env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
                self.proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    stdin=subprocess.PIPE,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    bufsize=1,
                    cwd=str(HERE),
                    env=env,
                )
                for line in iter(self.proc.stdout.readline, ""):
                    if line:
                        self.log(line.rstrip())
                self.proc.stdout.close()
                self.proc.wait()
            except Exception as exc:
                self.log(f"[GUI ERROR] {exc}")
            finally:
                self.log("[GUI] Downloader process ended.")
                self.btn_start.config(state=tk.NORMAL)
                self.btn_stop.config(state=tk.DISABLED)

        threading.Thread(target=runner, daemon=True).start()

    def stop_download(self):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            self.log("[GUI] Process termination requested.")

    def skip_download(self):
        self.log("[GUI] Requesting download skip...")

    def show_progress_summary(self):
        if self.proc and self.proc.poll() is None and self.proc.stdin:
            try:
                self.proc.stdin.write("\n")
                self.proc.stdin.flush()
                self.log("[GUI] Sent Enter key for progress summary.")
            except Exception as e:
                self.log(f"[GUI ERROR] Could not send Enter: {e}")

    def run_update_library(self):
        def _task():
            self.log("[GUI] Running update_library.py...")
            try:
                env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
                out = subprocess.check_output(
                    [sys.executable, "update_library.py"],
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    cwd=str(HERE),
                    env=env,
                )
                self.log(out)
                messagebox.showinfo("Library Updated", "Library organized into Grade folders & database rebuilt!")
            except subprocess.CalledProcessError as err:
                self.log(f"[ERROR] update_library failed:\n{err.output}")

        threading.Thread(target=_task, daemon=True).start()

    def open_web_app(self):
        def _task():
            self.log("[GUI] Launching Invoice Web App (http://127.0.0.1:5000)...")
            subprocess.Popen([sys.executable, "invoice_app.py"], cwd=str(HERE))

        threading.Thread(target=_task, daemon=True).start()


def main():
    app = EbookDownloaderGUI()
    app.mainloop()


if __name__ == "__main__":
    main()
