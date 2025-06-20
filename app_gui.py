import queue
import threading
from tkinter import Menu, messagebox
from typing import Optional, Any

import customtkinter as ctk
from loguru import logger
from PIL import Image, ImageDraw, ImageFont
import pyperclip
from pystray import Icon as TrayIcon, MenuItem as TrayItem

from managers import SettingsManager, TemplateManager, HistoryManager
from services import LLMService, SoundService
from background import ClipboardMonitor, HotkeyListener
from utils import APP_NAME, GLOBAL_HOTKEY

class AutoReclipperApp(ctk.CTk):
    """
    Основной класс GUI приложения AutoReclipper.
    """
    def __init__(self):
        super().__init__()
        logger.info("Initializing AutoReclipperApp GUI.")

        self.title(APP_NAME)
        self.protocol("WM_DELETE_WINDOW", self.on_closing)

        # --- Инициализация менеджеров и сервисов ---
        self.settings_manager = SettingsManager()
        self.template_manager = TemplateManager()
        self.history_manager = HistoryManager()
        self.llm_service = LLMService()
        self.sound_service = SoundService()
        
        self.current_content: Optional[str | Image.Image] = None
        self.processing_thread: Optional[threading.Thread] = None
        self.app_font: Optional[ctk.CTkFont] = None
        
        # --- ИЗМЕНЕНИЕ: Атрибуты для иконки в трее ---
        self.tray_icon: Optional[TrayIcon] = None
        self.tray_icon_thread: Optional[threading.Thread] = None

        self.load_state()
        self._setup_ui()
        self.apply_loaded_settings()
        self._setup_app_level_bindings()

        # --- Фоновые задачи ---
        self.task_queue = queue.Queue()
        self.clipboard_monitor = ClipboardMonitor(self.task_queue)
        self.clipboard_monitor.start()
        self.hotkey_listener = HotkeyListener(GLOBAL_HOTKEY, lambda: self.task_queue.put(("TOGGLE_VISIBILITY", None)))
        self.hotkey_listener.start()
        
        self.after(100, self.check_task_queue)
        logger.info("GUI initialization complete.")

    def _setup_ui(self) -> None:
        """Создает и настраивает все виджеты интерфейса."""
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        top_frame = ctk.CTkFrame(self)
        top_frame.grid(row=0, column=0, padx=10, pady=10, sticky="ew")
        top_frame.grid_columnconfigure(1, weight=1)

        self.template_combo = ctk.CTkComboBox(top_frame, width=280, values=self.template_manager.get_template_names(), command=self.on_template_select, font=self.app_font)
        self.template_combo.grid(row=0, column=0, padx=5, pady=5)
        
        self.history_combo = ctk.CTkComboBox(top_frame, values=[], command=self.on_history_select, font=self.app_font)
        self.history_combo.grid(row=0, column=1, padx=5, pady=5, sticky="ew")
        self.history_combo.set("History...")

        self.execute_button = ctk.CTkButton(top_frame, text="Execute", command=self.on_execute_button_click, font=self.app_font)
        self.execute_button.grid(row=0, column=2, padx=5, pady=5)

        self.accordion_frame = ctk.CTkFrame(self)
        self.accordion_frame.grid(row=1, column=0, padx=10, pady=(0, 10), sticky="ew")
        self.accordion_frame.grid_columnconfigure(0, weight=1)
        
        self.accordion_button = ctk.CTkButton(self.accordion_frame, text="Clipboard Input ▼", command=self.toggle_accordion, font=self.app_font)
        self.accordion_button.grid(row=0, column=0, sticky="ew", padx=2, pady=2)
        
        self.clipboard_textbox_frame = ctk.CTkFrame(self.accordion_frame, fg_color="transparent")
        self.clipboard_textbox_frame.grid(row=1, column=0, sticky="nsew")
        self.clipboard_textbox_frame.grid_columnconfigure(0, weight=1)
        self.clipboard_textbox_frame.grid_rowconfigure(0, weight=1)
        
        self.clipboard_textbox = ctk.CTkTextbox(self.clipboard_textbox_frame, wrap="word", height=150, font=self.app_font)
        self.clipboard_textbox.grid(row=0, column=0, sticky="nsew")
        
        result_frame = ctk.CTkFrame(self)
        result_frame.grid(row=2, column=0, padx=10, pady=(0, 10), sticky="nsew")
        result_frame.grid_columnconfigure(0, weight=1)
        result_frame.grid_rowconfigure(0, weight=1)

        self.result_textbox = ctk.CTkTextbox(result_frame, wrap="word", state="disabled", font=self.app_font)
        self.result_textbox.grid(row=0, column=0, sticky="nsew", padx=2, pady=2)

        self._setup_textbox_context_menu(self.clipboard_textbox)
        self.result_textbox.configure(state="normal")
        self._setup_textbox_context_menu(self.result_textbox)
        self.result_textbox.configure(state="disabled")

    def _is_textbox_disabled(self, textbox: ctk.CTkTextbox) -> bool:
        if textbox is self.result_textbox: return True
        if textbox is self.clipboard_textbox: return isinstance(self.current_content, Image.Image)
        return False

    def _setup_textbox_context_menu(self, textbox: ctk.CTkTextbox):
        context_menu = Menu(textbox, tearoff=0, bg="#2D2D2D", fg="white", activebackground="#555555", activeforeground="white", bd=0, font=(self.app_font.cget("family"), self.app_font.cget("size") - 1))
        context_menu.add_command(label="Copy", command=lambda: self._handle_app_copy(textbox))
        context_menu.add_command(label="Paste", command=lambda: self._handle_app_paste(textbox))
        context_menu.add_command(label="Cut", command=lambda: self._handle_app_cut(textbox))
        context_menu.add_separator()
        context_menu.add_command(label="Select all", command=lambda: self._handle_app_select_all(textbox))

        def show_context_menu(event):
            disabled = self._is_textbox_disabled(textbox)
            can_paste = bool(pyperclip.paste()) and not disabled
            has_selection = bool(textbox.tag_ranges("sel"))
            context_menu.entryconfigure("Copy", state="normal" if has_selection else "disabled")
            context_menu.entryconfigure("Cut", state="normal" if has_selection and not disabled else "disabled")
            context_menu.entryconfigure("Paste", state="normal" if can_paste else "disabled")
            context_menu.tk_popup(event.x_root, event.y_root)

        textbox.bind("<Button-3>", show_context_menu)
        logger.debug(f"Context menu set up for textbox widget: {textbox}")

    def _setup_app_level_bindings(self):
        self.bind_all("<Control-c>", lambda e: self._handle_app_copy())
        self.bind_all("<Control-C>", lambda e: self._handle_app_copy())
        self.bind_all("<Control-x>", lambda e: self._handle_app_cut())
        self.bind_all("<Control-X>", lambda e: self._handle_app_cut())
        self.bind_all("<Control-v>", lambda e: self._handle_app_paste())
        self.bind_all("<Control-V>", lambda e: self._handle_app_paste())
        self.bind_all("<Control-a>", lambda e: self._handle_app_select_all())
        self.bind_all("<Control-A>", lambda e: self._handle_app_select_all())
        logger.info("Application-level key bindings have been set up using 'bind_all'.")

    def _handle_app_copy(self, widget=None):
        focused_widget = widget or self.focus_get()
        if isinstance(focused_widget, ctk.CTkTextbox):
            try:
                if focused_widget.tag_ranges("sel"):
                    pyperclip.copy(focused_widget.get("sel.first", "sel.last"))
            except Exception as e: logger.error(f"Error during copy: {e}")
        return "break"

    def _handle_app_paste(self, widget=None):
        focused_widget = widget or self.focus_get()
        if isinstance(focused_widget, ctk.CTkTextbox):
            if self._is_textbox_disabled(focused_widget): return "break"
            try:
                if text := pyperclip.paste():
                    if focused_widget.tag_ranges("sel"): focused_widget.delete("sel.first", "sel.last")
                    focused_widget.insert("insert", text)
            except Exception as e: logger.error(f"Error during paste: {e}")
        return "break"

    def _handle_app_cut(self, widget=None):
        focused_widget = widget or self.focus_get()
        if isinstance(focused_widget, ctk.CTkTextbox):
            if self._is_textbox_disabled(focused_widget): return "break"
            self._handle_app_copy(focused_widget)
            try:
                if focused_widget.tag_ranges("sel"): focused_widget.delete("sel.first", "sel.last")
            except Exception as e: logger.error(f"Error during cut: {e}")
        return "break"

    def _handle_app_select_all(self, widget=None):
        focused_widget = widget or self.focus_get()
        if isinstance(focused_widget, ctk.CTkTextbox):
            focused_widget.tag_add("sel", "1.0", "end")
        return "break"

    def toggle_accordion(self):
        if self.clipboard_textbox_frame.winfo_viewable():
            self.clipboard_textbox_frame.grid_remove()
            self.accordion_button.configure(text="Clipboard Input ►")
        else:
            self.clipboard_textbox_frame.grid()
            self.accordion_button.configure(text="Clipboard Input ▼")

    # --- ИЗМЕНЕНИЕ: Полностью новая логика для работы с треем ---
    def toggle_visibility(self):
        """Переключает видимость окна между нормальным состоянием и иконкой в трее."""
        if self.state() == "withdrawn" or self.tray_icon:
            self.show_from_tray()
        else:
            self.hide_to_tray()

    def hide_to_tray(self):
        """Скрывает окно и показывает иконку в трее."""
        self.withdraw()
        if not self.tray_icon:
            logger.info("Hiding window to system tray.")
            image = self._create_tray_icon_image()
            menu = (TrayItem('Показать', self.show_from_tray, default=True), TrayItem('Выход', self.on_closing))
            self.tray_icon = TrayIcon(APP_NAME, image, APP_NAME, menu)
            self.tray_icon_thread = threading.Thread(target=self.tray_icon.run, daemon=True)
            self.tray_icon_thread.start()

    def show_from_tray(self):
        """Показывает окно и убирает иконку из трея."""
        if self.tray_icon:
            logger.info("Showing window from system tray.")
            self.tray_icon.stop()
            self.tray_icon = None
            self.tray_icon_thread = None
        
        self.after(100, self._restore_window_state)

    def _restore_window_state(self):
        """Восстанавливает нормальное состояние окна."""
        self.deiconify()
        self.lift()
        self.focus_force()

    def _create_tray_icon_image(self) -> Image.Image:
        """Создает простое изображение для иконки в трее на лету."""
        width, height = 64, 64
        image = Image.new('RGB', (width, height), color = 'black')
        draw = ImageDraw.Draw(image)
        try:
            font = ImageFont.truetype("seguisb.ttf", 50)
        except IOError:
            font = ImageFont.load_default()
        draw.text((15, 0), "A", fill="white", font=font)
        return image

    def update_ui_for_content(self, content: Any) -> None:
        self.current_content = content
        self.clipboard_textbox.configure(state="normal")
        self.clipboard_textbox.delete("1.0", "end")
        if isinstance(content, str): self.clipboard_textbox.insert("1.0", content)
        elif isinstance(content, Image.Image):
            self.clipboard_textbox.insert("1.0", f"[Image detected: {content.width}x{content.height}]")
            self.clipboard_textbox.configure(state="disabled")
        else:
            self.clipboard_textbox.insert("1.0", "[No text or image in clipboard]")
            self.clipboard_textbox.configure(state="disabled")

    def on_execute_button_click(self) -> None:
        if self.processing_thread and self.processing_thread.is_alive():
            logger.warning("Processing is already in progress.")
            return
        template_name = self.template_combo.get()
        template = self.template_manager.get_template(template_name)
        if not template:
            messagebox.showerror("Error", "Please select a valid template.")
            return
        content_to_process = self.clipboard_textbox.get("1.0", "end-1c").strip() if not isinstance(self.current_content, Image.Image) else self.current_content
        if not content_to_process:
            messagebox.showwarning("Warning", "Input content is empty.")
            return
        self.set_ui_state("disabled")
        self.sound_service.play_in()
        self.processing_thread = threading.Thread(target=self._process_request_thread, args=(template, content_to_process), daemon=True)
        self.processing_thread.start()

    def _process_request_thread(self, template: dict, content: Any) -> None:
        logger.info(f"Starting processing thread for template '{template['name']}'.")
        result = self.llm_service.execute_request(template, content)
        self.task_queue.put(("PROCESSING_COMPLETE", (result, template, content)))

    def _handle_processing_complete(self, result_data: tuple) -> None:
        result_text, template, source_content = result_data
        self.set_ui_state("normal")
        self.sound_service.play_out()
        if result_text is None:
            messagebox.showerror("API Error", "Failed to get response from the LLM service. Check logs for details.")
            return
        self.result_textbox.configure(state="normal")
        self.result_textbox.delete("1.0", "end")
        self.result_textbox.insert("1.0", result_text)
        self.result_textbox.configure(state="disabled")
        pyperclip.copy(result_text)
        logger.info("Result copied to clipboard.")
        self.history_manager.add_entry(source_content, template["name"], result_text)
        self.update_history_combo()

    def check_task_queue(self):
        try:
            task_type, data = self.task_queue.get_nowait()
            logger.debug(f"Got task from queue: {task_type}")
            if task_type == "EXECUTE_FROM_CLIPBOARD":
                self.show_from_tray() # Показываем окно перед выполнением
                self.after(150, lambda: self.update_ui_for_content(data))
                self.after(200, self.on_execute_button_click)
            elif task_type == "PROCESSING_COMPLETE":
                self._handle_processing_complete(data)
            elif task_type == "TOGGLE_VISIBILITY":
                self.toggle_visibility()
        except queue.Empty: pass
        finally: self.after(100, self.check_task_queue)

    def on_template_select(self, template_name: str):
        if template := self.template_manager.get_template(template_name):
            logger.info(f"Selected template '{template_name}': {template['description']}")

    def on_history_select(self, history_str: str):
        if history_str == "History...": return
        if entry := self.history_manager.get_entry_by_str(history_str):
            logger.info(f"Restoring state from history entry at {entry.timestamp}.")
            self.update_ui_for_content(entry.source_content)
            self.template_combo.set(entry.template_name)
            self.result_textbox.configure(state="normal")
            self.result_textbox.delete("1.0", "end")
            self.result_textbox.insert("1.0", entry.result_text)
            self.result_textbox.configure(state="disabled")
        self.after(100, lambda: self.history_combo.set("History..."))

    def update_history_combo(self):
        self.history_combo.configure(values=self.history_manager.get_history_display_list())

    def set_ui_state(self, state: str):
        self.execute_button.configure(state=state)
        self.template_combo.configure(state=state)
        self.history_combo.configure(state=state)
        self.execute_button.configure(text="Processing..." if state == "disabled" else "Execute")

    def save_state(self):
        settings = {
            "geometry": self.geometry(),
            "last_template": self.template_combo.get(),
            "font_family": self.app_font.cget("family"),
            "font_size": self.app_font.cget("size"),
        }
        self.settings_manager.save_settings(settings)
        logger.info("Application state saved.")

    def load_state(self):
        self.settings = self.settings_manager.load_settings()
        self.geometry(self.settings.get("geometry", "600x700"))
        font_family, font_size = self.settings.get("font_family"), self.settings.get("font_size")
        try:
            if not isinstance(font_family, str) or not font_family: raise ValueError
            font_size = int(font_size)
            if font_size <= 0: raise ValueError
        except (ValueError, TypeError):
            logger.warning(f"Invalid font settings found, falling back to defaults.")
            font_family, font_size = "Segoe UI", 13
        self.app_font = ctk.CTkFont(family=font_family, size=font_size)
        logger.info(f"Application font set to: {font_family}, {font_size}pt")

    def apply_loaded_settings(self):
        last_template = self.settings.get("last_template")
        if last_template and last_template in self.template_manager.get_template_names():
            self.template_combo.set(last_template)
        elif self.template_manager.get_template_names():
            self.template_combo.set(self.template_manager.get_template_names()[0])
        logger.info("Loaded settings applied to UI.")

    def on_closing(self):
        """Обработчик закрытия окна."""
        logger.info("Close window event detected.")
        if self.tray_icon:
            self.tray_icon.stop()
        self.save_state()
        self.clipboard_monitor.stop()
        self.hotkey_listener.stop()
        self.destroy()