from flask import Flask, request, abort
import re
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

# Background Task Scheduler
from apscheduler.schedulers.background import BackgroundScheduler

# ==========================================
# CONFIG
# ==========================================

CHANNEL_ACCESS_TOKEN = "cve00KYaRV/u02SyxIOyO1tTSTBxyderSe2Asq7UkO9jVYjrstPVfjtZKsoMbZ7PU3trkWUYhufZpN9f8ah8+pT/d420hnuIdr2ywgXokYlaKyht5VgvQuOZ0OognvlocC42kg096CjOylcqCeIjiAdB04t89/1O/w1cDnyilFU="
CHANNEL_SECRET = "c900eed30a1caff2ce1e1350fcb5da96"

TARGET_CHAT_ID = None 

# 💡 บัญชีรายชื่อพนักงานและแผนกหลัก
DEPARTMENT_MAPPING = {
    "อารยา": "กราฟฟิก",
    "ญาดา": "กราฟฟิก",
    "เพชรลดา": "กราฟฟิก",

    "ชญาดา": "การตลาด",
    "ธนภัทร": "การตลาด",
    
    "ศุกภรัตน์": "ไอที",
    "วราภรณ์": "ไอที",
    "ธนกร": "ไอที",
    "อัฑฒ์นิรุช": "ไอที",
    "อภิวัฒน์": "ไอที"
}

DEPT_ICONS = {
    "กราฟฟิก": "🎬 กราฟฟิก",
    "การตลาด": "📈 การตลาด",
    "ไอที": "💻 ไอที",
    "อื่น ๆ": "❓ อื่นๆ/ไม่ระบุแผนก"
}

GOOGLE_JSON = r"C:\Users\Graphic Head\Desktop\proj\annular-fold-420003-6b9d58cd215a.json"
SPREADSHEET_NAME = "LINE Office Log"
WORKSHEET_NAME = "งานประจำวัน"

app = Flask(__name__)
handler = WebhookHandler(CHANNEL_SECRET)
configuration = Configuration(access_token=CHANNEL_ACCESS_TOKEN)

# ==========================================
# GOOGLE SHEET CONNECT
# ==========================================

scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
try:
    creds = ServiceAccountCredentials.from_json_keyfile_name(GOOGLE_JSON, scope)
    client = gspread.authorize(creds)
    spreadsheet = client.open(SPREADSHEET_NAME)
    sheet = spreadsheet.worksheet(WORKSHEET_NAME)
    print("GOOGLE SHEET CONNECTED ✔")
except Exception as e:
    print("GOOGLE SHEET ERROR ❌\n", e)
    input("Press Enter to Exit...")
    exit()

# ==========================================
# FUNCTION: ระบบแจ้งเตือนอัตโนมัติ (Reminders)
# ==========================================

# 1. เตือนรอบเช้า 08:10 น. (ทุกวัน)
def send_morning_reminder():
    print("⏰ เริ่มทำงาน: แจ้งเตือนส่งแผนงานรอบเช้า")
    if TARGET_CHAT_ID is None:
        print("❌ ยังไม่มี Target Chat ID (ต้องรอให้มีคนพิมพ์ในกลุ่มก่อนอย่างน้อย 1 ครั้ง)")
        return
    try:
        with ApiClient(configuration) as api_client:
            line_bot_api = MessagingApi(api_client)
            push_message_request = PushMessageRequest(
                to=TARGET_CHAT_ID,
                messages=[TextMessage(text="อย่าลืมส่งแผนงานประจำวันกันนะค๊าบ 📅")]
            )
            line_bot_api.push_message(push_message_request)
            print("🔊 ส่งข้อความเตือนรอบเช้าสำเร็จ!")
    except Exception as e:
        print(f"❌ เตือนรอบเช้าผิดพลาด: {e}")

# 2. เตือนรอบเย็น 16:50 น. (ทุกวัน)
def send_evening_reminder():
    print("⏰ เริ่มทำงาน: แจ้งเตือนส่งสรุปงานรอบเย็น")
    if TARGET_CHAT_ID is None:
        print("❌ ยังไม่มี Target Chat ID")
        return
    try:
        with ApiClient(configuration) as api_client:
            line_bot_api = MessagingApi(api_client)
            push_message_request = PushMessageRequest(
                to=TARGET_CHAT_ID,
                messages=[TextMessage(text="ใกล้ถึงเวลาสรุปงานแล้ว ใครยังไม่ได้บันทึก รีบพิมพ์ส่งน้า ⏰")]
            )
            line_bot_api.push_message(push_message_request)
            print("🔊 ส่งข้อความเตือนรอบเย็นสำเร็จ!")
    except Exception as e:
        print(f"❌ เตือนรอบเย็นผิดพลาด: {e}")

# ==========================================
# FUNCTION: ดึงข้อมูลสรุปแยกแผนกตอน 17:00 น.
# ==========================================

def send_daily_summary():
    print("⏰ เริ่มทำงาน: ฟังก์ชันส่งสรุปประจำวันอัตโนมัติ")
    if TARGET_CHAT_ID is None:
        return
        
    try:
        all_records = sheet.get_all_records()
        if not all_records:
            return

        now = datetime.now()
        thai_year_short = str(now.year + 543)[-2:] 
        today_str = f"{now.day}/{now.month}/{thai_year_short}"
        
        department_tasks = {"กราฟฟิก": {}, "การตลาด": {}, "ไอที": {}, "อื่น ๆ": {}}
        has_data = False

        for row in all_records:
            sheet_date = str(row.get("วันที่", "")).strip()
            try:
                d_parts = sheet_date.split('/')
                if len(d_parts) == 3:
                    formatted_sheet_date = f"{int(d_parts[0])}/{int(d_parts[1])}/{d_parts[2][-2:]}"
                else:
                    formatted_sheet_date = sheet_date
            except:
                formatted_sheet_date = sheet_date

            if formatted_sheet_date == today_str:
                name = str(row.get("ชื่อ", "")).strip()
                task = str(row.get("งาน", "")).strip()
                
                if name and task:
                    has_data = True
                    dept = "อื่น ๆ"
                    for k, v in DEPARTMENT_MAPPING.items():
                        if k in name or name in k:
                            dept = v
                            break
                    
                    if name not in department_tasks[dept]:
                        department_tasks[dept][name] = []
                    department_tasks[dept][name].append(task)

        if not has_data:
            summary_text = f"สรุปงานวันที่ {today_str}\n\nวันนี้ยังไม่มีการบันทึกงานในระบบครับ"
        else:
            summary_text = f"สรุปงานวันที่ {today_str}\n"
            for dept_name in ["กราฟฟิก", "การตลาด", "ไอที", "อื่น ๆ"]:
                users = department_tasks[dept_name]
                if users:
                    summary_text += f"\n{DEPT_ICONS[dept_name]}\n"
                    for name, tasks in users.items():
                        summary_text += f"{name}\n"
                        for task in tasks:
                            summary_text += f"- {task}\n"
            summary_text = summary_text.strip()

        with ApiClient(configuration) as api_client:
            line_bot_api = MessagingApi(api_client)
            push_message_request = PushMessageRequest(to=TARGET_CHAT_ID, messages=[TextMessage(text=summary_text)])
            line_bot_api.push_message(push_message_request)
            print("🚀 ส่งสรุปแผนงานประจำวันสำเร็จ!")
    except Exception as e:
        print(f"❌ สรุปผิดพลาด: {e}")

# ==========================================
# SET UP SCHEDULER (ตั้งเวลาทำงาน "ทุกวัน")
# ==========================================

scheduler = BackgroundScheduler(daemon=True)

scheduler.add_job(send_morning_reminder, 'cron', hour=8, minute=10)
scheduler.add_job(send_evening_reminder, 'cron', hour=16, minute=50)
scheduler.add_job(send_daily_summary, 'cron', hour=17, minute=0)

scheduler.start()

# ==========================================
# WEBHOOK RECEIVER
# ==========================================

@app.route("/callback", methods=["POST"])
def callback():
    body = request.get_data(as_text=True)
    signature = request.headers.get("X-Line-Signature", "")
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return "OK"

# ==========================================
# HANDLE MESSAGE & PARSER (จัดกลุ่มแยกแผนกจบในบล็อกเดียว)
# ==========================================

@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    global TARGET_CHAT_ID 
    msg = event.message.text.strip()
    lines = msg.splitlines()

    if not lines:
        return

    if not (lines[0].startswith("แผนงานวันที่") or lines[0].startswith("สรุปงานวันที่")):
        return

    date_match = re.search(r'(\d+/\d+/\d+)', lines[0])
    if not date_match:
        return
    work_date = date_match.group(1).strip()

    if hasattr(event.source, 'group_id'):
        TARGET_CHAT_ID = event.source.group_id
    elif hasattr(event.source, 'user_id'):
        TARGET_CHAT_ID = event.source.user_id

    try:
        reply_dept = {"กราฟฟิก": [], "การตลาด": [], "ไอที": [], "อื่น ๆ": []}
        sheet_rows = []
        
        current_name = None
        unique_names = set()

        for line in lines[1:]:
            line_str = line.strip()
            if not line_str:
                continue

            if line_str.startswith("-"):
                if current_name:
                    task_text = line_str.replace("-", "", 1).strip()
                    sheet_rows.append([work_date, current_name, task_text])
                    
                    assigned_dept = "อื่น ๆ"
                    for emp_name, dept_name in DEPARTMENT_MAPPING.items():
                        if emp_name in current_name or current_name in emp_name:
                            assigned_dept = dept_name
                            break
                    
                    reply_dept[assigned_dept].append(f"✔ {current_name} → {task_text}")
            else:
                current_name = line_str
                unique_names.add(current_name)

        if sheet_rows:
            sheet.append_rows(sheet_rows)

        reply_text = "✅ บันทึกแผนงานเรียบร้อย\n\n"
        reply_text += f"📅 วันที่: {work_date}\n"
        reply_text += f"👤 จำนวนคน: {len(unique_names)} | 📝 จำนวนงาน: {len(sheet_rows)}\n"
        
        for dept_type in ["กราฟฟิก", "การตลาด", "ไอที", "อื่น ๆ"]:
            tasks_list = reply_dept[dept_type]
            if tasks_list:
                reply_text += f"\n{DEPT_ICONS[dept_type]}\n"
                for task_item in tasks_list:
                    reply_text += f"{task_item}\n"

        reply_text = reply_text.strip()

        with ApiClient(configuration) as api_client:
            line_bot_api = MessagingApi(api_client)
            line_bot_api.reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[TextMessage(text=reply_text)]
                )
            )
        print("🔊 บันทึกและส่งรายงานตอบกลับแยกแผนกสำเร็จ!")

    except Exception as e:
        print("SYSTEM ERROR ❌\n", e)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)