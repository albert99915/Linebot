"""LINE 預約機器人主程式"""

import os
import logging
from flask import Flask, request, abort
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    Configuration,
    ApiClient,
    MessagingApi,
    ReplyMessageRequest,
    TextMessage,
)
from linebot.v3.webhooks import MessageEvent, TextMessageContent

from db import init_db, add_reservation, get_user_reservations, delete_reservation
from parser import parse_reservation
from calendar_service import create_event

load_dotenv()

app = Flask(__name__)

configuration = Configuration(
    access_token=os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")
)
handler = WebhookHandler(os.getenv("LINE_CHANNEL_SECRET", ""))

# 初始化資料庫
init_db()

HELP_TEXT = """📋 預約機器人使用說明

【預約格式】
  預約 姓名 日期 時間 人數 服務

  範例：
  • 預約 王小明 2026/4/5 14:00 3人 剪髮
  • 預約 李大華 明天 下午2點 2位 染髮
  • 預約 張三 4/10 10:30 1人 護髮

【查詢預約】
  輸入「查詢預約」或「我的預約」

【取消預約】
  輸入「取消預約 編號」
  例如：取消預約 1

【支援的日期格式】
  2026/4/5、4/5、今天、明天、後天

【支援的時間格式】
  14:00、下午2點、上午10點半

【支援的服務關鍵字】
  剪髮、染髮、護髮、燙髮、按摩、美甲、
  美睫、SPA、諮詢、看診 等

輸入「幫助」可再次查看此說明"""


@app.route("/health")
def health():
    return "OK"


@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers.get("X-Line-Signature", "")
    body = request.get_data(as_text=True)

    logger.info("=== Webhook received ===")
    logger.info(f"Signature: {signature[:20]}..." if signature else "Signature: EMPTY")
    logger.info(f"Body: {body[:200]}")
    logger.info(f"SECRET set: {bool(os.getenv('LINE_CHANNEL_SECRET'))}")
    logger.info(f"TOKEN set: {bool(os.getenv('LINE_CHANNEL_ACCESS_TOKEN'))}")

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        logger.error("Invalid signature!")
        abort(400)
    except Exception as e:
        logger.error(f"Error: {e}")
        abort(500)

    return "OK"


@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    text = event.message.text.strip()
    user_id = event.source.user_id
    reply = process_message(text, user_id)

    with ApiClient(configuration) as api_client:
        api = MessagingApi(api_client)
        api.reply_message(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[TextMessage(text=reply)],
            )
        )


def process_message(text, user_id):
    """根據使用者輸入產生回覆"""

    # 幫助
    if text in ("幫助", "help", "說明", "使用說明", "指令"):
        return HELP_TEXT

    # 查詢預約
    if text in ("查詢預約", "我的預約", "預約查詢", "查詢"):
        rows = get_user_reservations(user_id)
        if not rows:
            return "目前沒有任何預約紀錄。"
        lines = ["📅 您的預約紀錄：\n"]
        for r in rows:
            lines.append(
                f"  #{r['id']} {r['date']} {r['time']}\n"
                f"    姓名：{r['name']}｜{r['people']}人\n"
                f"    服務：{r['service']}\n"
            )
        return "\n".join(lines)

    # 取消預約
    if text.startswith("取消預約"):
        parts = text.replace("取消預約", "").strip().split()
        if not parts or not parts[0].isdigit():
            return "請輸入要取消的預約編號，例如：取消預約 1"
        rid = int(parts[0])
        if delete_reservation(rid, user_id):
            return f"✅ 已取消預約 #{rid}"
        return f"❌ 找不到編號 #{rid} 的預約，或該預約不屬於您。"

    # 預約
    if any(kw in text for kw in ("預約", "訂位", "預定")):
        result, errors = parse_reservation(text)
        if errors:
            missing = "、".join(errors)
            return (
                f"⚠️ 無法辨識以下資訊：{missing}\n\n"
                "請使用以下格式：\n"
                "預約 姓名 日期 時間 人數 服務\n\n"
                "範例：預約 王小明 2026/4/5 14:00 3人 剪髮"
            )

        # 存入資料庫
        rid = add_reservation(
            user_id,
            result["name"],
            result["date"],
            result["time"],
            result["people"],
            result["service"],
        )

        # 嘗試加入 Google Calendar
        calendar_link = None
        try:
            calendar_link = create_event(
                result["name"],
                result["date"],
                result["time"],
                result["people"],
                result["service"],
            )
        except Exception:
            pass

        reply = (
            f"✅ 預約成功！（編號 #{rid}）\n\n"
            f"  姓名：{result['name']}\n"
            f"  日期：{result['date']}\n"
            f"  時間：{result['time']}\n"
            f"  人數：{result['people']} 人\n"
            f"  服務：{result['service']}"
        )

        if calendar_link:
            reply += f"\n\n📅 已加入 Google 日曆：\n{calendar_link}"

        reply += "\n\n輸入「查詢預約」查看所有預約\n輸入「取消預約 編號」取消預約"
        return reply

    # 預設回覆
    return (
        "您好！我是預約機器人 🤖\n\n"
        "請輸入「預約」開始預約，或輸入「幫助」查看使用說明。"
    )


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
