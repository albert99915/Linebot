"""解析使用者訊息中的預約資訊：姓名、日期、時間、人數、服務內容"""

import re
from datetime import datetime, timedelta


def parse_reservation(text):
    """
    從文字訊息解析預約資訊。

    支援格式範例：
      「預約 王小明 2026/4/5 14:00 3人 剪髮」
      「我要預約 李大華 明天 下午2點 2位 染髮」
      「預約 張三 4/10 10:30 1人 護髮」

    回傳 dict 或 None（解析失敗時）
    """
    result = {}
    errors = []

    # — 姓名 —
    name_match = re.search(
        r"(?:預約|訂位|預定)\s*[：:]?\s*([^\d\s]{2,5})", text
    )
    if name_match:
        result["name"] = name_match.group(1)
    else:
        errors.append("姓名")

    # — 日期 —
    today = datetime.now()
    date_val = None

    # 完整日期 2026/4/5 or 2026-4-5
    full_date = re.search(r"(\d{4})[/\-.](\d{1,2})[/\-.](\d{1,2})", text)
    # 短日期 4/5 or 4-5
    short_date = re.search(r"(?<!\d)(\d{1,2})[/\-.](\d{1,2})(?!\d)", text)

    if full_date:
        try:
            date_val = datetime(
                int(full_date.group(1)),
                int(full_date.group(2)),
                int(full_date.group(3)),
            )
        except ValueError:
            errors.append("日期")
    elif short_date:
        try:
            month = int(short_date.group(1))
            day = int(short_date.group(2))
            date_val = datetime(today.year, month, day)
            if date_val < today:
                date_val = datetime(today.year + 1, month, day)
        except ValueError:
            errors.append("日期")
    elif "明天" in text:
        date_val = today + timedelta(days=1)
    elif "後天" in text:
        date_val = today + timedelta(days=2)
    elif "大後天" in text:
        date_val = today + timedelta(days=3)
    elif "今天" in text:
        date_val = today
    else:
        errors.append("日期")

    if date_val:
        result["date"] = date_val.strftime("%Y-%m-%d")

    # — 時間 —
    time_val = None

    # 14:00 or 14:30
    time_match = re.search(r"(\d{1,2}):(\d{2})", text)
    # 下午2點 / 上午10點 / 早上9點半
    cn_time = re.search(
        r"(上午|早上|下午|晚上|中午)?\s*(\d{1,2})\s*[點時](?:\s*(\d{1,2})\s*分|半)?",
        text,
    )

    if time_match:
        h, m = int(time_match.group(1)), int(time_match.group(2))
        if 0 <= h <= 23 and 0 <= m <= 59:
            time_val = f"{h:02d}:{m:02d}"
        else:
            errors.append("時間")
    elif cn_time:
        period = cn_time.group(1) or ""
        h = int(cn_time.group(2))
        m_str = cn_time.group(3)
        m = int(m_str) if m_str else 0
        if "半" in text[cn_time.start() : cn_time.end() + 2]:
            m = 30
        if period in ("下午", "晚上") and h < 12:
            h += 12
        elif period in ("上午", "早上") and h == 12:
            h = 0
        elif period == "中午":
            h = 12
        if 0 <= h <= 23 and 0 <= m <= 59:
            time_val = f"{h:02d}:{m:02d}"
        else:
            errors.append("時間")
    else:
        errors.append("時間")

    if time_val:
        result["time"] = time_val

    # — 人數 —
    people_match = re.search(r"(\d{1,3})\s*[人位個名]", text)
    if people_match:
        result["people"] = int(people_match.group(1))
    else:
        errors.append("人數")

    # — 服務內容 —
    service_match = re.search(
        r"(\d+\s*[人位個名])\s+(.+?)$", text.strip()
    )
    if service_match:
        result["service"] = service_match.group(2).strip()
    else:
        # 嘗試抓最後一個詞
        keywords = ["剪髮", "染髮", "護髮", "燙髮", "洗髮", "按摩", "美甲",
                     "美睫", "SPA", "諮詢", "看診", "檢查", "保養", "造型",
                     "指定服務", "全套", "基礎", "進階"]
        for kw in keywords:
            if kw in text:
                result["service"] = kw
                break
        if "service" not in result:
            errors.append("服務內容")

    if errors:
        return None, errors

    return result, []
