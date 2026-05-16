import os
import json
import threading
from typing import Dict, Any, Optional

import httpx
from loguru import logger
from PIL import Image
import winsound

from utils import RESOURCES_DIR

CONFIG_FILE = "config.cfg"

def load_config() -> Dict[str, Any]:
    """Загружает конфигурацию из config.cfg."""
    defaults = {
        "api_base_url": "",
        "api_key": "",
        "default_model": "",
        "gpt_oss_settings": "medium"
    }
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                config = json.load(f)
            defaults.update(config)
    except Exception as e:
        logger.warning(f"Could not load config from {CONFIG_FILE}: {e}")
    return defaults

class LLMService:
    """
    Сервис для взаимодействия с API языковых моделей.
    """
    TIMEOUT_SECONDS = 60
    RETRY_ATTEMPTS = 3

    def __init__(self):
        self.config = load_config()
        if not self.config.get("api_base_url"):
            raise ValueError("api_base_url is not set in config.cfg")
        
        self.client = httpx.Client(timeout=self.TIMEOUT_SECONDS)
        logger.info(f"LLMService initialized with config: base_url={self.config.get('api_base_url')}, model={self.config.get('default_model')}")

    def execute_request(self, template: Dict[str, Any], content: str | Image.Image) -> Optional[str]:
        """
        Выполняет запрос к LLM на основе шаблона и контента.
        
        :param template: Словарь с данными шаблона.
        :param content: Текст или изображение из буфера обмена.
        :return: Результат от LLM или None в случае ошибки.
        """
        provider = template.get("api_provider")
        if provider == "gemini" or provider == "openai-compatible":
            return self._execute_openai_request(template, content)
        else:
            logger.error(f"Unsupported API provider: {provider}")
            return None

    def _execute_openai_request(self, template: Dict[str, Any], content: Any) -> Optional[str]:
        """
        Выполняет запрос к OpenAI-совместимому API.
        """
        base_url = self.config.get("api_base_url", "").rstrip("/")
        model = self.config.get("default_model") or template.get("model")
        input_type = template.get("input_type")
        prompt_template = template.get("prompt")
        
        full_prompt = prompt_template.format(clipboard_text=content if isinstance(content, str) else "")

        logger.info(f"Executing request to model '{model}' at '{base_url}' with input type '{input_type}'.")
        
        thinking_mode = self.config.get("thinking_mode", True)
        gpt_oss_settings = self.config.get("gpt_oss_settings", "medium")
        
        settings_map = {
            "low": "low",
            "medium": "medium", 
            "high": "high"
        }
        
        for attempt in range(1, self.RETRY_ATTEMPTS + 1):
            try:
                if input_type == "text" and isinstance(content, str):
                    payload = {
                        "model": model,
                        "input": full_prompt,
                        "temperature": 0.7
                    }
                    if not thinking_mode:
                        payload["reasoning"] = "off"
                    else:
                        payload["reasoning"] = settings_map.get(gpt_oss_settings, "medium")
                    
                    headers = {}
                    if self.config.get("api_key"):
                        headers["Authorization"] = f"Bearer {self.config['api_key']}"
                    
                    response = self.client.post(f"{base_url}/api/v1/chat", json=payload, headers=headers)
                    response.raise_for_status()
                    result = response.json()
                    for item in result.get("output", []):
                        if item.get("type") == "message":
                            return item.get("content", "").strip()
                    return ""
                    
                elif input_type == "image" and isinstance(content, Image.Image):
                    import base64
                    import io
                    buffered = io.BytesIO()
                    content.save(buffered, format="PNG")
                    img_b64 = base64.b64encode(buffered.getvalue()).decode()
                    
                    payload = {
                        "model": model,
                        "input": [
                            {"type": "text", "content": full_prompt},
                            {"type": "image", "data_url": f"data:image/png;base64,{img_b64}"}
                        ],
                        "temperature": 0.7
                    }
                    if not thinking_mode:
                        payload["reasoning"] = "off"
                    else:
                        payload["reasoning"] = settings_map.get(gpt_oss_settings, "medium")
                    
                    headers = {}
                    if self.config.get("api_key"):
                        headers["Authorization"] = f"Bearer {self.config['api_key']}"
                    
                    response = self.client.post(f"{base_url}/api/v1/chat", json=payload, headers=headers)
                    response.raise_for_status()
                    result = response.json()
                    for item in result.get("output", []):
                        if item.get("type") == "message":
                            return item.get("content", "").strip()
                    return ""
                else:
                    logger.error(
                        f"Mismatched input type: template requires '{input_type}' but content is '{type(content).__name__}'."
                    )
                    return f"Error: Template requires {input_type}, but received different content type."

            except httpx.TimeoutException:
                logger.warning(
                    f"Request timed out after {self.TIMEOUT_SECONDS}s (attempt {attempt}/{self.RETRY_ATTEMPTS})."
                )
                if attempt == self.RETRY_ATTEMPTS:
                    break
            except Exception as e:
                logger.opt(exception=True).error(f"An error occurred while querying API: {e}")
                if attempt == self.RETRY_ATTEMPTS:
                    break

        return None

class SoundService:
    """
    Сервис для воспроизведения звуковых сигналов.
    """
    def __init__(self, resource_dir: str = RESOURCES_DIR):
        self.in_sound_path = os.path.join(resource_dir, "in.wav")
        self.out_sound_path = os.path.join(resource_dir, "out.wav")
        self.fail_sound_path = os.path.join(resource_dir, "fail.wav")
        logger.info("SoundService initialized.")

    def _play_sound(self, sound_path: str):
        """Воспроизводит звук в отдельном потоке, чтобы не блокировать GUI."""
        if not os.path.exists(sound_path):
            logger.warning(f"Sound file not found: {sound_path}")
            return
        try:
            threading.Thread(target=lambda: winsound.PlaySound(sound_path, winsound.SND_FILENAME), daemon=True).start()
        except Exception as e:
            logger.error(f"Could not play sound {sound_path}: {e}")

    def play_in(self):
        """Воспроизводит звук начала операции."""
        logger.debug("Playing 'in' sound.")
        self._play_sound(self.in_sound_path)

    def play_out(self):
        """Воспроизводит звук завершения операции."""
        logger.debug("Playing 'out' sound.")
        self._play_sound(self.out_sound_path)

    def play_fail(self):
        """Воспроизводит звук неудачной операции."""
        logger.debug("Playing 'fail' sound.")
        self._play_sound(self.fail_sound_path)