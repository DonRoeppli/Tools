import customtkinter as ctk
import keyboard
import time
import os
import sys

class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("AutoWriter")
        self.iconbitmap(self.path("icon.ico"))
        self.geometry("530x470")
        self.attributes("-topmost", True)
        
        self.font = ctk.CTkFont(family="Cascadia Mono", size=16)
        self.font_small = ctk.CTkFont(family="Cascadia Mono", size=10)

        self.text_label = ctk.CTkLabel(self, text="Enter text to write:", font=self.font)
        self.text_label.pack(pady=5)

        self.text_area = ctk.CTkTextbox(self, width=500, height=300)
        self.text_area.pack(pady=5)
        
        self.delay_label = ctk.CTkLabel(self, text=f"Delay before writing (5s):", font=self.font)
        self.delay_label.pack(pady=5)
        
        self.delay_slider = ctk.CTkSlider(self, from_=0, to=10, width=200)
        self.delay_slider.configure(command=self.update_delay_label, number_of_steps=10)
        self.delay_slider.set(5)
        self.delay_slider.pack(pady=5)

        self.start_button = ctk.CTkButton(self, text="Start Writing", font=self.font, width=200, height=40, command=self.start_writing)
        self.start_button.pack(pady=5)
        
        self.watermark_label = ctk.CTkLabel(self, text="by Roeppli", font=self.font_small)
        self.watermark_label.place(relx=1.0, rely=1.0, anchor="se", x=-10)
        
    def update_delay_label(self, value):
        self.delay_label.configure(text=f"Delay before writing ({int(value)}s):")

    def start_writing(self):
        text_to_write = self.text_area.get("1.0", "end-1c")
        delay = self.delay_slider.get()
        
        self.destroy()
        time.sleep(delay)

        for char in text_to_write:
            if char == "\n":
                keyboard.press_and_release("enter")
            else:
                keyboard.write(char)

            
    def path(self, relative_path):
        if hasattr(sys, "_MEIPASS"):
            return os.path.join(sys._MEIPASS, relative_path) # type: ignore[attr-defined]
        return os.path.join(os.path.abspath("."), relative_path)        
            
            
if __name__ == "__main__":
    app = App()
    app.mainloop()
