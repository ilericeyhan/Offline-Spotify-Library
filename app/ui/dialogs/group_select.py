import customtkinter as ctk

class GroupSelectDialog(ctk.CTkToplevel):
    def __init__(self, parent, title, text, options):
        super().__init__(parent)
        self.title(title)
        self.geometry("300x200")
        self.resizable(False, False)
        
        # Center the dialog
        self.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() // 2) - (self.winfo_width() // 2)
        y = parent.winfo_y() + (parent.winfo_height() // 2) - (self.winfo_height() // 2)
        self.geometry(f"300x200+{x}+{y}")
        
        self.result = None
        
        self.label = ctk.CTkLabel(self, text=text, font=("Arial", 12))
        self.label.pack(pady=20)
        
        self.combobox = ctk.CTkComboBox(self, values=options)
        self.combobox.pack(pady=10)
        
        self.btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.btn_frame.pack(pady=20)
        
        self.btn_ok = ctk.CTkButton(self.btn_frame, text="OK", width=100, command=self._on_ok)
        self.btn_ok.pack(side="left", padx=10)
        
        self.btn_cancel = ctk.CTkButton(self.btn_frame, text="Cancel", width=100, fg_color="gray", command=self._on_cancel)
        self.btn_cancel.pack(side="left", padx=10)
        
        self.transient(parent)
        self.grab_set()
        self.focus_set()
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)

    def _on_ok(self):
        self.result = self.combobox.get()
        self.destroy()

    def _on_cancel(self):
        self.result = None
        self.destroy()

    def get_input(self):
        self.wait_window()
        return self.result
