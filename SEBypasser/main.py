import customtkinter as ctk
import os
import sys
import tempfile
import subprocess
import requests
import threading
import time


def path(relative_path):
        if hasattr(sys, "_MEIPASS"):
            return os.path.join(sys._MEIPASS, relative_path) # type: ignore[attr-defined]
        return os.path.join(os.path.abspath("."), relative_path)


class App(ctk.CTk):
    def __init__(self): 
        super().__init__()

        self.title("SEBypasser")
        self.iconbitmap(path("icon.ico"))
        self.geometry("250x130")
        self.resizable(False, False)
        self.attributes("-topmost", True)

        self.font = ctk.CTkFont(family="Cascadia Mono", size=16)
        self.font_small = ctk.CTkFont(family="Cascadia Mono", size=10)
        
        self.seb_url = "https://api.github.com/repos/SafeExamBrowser/seb-win-refactoring"
        self.seb_version = requests.get(f"{self.seb_url}/tags", timeout=10).json()[0]["name"]
        
        self.patch_url = "https://git.vichingo455.qzz.io/api/v1/repos/school-cheating/SEBPatch"
        self.patch_version = requests.get(f"{self.patch_url}/tags", timeout=10).json()[0]["name"]

        self.start_button = ctk.CTkButton(
            self,
            text="Start Bypass",
            font=self.font,
            width=200,
            height=40,
            command=self.start_bypass
        )
        self.start_button.pack(padx=10, pady=10)
        
        self.status_label = ctk.CTkLabel(
            self,
            text=f"SEB: {self.seb_version}\nPatch: {self.patch_version}",
            font=self.font
        )
        self.status_label.pack(padx=10)

        self.watermark_label = ctk.CTkLabel(
            self,
            text="by Roeppli",
            font=self.font_small
        )
        self.watermark_label.place(relx=1.0, rely=1.0, anchor="se", x=-10)

    def start_bypass(self):
        self.status_label.configure(text="Downloading...")
        self.start_button.configure(state="disabled")

        threading.Thread(target=self.download_and_launch, daemon=True).start()
        
    def download_and_launch(self):
        exe_url = f"https://git.vichingo455.qzz.io/school-cheating/SEBPatch/releases/download/{self.patch_version}/patch-seb.exe"
        temp_dir = tempfile.mkdtemp()
        exe_path = os.path.join(temp_dir, exe_url.split("/")[-1])

        try:
            r = requests.get(exe_url, timeout=10)
            r.raise_for_status()
        except Exception:
            self.after(0, lambda: self.status_label.configure(text="Download failed"))
            self.after(0, lambda: self.start_button.configure(state="normal"))
            return

        with open(exe_path, "wb") as f:
            f.write(r.content)

        self.after(0, lambda: self.status_label.configure(text="Launching..."))
        subprocess.Popen([exe_path], shell=True)
        time.sleep(1)
        self.after(0, lambda: self.destroy())


if __name__ == "__main__":
    app = App()
    app.mainloop()
