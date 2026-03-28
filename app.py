"""LINE 汗蒸預約機器人"""

import os
import logging
import urllib.parse
from datetime import datetime, timedelta

from flask import Flask, request, abort
from dotenv import load_dotenv

from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    Configuration,
    ApiClient,
    MessagingApi,
    ReplyMessageRequest,
    TextMessage,
    QuickReply,
    QuickReplyItem,
    PostbackAction,
    FlexMessage,
    FlexBubble,
    FlexBox,
    FlexText,
    FlexButton,
    FlexSeparator,
)
from linebot.v3.webhooks import MessageEvent, TextMessageContent, PostbackEvent

from db import (
    init_db,
    add_reservation,
    get_user_reservations,
    delete_reservation,
    get_available_hours,
    get_slot_capacity,
    get_max_capacity,
    set_max_capacity,
    get_all_reservations_by_date,
    cancel_reservation_admin,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

app = Flask(__name__)

configuration = Configuration(
    access_token=os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")
)
handler = WebhookHandler(os.getenv("LINE_CHANNEL_SECRET", ""))

ADMIN_USER_ID = os.getenv("ADMIN_USER_ID", "")

init_db()

HELP_TEXT = """📋 汗蒸預約使用說明

【預約】
  輸入「預約 您的姓名」開始預約
  範例：預約 王小明

  接著依照提示選擇：
  日期 → 時間 → 人數 → 確認

【查詢預約】
  輸入「查詢預約」或「我的預約」

【取消預約】
  輸入「取消預約 編號」
  例如：取消預約 1

輸入「幫助」可再次查看此說明"""

ADMIN_HELP_TEXT = """🔧 業主管理指令

【查詢預約】
  管理 查詢 → 查看今天預約
  管理 查詢 2026-04-01 → 查看指定日期

【取消預約】
  管理 取消 編號
  例如：管理 取消 5

【人數上限】
  管理 人數上限 → 查看目前上限
  管理 人數上限 8 → 設定為每時段 8 人

【管理說明】
  管理 說明"""


def reply(event, messages):
    """回覆訊息"""
    if isinstance(messages, str):
        messages = [TextMessage(text=messages)]
    elif not isinstance(messages, list):
        messages = [messages]
    with ApiClient(configuration) as api_client:
        api = MessagingApi(api_client)
        api.reply_message(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=messages,
            )
        )


# ─── Flask routes ───

@app.route("/health")
def health():
    return "OK"


@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers.get("X-Line-Signature", "")
    body = request.get_data(as_text=True)

    logger.info("=== Webhook received ===")

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        logger.error("Invalid signature!")
        abort(400)
    except Exception as e:
        logger.error(f"Error: {e}")
        abort(500)

    return "OK"


# ─── 預約流程：建立 QuickReply / Flex ───

def build_date_quick_reply(name):
    """產生未來 7 天的日期 QuickReply"""
    today = datetime.now()
    items = []
    weekday_names = ["一", "二", "三", "四", "五", "六", "日"]
    for i in range(7):
        d = today + timedelta(days=i)
        date_str = d.strftime("%Y-%m-%d")
        weekday = weekday_names[d.weekday()]
        if i == 0:
            label = f"今天 ({weekday})"
        elif i == 1:
            label = f"明天 ({weekday})"
        else:
            label = f"{d.month}/{d.day} ({weekday})"
        data = urllib.parse.urlencode({"action": "book", "step": "2", "name": name, "date": date_str})
        items.append(
            QuickReplyItem(action=PostbackAction(label=label, data=data, display_text=label))
        )
    return QuickReply(items=items)


def build_time_quick_reply(name, date, people=1):
    """產生可用時段的 QuickReply"""
    available = get_available_hours(date, people)
    if not available:
        return None
    items = []
    for time_str in available:
        hour = int(time_str.split(":")[0])
        label = f"{hour}:00"
        data = urllib.parse.urlencode({"action": "book", "step": "3", "name": name, "date": date, "time": time_str})
        items.append(
            QuickReplyItem(action=PostbackAction(label=label, data=data, display_text=label))
        )
    return QuickReply(items=items)


def build_people_quick_reply(name, date, time):
    """產生人數選擇的 QuickReply (1-6)"""
    max_cap = get_max_capacity()
    booked = get_slot_capacity(date, time)
    remaining = max_cap - booked
    max_people = min(remaining, 6)
    if max_people <= 0:
        return None
    items = []
    for p in range(1, max_people + 1):
        label = f"{p} 人"
        data = urllib.parse.urlencode({"action": "book", "step": "4", "name": name, "date": date, "time": time, "people": str(p)})
        items.append(
            QuickReplyItem(action=PostbackAction(label=label, data=data, display_text=label))
        )
    return QuickReply(items=items)


def build_confirmation_flex(name, date, time, people):
    """產生預約確認 FlexMessage"""
    confirm_data = urllib.parse.urlencode({"action": "confirm", "name": name, "date": date, "time": time, "people": str(people)})
    cancel_data = "action=cancel_flow"

    weekday_names = ["一", "二", "三", "四", "五", "六", "日"]
    dt = datetime.strptime(date, "%Y-%m-%d")
    weekday = weekday_names[dt.weekday()]
    hour = int(time.split(":")[0])

    bubble = FlexBubble(
        body=FlexBox(
            layout="vertical",
            contents=[
                FlexText(text="📋 預約確認", weight="bold", size="lg", color="#1a1a1a"),
                FlexSeparator(margin="md"),
                FlexBox(
                    layout="vertical",
                    margin="lg",
                    spacing="sm",
                    contents=[
                        FlexBox(layout="horizontal", contents=[
                            FlexText(text="姓名", size="sm", color="#888888", flex=2),
                            FlexText(text=name, size="sm", color="#333333", flex=5),
                        ]),
                        FlexBox(layout="horizontal", contents=[
                            FlexText(text="日期", size="sm", color="#888888", flex=2),
                            FlexText(text=f"{date} ({weekday})", size="sm", color="#333333", flex=5),
                        ]),
                        FlexBox(layout="horizontal", contents=[
                            FlexText(text="時間", size="sm", color="#888888", flex=2),
                            FlexText(text=f"{hour}:00", size="sm", color="#333333", flex=5),
                        ]),
                        FlexBox(layout="horizontal", contents=[
                            FlexText(text="人數", size="sm", color="#888888", flex=2),
                            FlexText(text=f"{people} 人", size="sm", color="#333333", flex=5),
                        ]),
                        FlexBox(layout="horizontal", contents=[
                            FlexText(text="服務", size="sm", color="#888888", flex=2),
                            FlexText(text="汗蒸", size="sm", color="#333333", flex=5),
                        ]),
                    ],
                ),
            ],
        ),
        footer=FlexBox(
            layout="horizontal",
            spacing="md",
            contents=[
                FlexButton(
                    style="primary",
                    color="#06C755",
                    action=PostbackAction(label="確認預約", data=confirm_data, display_text="確認預約"),
                ),
                FlexButton(
                    style="secondary",
                    action=PostbackAction(label="取消", data=cancel_data, display_text="取消預約"),
                ),
            ],
        ),
    )
    return FlexMessage(alt_text="預約確認", contents=bubble)


# ─── 訊息處理 ───

@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    text = event.message.text.strip()
    user_id = event.source.user_id

    logger.info(f"User ID: {user_id} | Message: {text}")

    # 業主管理指令
    if text.startswith("管理") and user_id == ADMIN_USER_ID:
        reply(event, process_admin(text))
        return

    # 一般使用者
    result = process_message(text, user_id)
    if isinstance(result, list):
        reply(event, result)
    else:
        reply(event, result)


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

    # 預約（格式：預約 姓名）
    for kw in ("預約", "訂位", "預定"):
        if kw in text:
            name = text.replace(kw, "").strip()
            if not name or len(name) < 1:
                return f"請輸入姓名，例如：預約 王小明"
            if len(name) > 10:
                return "姓名請勿超過 10 個字。"
            # 回覆日期選擇
            quick_reply = build_date_quick_reply(name)
            return [TextMessage(text=f"👋 {name} 您好！請選擇預約日期：", quick_reply=quick_reply)]

    # 預設回覆
    return "您好！我是汗蒸預約機器人 🧖\n\n請輸入「預約 您的姓名」開始預約\n或輸入「幫助」查看使用說明。"


# ─── Postback 處理（預約流程） ───

@handler.add(PostbackEvent)
def handle_postback(event):
    data = event.postback.data
    params = dict(urllib.parse.parse_qsl(data))
    action = params.get("action", "")

    if action == "book":
        handle_booking_step(event, params)
    elif action == "confirm":
        handle_confirm(event, params)
    elif action == "cancel_flow":
        reply(event, "已取消預約流程。")


def handle_booking_step(event, params):
    step = params.get("step", "")
    name = params.get("name", "")
    date = params.get("date", "")
    time = params.get("time", "")

    if step == "2":
        # 選完日期 → 顯示時間
        quick_reply = build_time_quick_reply(name, date)
        if not quick_reply:
            reply(event, f"😢 {date} 已經全部額滿了，請選擇其他日期。")
            return
        reply(event, [TextMessage(text=f"📅 {date}\n請選擇時間：", quick_reply=quick_reply)])

    elif step == "3":
        # 選完時間 → 顯示人數
        quick_reply = build_people_quick_reply(name, date, time)
        if not quick_reply:
            reply(event, f"😢 {date} {time} 已經額滿了，請選擇其他時段。")
            return
        hour = int(time.split(":")[0])
        reply(event, [TextMessage(text=f"📅 {date} {hour}:00\n請選擇人數：", quick_reply=quick_reply)])

    elif step == "4":
        # 選完人數 → 顯示確認
        people = int(params.get("people", "1"))
        # 檢查容量
        max_cap = get_max_capacity()
        booked = get_slot_capacity(date, time)
        remaining = max_cap - booked
        if people > remaining:
            reply(event, f"😢 該時段剩餘名額 {remaining} 人，無法預約 {people} 人。\n請重新輸入「預約 您的姓名」選擇其他時段。")
            return
        flex = build_confirmation_flex(name, date, time, people)
        reply(event, [flex])


def handle_confirm(event, params):
    name = params.get("name", "")
    date = params.get("date", "")
    time = params.get("time", "")
    people = int(params.get("people", "1"))
    user_id = event.source.user_id

    # 最終容量檢查
    max_cap = get_max_capacity()
    booked = get_slot_capacity(date, time)
    remaining = max_cap - booked
    if people > remaining:
        reply(event, f"😢 很抱歉，該時段名額已被其他人預約。\n剩餘名額：{remaining} 人\n\n請重新輸入「預約 您的姓名」選擇其他時段。")
        return

    rid = add_reservation(user_id, name, date, time, people)
    hour = int(time.split(":")[0])
    reply(event, (
        f"✅ 預約成功！（編號 #{rid}）\n\n"
        f"  姓名：{name}\n"
        f"  日期：{date}\n"
        f"  時間：{hour}:00\n"
        f"  人數：{people} 人\n"
        f"  服務：汗蒸\n\n"
        f"輸入「查詢預約」查看所有預約\n"
        f"輸入「取消預約 {rid}」取消此預約"
    ))


# ─── 業主管理 ───

def process_admin(text):
    parts = text.replace("管理", "").strip().split()
    if not parts:
        return ADMIN_HELP_TEXT

    cmd = parts[0]

    # 管理 說明
    if cmd in ("說明", "幫助", "help"):
        return ADMIN_HELP_TEXT

    # 管理 查詢 [日期]
    if cmd in ("查詢", "查看"):
        if len(parts) > 1:
            date = parts[1]
        else:
            date = datetime.now().strftime("%Y-%m-%d")
        rows = get_all_reservations_by_date(date)
        if not rows:
            return f"📅 {date} 沒有預約紀錄。"
        max_cap = get_max_capacity()
        lines = [f"📅 {date} 的預約紀錄：\n"]
        # 按時段統計
        time_slots = {}
        for r in rows:
            t = r["time"]
            if t not in time_slots:
                time_slots[t] = []
            time_slots[t].append(r)
        for t in sorted(time_slots.keys()):
            slot_people = sum(r["people"] for r in time_slots[t])
            lines.append(f"⏰ {t}（{slot_people}/{max_cap} 人）")
            for r in time_slots[t]:
                lines.append(f"  #{r['id']} {r['name']} {r['people']}人")
            lines.append("")
        return "\n".join(lines)

    # 管理 取消 編號
    if cmd == "取消":
        if len(parts) < 2 or not parts[1].lstrip("#").isdigit():
            return "請輸入要取消的預約編號，例如：管理 取消 5"
        rid = int(parts[1].lstrip("#"))
        if cancel_reservation_admin(rid):
            return f"✅ 已取消預約 #{rid}"
        return f"❌ 找不到編號 #{rid} 的有效預約。"

    # 管理 人數上限 [數字]
    if cmd == "人數上限":
        if len(parts) < 2:
            current = get_max_capacity()
            return f"目前每時段人數上限為 {current} 人。\n\n設定方式：管理 人數上限 8"
        if not parts[1].isdigit() or int(parts[1]) < 1:
            return "請輸入有效數字，例如：管理 人數上限 8"
        new_cap = int(parts[1])
        set_max_capacity(new_cap)
        return f"✅ 已將每時段人數上限設為 {new_cap} 人。"

    return ADMIN_HELP_TEXT


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
