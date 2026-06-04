"""
Gmail Auto-Organizer MCP Server
讓 Claude 可以直接執行 gmail_organizer.py 並讀取 log
"""

import subprocess
import sys
from pathlib import Path

from fastmcp import FastMCP

SCRIPT_DIR = Path(__file__).parent
ORGANIZER  = SCRIPT_DIR / "gmail_organizer.py"
LOG_FILE   = SCRIPT_DIR / "gmail_organizer.log"

mcp = FastMCP("gmail-organizer")


@mcp.tool()
def run_gmail_organizer() -> str:
    """執行 Gmail 自動整理腳本（分類標籤、清垃圾信）。"""
    result = subprocess.run(
        [sys.executable, str(ORGANIZER)],
        capture_output=True,
        text=True,
        cwd=str(SCRIPT_DIR),
    )
    output = result.stdout + result.stderr
    return output.strip() or "（無輸出）"


@mcp.tool()
def read_gmail_log(lines: int = 50) -> str:
    """讀取 gmail_organizer.log 最後 N 行（預設 50）。"""
    if not LOG_FILE.exists():
        return "log 檔不存在，請先執行 run_gmail_organizer。"
    log_lines = LOG_FILE.read_text(encoding="utf-8").splitlines()
    return "\n".join(log_lines[-lines:])


if __name__ == "__main__":
    mcp.run()
