import multiprocessing
import threading
import os
import sys
import customtkinter as ctk
from datetime import datetime
from menti_client import get_questions, vote_choice, vote_wordcloud

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# ── Relativ-Pfad ──────────────────────────────────────────────────────────────

def path(relative_path):
    if hasattr(sys, "_MEIPASS"):
        return os.path.join(sys._MEIPASS, relative_path)  # type: ignore[attr-defined]
    return os.path.join(os.path.abspath("."), relative_path)

# ── Worker-Prozess ────────────────────────────────────────────────────────────

def worker_process(slug: str, ic_id: str, slide_type: str,
                   choice_id: str, word: str, random_words: bool,
                   count: int, workers: int,
                   q: multiprocessing.Queue):
    """Läuft in einem separaten Prozess und sendet Votes."""
    import random
    import string

    def random_word():
        return ''.join(random.choices(string.ascii_lowercase, k=25))

    counter = 0

    def on_result(ok: bool):
        nonlocal counter
        if ok:
            counter += 1
            q.put(("ok", str(counter)))
        else:
            q.put(("fail", ""))

    try:
        if slide_type == "word-cloud":
            def _vote(_):
                w = random_word() if random_words else word
                return vote_wordcloud(slug, ic_id, choice_id, w, 1, on_result=on_result, max_workers=1)
            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=workers) as ex:
                list(ex.map(_vote, range(count)))
        else:
            vote_choice(slug, ic_id, choice_id, count, on_result=on_result, max_workers=workers)
        q.put(("done", ""))
    except Exception as e:
        q.put(("error", str(e)))

# ── GUI ───────────────────────────────────────────────────────────────────────

class MentiApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("MentiFlood")
        self.iconbitmap(path("icon.ico"))
        self.geometry("580x720")
        self.resizable(False, False)
        self.configure(fg_color="#1A1A2E")
        
        self._stat_proc_lbl: ctk.CTkLabel
        self._stat_ok_lbl: ctk.CTkLabel
        self._stat_fail_lbl: ctk.CTkLabel
        
        self._proc_var: ctk.StringVar
        self._count_var: ctk.StringVar
        self._worker_var: ctk.StringVar

        self._processes: list[multiprocessing.Process] = []
        self._q: multiprocessing.Queue = multiprocessing.Queue()
        self._questions: list[dict] = []
        self._selected_q: int = -1
        self._selected_c: int = -1

        self._stat_ok   = 0
        self._stat_fail = 0

        self._build_ui()
        self._poll_queue()

    def _build_ui(self):
        pad = {"padx": 24, "pady": 12}

        # ── Slug-Eingabe ──────────────────────────────────────────────────────
        form = ctk.CTkFrame(self, fg_color="#16213E", corner_radius=12)
        form.pack(fill="x", **pad)

        slug_row = ctk.CTkFrame(form, fg_color="transparent")
        slug_row.pack(fill="x", padx=16, pady=(12, 4))
        ctk.CTkLabel(slug_row, text="Menti-Slug", font=ctk.CTkFont("Segoe UI", 12, "bold"),
                     text_color="white", width=130, anchor="w").pack(side="left")
        self._slug_entry = ctk.CTkEntry(
            slug_row, placeholder_text="z. B. alfgvotyzg7d", height=36,
            fg_color="#0F3460", border_color="#0F3460",
            text_color="white", placeholder_text_color="#8892A4",
            font=ctk.CTkFont("Segoe UI", 13),
        )
        self._slug_entry.pack(side="left", fill="x", expand=True)

        self._load_btn = ctk.CTkButton(
            slug_row, text="Laden", width=80, height=36,
            fg_color="#0F3460", hover_color="#1a4a80",
            text_color="white", font=ctk.CTkFont("Segoe UI", 13, "bold"),
            command=self._on_load,
        )
        self._load_btn.pack(side="left", padx=(8, 0))

        ctk.CTkFrame(form, fg_color="transparent", height=8).pack()

        # ── Fragen-Liste ──────────────────────────────────────────────────────
        q_row = ctk.CTkFrame(form, fg_color="transparent")
        q_row.pack(fill="x", padx=16, pady=(4, 0))
        ctk.CTkLabel(q_row, text="Frage", font=ctk.CTkFont("Segoe UI", 12, "bold"),
                     text_color="white", width=130, anchor="w").pack(side="left")
        self._q_var = ctk.StringVar(value="— Zuerst laden —")
        self._q_menu = ctk.CTkOptionMenu(
            q_row, variable=self._q_var, values=["— Zuerst laden —"],
            fg_color="#0F3460", button_color="#1a4a80", button_hover_color="#2255a0",
            text_color="white", font=ctk.CTkFont("Segoe UI", 13),
            command=self._on_question_select,
        )
        self._q_menu.pack(side="left", fill="x", expand=True)

        # ── Optionen-Liste ────────────────────────────────────────────────────
        c_row = ctk.CTkFrame(form, fg_color="transparent")
        c_row.pack(fill="x", padx=16, pady=(10, 0))
        ctk.CTkLabel(c_row, text="Option / Wort", font=ctk.CTkFont("Segoe UI", 12, "bold"),
                     text_color="white", width=130, anchor="w").pack(side="left")
        self._c_var = ctk.StringVar(value="—")
        self._c_menu = ctk.CTkOptionMenu(
            c_row, variable=self._c_var, values=["—"],
            fg_color="#0F3460", button_color="#1a4a80", button_hover_color="#2255a0",
            text_color="white", font=ctk.CTkFont("Segoe UI", 13),
            command=self._on_choice_select,
        )
        self._c_menu.pack(side="left", fill="x", expand=True)

        # Word-Cloud Wort-Eingabe (wird bei word-cloud eingeblendet)
        self._word_entry = ctk.CTkEntry(
            c_row, placeholder_text="Wort eingeben", height=36, width=160,
            fg_color="#0F3460", border_color="#0F3460",
            text_color="white", placeholder_text_color="#8892A4",
            font=ctk.CTkFont("Segoe UI", 13),
        )
        self._random_var = ctk.BooleanVar(value=False)
        self._random_chk = ctk.CTkCheckBox(
            c_row, text="Zufällig", variable=self._random_var,
            font=ctk.CTkFont("Segoe UI", 12), text_color="white",
            fg_color="#0F3460", hover_color="#1a4a80",
            command=self._on_random_toggle,
        )

        # ── Anzahl / Prozesse / Workers ───────────────────────────────────────
        for label, attr, default in [
            ("Anzahl Votes",    "_count_var",   "50"),
            ("Prozesse",        "_proc_var",    "2"),
            ("Threads / Proc",  "_worker_var",  "10"),
        ]:
            row = ctk.CTkFrame(form, fg_color="transparent")
            row.pack(fill="x", padx=16, pady=(10, 0))
            ctk.CTkLabel(row, text=label, font=ctk.CTkFont("Segoe UI", 12, "bold"),
                         text_color="white", width=130, anchor="w").pack(side="left")
            var = ctk.StringVar(value=default)
            setattr(self, attr, var)
            ctk.CTkEntry(row, textvariable=var, height=36, width=80,
                         fg_color="#0F3460", border_color="#0F3460",
                         text_color="white", font=ctk.CTkFont("Segoe UI", 13),
                         justify="center").pack(side="left")

        ctk.CTkFrame(form, fg_color="transparent", height=10).pack()

        # ── Buttons ───────────────────────────────────────────────────────────
        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(fill="x", padx=24, pady=(4, 0))

        self._start_btn = ctk.CTkButton(
            btn_row, text="Abstimmen", height=42,
            fg_color="transparent", hover_color="#16A34A",
            border_width=1, border_color="#16A34A",
            text_color="white", font=ctk.CTkFont("Segoe UI", 14, "bold"),
            command=self._on_start,
        )
        self._start_btn.pack(side="left", fill="x", expand=True, padx=(0, 6))

        self._stop_btn = ctk.CTkButton(
            btn_row, text="Stoppen", height=42,
            fg_color="transparent", hover_color="#EF4444",
            border_width=1, border_color="#EF4444",
            text_color="white", font=ctk.CTkFont("Segoe UI", 14, "bold"),
            state="disabled", command=self._on_stop,
        )
        self._stop_btn.pack(side="left", fill="x", expand=True, padx=(6, 0))

        # ── Stats ─────────────────────────────────────────────────────────────
        stats_frame = ctk.CTkFrame(self, fg_color="#16213E", corner_radius=10)
        stats_frame.pack(fill="x", padx=24, pady=(10, 0))

        for col, (label, attr, color) in enumerate([
            ("Prozesse",   "_stat_proc_lbl",  "#8892A4"),
            ("✅ Erfolg",  "_stat_ok_lbl",    "#4ADE80"),
            ("❌ Fehler",  "_stat_fail_lbl",  "#E8553E"),
        ]):
            cell = ctk.CTkFrame(stats_frame, fg_color="transparent")
            cell.grid(row=0, column=col, padx=12, pady=8, sticky="ew")
            stats_frame.grid_columnconfigure(col, weight=1)
            val = ctk.CTkLabel(cell, text="0",
                               font=ctk.CTkFont("Segoe UI", 18, "bold"),
                               text_color=color)
            val.pack()
            ctk.CTkLabel(cell, text=label,
                         font=ctk.CTkFont("Segoe UI", 10),
                         text_color="#8892A4").pack()
            setattr(self, attr, val)

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

        # ── Footer ────────────────────────────────────────────────────────────
        ctk.CTkLabel(self, text="MentiFlood v1.0 • by Roeppli",
                     font=ctk.CTkFont("Segoe UI", 10),
                     text_color="#8892A4").pack(pady=(4, 6))

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
        self._stat_ok_lbl.configure(text=str(self._stat_ok))
        self._stat_fail_lbl.configure(text=str(self._stat_fail))

    def _poll_queue(self):
        try:
            while True:
                kind, detail = self._q.get_nowait()
                if kind == "ok":
                    self._stat_ok += 1
                    self._log_msg(f"✅ Vote #{detail} erfolgreich.", "ok")
                elif kind == "fail":
                    self._stat_fail += 1
                    self._log_msg("❌ Vote fehlgeschlagen.", "err")
                elif kind == "done":
                    self._log_msg("✅ Prozess abgeschlossen.", "ok")
                elif kind == "error":
                    self._log_msg(f"⚠ Fehler: {detail}", "warn")
                self._update_stats()
        except Exception:
            pass
        self.after(200, self._poll_queue)

    # ── Laden ─────────────────────────────────────────────────────────────────

    def _on_load(self):
        slug = self._slug_entry.get().strip()
        if not slug:
            self._log_msg("⚠ Bitte einen Slug eingeben.", "warn")
            return

        self._log_msg(f"🔄 Lade Fragen für '{slug}'...")
        self._load_btn.configure(state="disabled")

        def _load():
            try:
                questions = get_questions(slug)
                self.after(0, lambda: self._on_loaded(questions))
            except Exception as e:
                self.after(0, lambda: self._log_msg(f"❌ Fehler: {e}", "err"))
            finally:
                self.after(0, lambda: self._load_btn.configure(state="normal"))

        threading.Thread(target=_load, daemon=True).start()

    def _on_loaded(self, questions: list[dict]):
        self._questions = questions
        self._selected_q = -1
        self._selected_c = -1

        labels = []
        for i, q in enumerate(questions):
            status = "🟢" if q["open"] else "🔴"
            labels.append(f"{status} [{i}] {q['title']} ({q['type']})")

        if not labels:
            self._log_msg("⚠ Keine Fragen gefunden.", "warn")
            return

        self._q_menu.configure(values=labels)
        self._q_var.set(labels[0])
        self._on_question_select(labels[0])
        self._log_msg(f"✅ {len(questions)} Frage(n) geladen.", "ok")

    def _on_question_select(self, value: str):
        # Index aus Label extrahieren
        try:
            idx = int(value.split("[")[1].split("]")[0])
        except Exception:
            return
        self._selected_q = idx
        q = self._questions[idx]

        if q["type"] == "word-cloud":
            self._c_menu.pack_forget()
            self._word_entry.pack(side="left", fill="x", expand=True)
            self._random_chk.pack(side="left", padx=(8, 0))
            self._selected_c = 0
        else:
            self._word_entry.pack_forget()
            self._random_chk.pack_forget()
            choices = [f"[{i}] {c['label']}" for i, c in enumerate(q["choices"])]
            self._c_menu.configure(values=choices if choices else ["—"])
            self._c_var.set(choices[0] if choices else "—")
            self._c_menu.pack(side="left", fill="x", expand=True)
            self._on_choice_select(self._c_var.get())

    def _on_random_toggle(self):
        if self._random_var.get():
            self._word_entry.configure(state="disabled", placeholder_text="Zufällige Wörter")
        else:
            self._word_entry.configure(state="normal", placeholder_text="Wort eingeben")

    def _on_choice_select(self, value: str):
        try:
            self._selected_c = int(value.split("[")[1].split("]")[0])
        except Exception:
            self._selected_c = 0

    # ── Start / Stop ──────────────────────────────────────────────────────────

    def _on_start(self):
        slug = self._slug_entry.get().strip()
        if not slug or self._selected_q < 0 or not self._questions:
            self._log_msg("⚠ Zuerst eine Präsentation laden und Frage wählen.", "warn")
            return

        try:
            n_proc   = int(self._proc_var.get())
            n_count  = int(self._count_var.get())
            n_worker = int(self._worker_var.get())
            assert n_proc >= 1 and n_count >= 1 and n_worker >= 1
        except Exception:
            self._log_msg("⚠ Ungültige Konfiguration.", "warn")
            return

        q = self._questions[self._selected_q]
        ic_id = q["id"]
        slide_type = q["type"]

        if slide_type == "word-cloud":
            random_words = self._random_var.get()
            word = "" if random_words else self._word_entry.get().strip()
            if not random_words and not word:
                self._log_msg("⚠ Bitte ein Wort eingeben oder 'Zufällig' aktivieren.", "warn")
                return
            choice_id = q["choices"][0]["id"] if q["choices"] else ""
        else:
            if self._selected_c < 0 or self._selected_c >= len(q["choices"]):
                self._log_msg("⚠ Bitte eine Option wählen.", "warn")
                return
            choice_id = q["choices"][self._selected_c]["id"]
            word = ""
            random_words = False

        self._clear_log()
        self._stat_ok = self._stat_fail = 0
        self._update_stats()

        # Queue leeren
        while not self._q.empty():
            try: self._q.get_nowait()
            except: break

        self._processes.clear()
        votes_per_proc = n_count // n_proc

        for i in range(n_proc):
            count = votes_per_proc if i < n_proc - 1 else n_count - votes_per_proc * (n_proc - 1)
            p = multiprocessing.Process(
                target=worker_process,
                args=(slug, ic_id, slide_type, choice_id, word, random_words, count, n_worker, self._q),
                daemon=True,
            )
            p.start()
            self._processes.append(p)
            self._log_msg(f"▶ Prozess {i+1}/{n_proc} gestartet ({count} Votes).", "ok")

        self._start_btn.configure(state="disabled")
        self._stop_btn.configure(state="normal")
        self._update_stats()
        threading.Thread(target=self._watch_processes, daemon=True).start()

    def _watch_processes(self):
        import time
        while any(p.is_alive() for p in self._processes):
            self.after(0, self._update_stats)
            time.sleep(1)
        self.after(0, self._update_stats)
        self.after(0, lambda: self._start_btn.configure(state="normal"))
        self.after(0, lambda: self._stop_btn.configure(state="disabled"))
        self.after(0, lambda: self._log_msg(
            f"🏁 Fertig! ✅ {self._stat_ok} erfolgreich, ❌ {self._stat_fail} fehlgeschlagen.", "ok"))

    def _on_stop(self):
        for p in self._processes:
            if p.is_alive():
                p.terminate()
        self._processes.clear()
        self._start_btn.configure(state="normal")
        self._stop_btn.configure(state="disabled")
        self._update_stats()
        self._log_msg("⏹ Gestoppt.", "warn")


if __name__ == "__main__":
    multiprocessing.freeze_support()
    app = MentiApp()
    app.mainloop()
