from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Any

# Константы
APP_NAME = "AutoReclipper"
SETTINGS_FILE = "settings.json"
TEMPLATES_DIR = "templates"
RESOURCES_DIR = "rsc"
HISTORY_MAX_LEN = 20
GLOBAL_HOTKEY = "<ctrl>+<shift>+<space>"

@dataclass
class HistoryEntry:
    """
    Структура данных для хранения одной записи в истории операций.
    """
    source_content: str | Any  # Текст или PIL.Image
    template_name: str
    result_text: str
    timestamp: datetime

    def __str__(self) -> str:
        """
        Возвращает строковое представление для отображения в ComboBox.
        """
        time_str = self.timestamp.strftime('%Y-%m-%d %H:%M')
        
        source_preview = ""
        if isinstance(self.source_content, str):
            # --- ИСПРАВЛЕНИЕ: Длина предпросмотра увеличена до 50 символов ---
            source_preview = self.source_content[:50].replace('\n', ' ') + '...'
        else: # Предполагаем, что это изображение
            source_preview = "[Image]"

        return f"{time_str} | {self.template_name} | {source_preview}"