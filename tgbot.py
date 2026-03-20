import asyncio
import sys
import requests
import re
import random
from datetime import datetime, timedelta

# --- ЗАПЛАТКА ДЛЯ PYTHON 3.14 ---
def setup_loop():
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        return loop
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop

# Создаём event loop ДО импорта pyrogram
loop = setup_loop()

from pyrogram import Client, filters, idle
from pyrogram.enums import ChatAction

# --- ТВОИ ДАННЫЕ ---
# Загружаем из переменных окружения
import os
from dotenv import load_dotenv
load_dotenv()  # Загружает переменные из .env файла

API_ID = int(os.getenv("API_ID", "25511383"))
API_HASH = os.getenv("API_HASH", "YOUR_API_HASH")
FOLDER_ID = os.getenv("FOLDER_ID", "YOUR_FOLDER_ID")
YANDEX_API_KEY = os.getenv("YANDEX_API_KEY", "YOUR_YANDEX_API_KEY")

# ID чатов/пользователей для мониторинга (можно оставить тут или вынести в переменные)
TARGET_USERS = [int(os.getenv("TARGET_USER", "5795888564"))]

# СОСТОЯНИЕ БОТА
LAST_ACTIVITY = datetime.now()
PAUSE_UNTIL = datetime.now() # Пауза, если ты пишешь сам
PROACTIVE_DONE = False 
LAST_RESPONSES = []
BOT_IS_SENDING = False # Чтобы бот не принимал свои сообщения за твои

# Фразы-заглушки для обхода цензуры нейросети
REFUSAL_PHRASES = ["я не могу обсуждать", "я искусственный интеллект", "давайте поговорим о чем-нибудь еще", "не могу на это ответить"]
FALLBACKS = ["хз чет я затупил..", "лан забей, чет мысли в кучу..", "мде, чето я подвис, забей..", "хах, лан, проехали, туплю чето"]

def post_process_text(text):
    text_lower = text.lower().strip()
    
    # Проверка на цензуру
    for ref in REFUSAL_PHRASES:
        if ref in text_lower:
            return random.choice(FALLBACKS)
            
    text = re.sub(r'\.+$', '', text_lower) 
    text = re.sub(r'\.{3,}', '..', text)
    text = text.replace(' — ', ' ').replace(' - ', ' ')
    return text

def ask_yagpt(history_text, user_message="", mode="reply"):
    url = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"
    forbidden = ", ".join(LAST_RESPONSES[-3:])
    
    if mode == "reply":
        instruction = (
            "Ты — Арбузик, общаешься с девушкой. Стиль: ленивый, живой. "
            "МАЛЕНЬКИЕ БУКВАМИ, БЕЗ ТОЧЕК. Вместо '...' только '..'. "
            f"НЕ ПОВТОРЯЙ: {forbidden}. Отвечай кратко, не тупи как робот."
        )
    elif mode == "reaction":
        instruction = "Сообщение милое или позитивное? Ответ: YES или NO."
    else: 
        instruction = "В чате тишина. Напиши ОДНУ короткую фразу первым (маленькие буквы, без точек)."

    system_prompt = f"{instruction}\n\nКОНТЕКСТ:\n{history_text}"

    data = {
        "modelUri": f"gpt://{FOLDER_ID}/yandexgpt-lite",
        "completionOptions": {"stream": False, "temperature": 0.85, "maxTokens": "300"},
        "messages": [
            {"role": "system", "text": system_prompt},
            {"role": "user", "text": user_message if user_message else "действуй"}
        ]
    }
    headers = {"Content-Type": "application/json", "Authorization": f"Api-Key {YANDEX_API_KEY}"}
    try:
        response = requests.post(url, headers=headers, json=data)
        if response.status_code == 200:
            return response.json()['result']['alternatives'][0]['message']['text']
    except: pass
    return "хах хз"

async def respond_to_message(client, message):
    global LAST_ACTIVITY, PROACTIVE_DONE, LAST_RESPONSES, PAUSE_UNTIL, BOT_IS_SENDING
    
    # Если ты сам общаешься — бот не лезет
    if datetime.now() < PAUSE_UNTIL:
        return

    LAST_ACTIVITY = datetime.now()
    PROACTIVE_DONE = False 

    try:
        # 1. Имитация чтения (пауза перед тем как сообщение станет прочитанным)
        await asyncio.sleep(random.randint(3, 6))
        await client.read_chat_history(message.chat.id)

        # 2. Реакция
        is_cute = ask_yagpt(message.text, mode="reaction")
        if "YES" in is_cute.upper():
            await client.send_reaction(message.chat.id, message.id, "❤️")

        # 3. Сбор истории
        chat_context = []
        async for msg in client.get_chat_history(message.chat.id, limit=40):
            author = "Я" if msg.outgoing else "Она"
            if msg.text: chat_context.append(f"{author}: {msg.text}")
        chat_context.reverse()

        # 4. Имитация долгого набора текста
        await client.send_chat_action(message.chat.id, ChatAction.TYPING)
        
        # Время печати зависит от сложности, от 5 до 12 секунд
        typing_duration = random.randint(8, 20)
        await asyncio.sleep(typing_duration)

        ai_response = post_process_text(ask_yagpt("\n".join(chat_context), message.text, mode="reply"))
        LAST_RESPONSES.append(ai_response)
        
        # 5. ШАНС НА ОТВЕТ ЧЕРЕЗ ЦИТАТУ (30% шанс)
        use_reply = random.random() < 0.3
        
        BOT_IS_SENDING = True
        await message.reply_text(ai_response, quote=use_reply)
        BOT_IS_SENDING = False
        
        LAST_ACTIVITY = datetime.now()
        print(f"[+] Ответил: {ai_response} (Reply: {use_reply})")
        
    except Exception as e:
        print(f"[!] Ошибка: {e}")
        BOT_IS_SENDING = False

app = Client("my_account", api_id=API_ID, api_hash=API_HASH)

@app.on_message(filters.chat(TARGET_USERS))
async def on_message_handler(client, message):
    global PAUSE_UNTIL, BOT_IS_SENDING, LAST_ACTIVITY
    
    # Если сообщение исходит от тебя (не от бота) — засыпаем на 15 минут
    if message.outgoing and not BOT_IS_SENDING:
        PAUSE_UNTIL = datetime.now() + timedelta(minutes=15)
        LAST_ACTIVITY = datetime.now()
        print("[!] Ты сам в чате. Бот спит 15 минут")
        return

    if not message.outgoing:
        await respond_to_message(client, message)

async def proactive_thinker():
    global LAST_ACTIVITY, PROACTIVE_DONE, PAUSE_UNTIL
    while True:
        await asyncio.sleep(30)
        if datetime.now() < PAUSE_UNTIL: continue
        
        diff = (datetime.now() - LAST_ACTIVITY).total_seconds()
        
        # Если тишина больше 10 минут
        if diff > 50 and not PROACTIVE_DONE:
            chat_id = TARGET_USERS[0]
            try:
                chat_context = []
                async for msg in app.get_chat_history(chat_id, limit=20):
                    author = "Я" if msg.outgoing else "Она"
                    if msg.text: chat_context.append(f"{author}: {msg.text}")
                chat_context.reverse()
                
                topic = post_process_text(ask_yagpt("\n".join(chat_context), mode="proactive"))
                await app.send_message(chat_id, topic)
                PROACTIVE_DONE = True 
                LAST_ACTIVITY = datetime.now()
                print(f"[+] Инициатива: {topic}")
            except: pass

async def start_bot():
    import signal
    
    # Обработка сигналов для корректного завершения
    def signal_handler(sig, frame):
        print("\n[!] Получен сигнал завершения, закрываем бота...")
        loop.stop()
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        await app.start()
        print(">>> Бот-Арбузик PRO запущен.", flush=True)
        asyncio.create_task(proactive_thinker())
        await idle()
    except asyncio.CancelledError:
        print("\n[!] Задача отменена, закрываем бота...")
    finally:
        try:
            await app.stop()
        except:
            pass

if __name__ == "__main__":
    try:
        loop.run_until_complete(start_bot())
    except RuntimeError as e:
        if "Event loop is closed" in str(e):
            print("[!] Бот остановлен")
        else:
            raise
    except KeyboardInterrupt:
        print("[!] Бот остановлен пользователем")