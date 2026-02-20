import os
import threading
import time
from datetime import datetime
from typing import Any, Dict

import requests
from flask import Flask, jsonify, request


app = Flask(__name__)


TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()
WEBHOOK_PATH = os.getenv("WEBHOOK_PATH", "/webhook").strip() or "/webhook"
REQUEST_TIMEOUT_SECONDS = float(os.getenv("REQUEST_TIMEOUT_SECONDS", "8"))
EVENT_TTL_SECONDS = int(os.getenv("EVENT_TTL_SECONDS", "86400"))
PUSH_FILTER_ENABLED = os.getenv("PUSH_FILTER_ENABLED", "false").lower() == "true"
PUSH_ONLY_EVENT_TYPES = {
    value.strip() for value in os.getenv("PUSH_ONLY_EVENT_TYPES", "").split(",") if value.strip()
}
PUSH_ONLY_ROOM_IDS = {
    int(value.strip())
    for value in os.getenv("PUSH_ONLY_ROOM_IDS", "").split(",")
    if value.strip().isdigit()
}


_processed_event_ids: Dict[str, float] = {}
_event_lock = threading.Lock()


EVENT_TYPE_LABEL = {
    "SessionStarted": "录制开始",
    "FileOpening": "文件打开",
    "FileClosed": "文件关闭",
    "SessionEnded": "录制结束",
    "StreamStarted": "直播开始",
    "StreamEnded": "直播结束",
}


def _ensure_env() -> None:
    missing = []
    if not TELEGRAM_BOT_TOKEN:
        missing.append("TELEGRAM_BOT_TOKEN")
    if not TELEGRAM_CHAT_ID:
        missing.append("TELEGRAM_CHAT_ID")
    if missing:
        raise RuntimeError(f"缺少必要环境变量: {', '.join(missing)}")


def _cleanup_old_event_ids(now_ts: float) -> None:
    expire_before = now_ts - EVENT_TTL_SECONDS
    expired_ids = [eid for eid, ts in _processed_event_ids.items() if ts < expire_before]
    for eid in expired_ids:
        _processed_event_ids.pop(eid, None)


def _is_duplicate_event(event_id: str) -> bool:
    now_ts = time.time()
    with _event_lock:
        _cleanup_old_event_ids(now_ts)
        if event_id in _processed_event_ids:
            return True
        _processed_event_ids[event_id] = now_ts
    return False


def _format_datetime(value: str) -> str:
    if not value:
        return "-"
    try:
        parsed = datetime.fromisoformat(value)
        return parsed.strftime("%Y-%m-%d %H:%M:%S%z")
    except ValueError:
        return value


def _should_push(payload: Dict[str, Any]) -> bool:
    if not PUSH_FILTER_ENABLED:
        return True

    event_type = payload.get("EventType", "")
    data = payload.get("EventData") or {}

    if PUSH_ONLY_EVENT_TYPES and event_type not in PUSH_ONLY_EVENT_TYPES:
        return False

    room_id = data.get("RoomId")
    if PUSH_ONLY_ROOM_IDS and room_id not in PUSH_ONLY_ROOM_IDS:
        return False

    return True


def _build_message(payload: Dict[str, Any]) -> str:
    event_type = payload.get("EventType", "Unknown")
    event_timestamp = _format_datetime(payload.get("EventTimestamp", ""))
    event_id = payload.get("EventId", "")
    data = payload.get("EventData") or {}

    event_label = EVENT_TYPE_LABEL.get(event_type, f"未知事件({event_type})")

    base_lines = [
        f"📡 直播事件提醒: {event_label}",
        f"时间: {event_timestamp}",
        # f"房间: {data.get('RoomId', '-')}",
        f"主播: {data.get('Name', '-')}",
        f"标题: {data.get('Title', '-')}",
        # f"分区: {data.get('AreaNameParent', '-')}/{data.get('AreaNameChild', '-')}",
        f"录制中: {data.get('Recording', '-')}",
        f"直播中: {data.get('Streaming', '-')}",
    ]

    if event_type in {"FileOpening", "FileClosed"}:
        base_lines.append(f"文件: {data.get('RelativePath', '-')}")
    if event_type == "FileClosed":
        base_lines.append(f"时长: {data.get('Duration', '-')} 秒")
        base_lines.append(f"大小: {data.get('FileSize', '-')} 字节")
    # if data.get("SessionId"):
    #     base_lines.append(f"SessionId: {data.get('SessionId')}")
    # base_lines.append(f"EventId: {event_id}")

    return "\n".join(base_lines)


def _send_telegram_message(text: str) -> None:
    _ensure_env()
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "disable_web_page_preview": True,
    }

    response = requests.post(url, json=payload, timeout=REQUEST_TIMEOUT_SECONDS)
    if response.status_code >= 300:
        raise RuntimeError(
            f"Telegram API 返回异常: HTTP {response.status_code}, body={response.text}"
        )

    body = response.json()
    if not body.get("ok"):
        raise RuntimeError(f"Telegram API 返回失败: {body}")


@app.post(WEBHOOK_PATH)
def bililive_webhook() -> Any:
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "无效 JSON"}), 400

    event_id = payload.get("EventId")
    if not event_id:
        return jsonify({"error": "缺少 EventId"}), 400

    if _is_duplicate_event(event_id):
        return ("", 204)

    if not _should_push(payload):
        return ("", 204)

    try:
        message = _build_message(payload)
        _send_telegram_message(message)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500

    return ("", 204)


@app.get("/health")
def health() -> Any:
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    host = os.getenv("FLASK_HOST", "0.0.0.0")
    port = int(os.getenv("FLASK_PORT", "5000"))
    debug = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    app.run(host=host, port=port, debug=debug)