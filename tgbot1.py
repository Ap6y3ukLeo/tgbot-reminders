import logging
import sqlite3
import requests
from datetime import datetime, timedelta
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
import asyncio
from threading import Thread
import re
import sys
import io

# Telegram Bot Token
TELEGRAM_BOT_TOKEN = "8484739084:AAEFYcWm4aP96NXYsA_gMgvvrVHc4GSVDt8"

# Supabase credentials
SUPABASE_URL = "https://cgfbstfgnvdqwzxpjfjp.supabase.co"
SUPABASE_KEY = "cgfbstfgnvdqwzxpjfjp"

# Supabase configuration (used throughout the bot)
# Values already defined above

# Функции для работы с напоминаниями в Supabase
def get_reminders_from_supabase(chat_id):
    """Получает напоминания из Supabase по telegram_chat_id"""
    try:
        headers = {
            'apikey': SUPABASE_KEY,
            'Authorization': f'Bearer {SUPABASE_KEY}',
            'Content-Type': 'application/json',
            'Prefer': 'return=representation'
        }
        
        response = requests.get(
            f'{SUPABASE_URL}/rest/v1/reminders?telegram_chat_id=eq.{chat_id}&order=reminder_date.asc&order=reminder_time.asc',
            headers=headers
        )
        
        if response.status_code == 200:
            return response.json()
        else:
            print(f'Ошибка получения напоминаний из Supabase: {response.status_code}')
            return []
            
    except Exception as e:
        print(f'Ошибка при получении напоминаний из Supabase: {e}')
        return []

def add_reminder_to_supabase(chat_id, title, reminder_date, reminder_time):
    """Добавляет напоминание в Supabase"""
    try:
        headers = {
            'apikey': SUPABASE_KEY,
            'Authorization': f'Bearer {SUPABASE_KEY}',
            'Content-Type': 'application/json',
            'Prefer': 'return=representation'
        }
        
        # Пробуем найти пользователя по telegram_id
        user_response = requests.get(
            f'{SUPABASE_URL}/rest/v1/users?telegram_id=eq.{chat_id}&select=id',
            headers=headers
        )
        
        user_id = None
        if user_response.status_code == 200:
            users = user_response.json()
            if users:
                user_id = users[0]['id']
        
        data = {
            'telegram_chat_id': chat_id,
            'title': title,
            'reminder_date': reminder_date,
            'reminder_time': reminder_time,
            'user_id': user_id,  # может быть null
            'reminder_stage': 0,
            'extended_count': 0
        }
        
        response = requests.post(
            f'{SUPABASE_URL}/rest/v1/reminders',
            headers=headers,
            json=[data]
        )
        
        if response.status_code in [200, 201]:
            print(f'Напоминание добавлено в Supabase: {title}')
            return True
        else:
            print(f'Ошибка добавления в Supabase: {response.status_code} - {response.text}')
            return False
            
    except Exception as e:
        print(f'Ошибка при добавлении напоминания в Supabase: {e}')
        return False

def delete_reminder_from_supabase(reminder_id):
    """Удаляет напоминание из Supabase"""
    try:
        headers = {
            'apikey': SUPABASE_KEY,
            'Authorization': f'Bearer {SUPABASE_KEY}',
            'Content-Type': 'application/json'
        }
        
        response = requests.delete(
            f'{SUPABASE_URL}/rest/v1/reminders?id=eq.{reminder_id}',
            headers=headers
        )
        
        return response.status_code in [200, 204]
        
    except Exception as e:
        print(f'Ошибка при удалении из Supabase: {e}')
        return False

def update_reminder_in_supabase(reminder_id, updates):
    """Обновляет напоминание в Supabase"""
    print(f'DEBUG update_reminder_in_supabase: reminder_id={reminder_id}, updates={updates}')
    try:
        headers = {
            'apikey': SUPABASE_KEY,
            'Authorization': f'Bearer {SUPABASE_KEY}',
            'Content-Type': 'application/json',
            'Prefer': 'return=representation'
        }
        
        url = f'{SUPABASE_URL}/rest/v1/reminders?id=eq.{reminder_id}'
        print(f'DEBUG update_reminder_in_supabase: URL={url}')
        
        response = requests.patch(
            url,
            headers=headers,
            json=updates
        )
        
        print(f'DEBUG update_reminder_in_supabase: status_code={response.status_code}, response={response.text[:200]}')
        return response.status_code in [200, 204]
        
    except Exception as e:
        print(f'Ошибка при обновлении в Supabase: {e}')
        return False

def get_all_supabase_reminders():
    """Получает все напоминания из Supabase для отправки"""
    try:
        headers = {
            'apikey': SUPABASE_KEY,
            'Authorization': f'Bearer {SUPABASE_KEY}',
            'Content-Type': 'application/json',
            'Prefer': 'return=representation'
        }
        
        response = requests.get(
            f'{SUPABASE_URL}/rest/v1/reminders?order=reminder_date.asc&order=reminder_time.asc',
            headers=headers
        )
        
        if response.status_code == 200:
            return response.json()
        return []
        
    except Exception as e:
        print(f'Ошибка при получении всех напоминаний: {e}')
        return []

# Исправление проблемы с кодировкой на Windows
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', newline='\n')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', newline='\n')

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',level=logging.INFO)
BOT_TOKEN = TELEGRAM_BOT_TOKEN  # Use the token defined at the top
WAITING_TITLE,WAITING_DATE,WAITING_TIME,WAITING_EDIT_TITLE,WAITING_EDIT_DATE,WAITING_EDIT_TIME = range(6)
DAYS_OF_WEEK = {'понедельник':0,'вторник':1,'среда':2,'четверг':3,'пятница':4,'суббота':5,'воскресенье':6,'пн':0,'вт':1,'ср':2,'чт':3,'пт':4,'сб':5,'вс':6}

def format_date_russian(date_str):
  """Конвертирует дату из формата YYYY-MM-DD в русский формат DD.MM.YYYY"""
  try:
    if '-' in date_str:
      parts = date_str.split('-')
      if len(parts) == 3:
        return f'{parts[2]}.{parts[1]}.{parts[0]}'
  except:
    pass
  return date_str

# Функция для получения задач из Supabase
def get_tasks_from_supabase(user_telegram_id=None):
    """
    Получает задачи из Supabase.
    Если user_telegram_id указан - ищет по пользователю.
    Иначе - возвращает все задачи.
    """
    try:
        headers = {
            'apikey': SUPABASE_KEY,
            'Authorization': f'Bearer {SUPABASE_KEY}',
            'Content-Type': 'application/json',
            'Prefer': 'return=representation'
        }
        
        # Если есть telegram_id, пробуем найти пользователя
        if user_telegram_id:
            response = requests.get(
                f'{SUPABASE_URL}/rest/v1/users?telegram_id=eq.{user_telegram_id}&select=id',
                headers=headers
            )
            
            if response.status_code == 200:
                users = response.json()
                if users:
                    user_id = users[0]['id']
                    # Получаем задачи пользователя
                    response = requests.get(
                        f'{SUPABASE_URL}/rest/v1/tasks?user_id=eq.{user_id}&order=created_at.desc',
                        headers=headers
                    )
                    
                    if response.status_code == 200:
                        return response.json()
        
        # Иначе получаем все задачи
        response = requests.get(
            f'{SUPABASE_URL}/rest/v1/tasks?order=created_at.desc&limit=50',
            headers=headers
        )
        
        if response.status_code == 200:
            return response.json()
        return []
            
    except Exception as e:
        print(f'Ошибка при получении задач из Supabase: {e}')
        return []

# Функция для отображения задач в читабельном формате
def format_tasks_message(tasks):
    """Форматирует задачи для отображения в Telegram"""
    if not tasks:
        return "📭 У вас пока нет задач в приложении.\n\nСоздайте задачи в мобильном приложении, и они появятся здесь."
    
    # Группировка по колонкам
    columns = {
        'todo': ('📝 Сделать', []),
        'in-progress': ('⚡ В процессе', []),
        'done': ('✅ Готово', [])
    }
    
    for task in tasks:
        column = task.get('task_column', 'todo')
        if column in columns:
            title = task.get('title', 'Без названия')
            description = task.get('description', '')
            task_date = task.get('task_date', '')
            
            task_text = f"• <b>{title}</b>"
            if description:
                task_text += f"\n  {description}"
            if task_date:
                try:
                    date_obj = datetime.fromisoformat(task_date.replace('Z', '+00:00'))
                    task_text += f"\n  📅 {date_obj.strftime('%d.%m.%Y')}"
                except:
                    pass
            
            columns[column][1].append(task_text)
    
    # Формируем сообщение
    message = "📋 <b>Ваши задачи из приложения:</b>\n\n"
    
    for col_id, (col_name, col_tasks) in columns.items():
        if col_tasks:
            message += f"<b>{col_name}</b>\n"
            message += "\n".join(col_tasks)
            message += "\n\n"
    
    if not any(col[1] for col in columns.values()):
        message += "Задач пока нет.\n"
    
    message += "\n<i>Задачи создаются и редактируются в мобильном приложении.</i>"
    
    return message

def init_db():
  conn = sqlite3.connect('tasks.db',check_same_thread=False)
  cursor = conn.cursor()
  cursor.execute('''
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER,
            title TEXT,
            reminder_date TEXT,
            reminder_time TEXT,
            created_at TEXT,
            last_reminder_sent TEXT,
            reminder_stage INTEGER DEFAULT 0,
            extended_count INTEGER DEFAULT 0
        )
    ''')
  cursor.execute('PRAGMA table_info(tasks)')
  existing_columns = [column[1] for column in cursor.fetchall()]
  required_columns = ['reminder_date','reminder_time','extended_count']
  for column in required_columns:
    if column not in existing_columns:
      print(f'''🔄 Добавляем колонку: {column}''')
      if column == 'reminder_date':
        cursor.execute('ALTER TABLE tasks ADD COLUMN reminder_date TEXT')
        continue

      if column == 'reminder_time':
        cursor.execute('ALTER TABLE tasks ADD COLUMN reminder_time TEXT')
        continue

      if column == 'extended_count':
        cursor.execute('ALTER TABLE tasks ADD COLUMN extended_count INTEGER DEFAULT 0')

  if 'reminder_time' in existing_columns and len(existing_columns) == 7:
    print('🔄 Конвертируем данные из старого формата...')
    try:
      cursor.execute('''
                CREATE TABLE IF NOT EXISTS tasks_temp (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER,
                    title TEXT,
                    reminder_date TEXT,
                    reminder_time TEXT,
                    created_at TEXT,
                    last_reminder_sent TEXT,
                    reminder_stage INTEGER DEFAULT 0,
                    extended_count INTEGER DEFAULT 0
                )
            ''')
      cursor.execute('''
                INSERT INTO tasks_temp (id, chat_id, title, reminder_date, reminder_time, created_at, last_reminder_sent, reminder_stage, extended_count)
                SELECT 
                    id, 
                    chat_id, 
                    title,
                    date(reminder_time) as reminder_date,
                    time(reminder_time) as reminder_time,
                    created_at,
                    last_reminder_sent,
                    reminder_stage,
                    0 as extended_count
                FROM tasks
            ''')
      cursor.execute('DROP TABLE tasks')
      cursor.execute('ALTER TABLE tasks_temp RENAME TO tasks')
      print('✅ Данные успешно сконвертированы')
    except Exception as e:
      print(f'''❌ Ошибка при конвертации данных: {e}''')

  conn.commit()
  conn.close()
  print('✅ База данных подключена и готова к работе')

def add_task(chat_id,title,reminder_date,reminder_time):
  """Добавляет напоминание в Supabase"""
  print(f'''DEBUG add_task: chat_id={chat_id}, title={title}, date={reminder_date}, time={reminder_time}''')
  result = add_reminder_to_supabase(chat_id, title, reminder_date, reminder_time)
  if result:
    print(f'''DEBUG add_task: Задача сохранена в Supabase''')
  else:
    print(f'''DEBUG add_task: Ошибка сохранения в Supabase''')
  return result

def get_user_tasks(chat_id):
  """Получает напоминания пользователя из Supabase"""
  reminders = get_reminders_from_supabase(chat_id)
  # Конвертируем в формат, совместимый со старым SQLite форматом
  # (id, title, reminder_date, reminder_time, extended_count)
  result = []
  for r in reminders:
    result.append((
      r.get('id'),
      r.get('title'),
      r.get('reminder_date'),
      r.get('reminder_time'),
      r.get('extended_count', 0)
    ))
  return result

def delete_task(chat_id,task_id):
  """Удаляет напоминание из Supabase"""
  return delete_reminder_from_supabase(task_id)

def get_tasks_for_reminders():
  conn = sqlite3.connect('tasks.db',check_same_thread=False)
  cursor = conn.cursor()
  cursor.execute('SELECT * FROM tasks')
  tasks = cursor.fetchall()
  conn.close()
  return tasks

def get_all_reminders_for_sending():
  """Получает все напоминания для отправки (из SQLite и Supabase)"""
  all_reminders = []
  
  # Получаем из SQLite
  sqlite_reminders = get_tasks_for_reminders()
  for r in sqlite_reminders:
    # (id, chat_id, title, date, time, created_at, last_reminder, stage, extended)
    all_reminders.append({
      'source': 'sqlite',
      'id': r[0],
      'chat_id': r[1],
      'title': r[2],
      'reminder_date': r[3],
      'reminder_time': r[4],
      'created_at': r[5],
      'last_reminder': r[6],
      'reminder_stage': r[7],
      'extended_count': r[8]
    })
  
  # Получаем из Supabase
  try:
    supabase_reminders = get_all_supabase_reminders()
    for r in supabase_reminders:
      all_reminders.append({
        'source': 'supabase',
        'id': r.get('id'),
        'chat_id': r.get('telegram_chat_id'),
        'title': r.get('title'),
        'reminder_date': r.get('reminder_date'),
        'reminder_time': r.get('reminder_time'),
        'created_at': r.get('created_at'),
        'last_reminder': r.get('last_reminder_sent'),
        'reminder_stage': r.get('reminder_stage', 0),
        'extended_count': r.get('extended_count', 0)
      })
  except Exception as e:
    print(f'Ошибка получения напоминаний из Supabase: {e}')
  
  return all_reminders

def update_reminder_status(task_id,reminder_stage,last_reminder_sent=None):
  conn = sqlite3.connect('tasks.db',check_same_thread=False)
  cursor = conn.cursor()
  if last_reminder_sent:
    cursor.execute('UPDATE tasks SET reminder_stage = ?, last_reminder_sent = ? WHERE id = ?',(reminder_stage,last_reminder_sent,task_id))
  else:
    cursor.execute('UPDATE tasks SET reminder_stage = ? WHERE id = ?',(reminder_stage,task_id))

  conn.commit()
  conn.close()

def get_reminder_from_supabase_by_id(reminder_id):
  """Получает напоминание из Supabase по ID"""
  try:
    headers = {
      'apikey': SUPABASE_KEY,
      'Authorization': f'Bearer {SUPABASE_KEY}',
      'Content-Type': 'application/json'
    }
    response = requests.get(
      f'{SUPABASE_URL}/rest/v1/reminders?id=eq.{reminder_id}&limit=1',
      headers=headers
    )
    if response.status_code == 200:
      data = response.json()
      if data:
        r = data[0]
        # Возвращаем в формате совместимом с SQLite tuple
        # (id, chat_id, title, reminder_date, reminder_time, created_at, last_reminder_sent, reminder_stage, extended_count)
        return (
          r.get('id'),
          r.get('telegram_chat_id'),
          r.get('title'),
          r.get('reminder_date'),
          r.get('reminder_time'),
          r.get('created_at'),
          r.get('last_reminder_sent'),
          r.get('reminder_stage', 0),
          r.get('extended_count', 0)
        )
    return None
  except Exception as e:
    print(f'Ошибка получения напоминания из Supabase: {e}')
    return None

def is_uuid(value):
  """Проверяет является ли значение UUID"""
  import re
  uuid_pattern = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', re.IGNORECASE)
  return bool(uuid_pattern.match(str(value)))

def get_task_by_id(task_id):
  # Если task_id это UUID, ищем в Supabase
  if is_uuid(task_id):
    print(f'DEBUG get_task_by_id: Ищем UUID {task_id} в Supabase')
    task = get_reminder_from_supabase_by_id(task_id)
    if task:
      print(f'''DEBUG get_task_by_id: Найдена задача в Supabase id={task[0]}, title=\'{task[2]}\', date={task[3]}, time={task[4]}''')
    else:
      print(f'''DEBUG get_task_by_id: Задача {task_id} не найдена в Supabase''')
    return task

  # Иначе ищем в SQLite (пробуем как integer)
  try:
    int_id = int(task_id)
    conn = sqlite3.connect('tasks.db',check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM tasks WHERE id = ?',(int_id,))
    task = cursor.fetchone()
    conn.close()
    if task:
      print(f'''DEBUG get_task_by_id: Найдена задача в SQLite id={task[0]}, title=\'{task[2]}\', date={task[3]}, time={task[4]}''')
    else:
      print(f'''DEBUG get_task_by_id: Задача {task_id} не найдена в SQLite''')
    return task
  except ValueError:
    print(f'''DEBUG get_task_by_id: Неверный формат ID {task_id}''')
    return None

def extend_task(task_id,extension_type,custom_date=None,custom_time=None):
  print(f'''DEBUG extend_task: task_id={task_id}, type={extension_type}, custom_date={custom_date}, custom_time={custom_time}''')
  
  # Получаем задачу (из SQLite или Supabase)
  task = get_task_by_id(task_id)
  if not task:
    print(f'''DEBUG: Задача {task_id} не найдена''')
    return (False,None)
  
  # Распаковываем данные задачи (формат tuple от get_task_by_id)
  # (id, chat_id, title, reminder_date, reminder_time, created_at, last_reminder_sent, reminder_stage, extended_count)
  _, chat_id, title, current_date, current_time, _, _, _, extended_count = task
  print(f'''DEBUG: Найдена задача: '{title}', дата={current_date}, время={current_time}''')
  
  try:
    # Поддержка формата с секундами и без
    time_str = str(current_time)
    if len(time_str.split(':')) == 3:
      current_datetime = datetime.strptime(f'''{current_date} {time_str}''','%Y-%m-%d %H:%M:%S')
    else:
      current_datetime = datetime.strptime(f'''{current_date} {time_str}''','%Y-%m-%d %H:%M')
    now = datetime.now()
    print(f'''DEBUG: Текущее время задачи: {current_datetime}, сейчас: {now}''')
  except ValueError as e:
    print(f'''DEBUG: Ошибка парсинга времени: {e}''')
    return (False,None)

  new_datetime = None
  if extension_type == '1h':
    # +1 час от дедлайна задачи (или от текущего времени если уже просрочено)
    if current_datetime > now:
      new_datetime = current_datetime + timedelta(hours=1)
    else:
      new_datetime = now + timedelta(hours=1)
    print(f'''DEBUG: Продление на 1 час от дедлайна: {new_datetime}''')
  elif extension_type == 'tomorrow':
    tomorrow = now+timedelta(days=1)
    new_datetime = datetime.combine(tomorrow.date(),current_datetime.time())
    if new_datetime <= now:
      new_datetime = new_datetime+timedelta(days=1)
    print(f'''DEBUG: Продление на завтра: {new_datetime}''')
  elif extension_type == 'dayafter':
    day_after = now+timedelta(days=2)
    new_datetime = datetime.combine(day_after.date(),current_datetime.time())
    if new_datetime <= now:
      new_datetime = new_datetime+timedelta(days=1)
    print(f'''DEBUG: Продление на послезавтра: {new_datetime}''')
  elif extension_type == 'custom':
    try:
      if custom_date and custom_time:
        custom_datetime_str = f"{custom_date} {custom_time}"
        new_datetime = datetime.strptime(custom_datetime_str, '%Y-%m-%d %H:%M')
      elif custom_date:
        new_datetime = datetime.combine(datetime.strptime(custom_date, '%Y-%m-%d').date(), current_datetime.time())
      print(f'''DEBUG: Пользовательская дата: {new_datetime}''')
    except ValueError as e:
      print(f'''DEBUG: Ошибка парсинга пользовательской даты: {e}''')
      return (False,None)

  if not new_datetime:
    print('DEBUG: new_datetime is None')
    return (False,None)
    
  if new_datetime <= now:
    print(f'''DEBUG: Новая дата {new_datetime} в прошлом (сейчас {now})''')
    return (False,None)
  
  new_date = new_datetime.strftime('%Y-%m-%d')
  new_time = new_datetime.strftime('%H:%M')
  print(f'''DEBUG: Новая дата={new_date}, время={new_time}''')
  
  # Если это UUID - обновляем в Supabase
  if is_uuid(task_id):
    print(f'DEBUG: Обновляем напоминание в Supabase')
    try:
      updates = {
        'reminder_date': new_date,
        'reminder_time': new_time,
        'extended_count': extended_count + 1,
        'reminder_stage': 0,
        'last_reminder_sent': None
      }
      if update_reminder_in_supabase(task_id, updates):
        print(f'DEBUG: Напоминание в Supabase обновлено')
        return (True, task_id)
      else:
        print(f'DEBUG: Ошибка обновления в Supabase')
        return (False, None)
    except Exception as e:
      print(f'DEBUG: Ошибка при обновлении в Supabase: {e}')
      return (False, None)
  else:
    # Обновляем в SQLite
    print(f'DEBUG: Обновляем напоминание в SQLite')
    try:
      int_id = int(task_id)
      conn = sqlite3.connect('tasks.db',check_same_thread=False)
      cursor = conn.cursor()
      cursor.execute('DELETE FROM tasks WHERE id = ?',(int_id,))
      print(f'''DEBUG: Удалена старая задача {task_id}''')
      cursor.execute('''
        INSERT INTO tasks (chat_id, title, reminder_date, reminder_time, created_at,
                          last_reminder_sent, reminder_stage, extended_count)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
      ''',(chat_id,title,new_date,new_time,datetime.now().isoformat(),None,0,extended_count+1))
      new_task_id = cursor.lastrowid
      conn.commit()
      conn.close()
      print(f'''DEBUG: Создана новая задача {new_task_id}''')
      return (True,new_task_id)
    except Exception as e:
      print(f'DEBUG: Ошибка при обновлении в SQLite: {e}')
      return (False, None)

def parse_date(text):
  now = datetime.now()
  text_lower = text.lower().strip()
  if 'сегодня' in text_lower:
    return now.date()
  else:
    if 'завтра' in text_lower:
      return (now+timedelta(days=1)).date()
    else:
      for day_name,day_num in DAYS_OF_WEEK.items():
        if day_name in text_lower:
          current_day = now.weekday()
          days_ahead = day_num-current_day
          if days_ahead <= 0:
            days_ahead += 7

          return (now+timedelta(days=days_ahead)).date()
        
        # Пробуем разные форматы даты
        # Сначала пробуем с годом
        date_formats_with_year = ['%Y-%m-%d','%d-%m-%Y','%d.%m.%Y','%d/%m/%Y','%d %m %Y']
        for date_format in date_formats_with_year:
          try:
            date_obj = datetime.strptime(text,date_format).date()
            return date_obj
          except ValueError:
            pass
        
        # Теперь пробуем форматы без года (ДД-ММ или ДД.ММ) - добавляем текущий год
        date_formats_no_year = ['%d-%m','%d.%m','%d %m']
        for date_format in date_formats_no_year:
          try:
            date_obj = datetime.strptime(text,date_format)
            # Добавляем текущий год
            date_obj = date_obj.replace(year=now.year)
            # Если дата уже прошла в этом году, используем следующий год
            if date_obj.date() < now.date():
              date_obj = date_obj.replace(year=now.year + 1)
            return date_obj.date()
          except ValueError:
            pass

        return None

def parse_time(text):
  text_lower = text.lower().strip()
  time_text = re.sub('\\bв\\b|\\bво\\b','',text_lower).strip()
  time_match = re.search('(\\d{1,2}):(\\d{2})',time_text)
  if time_match:
    hours = int(time_match.group(1))
    minutes = int(time_match.group(2))
    if 0 <= hours <= 23 and 0 <= minutes <= 59:
      return f'{hours:02d}:{minutes:02d}'
    else:
      return None
  else:
    return None

def get_main_keyboard():
  keyboard = [
    ['📝 Добавить напоминание','📋 Мои напоминания'],
    ['📋 Мои задачи','🗑️ Удалить напоминание'],
    ['ℹ️ Помощь']
  ]
  return ReplyKeyboardMarkup(keyboard,resize_keyboard=True)

def get_cancel_keyboard():
  keyboard = [['❌ Отмена']]
  return ReplyKeyboardMarkup(keyboard,resize_keyboard=True)

def get_date_inline_keyboard():
  keyboard = []
  now = datetime.now()
  quick_dates = [('📅 Сегодня',now.strftime('%Y-%m-%d')),('📅 Завтра',(now+timedelta(days=1)).strftime('%Y-%m-%d')),('📅 Послезавтра',(now+timedelta(days=2)).strftime('%Y-%m-%d'))]
  for text,date_value in quick_dates:
    keyboard.append([InlineKeyboardButton(text,callback_data=f'''date_{date_value}''')])

  days_row = []
  days = [('Пн',0),('Вт',1),('Ср',2),('Чт',3),('Пт',4),('Сб',5),('Вс',6)]
  for day_name,day_num in days:
    days_row.append(InlineKeyboardButton(f'''📅 {day_name}''',callback_data=f'''day_{day_num}'''))
    if len(days_row) == 4:
      keyboard.append(days_row)
      days_row = []

  if days_row:
    keyboard.append(days_row)

  keyboard.append([InlineKeyboardButton('📅 Ввести свою дату',callback_data='custom_date')])
  keyboard.append([InlineKeyboardButton('❌ Отмена',callback_data='cancel')])
  return InlineKeyboardMarkup(keyboard)

def get_time_inline_keyboard():
  keyboard = []
  times = ['09:00','10:00','11:00','12:00','13:00','14:00','15:00','16:00','17:00','18:00','19:00','20:00']
  row = []
  for i,time in enumerate(times):
    row.append(InlineKeyboardButton(f'''⏰ {time}''',callback_data=f'''time_{time}'''))
    if len(row) == 3:
      keyboard.append(row)
      row = []

  if row:
    keyboard.append(row)

  keyboard.append([InlineKeyboardButton('⏰ Ввести своё время',callback_data='custom_time')])
  keyboard.append([InlineKeyboardButton('↩️ Назад к дате',callback_data='back_to_date')])
  keyboard.append([InlineKeyboardButton('❌ Отмена',callback_data='cancel')])
  return InlineKeyboardMarkup(keyboard)

def get_reminder_keyboard(task_id,is_overdue=False):
  keyboard = [
    [InlineKeyboardButton('✅ Выполнено',callback_data=f'''done_{task_id}''')],
    [InlineKeyboardButton('✏️ Редактировать',callback_data=f'''edit_{task_id}''')],
    [InlineKeyboardButton('⏱️ Перенести',callback_data=f'''extend_menu_{task_id}''')]
  ]
  return InlineKeyboardMarkup(keyboard)

# Функция для обновления напоминания в SQLite
def update_reminder_sqlite(task_id, title=None, reminder_date=None, reminder_time=None):
  """Обновляет напоминание в SQLite"""
  print(f'DEBUG update_reminder_sqlite: task_id={task_id}, title={title}, date={reminder_date}, time={reminder_time}')
  try:
    conn = sqlite3.connect('tasks.db',check_same_thread=False)
    cursor = conn.cursor()
    
    updates = []
    params = []
    if title is not None:
      updates.append('title = ?')
      params.append(title)
    if reminder_date is not None:
      updates.append('reminder_date = ?')
      params.append(reminder_date)
    if reminder_time is not None:
      updates.append('reminder_time = ?')
      params.append(reminder_time)
    
    if not updates:
      print(f'DEBUG update_reminder_sqlite: Нет полей для обновления')
      conn.close()
      return True
    
    query = f"UPDATE tasks SET {', '.join(updates)} WHERE id = ?"
    params.append(int(task_id))
    print(f'DEBUG update_reminder_sqlite: query={query}, params={params}')
    cursor.execute(query, params)
    conn.commit()
    rows_affected = cursor.rowcount
    conn.close()
    print(f'DEBUG: Напоминание {task_id} обновлено в SQLite, rows_affected={rows_affected}')
    return True
  except Exception as e:
    print(f'DEBUG: Ошибка обновления в SQLite: {e}')
    return False

# Функция для обновления напоминания (SQLite или Supabase)
def update_reminder(task_id, title=None, reminder_date=None, reminder_time=None):
  """Обновляет напоминание в SQLite или Supabase"""
  if is_uuid(task_id):
    # Собираем только не-None поля для обновления
    updates = {}
    if title is not None:
      updates['title'] = title
    if reminder_date is not None:
      updates['reminder_date'] = reminder_date
    if reminder_time is not None:
      updates['reminder_time'] = reminder_time
    
    if not updates:
      print(f'DEBUG update_reminder: Нет данных для обновления')
      return False
    
    print(f'DEBUG update_reminder: Обновляем UUID {task_id} с данными: {updates}')
    return update_reminder_in_supabase(task_id, updates)
  else:
    return update_reminder_sqlite(task_id, title, reminder_date, reminder_time)

def get_edit_menu_keyboard(task_id):
  """Клавиатура меню редактирования"""
  keyboard = [
    [InlineKeyboardButton('📝 Изменить название', callback_data=f'edit_title_{task_id}')],
    [InlineKeyboardButton('📅 Изменить дату', callback_data=f'edit_date_{task_id}')],
    [InlineKeyboardButton('⏰ Изменить время', callback_data=f'edit_time_{task_id}')],
    [InlineKeyboardButton('❌ Отмена', callback_data=f'cancel_edit_{task_id}')]
  ]
  return InlineKeyboardMarkup(keyboard)

def get_extend_menu_keyboard(task_id):
  keyboard = [[InlineKeyboardButton('⏱️ +1 час',callback_data=f'''extend_1h_{task_id}''')],[InlineKeyboardButton('📅 Завтра',callback_data=f'''extend_tomorrow_{task_id}''')],[InlineKeyboardButton('📅 Послезавтра',callback_data=f'''extend_dayafter_{task_id}''')],[InlineKeyboardButton('📅 Ввести свою дату',callback_data=f'''extend_custom_{task_id}''')],[InlineKeyboardButton('❌ Отмена',callback_data=f'''cancel_extend_{task_id}''')]]
  return InlineKeyboardMarkup(keyboard)

def get_extend_confirmation_keyboard(task_id,extension_type,extension_text):
  keyboard = [[InlineKeyboardButton(f'''✅ Да, продлить на {extension_text}''',callback_data=f'''confirm_extend_{extension_type}_{task_id}'''),InlineKeyboardButton('❌ Нет, отменить',callback_data=f'''cancel_extend_{task_id}''')]]
  return InlineKeyboardMarkup(keyboard)

async def start(update: Update,context: ContextTypes.DEFAULT_TYPE):
  welcome_text = '''
🎯 <b>Добро пожаловать в Simple Reminder Bot!</b>

Я помогу вам не забывать о важных делах!

<b>Простая система:</b>
1. 📝 Название напоминания
2. 📅 Дата напоминания
3. ⏰ Время напоминания

<b>Улучшенная система напоминаний:</b>
• ⏰ За 2 часа до дедлайна - первое уведомление
• 🔔 После дедлайна - напоминания каждые 30 минут
• ✅ Кнопка "Выполнено" во всех уведомлениях
• ⏱️ <b>НОВОЕ:</b> Возможность продления напоминаний!

<b>Поддерживаемые форматы:</b>
• <b>Дата:</b> 2024-12-31, 02-10-2025, 02.10.2025, сегодня, завтра, понедельник, пн
• <b>Время:</b> 14:30, 09:00, 18:45
    '''
  await update.message.reply_text(welcome_text,reply_markup=get_main_keyboard(),parse_mode='HTML')

async def handle_message(update: Update,context: ContextTypes.DEFAULT_TYPE):
  text = update.message.text
  if text == '📝 Добавить напоминание':
    await add_reminder_start(update,context)
    return None
  else:
    if text == '📋 Мои напоминания':
      await show_my_reminders(update,context)
      return None
    else:
      if text == '📋 Мои задачи':
        await show_my_tasks(update,context)
        return None
      else:
        if text == '🗑️ Удалить напоминание':
          await delete_reminder_start(update,context)
          return None
        else:
          if text == 'ℹ️ Помощь':
            await show_help(update,context)
            return None
          else:
            if text == '❌ Отмена':
              await cancel(update,context)
              return None
            else:
              state = context.user_data.get('state')
              if state == WAITING_TITLE:
                await process_title(update,context)
                return None
              else:
                if state == WAITING_DATE:
                  await process_custom_date(update,context)
                  return None
                else:
                  if state == WAITING_TIME:
                    await process_custom_time(update,context)
                    return None
                  else:
                    if state == 'waiting_extend_date':
                      await process_custom_date_extend(update,context)
                      return None
                    else:
                      if state == 'waiting_extend_time':
                        await process_custom_time_extend(update,context)
                        return None
                      else:
                        if state == 'waiting_extend_date_input':
                          await process_custom_date_extend(update,context)
                          return None
                        else:
                          if state == 'waiting_extend_time_input':
                            await process_custom_time_extend(update,context)
                            return None
                          else:
                            if state == WAITING_EDIT_TITLE:
                              await process_edit_title(update,context)
                              return None
                            else:
                              if state == WAITING_EDIT_DATE:
                                await process_edit_date(update,context)
                                return None
                              else:
                                if state == WAITING_EDIT_TIME:
                                  await process_edit_time(update,context)
                                  return None
                                else:
                                  await update.message.reply_text('Не понимаю команду. Используйте кнопки ниже 👇',reply_markup=get_main_keyboard())
                                  return None

async def process_custom_date_extend(update: Update,context: ContextTypes.DEFAULT_TYPE):
  text = update.message.text
  task_id = context.user_data.get('extending_task_id')
  if not task_id:
    await update.message.reply_text('❌ Ошибка: задача не найдена')
    return None
  else:
    parsed_date = parse_date(text)
    if not parsed_date:
      await update.message.reply_text('❌ Неверный формат даты!\nИспользуйте быстрые кнопки:',reply_markup=get_date_inline_keyboard())
      return None
    else:
      if parsed_date < datetime.now().date():
        await update.message.reply_text('❌ Дата должна быть в будущем! Выберите другую дату:',reply_markup=get_date_inline_keyboard())
        return None
      else:
        selected_date = parsed_date.strftime('%Y-%m-%d')
        context.user_data['extend_date'] = selected_date
        context.user_data['state'] = 'waiting_extend_time'
        await update.message.reply_text(f'''📅 <b>Дата установлена:</b> {selected_date}

⏰ Введите время в формате ЧЧ:ММ:''',parse_mode='HTML')
        return None

async def process_custom_time_extend(update: Update,context: ContextTypes.DEFAULT_TYPE):
  text = update.message.text
  task_id = context.user_data.get('extending_task_id')
  extend_date = context.user_data.get('extend_date')
  if not task_id or not extend_date:
    await update.message.reply_text('❌ Ошибка: данные не найдены')
    return None
  else:
    task = get_task_by_id(task_id)
    if not task:
      await update.message.reply_text('❌ Задача не найдена')
      return None
    else:
      title = task[2]
      old_date = task[3]
      old_time = task[4]
      parsed_time = parse_time(text)
      if not parsed_time:
        await update.message.reply_text('❌ Неверный формат времени!\nИспользуйте формат: ЧЧ:ММ (например: 14:30)')
        return None
      else:
        success,new_task_id = extend_task(task_id,'custom',extend_date,parsed_time)
        if success:
          new_task = get_task_by_id(new_task_id) if new_task_id else None
          if new_task:
            new_date = new_task[3]
            new_time = new_task[4]
            extended_count = new_task[8]
            success_text = f'''
✅ <b>Напоминание продлено!</b>

📝 <b>{title}</b>\n📅 <b>Старая дата:</b> {old_date} {old_time}\n📅 <b>Новая дата:</b> {new_date} {new_time}\n🔢 <b>Количество продлений:</b> {extended_count}\n'''
            await update.message.reply_text(success_text,parse_mode='HTML',reply_markup=get_main_keyboard())
          else:
            await update.message.reply_text('✅ Напоминание продлено!',parse_mode='HTML',reply_markup=get_main_keyboard())

        else:
          await update.message.reply_text('❌ Ошибка при продлении. Дата должна быть в будущем!',reply_markup=get_main_keyboard())

        context.user_data.clear()
        return None

async def handle_button_click(update: Update,context: ContextTypes.DEFAULT_TYPE):
  query = update.callback_query
  await query.answer()
  data = query.data
  if data == 'cancel':
    await query.edit_message_text('❌ Диалог отменен.')
    context.user_data.clear()
    return None
  elif data.startswith('list_edit_'):
    # Обработка нажатия на напоминание в списке
    task_id = data[10:]
    task = get_task_by_id(task_id)
    if not task:
      await query.edit_message_text('❌ Напоминание не найдено', reply_markup=get_main_keyboard())
      return None
    
    _, chat_id, title, reminder_date, reminder_time, _, _, _, extended_count = task
    
    # Убираем секунды из времени
    time_display = str(reminder_time).split(':')[0:2]
    time_str = ':'.join(time_display)
    
    keyboard = [
      [InlineKeyboardButton('✏️ Изменить название', callback_data=f'edit_title_{task_id}')],
      [InlineKeyboardButton('📅 Изменить дату', callback_data=f'edit_date_{task_id}')],
      [InlineKeyboardButton('⏰ Изменить время', callback_data=f'edit_time_{task_id}')],
      [InlineKeyboardButton('🗑️ Удалить', callback_data=f'delete_{task_id}')],
      [InlineKeyboardButton('↩️ Назад к списку', callback_data='back_to_list')]
    ]
    
    extended_text = f"\n🔄 Продлено: {extended_count} раз" if extended_count > 0 else ""
    
    await query.edit_message_text(
      f'''✏️ <b>Управление напоминанием:</b>

📝 <b>{title}</b>
📅 {reminder_date}
⏰ {time_str}{extended_text}

Выберите действие:''',
      parse_mode='HTML',
      reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return None
  elif data == 'back_to_list':
    # Возврат к списку напоминаний
    await show_my_reminders_from_query(query, context)
    return None
  else:
    if data == 'back_to_date':
      if context.user_data.get('state') == 'waiting_extend_date':
        task_id = context.user_data.get('extending_task_id')
        await query.edit_message_text('📅 Выберите дату для продления:',reply_markup=get_date_inline_keyboard())
      else:
        await query.edit_message_text('📅 Выберите дату напоминания:',reply_markup=get_date_inline_keyboard())

      return None
    else:
      if data == 'custom_date':
        if context.user_data.get('state') == 'waiting_extend_date':
          context.user_data['state'] = 'waiting_extend_date_input'
          await query.edit_message_text('''📅 Введите дату для продления:
<b>ГГГГ-ММ-ДД</b> - 2024-12-31
<b>ДД-ММ-ГГГГ</b> - 02-10-2025
<b>ДД.ММ.ГГГГ</b> - 02.10.2025
<b>ДД/ММ/ГГГГ</b> - 02/10/2025

<b>Или другие форматы:</b>
• Сегодня
• Завтра
• Понедельник
• Чт

Или используйте быстрые кнопки:''',reply_markup=get_date_inline_keyboard(),parse_mode='HTML')
        else:
          context.user_data['state'] = WAITING_DATE
          await query.edit_message_text('''📅 Введите дату в формате:
<b>ГГГГ-ММ-ДД</b> - 2024-12-31
<b>ДД-ММ-ГГГГ</b> - 02-10-2025
<b>ДД.ММ.ГГГГ</b> - 02.10.2025
<b>ДД/ММ/ГГГГ</b> - 02/10/2025

<b>Или другие форматы:</b>
• Сегодня
• Завтра
• Понедельник
• Четверг
• Пт

Или используйте быстрые кнопки:''',reply_markup=get_date_inline_keyboard(),parse_mode='HTML')

        return None
      else:
        if data.startswith('extend_menu_'):
          print('DEBUG: Обработка extend_menu_')
          task_id = data.split('_')[2]
          task = get_task_by_id(task_id)
          if task:
            title = task[2]
            await query.edit_message_text(f'''⏱️ <b>Продление напоминания:</b>

📝 <b>{title}</b>

Выберите вариант продления:''',parse_mode='HTML',reply_markup=get_extend_menu_keyboard(task_id))

          return None
        else:
          if data == 'custom_time':
            if context.user_data.get('state') == 'waiting_extend_time':
              context.user_data['state'] = 'waiting_extend_time_input'
              await query.edit_message_text('''⏰ Введите время для продления в формате:
<b>ЧЧ:ММ</b> - 14:30, 09:00, 18:45

Или используйте быстрые кнопки:''',reply_markup=get_time_inline_keyboard(),parse_mode='HTML')
            else:
              context.user_data['state'] = WAITING_TIME
              await query.edit_message_text('''⏰ Введите время в формате:
<b>ЧЧ:ММ</b> - 14:30, 09:00, 18:45

Или используйте быстрые кнопки:''',reply_markup=get_time_inline_keyboard(),parse_mode='HTML')

            return None
          else:
            if data.startswith('date_'):
              selected_date = data[5:]
              if context.user_data.get('state') == 'waiting_extend_date':
                task_id = context.user_data.get('extending_task_id')
                if task_id:
                  context.user_data['extend_date'] = selected_date
                  context.user_data['state'] = 'waiting_extend_time'
                  await query.edit_message_text(f'''📅 <b>Дата установлена:</b> {selected_date}

⏰ Теперь выберите время:''',reply_markup=get_time_inline_keyboard(),parse_mode='HTML')

              else:
                context.user_data['reminder_date'] = selected_date
                context.user_data['state'] = WAITING_TIME
                await query.edit_message_text(f'''📅 <b>Дата установлена:</b> {selected_date}

⏰ Теперь выберите время напоминания:''',reply_markup=get_time_inline_keyboard(),parse_mode='HTML')

              return None
            else:
              if data.startswith('day_'):
                day_num = int(data[4:])
                now = datetime.now()
                current_day = now.weekday()
                days_ahead = day_num-current_day
                if days_ahead <= 0:
                  days_ahead += 7

                target_date = now+timedelta(days=days_ahead)
                selected_date = target_date.strftime('%Y-%m-%d')
                if context.user_data.get('state') == 'waiting_extend_date':
                  task_id = context.user_data.get('extending_task_id')
                  if task_id:
                    context.user_data['extend_date'] = selected_date
                    context.user_data['state'] = 'waiting_extend_time'
                    day_names = ['Понедельник','Вторник','Среда','Четверг','Пятница','Суббота','Воскресенье']
                    day_name = day_names[day_num]
                    await query.edit_message_text(f'''📅 <b>Дата установлена:</b> {selected_date} ({day_name})

⏰ Теперь выберите время:''',reply_markup=get_time_inline_keyboard(),parse_mode='HTML')

                else:
                  context.user_data['reminder_date'] = selected_date
                  context.user_data['state'] = WAITING_TIME
                  day_names = ['Понедельник','Вторник','Среда','Четверг','Пятница','Суббота','Воскресенье']
                  day_name = day_names[day_num]
                  await query.edit_message_text(f'''📅 <b>Дата установлена:</b> {selected_date} ({day_name})

⏰ Теперь выберите время напоминания:''',reply_markup=get_time_inline_keyboard(),parse_mode='HTML')

                return None
              else:
                if data.startswith('time_'):
                  selected_time = data[5:]
                  if context.user_data.get('state') == 'waiting_extend_time':
                    task_id = context.user_data.get('extending_task_id')
                    extend_date = context.user_data.get('extend_date')
                    if task_id and extend_date:
                      task = get_task_by_id(task_id)
                      if not task:
                        await query.edit_message_text('❌ Задача не найдена')
                        return None
                      else:
                        title = task[2]
                        old_date = task[3]
                        old_time = task[4]
                        success,new_task_id = extend_task(task_id,'custom',extend_date,selected_time)
                        if success:
                          new_task = get_task_by_id(new_task_id) if new_task_id else None
                          if new_task:
                            new_date = new_task[3]
                            new_time = new_task[4]
                            extended_count = new_task[8]
                            success_text = f'''
    ✅ <b>Напоминание продлено!</b>

    📝 <b>{title}</b>\n    📅 <b>Старая дата:</b> {old_date} {old_time}\n    📅 <b>Новая дата:</b> {new_date} {new_time}\n    🔢 <b>Количество продлений:</b> {extended_count}\n    '''
                            await query.edit_message_text(success_text,parse_mode='HTML')
                          else:
                            await query.edit_message_text('✅ Напоминание продлено!',parse_mode='HTML')

                        else:
                          await query.edit_message_text('❌ Ошибка при продлении. Дата должна быть в будущем!',parse_mode='HTML')

                        context.user_data.clear()

                    return None
                  else:
                    await complete_reminder_creation(query,context,selected_time)
                    return None

                else:
                  if data.startswith('extend_1h_'):
                    task_id = data.split('_')[2]
                    await process_extend_option(query,context,task_id,'1h')
                    return None
                  else:
                    if data.startswith('extend_tomorrow_'):
                      task_id = data.split('_')[2]
                      await process_extend_option(query,context,task_id,'tomorrow')
                      return None
                    else:
                      if data.startswith('extend_dayafter_'):
                        task_id = data.split('_')[2]
                        await process_extend_option(query,context,task_id,'dayafter')
                        return None
                      else:
                        if data.startswith('extend_custom_'):
                          task_id = data.split('_')[2]
                          context.user_data['extending_task_id'] = task_id
                          context.user_data['state'] = 'waiting_extend_date'
                          await query.edit_message_text('📅 Выберите дату для продления:',reply_markup=get_date_inline_keyboard())
                          return None
                        else:
                          if data.startswith('cancel_extend_'):
                            task_id = data.split('_')[2]
                            task = get_task_by_id(task_id)
                            if task:
                              title = task[2]
                              reminder_date = task[3]
                              reminder_time = task[4]
                              reminder_datetime = datetime.strptime(f'''{reminder_date} {reminder_time}''','%Y-%m-%d %H:%M')
                              current_time = datetime.now()
                              if reminder_datetime <= current_time:
                                time_passed = current_time-reminder_datetime
                                hours_passed = int(time_passed.total_seconds()//3600)
                                minutes_passed = int(time_passed.total_seconds()%3600//60)
                                message = f'''
🔴 <b>ПРОСРОЧЕНО!</b>

📝 <b>{title}</b>\n⏰ Дедлайн был: {reminder_date} {reminder_time}\n⏱️ Прошло времени: {hours_passed}ч {minutes_passed}м\n'''
                              else:
                                time_until = reminder_datetime-current_time
                                hours_until = int(time_until.total_seconds()//3600)
                                minutes_until = int(time_until.total_seconds()%3600//60)
                                message = f'''
🟡 <b>НАПОМИНАНИЕ</b>

📝 <b>{title}</b>\n⏰ Дедлайн: {reminder_date} {reminder_time}\n🕐 Осталось: {hours_until}ч {minutes_until}м\n'''

                              await query.edit_message_text(message,parse_mode='HTML',reply_markup=get_reminder_keyboard(task_id))

                            return None
                          else:
                            if data.startswith('day_'):
                              day_num = int(data[4:])
                              now = datetime.now()
                              current_day = now.weekday()
                              days_ahead = day_num-current_day
                              if days_ahead <= 0:
                                days_ahead += 7

                              target_date = now+timedelta(days=days_ahead)
                              selected_date = target_date.strftime('%Y-%m-%d')
                              context.user_data['reminder_date'] = selected_date
                              day_names = ['Понедельник','Вторник','Среда','Четверг','Пятница','Суббота','Воскресенье']
                              day_name = day_names[day_num]
                              await query.edit_message_text(f'''📅 <b>Дата установлена:</b> {selected_date} ({day_name})

⏰ Теперь выберите время напоминания:''',reply_markup=get_time_inline_keyboard(),parse_mode='HTML')
                              return None
                            else:
                              if data.startswith('time_'):
                                selected_time = data[5:]
                                if context.user_data.get('state') == 'waiting_extend_time':
                                  task_id = context.user_data.get('extending_task_id')
                                  extend_date = context.user_data.get('extend_date')
                                  if task_id and extend_date:
                                    if extend_task(task_id,'custom',extend_date,selected_time):
                                      task = get_task_by_id(task_id)
                                      title = task[2]
                                      new_date = task[3]
                                      new_time = task[4]
                                      extended_count = task[8]
                                      success_text = f'''
    ✅ <b>Напоминание продлено!</b>

    📝 <b>{title}</b>\n    📅 <b>Новая дата:</b> {new_date}\n    ⏰ <b>Новое время:</b> {new_time}\n    🔢 <b>Количество продлений:</b> {extended_count}\n    '''
                                      await query.edit_message_text(success_text,parse_mode='HTML')
                                    else:
                                      await query.edit_message_text('❌ Ошибка при продлении. Дата должна быть в будущем!',parse_mode='HTML')

                                    context.user_data.clear()

                                  return None
                                else:
                                  return None

                              else:
                                # Сначала проверяем специфичные edit_*, потом общий edit_
                                if data.startswith('edit_title_'):
                                  task_id = data[11:]
                                  context.user_data['editing_task_id'] = task_id
                                  context.user_data['state'] = WAITING_EDIT_TITLE
                                  await query.edit_message_text('📝 Введите новое название напоминания:')
                                  return None
                                elif data.startswith('edit_date_'):
                                  task_id = data[10:]
                                  context.user_data['editing_task_id'] = task_id
                                  context.user_data['state'] = WAITING_EDIT_DATE
                                  await query.edit_message_text('📅 Выберите новую дату:', reply_markup=get_date_inline_keyboard())
                                  return None
                                elif data.startswith('edit_time_'):
                                  task_id = data[10:]
                                  context.user_data['editing_task_id'] = task_id
                                  context.user_data['state'] = WAITING_EDIT_TIME
                                  await query.edit_message_text('⏰ Выберите новое время:', reply_markup=get_time_inline_keyboard())
                                  return None
                                elif data.startswith('edit_'):
                                  # Обработка редактирования (общий случай edit_{task_id})
                                  task_id = data[5:]
                                  task = get_task_by_id(task_id)
                                  if task:
                                    title = task[2]
                                    reminder_date = task[3]
                                    reminder_time = task[4]
                                    await query.edit_message_text(
                                      f'''✏️ <b>Редактирование напоминания:</b>

📝 <b>{title}</b>
📅 {reminder_date} ⏰ {reminder_time}

Что хотите изменить?''',
                                      parse_mode='HTML',
                                      reply_markup=get_edit_menu_keyboard(task_id)
                                    )
                                  else:
                                    await query.answer('❌ Задача не найдена', show_alert=True)
                                  return None
                                elif data == 'cancel_edit':
                                  await query.edit_message_text('❌ Редактирование отменено.')
                                  context.user_data.clear()
                                  return None
                                elif data.startswith('cancel_edit_'):
                                  task_id = data[12:]
                                  task = get_task_by_id(task_id)
                                  if task:
                                    title = task[2]
                                    reminder_date = task[3]
                                    reminder_time = task[4]
                                    await query.edit_message_text(
                                      f'''✏️ <b>Редактирование напоминания:</b>

📝 <b>{title}</b>
📅 {reminder_date} ⏰ {reminder_time}

Что хотите изменить?''',
                                      parse_mode='HTML',
                                      reply_markup=get_edit_menu_keyboard(task_id)
                                    )
                                  return None
                                elif data.startswith('done_'):
                                  task_id = data[5:]
                                  chat_id = query.message.chat_id
                                  if delete_task(chat_id,task_id):
                                    await query.edit_message_text('✅ Задача отмечена как выполненная и удалена из напоминаний!',reply_markup=None)
                                    return None
                                  else:
                                    await query.answer('❌ Ошибка при удалении задачи',show_alert=True)
                                    return None

                                else:
                                  if data.startswith('delete_'):
                                    task_id = data[7:]  # UUID строка из Supabase
                                    chat_id = query.message.chat_id
                                    if delete_task(chat_id,task_id):
                                      # Показываем сообщение и обновляем список
                                      await query.answer('✅ Напоминание удалено!', show_alert=False)
                                      # Показываем обновлённый список напоминаний
                                      await query.edit_message_text('⏳ Загружаю обновлённый список...')
                                      await delete_reminder_start_from_context(query, context, chat_id)
                                      return None
                                    else:
                                      await query.edit_message_text('❌ Ошибка при удалении напоминания.')
                                      return None

                                  else:
                                    if data == 'cancel_delete':
                                      await query.edit_message_text('❌ Удаление отменено.')
                                      return None
                                    else:
                                      if data.startswith('extend_'):
                                        if data.startswith('extend_menu_'):
                                          return None
                                        else:
                                          if data.startswith('extend_1h_'):
                                            return None
                                          else:
                                            if data.startswith('extend_tomorrow_'):
                                              return None
                                            else:
                                              if data.startswith('extend_dayafter_'):
                                                return None
                                              else:
                                                if data.startswith('extend_custom_'):
                                                  return None
                                                else:
                                                  parts = data.split('_')
                                                  if len(parts) >= 3:
                                                    extension_type = parts[1]
                                                    task_id = int(parts[2])
                                                    task = get_task_by_id(task_id)
                                                    if not task:
                                                      await query.answer('❌ Задача не найдена',show_alert=True)
                                                      return None
                                                    else:
                                                      extension_texts = {'1h':'1 час','tomorrow':'завтра','dayafter':'послезавтра','3h':'3 часа','1d':'1 день','3d':'3 дня','7d':'7 дней'}
                                                      extension_text = extension_texts.get(extension_type,extension_type)
                                                      title = task[2]
                                                      reminder_date = task[3]
                                                      reminder_time = task[4]
                                                      confirm_text = f'''
    ⏱️ <b>Продление напоминания</b>

    📝 <b>{title}</b>\n    📅 Текущая дата: {reminder_date}\n    ⏰ Текущее время: {reminder_time}

    Вы действительно хотите перенести это напоминание на <b>{extension_text}</b>?\n    '''
                                                      await query.edit_message_text(confirm_text,parse_mode='HTML',reply_markup=get_extend_confirmation_keyboard(task_id,extension_type,extension_text))
                                                      return None

                                                  else:
                                                    return None

                                      else:
                                        if data.startswith('confirm_extend_'):
                                          parts = data.split('_')
                                          if len(parts) >= 4:
                                            extension_type = parts[2]
                                            task_id = int(parts[3])
                                            task = get_task_by_id(task_id)
                                            if not task:
                                              await query.answer('❌ Задача не найдена',show_alert=True)
                                              return None
                                            else:
                                              title = task[2]
                                              old_date = task[3]
                                              old_time = task[4]
                                              extended_count = task[8]
                                              success,new_task_id = extend_task(task_id,extension_type)
                                              if success:
                                                updated_task = get_task_by_id(new_task_id) if new_task_id else None
                                                if updated_task:
                                                  new_date = updated_task[3]
                                                  new_time = updated_task[4]
                                                  new_extended_count = updated_task[8]
                                                  extension_texts = {'1h':'1 час','tomorrow':'завтра','dayafter':'послезавтра'}
                                                  extension_text = extension_texts.get(extension_type,extension_type)
                                                  new_datetime = datetime.strptime(f'''{new_date} {new_time}''','%Y-%m-%d %H:%M')
                                                  day_of_week = new_datetime.strftime('%A')
                                                  success_text = f'''
    ✅ <b>Напоминание продлено!</b>

    📝 <b>{title}</b>\n    📅 <b>Старая дата:</b> {old_date} {old_time}\n    📅 <b>Новая дата:</b> {new_date} {new_time} ({day_of_week})\n    ⏱️ <b>Продлено на:</b> {extension_text}\n    🔢 <b>Количество продлений:</b> {new_extended_count}

    ⏰ <b>Новая система напоминаний:</b>
    • За 2 часа до нового дедлайна - уведомление
    • После дедлайна - напоминания каждые 30 минут
    '''
                                                  await query.edit_message_text(success_text,parse_mode='HTML')
                                                  return None
                                                else:
                                                  await query.edit_message_text('✅ Напоминание продлено!',parse_mode='HTML')
                                                  return None

                                              else:
                                                await query.edit_message_text('❌ Ошибка при продлении напоминания.',parse_mode='HTML')
                                                return None

                                          else:
                                            return None

                                        else:
                                          if data.startswith('cancel_extend_'):
                                            task_id = data.split('_')[2]
                                            task = get_task_by_id(task_id)
                                            if task:
                                              chat_id = query.message.chat_id
                                              title = task[2]
                                              reminder_date = task[3]
                                              reminder_time = task[4]
                                              reminder_datetime = datetime.strptime(f'''{reminder_date} {reminder_time}''','%Y-%m-%d %H:%M')
                                              current_time = datetime.now()
                                              if reminder_datetime <= current_time:
                                                time_passed = current_time-reminder_datetime
                                                hours_passed = int(time_passed.total_seconds()//3600)
                                                minutes_passed = int(time_passed.total_seconds()%3600//60)
                                                message = f'''
🔴 <b>ПРОСРОЧЕНО!</b>

📝 <b>{title}</b>\n⏰ Дедлайн был: {reminder_date} {reminder_time}\n⏱️ Прошло времени: {hours_passed}ч {minutes_passed}м
❗️ Не забудьте выполнить задачу!
'''
                                                reply_markup = get_reminder_keyboard(task_id,is_overdue=True)
                                              else:
                                                time_until = reminder_datetime-current_time
                                                hours_until = int(time_until.total_seconds()//3600)
                                                minutes_until = int(time_until.total_seconds()%3600//60)
                                                message = f'''
🟡 <b>НАПОМИНАНИЕ: ЧЕРЕЗ 2 ЧАСА ИСТЕКАЕТ СРОК!</b>

📝 <b>{title}</b>\n⏰ Дедлайн: {reminder_date} {reminder_time}\n🕐 Осталось: {hours_until}ч {minutes_until}м\n'''
                                                reply_markup = get_reminder_keyboard(task_id,is_overdue=False)

                                              await query.edit_message_text(message,parse_mode='HTML',reply_markup=reply_markup)
                                              return None

                                          else:
                                            return None
                                            return None

async def process_extend_option(query,context,task_id,extension_type):
  print(f'''DEBUG process_extend_option: task_id={task_id}, type={extension_type}''')
  task = get_task_by_id(task_id)
  if not task:
    print(f'''DEBUG: Задача {task_id} не найдена в get_task_by_id''')
    await query.answer('❌ Задача не найдена',show_alert=True)
    return None
  else:
    extension_texts = {'1h':'1 час','tomorrow':'завтра','dayafter':'послезавтра'}
    extension_text = extension_texts.get(extension_type,extension_type)
    success,new_task_id = extend_task(task_id,extension_type)
    print(f'''DEBUG: extend_task вернула success={success}, new_task_id={new_task_id}''')
    if success:
      updated_task = get_task_by_id(new_task_id) if new_task_id else None
      if updated_task:
        title = updated_task[2]
        new_date = updated_task[3]
        new_time = updated_task[4]
        extended_count = updated_task[8]
        success_text = f'''\n✅ <b>Напоминание продлено на {extension_text}!</b>

📝 <b>{title}</b>\n📅 <b>Новая дата:</b> {new_date}\n⏰ <b>Новое время:</b> {new_time}\n🔢 <b>Количество продлений:</b> {extended_count}

⏰ <b>Новая система напоминаний:</b>
• За 2 часа до нового дедлайна - уведомление
• После дедлайна - напоминания каждые 30 минут
'''
        await query.edit_message_text(success_text,parse_mode='HTML')
        return None
      else:
        await query.edit_message_text('✅ Напоминание продлено!',parse_mode='HTML')
        return None

    else:
      await query.edit_message_text('❌ Ошибка при продлении напоминания.',parse_mode='HTML')
      return None

async def complete_reminder_creation(query,context,selected_time):
  chat_id = query.message.chat_id
  title = context.user_data.get('title','')
  selected_date = context.user_data.get('reminder_date','')
  reminder_datetime_str = f'''{selected_date} {selected_time}'''
  try:
    reminder_datetime = datetime.strptime(reminder_datetime_str,'%Y-%m-%d %H:%M')
    if reminder_datetime <= datetime.now():
      await query.edit_message_text('❌ Время должно быть в будущем! Выберите другое время:',reply_markup=get_time_inline_keyboard())
      return None
    else:
      add_task(chat_id,title,selected_date,selected_time)
      success_text = f'''
✅ <b>Напоминание создано!</b>

📝 <b>Название:</b> {title}\n📅 <b>Дата:</b> {selected_date}\n⏰ <b>Время:</b> {selected_time}\n📅 <b>День недели:</b> {reminder_datetime.strftime('%A')}

🔔 <b>Система напоминаний:</b>
• ⏰ За 2 часа до дедлайна - первое уведомление
• 🔔 После дедлайна - напоминания каждые 30 минут
• ✅ Кнопка \'Выполнено\' во всех уведомлениях
• ⏱️ <b>НОВОЕ:</b> Возможность продления напоминаний!
'''
      await query.edit_message_text(success_text,parse_mode='HTML')
      context.user_data.clear()
      return None

  except ValueError as e:
    print(f'''Ошибка парсинга времени: {e}''')
    await query.edit_message_text('❌ Неверный формат времени! Выберите другое время:',reply_markup=get_time_inline_keyboard())
    return None

async def show_help(update: Update,context: ContextTypes.DEFAULT_TYPE):
  help_text = '''
<b>📖 Простое руководство:</b>

<b>Создание напоминания:</b>
1. Нажмите "📝 Добавить напоминание"
2. Введите название
3. Выберите дату
4. Выберите время

<b>Поддерживаемые форматы даты:</b>
• <b>ГГГГ-ММ-ДД</b> - 2024-12-31
• <b>ДД-ММ-ГГГГ</b> - 02-10-2025
• <b>ДД-ММ</b> - 02-10 (текущий год)
• <b>ДД.ММ.ГГГГ</b> - 02.10.2025
• <b>ДД/ММ/ГГГГ</b> - 02/10/2025
• <b>Сегодня</b> - на сегодня
• <b>Завтра</b> - на завтра
• <b>Понедельник</b> - на ближайший понедельник
• <b>Чт</b> - на ближайший четверг

<b>Поддерживаемые форматы времени:</b>
• <b>ЧЧ:ММ</b> - 14:30, 09:00, 18:45

<b>Улучшенная система напоминаний:</b>
🟡 <b>За 2 часа до дедлайна:</b> Первое уведомление
🔴 <b>После дедлайна:</b> "ПРОСРОЧЕНО! + сколько времени прошло"
    🔔 Напоминания каждые 30 минут
    ✅ Кнопка "Выполнено" во всех уведомлениях

<b>📅 НОВАЯ ФУНКЦИЯ: ПРОДЛЕНИЕ НАПОМИНАНИЙ</b>
Когда вы получаете уведомление о напоминании, вы можете:
• ⏱️ Перенести на 1 час, 3 часа
• 📅 Перенести на 1 день, 3 дня, 7 дней
• ✅ Отметить как выполненное

<b>Дни недели:</b>
Понедельник, Вторник, Среда, Четверг, Пятница, Суббота, Воскресенье
(или сокращенно: Пн, Вт, Ср, Чт, Пт, Сб, Вс)
    '''
  await update.message.reply_text(help_text,reply_markup=get_main_keyboard(),parse_mode='HTML')

async def add_reminder_start(update: Update,context: ContextTypes.DEFAULT_TYPE):
  context.user_data.clear()
  context.user_data['state'] = WAITING_TITLE
  await update.message.reply_text('📝 <b>Шаг 1 из 3</b>\nВведите название напоминания:',reply_markup=get_cancel_keyboard(),parse_mode='HTML')

async def process_title(update: Update,context: ContextTypes.DEFAULT_TYPE):
  context.user_data['title'] = update.message.text
  context.user_data['state'] = WAITING_DATE
  await update.message.reply_text('📅 <b>Шаг 2 из 3</b>\nВыберите дату напоминания:',reply_markup=get_date_inline_keyboard(),parse_mode='HTML')

async def process_custom_date(update: Update,context: ContextTypes.DEFAULT_TYPE):
  text = update.message.text
  parsed_date = parse_date(text)
  if not parsed_date:
    await update.message.reply_text('''❌ Неверный формат даты!
Используйте:
<b>ГГГГ-ММ-ДД</b> - 2024-12-31
<b>ДД-ММ-ГГГГ</b> - 02-10-2025
<b>ДД.ММ.ГГГГ</b> - 02.10.2025
<b>ДД/ММ/ГГГГ</b> - 02/10/2025

<b>Или другие форматы:</b>
• Сегодня
• Завтра
• Понедельник
• Чт

Или используйте быстрые кнопки:''',reply_markup=get_date_inline_keyboard(),parse_mode='HTML')
    return None
  else:
    if parsed_date < datetime.now().date():
      await update.message.reply_text('❌ Дата должна быть в будущем! Выберите другую дату:',reply_markup=get_date_inline_keyboard())
      return None
    else:
      selected_date = parsed_date.strftime('%Y-%m-%d')
      context.user_data['reminder_date'] = selected_date
      context.user_data['state'] = WAITING_TIME
      await update.message.reply_text(f'''📅 <b>Дата установлена:</b> {selected_date}

⏰ <b>Шаг 3 из 3</b>
Выберите время напоминания:''',reply_markup=get_time_inline_keyboard(),parse_mode='HTML')
      return None

async def process_custom_time(update: Update,context: ContextTypes.DEFAULT_TYPE):
  text = update.message.text
  chat_id = update.effective_chat.id
  title = context.user_data.get('title','')
  selected_date = context.user_data.get('reminder_date','')
  parsed_time = parse_time(text)
  if not parsed_time:
    await update.message.reply_text('''❌ Неверный формат времени!
Используйте формат: <b>ЧЧ:ММ</b>
<b>Пример:</b> 14:30, 09:00, 18:45

Или используйте быстрые кнопки:''',reply_markup=get_time_inline_keyboard(),parse_mode='HTML')
    return None
  else:
    reminder_datetime_str = f'''{selected_date} {parsed_time}'''
    try:
      reminder_datetime = datetime.strptime(reminder_datetime_str,'%Y-%m-%d %H:%M')
      if reminder_datetime <= datetime.now():
        await update.message.reply_text('❌ Время должно быть в будущем! Выберите другое время:',reply_markup=get_time_inline_keyboard())
        return None
      else:
        add_task(chat_id,title,selected_date,parsed_time)
        success_text = f'''
✅ <b>Напоминание создано!</b>

📝 <b>Название:</b> {title}\n📅 <b>Дата:</b> {selected_date}\n⏰ <b>Время:</b> {parsed_time}\n📅 <b>День недели:</b> {reminder_datetime.strftime('%A')}

🔔 <b>Система напоминаний:</b>
• ⏰ За 2 часа до дедлайна - первое уведомление
• 🔔 После дедлайна - напоминания каждые 30 минут
• ✅ Кнопка \'Выполнено\' во всех уведомлениях
• ⏱️ <b>НОВОЕ:</b> Возможность продления напоминаний!
'''
        await update.message.reply_text(success_text,reply_markup=get_main_keyboard(),parse_mode='HTML')
        context.user_data.clear()
        return None

    except ValueError as e:
      print(f'''Ошибка создания даты: {e}''')
      await update.message.reply_text('❌ Ошибка при создании даты! Выберите другое время:',reply_markup=get_time_inline_keyboard())
      return None

async def delete_reminder_start_from_context(query, context, chat_id):
  """Вспомогательная функция для показа списка удаления (из callback)"""
  tasks = get_user_tasks(chat_id)
  if not tasks:
    await query.edit_message_text('📭 У вас больше нет напоминаний.',reply_markup=get_main_keyboard())
    return None
  else:
    keyboard = []
    for task in tasks:
      task_id, title, reminder_date, reminder_time, extended_count = task
      button_text = f'''{title} - {reminder_date} {reminder_time}'''
      if extended_count > 0:
        button_text += f''' (продлено {extended_count} раз)'''

      if len(button_text) > 50:
        button_text = button_text[:47]+'...'

      keyboard.append([InlineKeyboardButton(button_text,callback_data=f'''delete_{task_id}''')])

    keyboard.append([InlineKeyboardButton('❌ Отмена',callback_data='cancel_delete')])
    tasks_text = '''🗑️ <b>Выберите напоминание для удаления:</b>

'''
    for task in tasks:
      task_id, title, reminder_date, reminder_time, extended_count = task
      tasks_text += f'''• <b>{title}</b>\n'''
      tasks_text += f'''   📅 {reminder_date} ⏰ {reminder_time}'''
      if extended_count > 0:
        tasks_text += f''' 🔄 Продлено: {extended_count} раз\n'''
      tasks_text += '\n'

    await query.edit_message_text(tasks_text,reply_markup=InlineKeyboardMarkup(keyboard),parse_mode='HTML')
    return None

async def process_edit_title(update: Update,context: ContextTypes.DEFAULT_TYPE):
  """Обработка изменения названия"""
  new_title = update.message.text
  task_id = context.user_data.get('editing_task_id')
  print(f'DEBUG process_edit_title: task_id={task_id}, new_title={new_title}')
  
  if not task_id:
    await update.message.reply_text('❌ Ошибка: задача не найдена')
    return None
  
  task = get_task_by_id(task_id)
  if not task:
    await update.message.reply_text('❌ Задача не найдена')
    context.user_data.clear()
    return None
  
  old_title = task[2]
  result = update_reminder(task_id, title=new_title)
  print(f'DEBUG process_edit_title: update_reminder result={result}')
  
  if result:
    await update.message.reply_text(
      f'''✅ <b>Название изменено!</b>

📝 <b>Старое:</b> {old_title}
📝 <b>Новое:</b> {new_title}''',
      parse_mode='HTML',
      reply_markup=get_main_keyboard()
    )
  else:
    await update.message.reply_text('❌ Ошибка при обновлении', reply_markup=get_main_keyboard())
  context.user_data.clear()
  return None

async def process_edit_date(update: Update,context: ContextTypes.DEFAULT_TYPE):
  """Обработка изменения даты"""
  text = update.message.text
  task_id = context.user_data.get('editing_task_id')
  print(f'DEBUG process_edit_date: task_id={task_id}, text={text}')
  
  if not task_id:
    await update.message.reply_text('❌ Ошибка: задача не найдена')
    return None
  
  parsed_date = parse_date(text)
  print(f'DEBUG process_edit_date: parsed_date={parsed_date}')
  
  if not parsed_date:
    await update.message.reply_text('❌ Неверный формат даты!\nИспользуйте быстрые кнопки:', reply_markup=get_date_inline_keyboard())
    return None
  
  if parsed_date < datetime.now().date():
    await update.message.reply_text('❌ Дата должна быть в будущем! Выберите другую дату:', reply_markup=get_date_inline_keyboard())
    return None
  
  new_date = parsed_date.strftime('%Y-%m-%d')
  task = get_task_by_id(task_id)
  if not task:
    await update.message.reply_text('❌ Задача не найдена')
    context.user_data.clear()
    return None
  
  old_date = task[3]
  result = update_reminder(task_id, reminder_date=new_date)
  print(f'DEBUG process_edit_date: update_reminder result={result}')
  
  if result:
    await update.message.reply_text(
      f'''✅ <b>Дата изменена!</b>

📅 <b>Старая:</b> {old_date}
📅 <b>Новая:</b> {new_date}''',
      parse_mode='HTML',
      reply_markup=get_main_keyboard()
    )
  else:
    await update.message.reply_text('❌ Ошибка при обновлении', reply_markup=get_main_keyboard())
  context.user_data.clear()
  return None

async def process_edit_time(update: Update,context: ContextTypes.DEFAULT_TYPE):
  """Обработка изменения времени"""
  text = update.message.text
  task_id = context.user_data.get('editing_task_id')
  print(f'DEBUG process_edit_time: task_id={task_id}, text={text}')
  
  if not task_id:
    await update.message.reply_text('❌ Ошибка: задача не найдена')
    return None
  
  parsed_time = parse_time(text)
  print(f'DEBUG process_edit_time: parsed_time={parsed_time}')
  
  if not parsed_time:
    await update.message.reply_text('❌ Неверный формат времени!\nИспользуйте формат: ЧЧ:ММ (например: 14:30)', reply_markup=get_time_inline_keyboard())
    return None
  
  task = get_task_by_id(task_id)
  if not task:
    await update.message.reply_text('❌ Задача не найдена')
    context.user_data.clear()
    return None
  
  old_time = task[4]
  result = update_reminder(task_id, reminder_time=parsed_time)
  print(f'DEBUG process_edit_time: update_reminder result={result}')
  
  if result:
    await update.message.reply_text(
      f'''✅ <b>Время изменено!</b>

⏰ <b>Старое:</b> {old_time}
⏰ <b>Новое:</b> {parsed_time}''',
      parse_mode='HTML',
      reply_markup=get_main_keyboard()
    )
  else:
    await update.message.reply_text('❌ Ошибка при обновлении', reply_markup=get_main_keyboard())
  context.user_data.clear()
  return None

async def delete_reminder_start(update: Update,context: ContextTypes.DEFAULT_TYPE):
  chat_id = update.effective_chat.id
  tasks = get_user_tasks(chat_id)
  if not tasks:
    await update.message.reply_text('📭 У вас пока нет напоминаний.',reply_markup=get_main_keyboard())
    return None
  else:
    keyboard = []
    for task in tasks:
      task_id, title, reminder_date, reminder_time, extended_count = task
      button_text = f'''{title} - {reminder_date} {reminder_time}'''
      if extended_count > 0:
        button_text += f''' (продлено {extended_count} раз)'''

      if len(button_text) > 50:
        button_text = button_text[:47]+'...'

      keyboard.append([InlineKeyboardButton(button_text,callback_data=f'''delete_{task_id}''')])

    keyboard.append([InlineKeyboardButton('❌ Отмена',callback_data='cancel_delete')])
    tasks_text = '''🗑️ <b>Выберите напоминание для удаления:</b>

'''
    for task in tasks:
      task_id, title, reminder_date, reminder_time, extended_count = task
      tasks_text += f'''• <b>{title}</b>\n'''
      tasks_text += f'''   📅 {reminder_date} ⏰ {reminder_time}'''
      if extended_count > 0:
        tasks_text += f''' 🔄 Продлено: {extended_count} раз\n'''
      tasks_text += '\n'

    await update.message.reply_text(tasks_text,reply_markup=InlineKeyboardMarkup(keyboard),parse_mode='HTML')
    return None

async def cancel(update: Update,context: ContextTypes.DEFAULT_TYPE):
  context.user_data.clear()
  await update.message.reply_text('❌ Диалог отменен.',reply_markup=get_main_keyboard())

async def show_my_reminders(update: Update,context: ContextTypes.DEFAULT_TYPE):
  chat_id = update.effective_chat.id
  tasks = get_user_tasks(chat_id)
  if not tasks:
    await update.message.reply_text('''📭 У вас пока нет напоминаний.

Нажмите «📝 Добавить напоминание» чтобы создать первое!''',reply_markup=get_main_keyboard())
    return None
  else:
    # Создаем клавиатуру с кнопками для каждого напоминания
    keyboard = []
    tasks_text = '''📋 <b>Ваши напоминания:</b>

'''
    
    for i,(task_id,title,reminder_date,reminder_time,extended_count) in enumerate(tasks,1):
      try:
        # Поддержка формата с секундами и без
        time_str = str(reminder_time)
        if len(time_str.split(':')) == 3:
          task_datetime = datetime.strptime(f'''{reminder_date} {time_str}''','%Y-%m-%d %H:%M:%S')
        else:
          task_datetime = datetime.strptime(f'''{reminder_date} {time_str}''','%Y-%m-%d %H:%M')
        day_of_week = task_datetime.strftime('%A')
        now = datetime.now()
        status = '🟢'
        time_until = task_datetime-now
        if task_datetime <= now:
          status = '🔴'
        elif time_until <= timedelta(hours=2):
          status = '🟡'

        # Убираем секунды из времени
        time_display = str(reminder_time).split(':')[0:2]
        time_str_short = ':'.join(time_display)
        
        button_text = f"{status} {title[:20]}{'...' if len(title) > 20 else ''} | {reminder_date} {time_str_short}"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=f'list_edit_{task_id}')])
        
        tasks_text += f'''{i}. {status} <b>{title}</b>
   📅 {reminder_date} ⏰ {time_str_short} ({day_of_week})'''
        if extended_count > 0:
          tasks_text += f''' 🔄 {extended_count}'''
        tasks_text += '''\n\n'''
      except ValueError as e:
        print(f'''Ошибка обработки задачи {task_id}: {e}''')
        button_text = f"⚠️ {title[:20]}{'...' if len(title) > 20 else ''} | {reminder_date}"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=f'list_edit_{task_id}')])
        tasks_text += f'''{i}. ⚠️ <b>{title}</b> (ошибка формата)\n\n'''
        continue

    tasks_text += '\n<i>Нажмите на напоминание, чтобы отредактировать или удалить его</i>'
    await update.message.reply_text(tasks_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
    return None

async def handle_list_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
  """Обработка нажатия на напоминание в списке"""
  query = update.callback_query
  await query.answer()
  data = query.data
  
  if data.startswith('list_edit_'):
    task_id = data[10:]
    task = get_task_by_id(task_id)
    if not task:
      await query.edit_message_text('❌ Напоминание не найдено', reply_markup=get_main_keyboard())
      return None
    
    _, chat_id, title, reminder_date, reminder_time, _, _, _, extended_count = task
    
    # Убираем секунды из времени
    time_display = str(reminder_time).split(':')[0:2]
    time_str = ':'.join(time_display)
    
    keyboard = [
      [InlineKeyboardButton('✏️ Изменить название', callback_data=f'edit_title_{task_id}')],
      [InlineKeyboardButton('📅 Изменить дату', callback_data=f'edit_date_{task_id}')],
      [InlineKeyboardButton('⏰ Изменить время', callback_data=f'edit_time_{task_id}')],
      [InlineKeyboardButton('🗑️ Удалить', callback_data=f'delete_{task_id}')],
      [InlineKeyboardButton('↩️ Назад к списку', callback_data='back_to_list')]
    ]
    
    extended_text = f"\n🔄 Продлено: {extended_count} раз" if extended_count > 0 else ""
    
    await query.edit_message_text(
      f'''✏️ <b>Управление напоминанием:</b>

📝 <b>{title}</b>
📅 {reminder_date}
⏰ {time_str}{extended_text}

Выберите действие:''',
      parse_mode='HTML',
      reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return None
  elif data == 'back_to_list':
    # Возврат к списку напоминаний
    await show_my_reminders_from_query(query, context)
    return None

async def show_my_reminders_from_query(query, context: ContextTypes.DEFAULT_TYPE):
  """Показ списка напоминаний из callback query"""
  chat_id = query.message.chat_id
  tasks = get_user_tasks(chat_id)
  if not tasks:
    await query.edit_message_text('📭 У вас пока нет напоминаний.', reply_markup=get_main_keyboard())
    return None
  
  keyboard = []
  tasks_text = '''📋 <b>Ваши напоминания:</b>\n\n'''
  
  for i,(task_id,title,reminder_date,reminder_time,extended_count) in enumerate(tasks,1):
    try:
      time_str = str(reminder_time)
      if len(time_str.split(':')) == 3:
        task_datetime = datetime.strptime(f'''{reminder_date} {time_str}''','%Y-%m-%d %H:%M:%S')
      else:
        task_datetime = datetime.strptime(f'''{reminder_date} {time_str}''','%Y-%m-%d %H:%M')
      day_of_week = task_datetime.strftime('%A')
      now = datetime.now()
      status = '🟢'
      time_until = task_datetime-now
      if task_datetime <= now:
        status = '🔴'
      elif time_until <= timedelta(hours=2):
        status = '🟡'

      time_display = str(reminder_time).split(':')[0:2]
      time_str_short = ':'.join(time_display)
      
      button_text = f"{status} {title[:20]}{'...' if len(title) > 20 else ''} | {reminder_date} {time_str_short}"
      keyboard.append([InlineKeyboardButton(button_text, callback_data=f'list_edit_{task_id}')])
      keyboard.append([InlineKeyboardButton('✏️ Редактировать', callback_data=f'list_edit_{task_id}')])
      
      tasks_text += f'''{i}. {status} <b>{title}</b>\n   📅 {reminder_date} ⏰ {time_str_short} ({day_of_week})'''
      if extended_count > 0:
        tasks_text += f''' 🔄 {extended_count}'''
      tasks_text += '''\n\n'''
    except ValueError as e:
      print(f'''Ошибка обработки задачи {task_id}: {e}''')
      button_text = f"⚠️ {title[:20]}{'...' if len(title) > 20 else ''}"
      keyboard.append([InlineKeyboardButton(button_text, callback_data=f'list_edit_{task_id}')])
      keyboard.append([InlineKeyboardButton('✏️ Редактировать', callback_data=f'list_edit_{task_id}')])
      tasks_text += f'''{i}. ⚠️ <b>{title}</b>\n\n'''
      continue

  tasks_text += '\n<i>Нажмите на напоминание для редактирования</i>'
  await query.edit_message_text(tasks_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

async def show_my_tasks(update: Update,context: ContextTypes.DEFAULT_TYPE):
  """Показывает задачи из мобильного приложения (из Supabase)"""
  chat_id = update.effective_chat.id
  
  await update.message.reply_text('⏳ Загружаю задачи из приложения...',reply_markup=get_main_keyboard())
  
  # Получаем задачи из Supabase (все, без фильтра)
  print(f'DEBUG: Запрос задач для chat_id={chat_id}')
  tasks = get_tasks_from_supabase()
  print(f'DEBUG: Получено задач: {len(tasks)}')
  
  # Форматируем сообщение
  tasks_text = format_tasks_message(tasks)
  
  await update.message.reply_text(tasks_text,reply_markup=get_main_keyboard(),parse_mode='HTML')
  return None

def send_reminders_sync():
  """Синхронная версия для фонового потока"""
  import sys
  import time
  import requests
  print('DEBUG: Синхронная функция send_reminders запущена!', flush=True)
  
  while True:
    try:
      print('='*30, flush=True)
      print('DEBUG: Начинаю проверку напоминаний...', flush=True)
      # Получаем напоминания из SQLite и Supabase
      all_tasks = get_all_reminders_for_sending()
      print(f'DEBUG: Найдено {len(all_tasks)} напоминаний', flush=True)
      # Используем московское время (UTC+3)
      current_time = datetime.utcnow() + timedelta(hours=3)
      print(f'DEBUG: Текущее время (Москва): {current_time}', flush=True)
      for t in all_tasks:
        rd = t.get('reminder_date')
        rt = t.get('reminder_time')
        cid = t.get('chat_id')
        print(f'  - {t.get("title")} на {rd} {rt} для chat_id={cid} (source={t.get("source")})', flush=True)
      
      # Обрабатываем каждое напоминание
      for task in all_tasks:
        try:
          task_id = task['id']
          chat_id = task['chat_id']
          title = task['title']
          reminder_date = task['reminder_date']
          reminder_time = task['reminder_time']
          last_reminder = task.get('last_reminder')
          reminder_stage = task.get('reminder_stage', 0)
          extended_count = task.get('extended_count', 0)
          source = task.get('source', 'sqlite')
          
          if not reminder_date or not reminder_time:
            continue
          
          # Поддержка формата с секундами и без
          time_str = str(reminder_time)
          if len(time_str.split(':')) == 3:
            reminder_datetime = datetime.strptime(f'''{reminder_date} {time_str}''','%Y-%m-%d %H:%M:%S')
          else:
            reminder_datetime = datetime.strptime(f'''{reminder_date} {time_str}''','%Y-%m-%d %H:%M')
          
          time_diff = reminder_datetime - current_time
          hours_until_deadline = time_diff.total_seconds() / 3600
          should_send = False
          message = ''
          new_stage = reminder_stage
          is_overdue = False
          
          if reminder_stage == 0:
            if 0 < hours_until_deadline <= 2:
              hours = int(hours_until_deadline)
              minutes = int(hours_until_deadline - hours * 60)
              message = f'''🟡 <b>НАПОМИНАНИЕ: ЧЕРЕЗ 2 ЧАСА ИСТЕКАЕТ СРОК!</b>

📝 <b>{title}</b>
⏰ Дедлайн: {format_date_russian(reminder_date)} {reminder_time}
🕐 Осталось: {hours}ч {minutes}м'''
              new_stage = 1
              should_send = True
              is_overdue = False
            elif hours_until_deadline <= 0:
              # Проверяем 30-минутный интервал для просроченных напоминаний
              if last_reminder:
                try:
                  # Убираем timezone и парсим вручную
                  clean_time = last_reminder.replace('+03:00', '').replace('Z', '').strip()
                  # Меняем T на пробел для парсинга
                  clean_time = clean_time.replace('T', ' ')
                  # Убираем микросекунды если есть
                  if '.' in clean_time:
                    clean_time = clean_time.split('.')[0]
                  last_reminder_dt = datetime.strptime(clean_time, '%Y-%m-%d %H:%M:%S')
                  # Делаем current_time тоже naive для сравнения
                  current_time_naive = current_time.replace(tzinfo=None)
                  time_since_last = current_time_naive - last_reminder_dt
                  if time_since_last >= timedelta(minutes=30):
                    message = f'''🔴 <b>ВНИМАНИЕ: СРОК ИСТЁК!</b>

📝 <b>{title}</b>
⏰ Дедлайн: {format_date_russian(reminder_date)} {reminder_time}'''
                    new_stage = 2
                    should_send = True
                    is_overdue = True
                    print(f'  -> Просрочка: прошло {time_since_last.total_seconds()/60:.1f} мин, отправляю', flush=True)
                  else:
                    print(f'  -> Просрочка: прошло только {time_since_last.total_seconds()/60:.1f} мин, пропускаю', flush=True)
                    should_send = False
                except Exception as e:
                  print(f'  -> Ошибка парсинга last_reminder: {e}', flush=True)
                  message = f'''🔴 <b>ВНИМАНИЕ: СРОК ИСТЁК!</b>

📝 <b>{title}</b>
⏰ Дедлайн: {format_date_russian(reminder_date)} {reminder_time}'''
                  new_stage = 2
                  should_send = True
                  is_overdue = True
              else:
                # Нет last_reminder - отправляем сразу
                message = f'''🔴 <b>ВНИМАНИЕ: СРОК ИСТЁК!</b>

📝 <b>{title}</b>
⏰ Дедлайн: {format_date_russian(reminder_date)} {reminder_time}'''
                new_stage = 2
                should_send = True
                is_overdue = True
                print(f'  -> Первое просроченное напоминание (stage=0)', flush=True)
          else:
            # Просроченные напоминания - проверяем не чаще чем раз в 30 минут
            if reminder_datetime <= current_time:
              time_passed = current_time - reminder_datetime
              hours_passed = int(time_passed.total_seconds() // 3600)
              minutes_passed = int(time_passed.total_seconds() % 3600 // 60)
              
              # По умолчанию НЕ отправляем
              should_send = False
              
              # Всегда проверяем время с момента последнего напоминания
              if last_reminder:
                try:
                  # Убираем timezone и парсим вручную
                  clean_time = last_reminder.replace('+03:00', '').replace('Z', '').strip()
                  # Меняем T на пробел для парсинга
                  clean_time = clean_time.replace('T', ' ')
                  # Убираем микросекунды если есть
                  if '.' in clean_time:
                    clean_time = clean_time.split('.')[0]
                  last_reminder_time = datetime.strptime(clean_time, '%Y-%m-%d %H:%M:%S')
                  # Делаем current_time тоже naive для сравнения
                  current_time_naive = current_time.replace(tzinfo=None)
                  time_since_last = current_time_naive - last_reminder_time
                  # Отправляем только если прошло 30+ минут
                  if time_since_last >= timedelta(minutes=30):
                    should_send = True
                    print(f'  -> Прошло {time_since_last.total_seconds()/60:.1f} мин, отправляю напоминание', flush=True)
                  else:
                    print(f'  -> Прошло только {time_since_last.total_seconds()/60:.1f} мин, пропускаю', flush=True)
                except Exception as e:
                  print(f'  -> Ошибка парсинга last_reminder: {e}, пропускаю', flush=True)
                  should_send = False
              else:
                # Нет last_reminder - первый раз для просрочки
                should_send = True
                print(f'  -> Первое просроченное напоминание (last_reminder=None)', flush=True)
              
              if should_send:
                message = f'''🔴 <b>ПРОСРОЧЕНО!</b>

📝 <b>{title}</b>
⏰ Дедлайн был: {format_date_russian(reminder_date)} {reminder_time}
⏱️ Прошло времени: {hours_passed}ч {minutes_passed}м
❗️ Не забудьте выполнить задачу!'''
                new_stage = 2
                is_overdue = True
          
          if should_send:
            try:
              # Формируем inline keyboard с кнопками
              task_id_str = str(task_id)
              
              # Добавляем ссылку в текст сообщения (без HTML, чтобы Telegram сделал её кликабельной)
              deep_link = f'taskboard://reminder/{task_id_str}'
              message_with_link = message + f'\n\n📱 Открыть в приложении: {deep_link}'
              
              reply_markup = {
                'inline_keyboard': [
                  [{'text': '✅ Выполнено', 'callback_data': f'done_{task_id_str}'}],
                  [{'text': '⏱️ Перенести', 'callback_data': f'extend_menu_{task_id_str}'}]
                ]
              }
              
              # Отправляем через синхронный requests
              url = f'https://api.telegram.org/bot{BOT_TOKEN}/sendMessage'
              data = {
                  'chat_id': chat_id,
                  'text': message_with_link,
                  'parse_mode': 'HTML',
                  'reply_markup': reply_markup
              }
              resp = requests.post(url, json=data)
              print(f'Отправлено напоминание: {title} (Этап: {reminder_stage} -> {new_stage})', flush=True)
              
              # Обновляем статус (используем UTC+3 для консистентности)
              now_moscow = datetime.utcnow() + timedelta(hours=3)
              if source == 'sqlite':
                update_reminder_status(task_id, new_stage, now_moscow.isoformat())
              else:
                update_reminder_in_supabase(task_id, {
                  'reminder_stage': new_stage,
                  'last_reminder_sent': now_moscow.isoformat()
                })
            except Exception as e:
              print(f'Ошибка отправки: {e}', flush=True)
        except Exception as e:
          print(f'Ошибка обработки: {e}', flush=True)
          continue
      
      # Ждём 30 секунд перед следующей проверкой
      time.sleep(30)
    except Exception as e:
      print(f'Ошибка в цикле напоминаний: {e}', flush=True)
      time.sleep(60)

# Оригинальная async функция для обратной совместимости
async def send_reminders(app):
  # Запускаем синхронную версию в отдельном потоке
  import threading
  thread = threading.Thread(target=send_reminders_sync, daemon=True)
  thread.start()

async def post_init(application: Application):
  print('='*50)
  print('DEBUG: post_init ВЫЗВАН!')
  print('='*50)
  asyncio.create_task(send_reminders(application))

def main():
  try:
    init_db()
    # Создаем приложение с настройками для работы через прокси/с ограничениями
    from telegram.request import HTTPXRequest
    request = HTTPXRequest(connection_pool_size=8, connect_timeout=30, read_timeout=30)
    application = Application.builder().token(BOT_TOKEN).post_init(post_init).request(request).build()
    
    # Команда для тестирования напоминаний
    async def test_reminders(update: Update, context: ContextTypes.DEFAULT_TYPE):
      chat_id = update.effective_chat.id
      await update.message.reply_text('🔄 Проверяю напоминания...')
      all_tasks = get_all_reminders_for_sending()
      await update.message.reply_text(f'Найдено {len(all_tasks)} напоминаний в базе.')
      current_time = datetime.now()
      for task in all_tasks:
        rd = task.get('reminder_date')
        rt = task.get('reminder_time')
        cid = task.get('chat_id')
        await update.message.reply_text(f'- {task.get("title")} на {rd} {rt} для chat_id={cid}')
    
    application.add_handler(CommandHandler('start',start))
    application.add_handler(CommandHandler('testreminders',test_reminders))
    application.add_handler(CallbackQueryHandler(handle_button_click))
    application.add_handler(MessageHandler(filters.TEXT&~(filters.COMMAND),handle_message))
    
    # Фоновая задача напоминаний запускается через post_init
    print('🤖 Бот запущен...')
    print('Для остановки нажмите Ctrl+C')
    print('⚠️ Если возникают сетевые ошибки, проверьте подключение к Telegram API')
    application.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)
    return None
  except Exception as e:
    print(f'''Критическая ошибка: {e}''')
    import traceback
    traceback.print_exc()
    input('Нажмите Enter для выхода...')
    return None

if __name__ == '__main__':
  main()
