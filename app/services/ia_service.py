"""Integração com provedores de IA para extração de metadados de PDFs."""
import logging
import time

import requests

logger = logging.getLogger(__name__)

DEEPSEEK_URL = "https://api.deepseek.com/v1/chat/completions"
OPENAI_URL = "https://api.openai.com/v1/chat/completions"


def _post_with_retry(url, api_key, model, prompt, retries=3, delay=2):
    if not api_key:
        logger.warning("API key ausente para %s — pulando chamada.", url)
        return None

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    data = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 150,
    }

    for i in range(retries):
        try:
            response = requests.post(url, headers=headers, json=data, timeout=30)
            logger.info(
                "[IA] %s tentativa %d status=%s body=%s",
                url, i + 1, response.status_code, response.text[:800],
            )
            if response.status_code == 200:
                content = response.json()["choices"][0]["message"]["content"]
                logger.info("[IA] conteúdo retornado (%d chars):\n%s", len(content), content)
                return content
            logger.warning(
                "Tentativa %d falhou (%s): %s %s",
                i + 1, url, response.status_code, response.text,
            )
        except requests.RequestException as exc:
            logger.warning("Tentativa %d falhou (%s): %s", i + 1, url, exc)
        time.sleep(delay)
    return None


def send_to_deepseek_with_retry(prompt, api_key, retries=3, delay=2):
    return _post_with_retry(DEEPSEEK_URL, api_key, "deepseek-chat", prompt, retries, delay)


def send_to_gpt_with_retry(prompt, api_key, retries=3, delay=2):
    return _post_with_retry(OPENAI_URL, api_key, "gpt-4o-mini", prompt, retries, delay)
