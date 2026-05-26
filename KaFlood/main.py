import asyncio
import multiprocessing
import threading
import os
import sys
import customtkinter as ctk
from datetime import datetime
from kahoot_client import KahootClient

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# ── Relativ-Pfad ──────────────────────────────────────────────────────────────

def path(relative_path):
    if hasattr(sys, "_MEIPASS"):
        return os.path.join(sys._MEIPASS, relative_path) # type: ignore[attr-defined]
    return os.path.join(os.path.abspath("."), relative_path)

# ── Worker-Prozess ────────────────────────────────────────────────────────────

def worker_process(pin: int, name_prefix: str, start_index: int,
                   max_concurrent: int, spawn_delay: float,
                   q: multiprocessing.Queue):

    async def run_bot(name: str) -> None:
        joined = False

        async def on_event(event: str, data: dict):
            nonlocal joined
            if event == "login_response":
                if data.get("error"):
                    q.put(("rejected", data.get("description", data["error"])))
                else:
                    joined = True
                    q.put(("joined", name))

        client = KahootClient(on_event=on_event)
        try:
            await client.join(pin, name)
        except Exception as e:
            if not joined:
                q.put(("error", str(e)))
        await asyncio.sleep(max(spawn_delay, 0.5))

    async def main():
        counter = start_index
        tasks: set[asyncio.Task] = set()

        for _ in range(max_concurrent):
            t = asyncio.create_task(run_bot(f"{name_prefix}{counter}"))
            tasks.add(t)
            counter += 1
            await asyncio.sleep(spawn_delay)

        while True:
            done, tasks = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for _ in done:
                t = asyncio.create_task(run_bot(f"{name_prefix}{counter}"))
                tasks.add(t)
                counter += 1

    asyncio.run(main())

# ── GUI ───────────────────────────────────────────────────────────────────────

class KahootApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("KaFlood")
        self.iconbitmap(path("icon.ico"))
        self.geometry("560x650")
        self.resizable(False, False)
        self.configure(fg_color="#1A1A2E")

        self._processes: list[multiprocessing.Process] = []
        self._q: multiprocessing.Queue = multiprocessing.Queue()

        # Stats
        self._stat_joined   = 0
        self._stat_rejected = 0
        self._stat_errors   = 0

        self._pin_entry:  ctk.CTkEntry
        self._name_entry: ctk.CTkEntry
        self._proc_var:   ctk.StringVar
        self._conc_var:   ctk.StringVar
        self._delay_var:  ctk.StringVar
        
        self._stat_proc_lbl:     ctk.CTkLabel
        self._stat_joined_lbl:   ctk.CTkLabel
        self._stat_rejected_lbl: ctk.CTkLabel
        self._stat_errors_lbl:   ctk.CTkLabel

        self._build_ui()
        self._poll_queue()

    def _build_ui(self):
        pad = {"padx": 24, "pady": 16}

        form = ctk.CTkFrame(self, fg_color="#16213E", corner_radius=12)
        form.pack(fill="x", **pad)

        for label, attr, ph in [
            ("Game PIN",      "pin",  "z. B. 123456"),
            ("Name (Prefix)", "name", "z. B. Bot"),
        ]:
            row = ctk.CTkFrame(form, fg_color="transparent")
            row.pack(fill="x", padx=16, pady=(10, 0))
            ctk.CTkLabel(row, text=label, font=ctk.CTkFont("Segoe UI", 12, "bold"),
                         text_color="white", width=150, anchor="w").pack(side="left")
            entry = ctk.CTkEntry(row, placeholder_text=ph, height=36,
                                 fg_color="#0F3460", border_color="#0F3460",
                                 text_color="white", placeholder_text_color="#8892A4",
                                 font=ctk.CTkFont("Segoe UI", 13))
            entry.pack(side="left", fill="x", expand=True)
            setattr(self, f"_{attr}_entry", entry)

        for label, attr, default in [
            ("Prozesse",          "_proc_var",  "2"),
            ("Concurrent / Proc", "_conc_var",  "5"),
            ("Spawn-Delay (s)",   "_delay_var", "0.3"),
        ]:
            row = ctk.CTkFrame(form, fg_color="transparent")
            row.pack(fill="x", padx=16, pady=(10, 0))
            ctk.CTkLabel(row, text=label, font=ctk.CTkFont("Segoe UI", 12, "bold"),
                         text_color="white", width=150, anchor="w").pack(side="left")
            var = ctk.StringVar(value=default)
            setattr(self, attr, var)
            ctk.CTkEntry(row, textvariable=var, height=36, width=80,
                         fg_color="#0F3460", border_color="#0F3460",
                         text_color="white", font=ctk.CTkFont("Segoe UI", 13),
                         justify="center").pack(side="left")

        ctk.CTkFrame(form, fg_color="transparent", height=10).pack()

        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(fill="x", padx=24, pady=(4, 0))

        self._join_btn = ctk.CTkButton(
            btn_row, text="Verbinden", height=42,
            fg_color="transparent", hover_color="#16A34A",
            border_width=1, border_color="#16A34A",
            text_color="white", font=ctk.CTkFont("Segoe UI", 14, "bold"),
            command=self._on_join,
        )
        self._join_btn.pack(side="left", fill="x", expand=True, padx=(0, 6))

        self._leave_btn = ctk.CTkButton(
            btn_row, text="Verlassen", height=42,
            fg_color="transparent", hover_color="#EF4444",
            border_width=1, border_color="#EF4444",
            text_color="white", font=ctk.CTkFont("Segoe UI", 14, "bold"),
            state="disabled", command=self._on_leave,
        )
        self._leave_btn.pack(side="left", fill="x", expand=True, padx=(6, 0))

        # ── Stats-Leiste ──────────────────────────────────────────────────────
        stats_frame = ctk.CTkFrame(self, fg_color="#16213E", corner_radius=10)
        stats_frame.pack(fill="x", padx=24, pady=(10, 0))

        for col, (label, attr, color) in enumerate([
            ("Prozesse",  "_stat_proc_lbl",     "#8892A4"),
            ("✅ Gejoint", "_stat_joined_lbl",   "#4ADE80"),
            ("❌ Rejected","_stat_rejected_lbl", "#E8553E"),
            ("⚠ Fehler",  "_stat_errors_lbl",   "#FACC15"),
        ]):
            cell = ctk.CTkFrame(stats_frame, fg_color="transparent")
            cell.grid(row=0, column=col, padx=12, pady=8, sticky="ew")
            stats_frame.grid_columnconfigure(col, weight=1)

            val_lbl = ctk.CTkLabel(cell, text="0",
                                   font=ctk.CTkFont("Segoe UI", 18, "bold"),
                                   text_color=color)
            val_lbl.pack()
            ctk.CTkLabel(cell, text=label,
                         font=ctk.CTkFont("Segoe UI", 10),
                         text_color="#8892A4").pack()
            setattr(self, attr, val_lbl)

        # ── Log ───────────────────────────────────────────────────────────────
        self._log = ctk.CTkTextbox(
            self, fg_color="#16213E", text_color="#CBD5E1",
            font=ctk.CTkFont("Consolas", 12), corner_radius=10,
            wrap="word", state="disabled",
        )
        self._log.pack(fill="both", expand=True, padx=24, pady=(10, 0))
        self._log._textbox.tag_configure("ok",   foreground="#4ADE80")
        self._log._textbox.tag_configure("warn", foreground="#FACC15")
        self._log._textbox.tag_configure("err",  foreground="#E8553E")
        
        # ── Footer (Version / Creator) ──────────────────────────────────────────────
        footer = ctk.CTkLabel(
            self,
            text="KaFlood v1.0 • by Roeppli",
            font=ctk.CTkFont("Segoe UI", 10),
            text_color="#8892A4"
        )
        footer.pack()

    # ── Hilfsmethoden ─────────────────────────────────────────────────────────

    def _log_msg(self, text: str, tag: str = ""):
        ts = datetime.now().strftime("%H:%M:%S")
        self._log.configure(state="normal")
        self._log._textbox.insert("end", f"[{ts}]  {text}\n", tag)
        self._log._textbox.see("end")
        self._log.configure(state="disabled")
    
    def _clear_log(self):
        self._log.configure(state="normal")
        self._log.delete("1.0", "end")
        self._log.configure(state="disabled")

    def _update_stats(self):
        active = sum(1 for p in self._processes if p.is_alive())
        self._stat_proc_lbl.configure(text=str(active))
        self._stat_joined_lbl.configure(text=str(self._stat_joined))
        self._stat_rejected_lbl.configure(text=str(self._stat_rejected))
        self._stat_errors_lbl.configure(text=str(self._stat_errors))

    def _poll_queue(self):
        """Liest Queue-Nachrichten aus den Worker-Prozessen."""
        try:
            while True:
                kind, detail = self._q.get_nowait()
                if kind == "joined":
                    self._stat_joined += 1
                    self._log_msg(f"✅ {detail} gejoint.", "ok")
                elif kind == "rejected":
                    self._stat_rejected += 1
                    self._log_msg(f"❌ Rejected: {detail}", "err")
                elif kind == "error":
                    self._stat_errors += 1
                    self._log_msg(f"⚠ Fehler: {detail}", "warn")
                self._update_stats()
        except Exception:
            pass
        self.after(200, self._poll_queue)

    # ── Join / Leave ──────────────────────────────────────────────────────────

    def _on_join(self):
        pin_raw  = self._pin_entry.get().strip()
        name_raw = self._name_entry.get().strip()

        if not pin_raw.isdigit():
            self._log_msg("⚠ Ungültige PIN.", "warn"); return
        if not name_raw:
            self._log_msg("⚠ Bitte einen Namen eingeben.", "warn"); return

        try:
            n_proc = int(self._proc_var.get())
            n_conc = int(self._conc_var.get())
            delay  = float(self._delay_var.get())
            assert n_proc >= 1 and n_conc >= 1 and delay >= 0
        except Exception:
            self._log_msg("⚠ Ungültige Konfiguration.", "warn"); return
        
        self._clear_log()
        
        self._join_btn.configure(state="disabled")
        self._leave_btn.configure(state="normal")
        self._processes.clear()

        # Stats zurücksetzen
        self._stat_joined = self._stat_rejected = self._stat_errors = 0
        self._update_stats()

        # Alte Queue leeren
        while not self._q.empty():
            try: self._q.get_nowait()
            except: break

        for i in range(n_proc):
            p = multiprocessing.Process(
                target=worker_process,
                args=(int(pin_raw), name_raw, i * 100_000, n_conc, delay, self._q),
                daemon=True,
            )
            p.start()
            self._processes.append(p)
            self._log_msg(f"▶ Prozess {i+1}/{n_proc} gestartet.", "ok")

        self._update_stats()
        threading.Thread(target=self._watch_processes, daemon=True).start()

    def _watch_processes(self):
        import time
        while any(p.is_alive() for p in self._processes):
            self.after(0, self._update_stats)
            time.sleep(2)
        self.after(0, self._update_stats)

    def _on_leave(self):
        for p in self._processes:
            if p.is_alive():
                p.terminate()
        self._processes.clear()
        self._join_btn.configure(state="normal")
        self._leave_btn.configure(state="disabled")
        self._update_stats()
        self._log_msg("Alle Prozesse gestoppt.", "warn")


if __name__ == "__main__":
    multiprocessing.freeze_support()
    app = KahootApp()
    app.mainloop()
