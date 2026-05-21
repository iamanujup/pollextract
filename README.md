# Telegram Quiz Bot R2R

Ye Bot Token wala version hai. Isme session nahi chahiye.

Important:
- Bot external Telegram link se old poll read nahi kar sakta.
- Questions text format se load honge.
- Bot group me quiz poll bhejega, 20 sec baad close karega, result dega.

## Render

Runtime: Python

Build Command:
```bash
pip install -r requirements.txt
```

Start Command:
```bash
python main.py
```

Environment Variables:
```env
API_ID=your_api_id
API_HASH=your_api_hash
BOT_TOKEN=your_bot_token
QUESTION_TIME=20
```

## Telegram commands

```text
/start
/help
/sample
/loadquiz
/startquiz
/result
/settime 30
/stopquiz
/clearquiz
```

## Use

1. /sample bhejo aur format dekho
2. Apne questions ek message me bhejo
3. Us questions message par reply karke /loadquiz likho
4. /startquiz
5. /result
