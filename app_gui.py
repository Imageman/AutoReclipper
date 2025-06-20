import queue
import threading
from tkinter import messagebox
from typing import Optional, Any

import customtkinter as ctk
from loguru import logger
from PIL import Image, ImageGrab
import pyperclip

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

        # --- Настройка UI ---
        self._setup_ui()
        self.load_state()

        # --- Фоновые задачи ---
        self.task_queue = queue.Queue()
        self.clipboard_monitor = ClipboardMonitor(self.task_queue)
        self.clipboard_monitor.start()

        self.hotkey_listener = HotkeyListener(GLOBAL_HOTKEY, self.toggle_visibility)
        self.hotkey_listener.start()
        
        self.after(100, self.check_task_queue)
        logger.info("GUI initialization complete.")

    def _setup_ui(self) -> None:
        """Создает и настраивает все виджеты интерфейса."""
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1) # Основной вес у аккордеона

        # --- Верхняя панель управления ---
        top_frame = ctk.CTkFrame(self)
        top_frame.grid(row=0, column=0, padx=10, pady=10, sticky="ew")
        top_frame.grid_columnconfigure(1, weight=1)

        self.template_combo = ctk.CTkComboBox(top_frame, values=self.template_manager.get_template_names(), command=self.on_template_select)
        self.template_combo.grid(row=0, column=0, padx=5, pady=5)
        
        self.history_combo = ctk.CTkComboBox(top_frame, values=[], command=self.on_history_select)
        self.history_combo.grid(row=0, column=1, padx=5, pady=5, sticky="ew")
        self.history_combo.set("History...")

        self.execute_button = ctk.CTkButton(top_frame, text="Execute", command=self.on_execute_button_click)
        self.execute_button.grid(row=0, column=2, padx=5, pady=5)

        # --- Аккордеон для буфера обмена ---
        self.accordion_frame = ctk.CTkFrame(self)
        self.accordion_frame.grid(row=1, column=0, padx=10, pady=(0, 10), sticky="ew")
        self.accordion_frame.grid_columnconfigure(0, weight=1)
        
        self.accordion_button = ctk.CTkButton(self.accordion_frame, text="Clipboard Input ▼", command=self.toggle_accordion)
        self.accordion_button.grid(row=0, column=0, sticky="ew", padx=2, pady=2)
        
        self.clipboard_textbox_frame = ctk.CTkFrame(self.accordion_frame, fg_color="transparent")
        self.clipboard_textbox_frame.grid(row=1, column=0, sticky="nsew")
        self.clipboard_textbox_frame.grid_columnconfigure(0, weight=1)
        self.clipboard_textbox_frame.grid_rowconfigure(0, weight=1)
        
        self.clipboard_textbox = ctk.CTkTextbox(self.clipboard_textbox_frame, wrap="word", height=150)
        self.clipboard_textbox.grid(row=0, column=0, sticky="nsew")
        
        # --- Поле для результата ---
        result_frame = ctk.CTkFrame(self)
        result_frame.grid(row=2, column=0, padx=10, pady=(0, 10), sticky="nsew")
        result_frame.grid_columnconfigure(0, weight=1)
        result_frame.grid_rowconfigure(0, weight=1)

        self.result_textbox = ctk.CTkTextbox(result_frame, wrap="word", state="disabled")
        self.result_textbox.grid(row=0, column=0, sticky="nsew", padx=2, pady=2)

    def toggle_accordion(self):
        """Переключает видимость текстового поля в аккордеоне."""
        if self.clipboard_textbox_frame.winfo_viewable():
            self.clipboard_textbox_frame.grid_remove()
            self.accordion_button.configure(text="Clipboard Input ►")
        else:
            self.clipboard_textbox_frame.grid()
            self.accordion_button.configure(text="Clipboard Input ▼")

    def toggle_visibility(self):
        """Переключает видимость главного окна."""
        if self.state() == "normal":
            self.withdraw()
        else:
            self.deiconify()
            self.lift()
            self.focus_force()

    def update_ui_for_content(self, content: Any) -> None:
        """Обновляет UI в зависимости от типа контента (текст или изображение)."""
        self.current_content = content
        self.clipboard_textbox.configure(state="normal")
        self.clipboard_textbox.delete("1.0", "end")
        if isinstance(content, str):
            self.clipboard_textbox.insert("1.0", content)
        elif isinstance(content, Image.Image):
            self.clipboard_textbox.insert("1.0", f"[Image detected: {content.width}x{content.height}]")
            self.clipboard_textbox.configure(state="disabled")
        else:
            self.clipboard_textbox.insert("1.0", "[No text or image in clipboard]")
            self.clipboard_textbox.configure(state="disabled")

    def on_execute_button_click(self) -> None:
        """Обработчик нажатия кнопки 'Execute'."""
        if self.processing_thread and self.processing_thread.is_alive():
            logger.warning("Processing is already in progress.")
            return

        template_name = self.template_combo.get()
        template = self.template_manager.get_template(template_name)
        if not template:
            messagebox.showerror("Error", "Please select a valid template.")
            return

        # Если в поле ввода текст, берем его. Иначе используем `current_content` (может быть изображением)
        if self.clipboard_textbox.cget("state") == "normal":
            content_to_process = self.clipboard_textbox.get("1.0", "end-1c")
        else:
            content_to_process = self.current_content

        if not content_to_process:
            messagebox.showwarning("Warning", "Input content is empty.")
            return

        self.set_ui_state("disabled")
        self.sound_service.play_in()

        self.processing_thread = threading.Thread(
            target=self._process_request_thread,
            args=(template, content_to_process),
            daemon=True
        )
        self.processing_thread.start()

    def _process_request_thread(self, template: dict, content: Any) -> None:
        """
        Выполняет LLM-запрос в отдельном потоке, чтобы не блокировать GUI.
        """
        logger.info(f"Starting processing thread for template '{template['name']}'.")
        result = self.llm_service.execute_request(template, content)
        # Помещаем результат в очередь для безопасного обновления GUI из основного потока
        self.task_queue.put(("PROCESSING_COMPLETE", (result, template, content)))

    def _handle_processing_complete(self, result_data: tuple) -> None:
        """
        Обрабатывает результат, полученный из потока-обработчика.
        """
        result_text, template, source_content = result_data
        
        self.set_ui_state("normal")
        self.sound_service.play_out()

        if result_text is None:
            messagebox.showerror("API Error", "Failed to get response from the LLM service. Check logs for details.")
            return

        # Обновляем поле результата
        self.result_textbox.configure(state="normal")
        self.result_textbox.delete("1.0", "end")
        self.result_textbox.insert("1.0", result_text)
        self.result_textbox.configure(state="disabled")

        # Копируем в буфер обмена
        pyperclip.copy(result_text)
        logger.info("Result copied to clipboard.")

        # Добавляем в историю
        self.history_manager.add_entry(source_content, template["name"], result_text)
        self.update_history_combo()

    def check_task_queue(self):
        """Проверяет очередь на наличие задач от фоновых потоков."""
        try:
            task_type, data = self.task_queue.get_nowait()
            logger.debug(f"Got task from queue: {task_type}")

            if task_type == "EXECUTE_FROM_CLIPBOARD":
                self.update_ui_for_content(data)
                self.on_execute_button_click()
            elif task_type == "PROCESSING_COMPLETE":
                self._handle_processing_complete(data)

        except queue.Empty:
            pass
        finally:
            self.after(100, self.check_task_queue)

    def on_template_select(self, template_name: str):
        """Обновляет подсказку при выборе шаблона."""
        template = self.template_manager.get_template(template_name)
        if template:
            # В customtkinter нет простого способа сделать tooltip, можно использовать внешнюю библиотеку
            # или просто логировать для отладки.
            logger.info(f"Selected template '{template_name}': {template['description']}")

    def on_history_select(self, history_str: str):
        """Восстанавливает состояние из выбранной записи истории."""
        if history_str == "History...":
            return
            
        entry = self.history_manager.get_entry_by_str(history_str)
        if entry:
            logger.info(f"Restoring state from history entry at {entry.timestamp}.")
            self.update_ui_for_content(entry.source_content)
            self.template_combo.set(entry.template_name)
            
            self.result_textbox.configure(state="normal")
            self.result_textbox.delete("1.0", "end")
            self.result_textbox.insert("1.0", entry.result_text)
            self.result_textbox.configure(state="disabled")
        
        # Сбрасываем комбобокс в дефолтное состояние после выбора
        self.after(100, lambda: self.history_combo.set("History..."))

    def update_history_combo(self):
        """Обновляет список в выпадающем меню истории."""
        self.history_combo.configure(values=self.history_manager.get_history_display_list())

    def set_ui_state(self, state: str):
        """Включает или выключает элементы управления во время обработки."""
        self.execute_button.configure(state=state)
        self.template_combo.configure(state=state)
        self.history_combo.configure(state=state)
        if state == "disabled":
            self.execute_button.configure(text="Processing...")
        else:
            self.execute_button.configure(text="Execute")

    def save_state(self):
        """Сохраняет текущее состояние окна и настроек."""
        settings = {
            "geometry": self.geometry(),
            "last_template": self.template_combo.get()
        }
        self.settings_manager.save_settings(settings)
        logger.info("Application state saved.")

    def load_state(self):
        """Загружает последнее состояние окна и настроек."""
        settings = self.settings_manager.load_settings()
        self.geometry(settings.get("geometry", "600x700"))
        last_template = settings.get("last_template")
        if last_template and last_template in self.template_manager.get_template_names():
            self.template_combo.set(last_template)
        elif self.template_manager.get_template_names():
            self.template_combo.set(self.template_manager.get_template_names()[0])
        logger.info("Application state loaded.")

    def on_closing(self):
        """Обработчик закрытия окна."""
        logger.info("Close window event detected.")
        self.save_state()
        self.clipboard_monitor.stop()
        self.hotkey_listener.stop()
        self.destroy()