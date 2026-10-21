"""opencode_cli.py — opencode run CLI 経由で LLM を実行する。

利点: opencode.jsonc のプロバイダ設定を再利用できる（Sleev ヘッダ・body 設定が不要）。
実測（2026-10-12）: 既定フォーマットでは応答テキストのみが stdout に出る
（"> build · model" 等のステータス行は stderr）。呼び出しごとに新規セッションが1件作られる。
model は provider/model 形式（例: strata-sleev/qwen3.8-flash-next-iq2_xs）。
"""
import subprocess

MODEL_DEFAULT = "strata-sleev/qwen3.8-flash-next-iq2_xs"
TIMEOUT_DEFAULT = 120


class OpenCodeCLIAdapter:
    """opencode run を1回実行し、stdout を生成文とする。"""

    def __init__(self, model=None, timeout=TIMEOUT_DEFAULT, agent=None,
                 standalone=False, auto=True, cwd=None):
        self.model = model or MODEL_DEFAULT
        self.timeout = timeout
        self.agent = agent
        self.standalone = standalone
        self.auto = auto
        self.cwd = cwd

    def chat(self, prompt):
        """opencode run を1回呼んで生成文を返す。失敗時は (None, error) を返す。"""
        cmd = ["opencode", "run", "--model", self.model]
        if self.agent:
            cmd += ["--agent", self.agent]
        if self.standalone:
            cmd.append("--standalone")
        if self.auto:
            cmd.append("--auto")
        cmd.append(prompt)
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True,
                                  timeout=self.timeout, cwd=self.cwd)
        except subprocess.TimeoutExpired:
            return None, f"timeout: {self.timeout} s"
        except OSError as exc:
            return None, str(exc)
        if proc.returncode != 0:
            err_lines = (proc.stderr or "").strip().splitlines()
            return None, f"rc={proc.returncode}: {err_lines[-1] if err_lines else 'no stderr'}"
        text = proc.stdout.strip()
        if not text:
            return None, "empty output"
        return text, None
