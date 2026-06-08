from flask import Flask, request, abort
import re
import os     
import json   
import time
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime

# LINE SDK v3 Elements
from linebot.v3.webhook import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.webhooks import (
    MessageEvent,
    TextMessageContent
)
from linebot.v3.messaging import (
    Configuration,
    ApiClient,
    MessagingApi,
    PushMessageRequest,
    ReplyMessageRequest,
    TextMessage
)

# Background Task Scheduler + Timezone Support
from apscheduler.schedulers.background import BackgroundScheduler
from pytz import timezone

# ==========================================
# CONFIG
# ==========================================

CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "cve00KYaRV/u02SyxIOyO1tTSTBxyderSe2Asq7UkO9jVYjrstPVfjtZKsoMbZ7PU3trkWUYhufZpN9f8ah8+pT/d420hnuIdr2ywgXokYlaKyht5VgvQuOZ0OognvlocC42kg096CjOylcqCeIjiAdB04t89/1O/w1cDnyilFU=")
CHANNEL_SECRET = os.environ.get("LINE_CHANNEL_SECRET", "c900eed30a1caff2ce1e1350fcb5da96")
TARGET_CHAT_ID = "C4537b26bab93b8b27236efbf6963d27a"

DEPARTMENT_MAPPING = {
    "อารยา": "กราฟฟิก", "ญาดา": "กราฟฟิก", "สุรยุทธ์": "กราฟฟิก",
    "ชญาดา": "การตลาด", "ธนภัทร": "การตลาด", "พัลลภา": "การตลาด",    
    "ศุกภรัตน์": "ไอที", "วราภรณ์": "ไอที", "ธนกร": "ไอที", "อัฑฒ์นิรุช": "ไอที", "อภิวัฒน์": "ไอที"
}

DEPT_ICONS = {
    "กราฟฟิก": "🎬 กราฟฟิก",
    "การตลาด": "📈 การตลาด",
    "ไอที": "💻 ไอที",
    "อื่น ๆ": "❓ อื่นๆ/ไม่ระบุแผนก"
}

SPREADSHEET_NAME = "LINE Office Log"
WORKSHEET_NAME = "งานประจำวัน"

app = Flask(__name__)
handler = WebhookHandler(CHANNEL_SECRET)
configuration = Configuration(access_token=CHANNEL_ACCESS_TOKEN)

# ==========================================
# GOOGLE SHEET CONNECTION MANAGEMENT
# ==========================================

scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]

def get_google_sheet():
    """ ฟังก์ชันดึงเซสชันใหม่เพื่อป้องกันปัญหา Token Expired """
    try:
        google_creds_json = os.environ.get("GOOGLE_CREDENTIALS_JSON")
        if google_creds_json:
            creds_dict = json.loads(google_creds_json)
            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        else:
            GOOGLE_JSON_PATH = r"C:\Users\Graphic Head\Desktop\proj\annular-fold-420003-6b9d58cd215a.json"
            if os.path.exists(GOOGLE_JSON_PATH):
                creds = ServiceAccountCredentials.from_json_keyfile_name(GOOGLE_JSON_PATH, scope)
            else:
                return None
        
        client = gspread.authorize(creds)
        spreadsheet = client.open(SPREADSHEET_NAME)
        return spreadsheet.worksheet(WORKSHEET_NAME)
    except Exception as e:
        print(f"❌ Google Sheet Connection Error: {e}")
        return None

# ==========================================
# FUNCTIONS: Reminders & Summary
# ==========================================

def send_morning_reminder():
    if not TARGET_CHAT_ID: return
    try:
        with ApiClient(configuration) as api_client:
            MessagingApi(api_client).push_message(PushMessageRequest(
                to=TARGET_CHAT_ID, messages=[TextMessage(text="อย่าลืมส่งแผนงานประจำวันกันนะค๊าบ 📅")]
            ))
    except Exception as e: print(f"❌ Morning Reminder Error: {e}")

def send_evening_reminder():
    if not TARGET_CHAT_ID: return
    try:
        with ApiClient(configuration) as api_client:
            MessagingApi(api_client).push_message(PushMessageRequest(
                to=TARGET_CHAT_ID, messages=[TextMessage(text="ใกล้ถึงเวลาสรุปงานแล้ว ใครยังไม่ได้บันทึก รีบพิมพ์ส่งน้า ⏰")]
            ))
    except Exception as e: print(f"❌ Evening Reminder Error: {e}")

def send_daily_summary():
    sheet_instance = get_google_sheet()
    if not TARGET_CHAT_ID or sheet_instance is None: return
    try:
        all_records = sheet_instance.get_all_records()
        now = datetime.now(timezone('Asia/Bangkok'))
        today_str = f"{now.day}/{now.month}/{str(now.year + 543)[-2:]}"
        
        dept_tasks = {"กราฟฟิก": {}, "การตลาด": {}, "ไอที": {}, "อื่น ๆ": {}}
        has_data = False

        for row in all_records:
            if str(row.get("วันที่", "")).strip() == today_str:
                name, task = str(row.get("ชื่อ", "")).strip(), str(row.get("งาน", "")).strip()
                if name and task:
                    has_data = True
                    dept = next((v for k, v in DEPARTMENT_MAPPING.items() if k == name), "อื่น ๆ")
                    if name not in dept_tasks[dept]: dept_tasks[dept][name] = []
                    dept_tasks[dept][name].append(task)

        summary_text = f"สรุปงานวันที่ {today_str}\n"
        if not has_data:
            summary_text += "\nวันนี้ยังไม่มีการบันทึกงานครับ"
        else:
            for d_name in ["กราฟฟิก", "การตลาด", "ไอที", "อื่น ๆ"]:
                if dept_tasks[d_name]:
                    summary_text += f"\n{DEPT_ICONS[d_name]}\n"
                    for name, tasks in dept_tasks[d_name].items():
                        summary_text += f"{name}\n" + "\n".join([f"- {t}" for t in tasks]) + "\n"

        with ApiClient(configuration) as api_client:
            MessagingApi(api_client).push_message(PushMessageRequest(to=TARGET_CHAT_ID, messages=[TextMessage(text=summary_text.strip())]))
    except Exception as e: print(f"❌ Summary Error: {e}")

# ==========================================
# SCHEDULER & WEBHOOK
# ==========================================

tz = timezone('Asia/Bangkok')
scheduler = BackgroundScheduler(daemon=True, timezone=tz)
scheduler.add_job(send_morning_reminder, 'cron', hour=8, minute=10)
scheduler.add_job(send_evening_reminder, 'cron', hour=16, minute=50)
scheduler.add_job(send_daily_summary, 'cron', hour=17, minute=0)
scheduler.start()

@app.route("/callback", methods=["POST"])
def callback():
    body = request.get_data(as_text=True)
    signature = request.headers.get("X-Line-Signature", "")
    try: handler.handle(body, signature)
    except InvalidSignatureError: abort(400)
    return "OK"

# ==========================================
# MESSAGE HANDLER
# ==========================================

@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    global TARGET_CHAT_ID
    msg = event.message.text.strip()

    # 🌟 ฟังก์ชันคำสั่งพิเศษ 1: เช็คไอดีห้อง
    if msg == "เช็คไอดีห้อง":
        cid = getattr(event.source, 'group_id', getattr(event.source, 'room_id', "N/A"))
        with ApiClient(configuration) as api_client:
            MessagingApi(api_client).reply_message(ReplyMessageRequest(reply_token=event.reply_token, messages=[TextMessage(text=f"🆔 ไอดีห้อง: {cid}")]))
        return

    # 🌟 ฟังก์ชันคำสั่งพิเศษ 2: วิธีเข้าแนส / วิธีเข้า nas / ขอแนส
    if msg.lower() in ["วิธีเข้าแนส", "วิธีเข้า nas", "ขอแนส"]:
        nas_reply = (
            "📁 วิธีการเข้าใช้งาน NAS ประจำออฟฟิศ\n\n"
            "🌐 เข้าใช้งานผ่านลิงก์เว็บอินเทอร์เน็ต:\n"
            "เข้าผ่าน https://quickconnect.to/dataft\n"
            "👤 User: graphic\n"
            "🔑 Pass: 0XEWb9&f\n\n"
            "📶 หรือเข้าผ่านโครงข่าย Wi-Fi ออฟฟิศ:\n"
            "สร้าง shortcut บล็อกพาร์ท: \\\\data_ft\n"
            "👤 User: graphic\n"
            "🔑 Pass: 0XEWb9&f"
        )
        with ApiClient(configuration) as api_client:
            MessagingApi(api_client).reply_message(ReplyMessageRequest(reply_token=event.reply_token, messages=[TextMessage(text=nas_reply)]))
        return

    # 🌟 ฟังก์ชันคำสั่งพิเศษ 3: ขอ wifi
    if msg.lower() == "ขอwifi":
        wifi_reply = (
            "📶 ข้อมูล Wi-Fi ออฟฟิศ\n\n"
            "📛 ชื่อ Wi-Fi: FT_IT\n"
            "🔑 รหัสผ่าน: 88888888"
        )
        with ApiClient(configuration) as api_client:
            MessagingApi(api_client).reply_message(ReplyMessageRequest(reply_token=event.reply_token, messages=[TextMessage(text=wifi_reply)]))
        return

    # 🌟 ฟังก์ชันคำสั่งพิเศษ 4: ขอ tiktok
    if msg.lower() == "ขอtiktok":
        tiktok_reply = (
            "🎬 ข้อมูลบัญชี TikTok ออฟฟิศ\n\n"
            "👤 User: info1@fountaintreeresort.com\n"
            "🔑 Pass: Farmmraf@2568"
        )
        with ApiClient(configuration) as api_client:
            MessagingApi(api_client).reply_message(ReplyMessageRequest(reply_token=event.reply_token, messages=[TextMessage(text=tiktok_reply)]))
        return

    # 🌟 ฟังก์ชันคำสั่งพิเศษ 5: เบอร์หัวหน้า (เพิ่มใหม่ตรงนี้เลยแก)
    if msg == "เบอร์หัวหน้า":
        boss_reply = "โทร 083-0002507 Email:forzatoshiki@gmail.com"
        with ApiClient(configuration) as api_client:
            MessagingApi(api_client).reply_message(ReplyMessageRequest(reply_token=event.reply_token, messages=[TextMessage(text=boss_reply)]))
        return

    # ระบบบันทึกงานปกติ
    lines = msg.splitlines()
    if not lines or not (lines[0].startswith("แผนงานวันที่") or lines[0].startswith("สรุปงานวันที่")): return

    date_match = re.search(r'(\d+/\d+/\d+)', lines[0])
    if not date_match: return
    work_date = date_match.group(1).strip()

    if hasattr(event.source, 'group_id'): TARGET_CHAT_ID = event.source.group_id

    sheet_instance = get_google_sheet()
    if not sheet_instance: return

    try:
        reply_dept = {"กราฟฟิก": [], "การตลาด": [], "ไอที": [], "อื่น ๆ": []}
        sheet_rows, current_name, unique_names = [], None, set()

        for line in lines[1:]:
            l = line.strip()
            if not l: continue
            if l.startswith("-"):
                if current_name:
                    task = l.replace("-", "", 1).strip()
                    sheet_rows.append([work_date, current_name, task])
                    dept = next((v for k, v in DEPARTMENT_MAPPING.items() if k == current_name), "อื่น ๆ")
                    reply_dept[dept].append(f"✔ {current_name} → {task}")
            else:
                current_name = l
                unique_names.add(current_name)

        if sheet_rows: sheet_instance.append_rows(sheet_rows)

        reply_text = f"✅ บันทึกแผนงานเรียบร้อย\n\n📅 แผนงานวันที่: {work_date}\n👤 จำนวนคน: {len(unique_names)} | 📝 จำนวนงาน: {len(sheet_rows)}\n"
        
        for d in ["กราฟฟิก", "การตลาด", "ไอที", "อื่น ๆ"]:
            if reply_dept[d]:
                reply_text += f"\n{DEPT_ICONS[d]}\n" + "\n".join(reply_dept[d]) + "\n"

        with ApiClient(configuration) as api_client:
            MessagingApi(api_client).reply_message(ReplyMessageRequest(reply_token=event.reply_token, messages=[TextMessage(text=reply_text.strip())]))
    except Exception as e: print(f"❌ Processing Error: {e}")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
