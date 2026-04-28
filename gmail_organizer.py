#!/usr/bin/env python3
"""
Gmail 自動整理工具
帳號: TOCIN53@Gmail.COM
功能: 自動分類標籤、刪除垃圾郵件
"""

import os
import json
import base64
import logging
from datetime import datetime
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# ── 設定 ──────────────────────────────────────────────────────────────
SCRIPT_DIR   = Path(__file__).parent
RULES_FILE   = SCRIPT_DIR / "gmail_rules.json"
TOKEN_FILE   = SCRIPT_DIR / "token.json"
CREDS_FILE   = SCRIPT_DIR / "credentials.json"
LOG_FILE     = SCRIPT_DIR / "gmail_organizer.log"

SCOPES = [
    "https://mail.google.com/",  # 包含 modify + labels + 永久刪除
]

# ── 日誌 ──────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger(__name__)


# ── Gmail 認證 ────────────────────────────────────────────────────────
def get_gmail_service():
    """取得已授權的 Gmail API 服務物件"""
    creds = None
    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not CREDS_FILE.exists():
                raise FileNotFoundError(
                    f"找不到 {CREDS_FILE}\n"
                    "請先下載 Google Cloud 的 OAuth credentials.json 並放到此資料夾"
                )
            flow = InstalledAppFlow.from_client_secrets_file(str(CREDS_FILE), SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())

    return build("gmail", "v1", credentials=creds)


# ── 標籤管理 ──────────────────────────────────────────────────────────
LABEL_COLORS = {
    "blue":   {"backgroundColor": "#4986e7", "textColor": "#ffffff"},
    "green":  {"backgroundColor": "#2da2bb", "textColor": "#ffffff"},
    "red":    {"backgroundColor": "#cc3a21", "textColor": "#ffffff"},
    "yellow": {"backgroundColor": "#fad165", "textColor": "#ffffff"},
    "purple": {"backgroundColor": "#a479e2", "textColor": "#ffffff"},
}

def get_or_create_label(service, name: str, color: str) -> str:
    """取得或建立 Gmail 標籤，回傳 label_id"""
    results = service.users().labels().list(userId="me").execute()
    existing = {lbl["name"]: lbl["id"] for lbl in results.get("labels", [])}

    if name in existing:
        return existing[name]

    body = {
        "name": name,
        "labelListVisibility": "labelShow",
        "messageListVisibility": "show",
    }
    if color in LABEL_COLORS:
        body["color"] = LABEL_COLORS[color]

    created = service.users().labels().create(userId="me", body=body).execute()
    log.info(f"建立標籤: {name}")
    return created["id"]


# ── 郵件搜尋與讀取 ────────────────────────────────────────────────────
def search_messages(service, query: str, max_results: int = 500):
    """搜尋郵件，回傳 message id 列表"""
    messages = []
    request = service.users().messages().list(userId="me", q=query, maxResults=min(max_results, 500))
    while request:
        resp = request.execute()
        messages.extend(resp.get("messages", []))
        request = service.users().messages().list_next(request, resp)
        if len(messages) >= max_results:
            break
    return messages[:max_results]

def get_message_headers(service, msg_id: str) -> dict:
    """取得郵件標頭（寄件者、主題）與 snippet"""
    msg = service.users().messages().get(
        userId="me", id=msg_id, format="metadata",
        metadataHeaders=["From", "Subject", "To"]
    ).execute()
    headers = {h["name"].lower(): h["value"] for h in msg.get("payload", {}).get("headers", [])}
    headers["snippet"] = msg.get("snippet", "")
    headers["label_ids"] = msg.get("labelIds", [])
    return headers

def apply_label(service, msg_id: str, label_id: str):
    service.users().messages().modify(
        userId="me", id=msg_id,
        body={"addLabelIds": [label_id], "removeLabelIds": []}
    ).execute()

def move_to_trash(service, msg_id: str):
    service.users().messages().trash(userId="me", id=msg_id).execute()

def delete_permanently(service, msg_id: str):
    service.users().messages().delete(userId="me", id=msg_id).execute()


# ── 規則比對 ──────────────────────────────────────────────────────────
def matches_rule(headers: dict, rule: dict) -> bool:
    sender  = headers.get("from", "").lower()
    subject = headers.get("subject", "").lower()
    snippet = headers.get("snippet", "").lower()

    for s in rule.get("senders", []):
        if s.lower() in sender:
            return True
    for kw in rule.get("subject_keywords", []):
        if kw.lower() in subject:
            return True
    for kw in rule.get("body_keywords", []):
        if kw.lower() in snippet:
            return True
    return False

def is_spam(headers: dict, spam_rules: dict) -> bool:
    sender  = headers.get("from", "").lower()
    subject = headers.get("subject", "").lower()
    snippet = headers.get("snippet", "").lower()

    for s in spam_rules.get("sender_blacklist", []):
        if s.lower() in sender:
            return True
    for kw in spam_rules.get("subject_blacklist", []):
        if kw.lower() in subject:
            return True
    for kw in spam_rules.get("body_blacklist", []):
        if kw.lower() in snippet:
            return True
    return False


# ── 主流程 ────────────────────────────────────────────────────────────
def run():
    log.info("=" * 60)
    log.info(f"開始執行 Gmail 整理 ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')})")

    # 讀取規則
    with open(RULES_FILE, encoding="utf-8") as f:
        config = json.load(f)

    service = get_gmail_service()
    log.info("Gmail API 連線成功")

    # ── 步驟 1: 建立標籤並整理分類 ──
    label_map = {}  # name -> label_id
    for label_cfg in config["labels"]:
        lid = get_or_create_label(service, label_cfg["name"], label_cfg.get("color", "blue"))
        label_map[label_cfg["name"]] = lid

    # 搜尋未分類的收件匣郵件
    log.info("搜尋收件匣郵件...")
    messages = search_messages(service, "in:inbox", max_results=200)
    log.info(f"找到 {len(messages)} 封郵件")

    label_counts = {name: 0 for name in label_map}

    for msg in messages:
        try:
            headers = get_message_headers(service, msg["id"])

            # 比對每個分類規則
            for label_cfg in config["labels"]:
                if matches_rule(headers, label_cfg["rules"]):
                    lid = label_map[label_cfg["name"]]
                    # 若尚未貼上此標籤才操作
                    if lid not in headers.get("label_ids", []):
                        apply_label(service, msg["id"], lid)
                        label_counts[label_cfg["name"]] += 1
                        log.debug(f'  [{label_cfg["name"]}] {headers.get("subject","(無主旨)")[:50]}')
                    break  # 只套用第一個符合的標籤

        except HttpError as e:
            log.warning(f"處理郵件 {msg['id']} 失敗: {e}")

    log.info("分類結果:")
    for name, count in label_counts.items():
        if count > 0:
            log.info(f"  {name}: {count} 封")

    # ── 步驟 2: 處理垃圾郵件 ──
    log.info("搜尋垃圾郵件...")
    spam_rules = config["spam_rules"]

    # Gmail 已標記的垃圾郵件 + 我們自訂的黑名單
    spam_messages = search_messages(service, "in:spam", max_results=500)
    log.info(f"Gmail 垃圾桶中有 {len(spam_messages)} 封")

    # 自訂黑名單掃描收件匣
    inbox_messages = search_messages(service, "in:inbox", max_results=200)
    custom_spam = []
    for msg in inbox_messages:
        try:
            headers = get_message_headers(service, msg["id"])
            if is_spam(headers, spam_rules):
                custom_spam.append(msg)
                log.info(f'  偵測垃圾: {headers.get("subject","(無主旨)")[:60]}')
        except HttpError as e:
            log.warning(f"檢查郵件 {msg['id']} 失敗: {e}")

    trash_mode = spam_rules.get("move_to_trash_instead_of_delete", True)
    action_name = "移至垃圾桶" if trash_mode else "永久刪除"

    # 處理 Gmail 垃圾郵件資料夾
    deleted = 0
    for msg in spam_messages:
        try:
            if trash_mode:
                move_to_trash(service, msg["id"])
            else:
                delete_permanently(service, msg["id"])
            deleted += 1
        except HttpError as e:
            log.warning(f"刪除郵件 {msg['id']} 失敗: {e}")

    # 處理自訂黑名單偵測到的垃圾
    for msg in custom_spam:
        try:
            if trash_mode:
                move_to_trash(service, msg["id"])
            else:
                delete_permanently(service, msg["id"])
            deleted += 1
        except HttpError as e:
            log.warning(f"刪除郵件 {msg['id']} 失敗: {e}")

    log.info(f"垃圾郵件移至垃圾桶: {deleted} 封")

    # ── 步驟 3: 清空垃圾桶（永久刪除）──
    log.info("清空垃圾桶...")
    trash_messages = search_messages(service, "in:trash", max_results=1000)
    purged = 0
    for msg in trash_messages:
        try:
            delete_permanently(service, msg["id"])
            purged += 1
        except HttpError as e:
            log.warning(f"清除郵件 {msg['id']} 失敗: {e}")
    log.info(f"垃圾桶清空: {purged} 封永久刪除")
    log.info("整理完成！")
    log.info("=" * 60)


if __name__ == "__main__":
    run()
