"""openai_compatible.py — OpenAI 互換 /v1/chat/completions を直接呼ぶ（標準ライブラリのみ）。

generate_summary.py / create_pattern.py に重複していた call_chat() の切り出し。
例外捕捉は generate_summary.py 版（URLError / TimeoutError / OSError / JSONDecodeError）に統一した
（create_pattern.py 側は TimeoutError / OSError を捕捉しておらず read タイムアウトで未捕捉例外になっていた）。
"""
import json
import urllib.error
import urllib.request

BASE_URL_DEFAULT = "http://127.0.0.1:8080/v1"
MODEL_DEFAULT = "qwen3.8-flash-next-iq2_xs"
TIMEOUT_DEFAULT = 120

# 既定ヘッダ。環境依存のヘッダ（例: Sleev → Strata 中継の sleev-harness / sleev-base-url）は
# config.toml [llm.headers] で指定する（指定分はここにマージし、同名キーを上書きする）
DEFAULT_HEADERS = {
    "Content-Type": "application/json",
}

# opencode.jsonc の body（Strata Thinking 設定）
DEFAULT_BODY = {
    "reasoning_effort": "none",
    "reasoning_budget_tokens": 0,
    "temperature": 0.5,
    "top_p": 0.95,
}


class OpenAICompatibleAdapter:
    """/v1/chat/completions を呼ぶアダプタ。body はスクリプト側の設定で丸ごと上書きできる。"""

    def __init__(self, base_url=BASE_URL_DEFAULT, model=None, timeout=TIMEOUT_DEFAULT,
                 headers=None, body=None):
        self.base_url = base_url
        self.model = model or MODEL_DEFAULT
        self.timeout = timeout
        self.headers = {**DEFAULT_HEADERS, **(headers or {})}
        self.body = dict(DEFAULT_BODY) if body is None else dict(body)

    def chat(self, prompt):
        """/v1/chat/completions を1回呼んで生成文を返す。失敗時は (None, error) を返す。"""
        payload = {"model": self.model, "messages": [{"role": "user", "content": prompt}]}
        payload.update(self.body)
        req = urllib.request.Request(
            self.base_url.rstrip("/") + "/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers=self.headers,
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            # TimeoutError は urlopen の read 中に発生しうる（URLError のサブクラスではない）
            return None, str(exc)

        choices = data.get("choices") or []
        if not choices:
            return None, f"no choices: {data}"
        text = (choices[0].get("message") or {}).get("content") or ""
        if not text.strip():
            return None, "empty content"
        return text, None
