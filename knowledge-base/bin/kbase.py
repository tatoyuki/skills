"""kbase.py — knowledge-base スクリプト（index_markdown / generate_summary / create_pattern）の共通設定とユーティリティ。

スキルディレクトリの config.toml を読み、パス既定値と LLM 接続設定を提供する。
- knowledge_root → DB_DEFAULT / WIKI_DEFAULT を導出
- xxh_filelist → XXH_FILELIST（未設定ならシステム一時ディレクトリ）
- [llm] セクション → create_llm_adapter() の既定値（adapter / base_url / model / timeout / headers）

設定の優先順位: CLI オプション > config.toml > アダプタ既定値。
"""
import os
import re
import subprocess
import sys
import tempfile

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(SKILL_DIR, "config.toml")

# config.toml は必須（config.toml.template をコピーして作成する）


def _load_config():
    """config.toml を dict で返す。tomllib は Python 3.11+。無い場合は空 dict（従来動作）。"""
    if not os.path.exists(CONFIG_PATH):
        return {}
    import tomllib
    with open(CONFIG_PATH, "rb") as f:
        return tomllib.load(f)


CONFIG = _load_config()
KNOWLEDGE_ROOT = CONFIG.get("knowledge_root")
if not KNOWLEDGE_ROOT:
    raise SystemExit(
        "error: knowledge_root が設定されていません。"
        "config.toml.template を config.toml にコピーして knowledge_root を設定してください"
        f"（探索先: {CONFIG_PATH}）"
    )
DB_DEFAULT = os.path.join(KNOWLEDGE_ROOT, "index.db")
WIKI_DEFAULT = os.path.join(KNOWLEDGE_ROOT, "wiki")

# index_markdown.py の走査ルート（config.toml index_root。未設定ならホームディレクトリ）
INDEX_ROOT_DEFAULT = CONFIG.get("index_root") or os.path.expanduser("~")

# LLM 接続設定（config.toml [llm]。無いキーはアダプタ既定にフォールバック）
LLM_CONFIG = dict(CONFIG.get("llm") or {})
ADAPTER_DEFAULT = LLM_CONFIG.get("adapter") or "openai_compatible"

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    path TEXT NOT NULL UNIQUE,
    modified_at INTEGER NOT NULL,
    summary TEXT NOT NULL DEFAULT '',
    summary_at INTEGER NOT NULL DEFAULT 0,
    hash TEXT NOT NULL DEFAULT '',
    summary_hash TEXT NOT NULL DEFAULT '',
    ingest_status TEXT NOT NULL DEFAULT '',
    ingested_at INTEGER NOT NULL DEFAULT 0,
    ingested_hash TEXT NOT NULL DEFAULT '',
    ingest_priority INTEGER,
    summary_error TEXT NOT NULL DEFAULT '',
    summary_error_hash TEXT NOT NULL DEFAULT '',
    ingest_error TEXT NOT NULL DEFAULT ''
)
"""

IGNORE_SCHEMA = """
CREATE TABLE IF NOT EXISTS ignore_path (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    path TEXT NOT NULL UNIQUE,
    is_dir INTEGER NOT NULL DEFAULT 0
)
"""

# xxhsum へ渡す filelist の一時ファイル（index_markdown / generate_summary 共用）。
# config.toml xxh_filelist。未設定ならシステム一時ディレクトリ
XXH_FILELIST = CONFIG.get("xxh_filelist") or os.path.join(tempfile.gettempdir(), "xxh_filelist.txt")


def create_llm_adapter(name=None, base_url=None, model=None, timeout=None, body=None):
    """LLM アダプタを生成する。優先順位: 明示引数 > config.toml [llm] > アダプタ既定値。

    body は openai_compatible のみ有効（スクリプト側の生成設定。None でアダプタ既定）。
    """
    from adapters import create_adapter
    name = name or ADAPTER_DEFAULT
    kwargs = {}
    model = model or LLM_CONFIG.get("model")
    timeout = timeout or LLM_CONFIG.get("timeout")
    if model:
        kwargs["model"] = model
    if timeout:
        kwargs["timeout"] = int(timeout)
    if name == "openai_compatible":
        base_url = base_url or LLM_CONFIG.get("base_url")
        if base_url:
            kwargs["base_url"] = base_url
        headers = LLM_CONFIG.get("headers")
        if headers:
            kwargs["headers"] = headers
        if body:
            kwargs["body"] = body
    return create_adapter(name, **kwargs)


def ensure_summary_hash(con):
    """documents に summary_hash 列がなければ ALTER TABLE で追加する（移行）。
    SCHEMA 側は index_markdown.py の ensure_schema と対として維持している。"""
    cols = {row[1] for row in con.execute("PRAGMA table_info(documents)")}
    if "summary_hash" not in cols:
        con.execute("ALTER TABLE documents ADD COLUMN summary_hash TEXT NOT NULL DEFAULT ''")


def ensure_ingest_priority(con):
    """documents に ingest_priority 列がなければ ALTER TABLE で追加する（移行。NULL = 未採点）。
    SCHEMA 側は index_markdown.py の ensure_schema と対として維持している。"""
    cols = {row[1] for row in con.execute("PRAGMA table_info(documents)")}
    if "ingest_priority" not in cols:
        con.execute("ALTER TABLE documents ADD COLUMN ingest_priority INTEGER")


def ensure_error_columns(con):
    """LLM 失敗フラグ列を追加する（移行）。失敗時はエラーメッセージと失敗時点の hash を保存し、
    ファイル内容（hash）が変わるまで再試行しない。
    SCHEMA 側は index_markdown.py の ensure_schema と対として維持している。"""
    cols = {row[1] for row in con.execute("PRAGMA table_info(documents)")}
    if "summary_error" not in cols:
        con.execute("ALTER TABLE documents ADD COLUMN summary_error TEXT NOT NULL DEFAULT ''")
    if "summary_error_hash" not in cols:
        con.execute("ALTER TABLE documents ADD COLUMN summary_error_hash TEXT NOT NULL DEFAULT ''")
    if "ingest_error" not in cols:
        con.execute("ALTER TABLE documents ADD COLUMN ingest_error TEXT NOT NULL DEFAULT ''")


def hash_files(paths):
    """xxhsum --filelist で全 path の XXH64 を一括計算し {path: hash} を返す。

    出力は `HASH  path`（16hex + 2スペース）。正規行以外はスキップ（例: Couldn't open）。
    xxhsum が無い場合は空 dict（その実行はハッシュなしで従来動作）。
    """
    if not paths:
        return {}
    with open(XXH_FILELIST, "w", encoding="utf-8") as f:
        f.write("\n".join(paths) + "\n")
    try:
        proc = subprocess.run(["xxhsum", "--filelist", XXH_FILELIST],
                              capture_output=True, text=True, check=False)
    except FileNotFoundError:
        return {}
    hashes = {}
    for line in proc.stdout.splitlines():
        if len(line) > 18 and re.fullmatch(r"[0-9a-f]{16}", line[:16]) and line[16:18] == "  ":
            hashes[line[18:]] = line[:16]
    return hashes


def load_ignore(con):
    """ignore_path を (ファイル集合, ディレクトリprefixリスト) に読み込む。"""
    files = set()
    dirs = []
    for path, is_dir in con.execute("SELECT path, is_dir FROM ignore_path"):
        if is_dir:
            dirs.append(path if path.endswith(os.sep) else path + os.sep)
        else:
            files.add(path)
    return files, dirs


def is_ignored(p, files, dirs):
    """ファイルエントリは完全一致、ディレクトリエントリは配下すべてを対象外とする。"""
    return p in files or any(p.startswith(d) for d in dirs)


def setup_stop_key():
    """stdin で 1 キー入力を受け、停止キー検出関数を返す。

    停止キー: q / Q / Ctrl-C / Ctrl-D。検出は非ブロッキング（select で待たずに読む）。
    stdin が TTY でない場合は常に False を返す関数を返す。
    設定は atexit で復元する（停止しなくても端末状態を元に戻す）。
    """
    if not sys.stdin.isatty():
        return lambda: False
    import atexit
    import select
    import termios
    import tty

    fd = sys.stdin.fileno()
    old_attrs = termios.tcgetattr(fd)
    tty.setcbreak(fd)
    atexit.register(termios.tcsetattr, fd, termios.TCSADRAIN, old_attrs)

    state = {"stop": False}

    def stop_requested():
        if state["stop"]:
            return True
        r, _, _ = select.select([sys.stdin], [], [], 0)
        if r and os.read(fd, 1) in (b"q", b"Q", b"\x03", b"\x04"):
            state["stop"] = True
        return state["stop"]

    return stop_requested
