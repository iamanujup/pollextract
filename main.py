import os
import re
import asyncio
from collections import defaultdict
from dotenv import load_dotenv

from pyrogram import Client, filters
from pyrogram.types import Poll
from pyrogram.errors import FloodWait

load_dotenv()

API_ID = int(os.getenv("API_ID", "5074166"))
API_HASH = os.getenv("API_HASH", "3cb93a9a9345592f5e6a42020687cdbe")
BOT_TOKEN = os.getenv("BOT_TOKEN", "8809092646:AAEPX9hfULZ07jm8p10HxquHLKo7m22XuJw")
QUESTION_TIME = int(os.getenv("QUESTION_TIME", "20"))

if not API_ID or not API_HASH or not BOT_TOKEN:
    print("ERROR: .env me API_ID, API_HASH, BOT_TOKEN set karo.")
    raise SystemExit(1)

app = Client(
    "quiz_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

# chat_id wise data
QUIZ = {}

# Format:
# Q. भारत की राजधानी क्या है?
# A) मुंबई
# B) दिल्ली
# C) कोलकाता
# D) चेन्नई
# Ans: B
# Ex: भारत की राजधानी नई दिल्ली है।
def parse_questions(text: str):
    blocks = re.split(r"\n\s*\n", text.strip())
    questions = []

    for block in blocks:
        lines = [x.strip() for x in block.splitlines() if x.strip()]
        if len(lines) < 6:
            continue

        q_line = lines[0]
        q_line = re.sub(r"^(Q\.?|प्रश्न\.?)\s*", "", q_line, flags=re.I).strip()

        options = []
        ans_letter = None
        explanation = ""

        for line in lines[1:]:
            m = re.match(r"^([A-Da-d])[\)\.\-]\s*(.+)$", line)
            if m:
                options.append(m.group(2).strip())
                continue

            m = re.match(r"^(Ans|Answer|उत्तर)\s*[:\-]\s*([A-Da-d])", line, flags=re.I)
            if m:
                ans_letter = m.group(2).upper()
                continue

            m = re.match(r"^(Ex|Exp|Explanation|व्याख्या)\s*[:\-]\s*(.+)$", line, flags=re.I)
            if m:
                explanation = m.group(2).strip()
                continue

        if q_line and len(options) >= 2 and ans_letter:
            correct = ord(ans_letter) - ord("A")
            if 0 <= correct < len(options):
                questions.append({
                    "question": q_line,
                    "options": options[:10],
                    "correct": correct,
                    "explanation": explanation
                })

    return questions


def ensure_chat(chat_id):
    if chat_id not in QUIZ:
        QUIZ[chat_id] = {
            "questions": [],
            "polls": {},
            "scores": defaultdict(lambda: {"name": "", "score": 0, "correct": 0, "wrong": 0, "attempted": 0}),
            "answered": set(),
            "running": False,
            "time": QUESTION_TIME
        }
    return QUIZ[chat_id]


@app.on_message(filters.command("start"))
async def start(client, message):
    await message.reply_text(
        "👋 Quiz Bot Ready\n\n"
        "Commands:\n"
        "/help - commands\n"
        "/sample - question format\n"
        "/loadquiz - reply karke questions load karo\n"
        "/startquiz - quiz start\n"
        "/result - result\n"
        "/settime 20 - time set\n"
        "/stopquiz - stop\n"
        "/clearquiz - clear\n\n"
        "Note: Bot external Telegram link se old polls read nahi kar sakta. "
        "Questions text se load honge."
    )


@app.on_message(filters.command("help"))
async def help_cmd(client, message):
    await message.reply_text(
        "📘 Commands\n\n"
        "/sample - format dekho\n"
        "/loadquiz - questions wale message par reply karke bhejo\n"
        "/startquiz - ek-ek question auto chalega\n"
        "/settime 30 - har question ka time\n"
        "/result - leaderboard\n"
        "/stopquiz - quiz stop\n"
        "/clearquiz - data clear\n\n"
        "Marking: 1 सही answer = 1 number"
    )


@app.on_message(filters.command("sample"))
async def sample(client, message):
    await message.reply_text(
        "इस format में questions भेजो, फिर उस message पर reply करके /loadquiz लिखो:\n\n"
        "Q. भारत की राजधानी क्या है?\n"
        "A) मुंबई\n"
        "B) दिल्ली\n"
        "C) कोलकाता\n"
        "D) चेन्नई\n"
        "Ans: B\n"
        "Ex: भारत की राजधानी नई दिल्ली है।\n\n"
        "Q. उत्तर प्रदेश की राजधानी क्या है?\n"
        "A) कानपुर\n"
        "B) आगरा\n"
        "C) लखनऊ\n"
        "D) मेरठ\n"
        "Ans: C\n"
        "Ex: उत्तर प्रदेश की राजधानी लखनऊ है।"
    )


@app.on_message(filters.command("settime"))
async def settime(client, message):
    chat_id = message.chat.id
    data = ensure_chat(chat_id)

    if len(message.command) < 2 or not message.command[1].isdigit():
        await message.reply_text("Use: /settime 20")
        return

    sec = int(message.command[1])
    if sec < 5:
        await message.reply_text("Minimum 5 sec रखो।")
        return
    if sec > 300:
        await message.reply_text("Maximum 300 sec रखो।")
        return

    data["time"] = sec
    await message.reply_text(f"✅ Time set: {sec} sec")


@app.on_message(filters.command("loadquiz"))
async def loadquiz(client, message):
    chat_id = message.chat.id
    data = ensure_chat(chat_id)

    if not message.reply_to_message or not message.reply_to_message.text:
        await message.reply_text("❌ Questions वाले text message पर reply करके /loadquiz लिखो।")
        return

    questions = parse_questions(message.reply_to_message.text)

    if not questions:
        await message.reply_text("❌ कोई valid question नहीं मिला। /sample देखकर format use करो।")
        return

    data["questions"] = questions
    data["polls"] = {}
    data["scores"] = defaultdict(lambda: {"name": "", "score": 0, "correct": 0, "wrong": 0, "attempted": 0})
    data["answered"] = set()
    data["running"] = False

    await message.reply_text(
        f"✅ Quiz Loaded\n\n"
        f"Total Questions: {len(questions)}\n"
        f"Time per Question: {data['time']} sec\n\n"
        "Start करने के लिए /startquiz"
    )


@app.on_message(filters.command("startquiz"))
async def startquiz(client, message):
    chat_id = message.chat.id
    data = ensure_chat(chat_id)

    if not data["questions"]:
        await message.reply_text("❌ पहले questions load करो: /sample फिर /loadquiz")
        return

    if data["running"]:
        await message.reply_text("⚠️ Quiz पहले से चल रहा है।")
        return

    data["running"] = True
    data["polls"] = {}
    data["scores"] = defaultdict(lambda: {"name": "", "score": 0, "correct": 0, "wrong": 0, "attempted": 0})
    data["answered"] = set()

    await message.reply_text(
        "🎯 Quiz शुरू हो रहा है...\n\n"
        f"Total Questions: {len(data['questions'])}\n"
        f"Time per Question: {data['time']} sec\n"
        "Marking: 1 सही answer = 1 number"
    )

    for i, q in enumerate(data["questions"], start=1):
        if not data["running"]:
            break

        try:
            sent = await client.send_poll(
                chat_id=chat_id,
                question=f"Q{i}. {q['question']}",
                options=q["options"],
                type=Poll.QUIZ,
                correct_option_id=q["correct"],
                explanation=q["explanation"] or "",
                is_anonymous=False
            )

            data["polls"][sent.poll.id] = {
                "q_index": i - 1,
                "correct": q["correct"]
            }

            await asyncio.sleep(data["time"])

            try:
                await client.stop_poll(chat_id, sent.id)
            except Exception:
                pass

            await asyncio.sleep(1)

        except FloodWait as e:
            await asyncio.sleep(e.value)
        except Exception as e:
            print("Send poll error:", e)
            await asyncio.sleep(2)

    data["running"] = False
    await message.reply_text("✅ Quiz Complete\n\nResult देखने के लिए /result")


@app.on_poll_answer()
async def poll_answer(client, poll_answer):
    poll_id = poll_answer.poll_id
    user = poll_answer.user

    if not poll_answer.option_ids:
        return

    selected = poll_answer.option_ids[0]

    for chat_id, data in QUIZ.items():
        if poll_id not in data["polls"]:
            continue

        key = (poll_id, user.id)
        if key in data["answered"]:
            return

        data["answered"].add(key)

        correct = data["polls"][poll_id]["correct"]
        score = data["scores"][user.id]
        score["name"] = (user.first_name or "") + ((" " + user.last_name) if user.last_name else "")
        if not score["name"].strip():
            score["name"] = user.username or str(user.id)

        score["attempted"] += 1

        if selected == correct:
            score["score"] += 1
            score["correct"] += 1
        else:
            score["wrong"] += 1

        return


@app.on_message(filters.command("result"))
async def result(client, message):
    chat_id = message.chat.id
    data = ensure_chat(chat_id)

    if not data["scores"]:
        await message.reply_text("❌ अभी कोई result नहीं है।")
        return

    total = len(data["questions"])
    rows = sorted(data["scores"].values(), key=lambda x: x["score"], reverse=True)

    text = "🏆 FINAL QUIZ RESULT 🏆\n\n"
    text += f"Total Questions: {total}\n"
    text += "Marking: 1 सही answer = 1 number\n\n"

    for rank, r in enumerate(rows[:50], start=1):
        medal = "🥇" if rank == 1 else "🥈" if rank == 2 else "🥉" if rank == 3 else f"{rank}."
        text += (
            f"{medal} {r['name']}\n"
            f"   Score: {r['score']}/{total}\n"
            f"   Correct: {r['correct']} | Wrong: {r['wrong']} | Attempted: {r['attempted']}\n\n"
        )

    if len(text) > 4000:
        text = text[:3900] + "\n\nTop users shown."

    await message.reply_text(text)


@app.on_message(filters.command("stopquiz"))
async def stopquiz(client, message):
    chat_id = message.chat.id
    data = ensure_chat(chat_id)
    data["running"] = False
    await message.reply_text("🛑 Quiz stop कर दिया गया।")


@app.on_message(filters.command("clearquiz"))
async def clearquiz(client, message):
    chat_id = message.chat.id
    if chat_id in QUIZ:
        del QUIZ[chat_id]
    await message.reply_text("🧹 Quiz data clear कर दिया गया।")


print("Quiz Bot started...")
app.run()
