import os
import re
import asyncio
from collections import defaultdict
from dotenv import load_dotenv

from telethon import TelegramClient, events, functions, types
from telethon.errors import FloodWaitError

load_dotenv()

API_ID = int(os.getenv("API_ID", "5074166"))
API_HASH = os.getenv("API_HASH", "3cb93a9a9345592f5e6a42020687cdbe")
SESSION_NAME = os.getenv("SESSION_NAME", "quiz_userbot")
DEFAULT_QUESTION_TIME = int(os.getenv("QUESTION_TIME", "20"))

if not API_ID or not API_HASH:
    print("ERROR: .env me API_ID aur API_HASH set karo.")
    raise SystemExit(1)

client = TelegramClient(SESSION_NAME, API_ID, API_HASH)

QUIZ_DATA = {}


def parse_telegram_link(link: str):
    link = link.strip()

    m = re.search(r"t\.me/c/(\d+)/(\d+)(?:/(\d+))?", link)
    if m:
        internal_id = m.group(1)
        start_id = int(m.group(2))
        count = int(m.group(3)) if m.group(3) else 1
        chat_id = int("-100" + internal_id)
        return chat_id, start_id, count

    m = re.search(r"t\.me/([A-Za-z0-9_]+)/(\d+)(?:/(\d+))?", link)
    if m:
        username = m.group(1)
        start_id = int(m.group(2))
        count = int(m.group(3)) if m.group(3) else 1
        return username, start_id, count

    return None, None, None


def get_text(obj):
    if obj is None:
        return ""
    if hasattr(obj, "text"):
        return obj.text
    return str(obj)


def extract_poll_data(msg):
    if not msg or not msg.media:
        return None
    if not isinstance(msg.media, types.MessageMediaPoll):
        return None

    poll = msg.media.poll
    results = msg.media.results

    if not getattr(poll, "quiz", False):
        return None

    question = get_text(poll.question).strip()
    options = [get_text(ans.text).strip() for ans in poll.answers]

    if len(options) < 2:
        return None

    correct_index = None
    if results and results.results:
        for idx, res in enumerate(results.results):
            if getattr(res, "correct", False):
                correct_index = idx
                break

    if correct_index is None:
        return None

    explanation = ""
    if results and getattr(results, "solution", None):
        explanation = results.solution or ""

    return {
        "question": question,
        "options": options,
        "correct_index": correct_index,
        "explanation": explanation
    }


async def send_quiz_poll(target_chat, quiz, q_no):
    answers = []
    for idx, opt in enumerate(quiz["options"]):
        answers.append(
            types.PollAnswer(
                text=types.TextWithEntities(text=opt, entities=[]),
                option=str(idx).encode()
            )
        )

    correct_option = str(quiz["correct_index"]).encode()

    poll = types.Poll(
        id=0,
        question=types.TextWithEntities(
            text=f"Q{q_no}. {quiz['question']}",
            entities=[]
        ),
        answers=answers,
        closed=False,
        public_voters=True,
        multiple_choice=False,
        quiz=True
    )

    media = types.InputMediaPoll(
        poll=poll,
        correct_answers=[correct_option],
        solution=quiz["explanation"] or None,
        solution_entities=[]
    )

    sent = await client.send_file(target_chat, file=media)
    return sent


async def close_sent_poll(target_chat, sent):
    try:
        await client(
            functions.messages.EditMessageRequest(
                peer=target_chat,
                id=sent.id,
                media=types.InputMediaPoll(
                    poll=types.Poll(
                        id=sent.media.poll.id,
                        question=sent.media.poll.question,
                        answers=sent.media.poll.answers,
                        closed=True,
                        public_voters=True,
                        multiple_choice=False,
                        quiz=True
                    )
                )
            )
        )
    except Exception as e:
        print("Poll close failed:", e)


async def get_voters_for_option(chat, msg_id, option_bytes):
    voters = []
    offset = ""

    while True:
        res = await client(
            functions.messages.GetPollVotesRequest(
                peer=chat,
                id=msg_id,
                option=option_bytes,
                offset=offset,
                limit=100
            )
        )

        if not res.votes:
            break

        for vote in res.votes:
            if hasattr(vote, "user_id"):
                voters.append(vote.user_id)

        if not getattr(res, "next_offset", None):
            break

        offset = res.next_offset

    return voters


async def get_all_voters_for_poll(chat, msg_id, options_count):
    attempted = set()

    for idx in range(options_count):
        try:
            voters = await get_voters_for_option(chat, msg_id, str(idx).encode())
            attempted.update(voters)
            await asyncio.sleep(0.2)
        except Exception:
            continue

    return attempted


async def get_user_name(user_id):
    try:
        user = await client.get_entity(user_id)
        first = getattr(user, "first_name", "") or ""
        last = getattr(user, "last_name", "") or ""
        username = getattr(user, "username", "") or ""
        name = (first + " " + last).strip()
        return name or (f"@{username}" if username else str(user_id))
    except Exception:
        return str(user_id)


@client.on(events.NewMessage(outgoing=True, pattern=r"\.helpquiz"))
async def helpquiz(event):
    await event.reply(
        "📘 Quiz Userbot Commands\n\n"
        ".loadquiz <telegram_link>\n"
        ".startquiz\n"
        ".settime <seconds>\n"
        ".resultquiz\n"
        ".stopquiz\n"
        ".clearquiz\n"
        ".ping\n\n"
        "Example:\n"
        ".loadquiz https://t.me/examdrishtiquiz/2591118/50\n"
        ".startquiz\n"
        ".resultquiz\n\n"
        "Rule: 1 सही answer = 1 number"
    )


@client.on(events.NewMessage(outgoing=True, pattern=r"\.ping"))
async def ping(event):
    await event.reply("✅ Userbot running")


@client.on(events.NewMessage(outgoing=True, pattern=r"\.settime\s+(\d+)"))
async def settime(event):
    chat_id = event.chat_id
    seconds = int(event.pattern_match.group(1))

    if seconds < 5:
        await event.reply("❌ Minimum time 5 sec रखो।")
        return
    if seconds > 300:
        await event.reply("❌ Maximum time 300 sec रखो।")
        return

    if chat_id not in QUIZ_DATA:
        QUIZ_DATA[chat_id] = {
            "questions": [],
            "polls": [],
            "total": 0,
            "running": False,
            "delay": seconds
        }
    else:
        QUIZ_DATA[chat_id]["delay"] = seconds

    await event.reply(f"✅ Question time set: `{seconds}` sec")


@client.on(events.NewMessage(outgoing=True, pattern=r"\.clearquiz"))
async def clearquiz(event):
    chat_id = event.chat_id
    if chat_id in QUIZ_DATA:
        del QUIZ_DATA[chat_id]
        await event.reply("🧹 Quiz data clear कर दिया गया।")
    else:
        await event.reply("❌ कोई quiz data नहीं है।")


@client.on(events.NewMessage(outgoing=True, pattern=r"\.stopquiz"))
async def stopquiz(event):
    chat_id = event.chat_id
    if chat_id in QUIZ_DATA:
        QUIZ_DATA[chat_id]["running"] = False
        await event.reply("🛑 Quiz stop कर दिया गया।")
    else:
        await event.reply("❌ कोई active quiz नहीं है।")


@client.on(events.NewMessage(outgoing=True, pattern=r"\.loadquiz\s+(.+)"))
async def loadquiz(event):
    target_chat_id = event.chat_id
    link = event.pattern_match.group(1).strip()

    source_chat, start_id, count = parse_telegram_link(link)
    if not source_chat:
        await event.reply("❌ Invalid Telegram link.")
        return

    if count > 150:
        count = 150

    status = await event.reply(
        f"🔍 Questions load हो रहे हैं...\n\n"
        f"Source: `{source_chat}`\n"
        f"Start ID: `{start_id}`\n"
        f"Check Count: `{count}`"
    )

    QUIZ_DATA[target_chat_id] = {
        "questions": [],
        "polls": [],
        "total": 0,
        "running": False,
        "delay": DEFAULT_QUESTION_TIME
    }

    loaded = skipped = failed = 0

    for msg_id in range(start_id, start_id + count):
        try:
            src_msg = await client.get_messages(source_chat, ids=msg_id)
            quiz = extract_poll_data(src_msg)

            if not quiz:
                skipped += 1
                continue

            QUIZ_DATA[target_chat_id]["questions"].append(quiz)
            loaded += 1
            await asyncio.sleep(0.25)

        except FloodWaitError as e:
            await status.edit(f"⏳ FloodWait: {e.seconds} sec wait कर रहा हूँ...")
            await asyncio.sleep(e.seconds)

        except Exception as e:
            failed += 1
            print(f"Failed msg {msg_id}: {e}")
            await asyncio.sleep(0.5)

    QUIZ_DATA[target_chat_id]["total"] = loaded

    await status.edit(
        "✅ Questions Loaded\n\n"
        f"📌 Loaded quiz polls: `{loaded}`\n"
        f"⏭ Skipped: `{skipped}`\n"
        f"⚠️ Failed: `{failed}`\n\n"
        "Quiz शुरू करने के लिए:\n"
        "`.startquiz`\n\n"
        f"हर प्रश्न `{QUIZ_DATA[target_chat_id]['delay']}` sec रहेगा।"
    )


@client.on(events.NewMessage(outgoing=True, pattern=r"\.startquiz"))
async def startquiz(event):
    target_chat = await event.get_chat()
    target_chat_id = event.chat_id

    if target_chat_id not in QUIZ_DATA:
        await event.reply("❌ पहले `.loadquiz <link>` चलाओ।")
        return

    data = QUIZ_DATA[target_chat_id]
    if not data["questions"]:
        await event.reply("❌ कोई question loaded नहीं है।")
        return
    if data["running"]:
        await event.reply("⚠️ Quiz पहले से चल रहा है।")
        return

    data["running"] = True
    data["polls"] = []
    delay = data.get("delay", DEFAULT_QUESTION_TIME)

    await event.reply(
        "🎯 Quiz शुरू हो रहा है...\n\n"
        f"Total Questions: `{len(data['questions'])}`\n"
        f"Time per Question: `{delay}` sec\n"
        "Marking: 1 सही answer = 1 number"
    )

    q_no = 1
    for quiz in data["questions"]:
        if not data["running"]:
            break

        try:
            sent = await send_quiz_poll(target_chat, quiz, q_no)

            data["polls"].append({
                "msg_id": sent.id,
                "question": quiz["question"],
                "correct_index": quiz["correct_index"],
                "correct_option_bytes": str(quiz["correct_index"]).encode(),
                "options_count": len(quiz["options"])
            })

            await asyncio.sleep(delay)
            await close_sent_poll(target_chat, sent)

            q_no += 1
            await asyncio.sleep(1)

        except FloodWaitError as e:
            await event.reply(f"⏳ FloodWait: {e.seconds} sec wait कर रहा हूँ...")
            await asyncio.sleep(e.seconds)

        except Exception as e:
            print(f"Send quiz failed: {e}")
            await asyncio.sleep(2)

    data["running"] = False
    await event.reply("✅ Quiz Complete\n\nResult देखने के लिए:\n`.resultquiz`")


@client.on(events.NewMessage(outgoing=True, pattern=r"\.resultquiz"))
async def resultquiz(event):
    chat = await event.get_chat()
    chat_id = event.chat_id

    if chat_id not in QUIZ_DATA or not QUIZ_DATA[chat_id].get("polls"):
        await event.reply("❌ कोई quiz result data नहीं मिला। पहले `.startquiz` चलाओ।")
        return

    status = await event.reply("📊 Result बना रहा हूँ...")

    scores = defaultdict(int)
    attempted_count = defaultdict(int)
    total_questions = len(QUIZ_DATA[chat_id]["polls"])

    for poll_data in QUIZ_DATA[chat_id]["polls"]:
        msg_id = poll_data["msg_id"]
        correct_option_bytes = poll_data["correct_option_bytes"]
        options_count = poll_data.get("options_count", 4)

        try:
            correct_voters = await get_voters_for_option(chat, msg_id, correct_option_bytes)
            attempted_users = await get_all_voters_for_poll(chat, msg_id, options_count)

            for uid in attempted_users:
                attempted_count[uid] += 1
            for uid in correct_voters:
                scores[uid] += 1

            await asyncio.sleep(0.4)

        except FloodWaitError as e:
            await asyncio.sleep(e.seconds)

        except Exception as e:
            print(f"Result fetch failed for poll {msg_id}: {e}")
            continue

    all_users = set(scores.keys()) | set(attempted_count.keys())

    if not all_users:
        await status.edit(
            "❌ अभी result नहीं बन पाया।\n\n"
            "Possible reasons:\n"
            "1. किसी ने answer नहीं दिया\n"
            "2. Poll voters access नहीं मिला\n"
            "3. Group/channel permission issue"
        )
        return

    sorted_users = sorted(all_users, key=lambda uid: scores.get(uid, 0), reverse=True)

    text = "🏆 FINAL QUIZ RESULT 🏆\n\n"
    text += f"Total Questions: {total_questions}\n"
    text += "Marking: 1 सही answer = 1 number\n\n"

    for rank, user_id in enumerate(sorted_users[:50], start=1):
        name = await get_user_name(user_id)
        score = scores.get(user_id, 0)
        attempted = attempted_count.get(user_id, 0)
        wrong = attempted - score

        medal = "🥇" if rank == 1 else "🥈" if rank == 2 else "🥉" if rank == 3 else f"{rank}."
        text += (
            f"{medal} {name}\n"
            f"   Score: {score}/{total_questions}\n"
            f"   Correct: {score} | Wrong: {wrong} | Attempted: {attempted}\n\n"
        )

    if len(text) > 4000:
        text = text[:3900] + "\n\nResult बहुत बड़ा है, top users दिखाए गए हैं।"

    await status.edit(text)


async def main():
    print("Quiz Userbot started...")
    print("Telegram me .helpquiz command bhejo.")
    await client.start()
    await client.run_until_disconnected()


if __name__ == "__main__":
    client.loop.run_until_complete(main())
