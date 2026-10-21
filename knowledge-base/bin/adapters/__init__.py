"""adapters — LLMへの接続を切り出すパッケージ。

create_adapter(name, **kwargs) でアダプタを生成する。
name:
- openai_compatible: OpenAI 互換 /v1/chat/completions を直接呼ぶ（既定・従来実装の切り出し）
- opencode_cli:      opencode run CLI 経由で実行する

全アダプタの chat(prompt) は (text, error) を返す（従来 call_chat() と同じ契約）。
"""
from .openai_compatible import OpenAICompatibleAdapter
from .opencode_cli import OpenCodeCLIAdapter

ADAPTERS = {
    "openai_compatible": OpenAICompatibleAdapter,
    "opencode_cli": OpenCodeCLIAdapter,
}


def create_adapter(name, **kwargs):
    """名前でアダプタを生成する。model=None のとき各アダプタの既定モデルを使う。"""
    if name not in ADAPTERS:
        raise ValueError(f"unknown adapter: {name} (choices: {', '.join(ADAPTERS)})")
    return ADAPTERS[name](**kwargs)
