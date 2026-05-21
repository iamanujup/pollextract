# Quiz Userbot R2R

## Setup

1. Install:
```bash
pip install -r requirements.txt
```

2. `.env.example` ko copy karke `.env` banao:
```bash
cp .env.example .env
```

3. `.env` me API_ID aur API_HASH भरो.

API_ID/API_HASH yaha se milega:
https://my.telegram.org

4. Run:
```bash
python userbot.py
```

First time phone number, OTP, 2FA password मांगेगा.

## Commands

```text
.helpquiz
.ping
.loadquiz <telegram_link>
.startquiz
.settime <seconds>
.resultquiz
.stopquiz
.clearquiz
```

Example:

```text
.loadquiz https://t.me/examdrishtiquiz/2591118/50
.startquiz
.resultquiz
```

Rule:
1 सही answer = 1 number

Default time:
20 sec per question.
