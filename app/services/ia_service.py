"""Integração com provedores de IA para extração de metadados de PDFs."""
import time

import requests

DEEPSEEK_URL = "https://api.deepseek.com/v1/chat/completions"
OPENAI_URL = "https://api.openai.com/v1/chat/completions"


def _post_with_retry(url, api_key, model, prompt, retries=3, delay=2):
    if not api_key:
        print(f"API key ausente para {url}")
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
            if response.status_code == 200:
                return response.json()["choices"][0]["message"]["content"]
            print(f"Tentativa {i+1} falhou. Erro: {response.status_code}, {response.text}")
        except Exception as exc:
            print(f"Tentativa {i+1} falhou. Erro ao comunicar com {url}: {exc}")
        time.sleep(delay)
    return None


def send_to_deepseek_with_retry(prompt, api_key, retries=3, delay=2):
    return _post_with_retry(DEEPSEEK_URL, api_key, "deepseek-chat", prompt, retries, delay)


def send_to_gpt_with_retry(prompt, api_key, retries=3, delay=2):
    return _post_with_retry(OPENAI_URL, api_key, "gpt-4o-mini", prompt, retries, delay)
