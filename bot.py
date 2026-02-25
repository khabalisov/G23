import vk_api
from vk_api.longpoll import VkLongPoll, VkEventType
from vk_api.utils import get_random_id
import datetime
import sqlite3
import re
import math
import os
import sys
import time

# ========== НАСТРОЙКИ ==========
VK_TOKEN = "vk1.a.niwLTYj0OoJ0UdULM3MTnvexSLVsLuYr4_jH2Zr10SCDmyg79AjugdUmmkn6Ju-4s2Std7s-gCkYkafqtiGf79vChqjYa2Mk-IloP1HDd7A4NfypIQ1L_SngypDjKearC5O0_haOMXhYnsmkPRYL_kCuiZW92lhPdVmZ1ghcpj_c1AUvSeE0p8Je8K6kLlTeqwGSb7DltcrY0vm0AaOvdg"
GROUP_ID = 218666977
TARGET_POST_ID = 439
SECRET_CODE = "3461687"
# ===============================

print("=" * 50)
print("ЗАПУСК БОТА")
print(f"ID группы: {GROUP_ID}")
print(f"ID поста: {TARGET_POST_ID}")
print(f"Код: {SECRET_CODE}")
print("=" * 50)

# Проверка подключения к VK
try:
    vk_session = vk_api.VkApi(token=VK_TOKEN)
    vk = vk_session.get_api()
    # Проверяем, что токен работает
    group_info = vk.groups.getById(group_id=GROUP_ID)
    print(f"✅ Подключение к VK успешно! Группа: {group_info[0]['name']}")
except Exception as e:
    print(f"❌ Ошибка подключения к VK: {e}")
    print("Проверьте токен и настройки группы")
    sys.exit(1)


# Инициализация базы данных
def init_db():
    try:
        conn = sqlite3.connect('game_data.db')
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS users
                     (user_id INTEGER PRIMARY KEY,
                      username TEXT,
                      attempts_today INTEGER DEFAULT 0,
                      last_attempt_date TEXT,
                      guessed_numbers TEXT DEFAULT '',
                      last_hint_threshold INTEGER DEFAULT 0)''')
        c.execute('''CREATE TABLE IF NOT EXISTS attempts
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      user_id INTEGER,
                      attempt_number TEXT,
                      attempt_date TEXT,
                      correct INTEGER DEFAULT 0)''')
        conn.commit()
        conn.close()
        print("✅ База данных инициализирована")
    except Exception as e:
        print(f"❌ Ошибка базы данных: {e}")


init_db()


class VKBot:
    def __init__(self, token):
        self.vk_session = vk_api.VkApi(token=token)
        self.vk = self.vk_session.get_api()
        self.longpoll = VkLongPoll(self.vk_session)
        print("✅ LongPoll инициализирован")

    def send_message(self, user_id, message):
        try:
            self.vk.messages.send(
                user_id=user_id,
                random_id=get_random_id(),
                message=message
            )
            print(f"📤 Отправлено сообщение пользователю {user_id}: {message[:50]}...")
        except Exception as e:
            print(f"❌ Ошибка отправки сообщения: {e}")

    def send_comment_reply(self, post_id, comment_id, message):
        try:
            self.vk.wall.createComment(
                post_id=post_id,
                comment_id=comment_id,
                message=message
            )
            print(f"💬 Ответ на комментарий {comment_id}: {message[:50]}...")
        except Exception as e:
            print(f"❌ Ошибка ответа на комментарий: {e}")

    def check_subscription(self, user_id):
        try:
            result = self.vk.groups.isMember(group_id=GROUP_ID, user_id=user_id)
            return result == 1
        except:
            return False

    def check_repost(self, user_id, post_id):
        try:
            wall = self.vk.wall.get(owner_id=user_id, count=10)
            for item in wall['items']:
                if 'copy_history' in item:
                    for copy in item['copy_history']:
                        if copy.get('id') == post_id and abs(copy.get('owner_id')) == GROUP_ID:
                            return True
            return False
        except:
            return False

    def check_like(self, user_id, post_id):
        try:
            result = self.vk.likes.isLiked(
                user_id=user_id,
                type='post',
                owner_id=-GROUP_ID,
                item_id=post_id
            )
            return result['liked'] == 1
        except:
            return False

    def calculate_total_attempts(self, user_id, post_id):
        base = 3
        if self.check_subscription(user_id):
            base += 7
        if self.check_repost(user_id, post_id):
            base += 15
        if self.check_like(user_id, post_id):
            base += 5
        return base

    def handle_comment(self, event):
        print(f"📝 Новый комментарий от {event.user_id}: {event.text}")

        # Проверяем, что это нужный пост
        if event.post_id != TARGET_POST_ID:
            print(f"⏭️ Игнорируем пост {event.post_id}, нужен {TARGET_POST_ID}")
            return

        text = event.text.strip()

        # Проверяем, что это 7 цифр
        if not re.match(r'^\d{7}$', text):
            print(f"⏭️ Не код: {text}")
            return

        user_id = event.user_id
        print(f"🎯 Обрабатываем код {text} от пользователя {user_id}")

        try:
            conn = sqlite3.connect('game_data.db')
            c = conn.cursor()
            today = datetime.date.today().isoformat()

            # Получаем или создаем пользователя
            c.execute("SELECT attempts_today, last_attempt_date FROM users WHERE user_id=?", (user_id,))
            r = c.fetchone()
            if r:
                attempts_today, last_date = r
                if last_date != today:
                    attempts_today = 0
                    c.execute("UPDATE users SET attempts_today=0, last_attempt_date=? WHERE user_id=?",
                              (today, user_id))
            else:
                c.execute("INSERT INTO users (user_id, username, attempts_today, last_attempt_date) VALUES (?,?,0,?)",
                          (user_id, f"User{user_id}", today))
                attempts_today = 0
            conn.commit()

            # Проверяем лимит попыток
            total = self.calculate_total_attempts(user_id, event.post_id)
            if attempts_today >= total:
                self.send_comment_reply(event.post_id, event.comment_id,
                                        f"❌ У тебя закончились попытки на сегодня! Использовано: {attempts_today}/{total}")
                conn.close()
                return

            # Проверяем код
            if text == SECRET_CODE:
                c.execute("INSERT INTO attempts (user_id, attempt_number, attempt_date, correct) VALUES (?,?,?,1)",
                          (user_id, text, datetime.datetime.now().isoformat()))
                conn.commit()
                self.send_comment_reply(event.post_id, event.comment_id, f"🎉 ПОБЕДА! Код {SECRET_CODE}!")
                self.send_message(user_id, f"🎉 Поздравляю! Ты отгадал код {SECRET_CODE}!")
                print(f"🏆 Пользователь {user_id} победил!")
            else:
                c.execute("INSERT INTO attempts (user_id, attempt_number, attempt_date, correct) VALUES (?,?,?,0)",
                          (user_id, text, datetime.datetime.now().isoformat()))
                c.execute("UPDATE users SET attempts_today=attempts_today+1 WHERE user_id=?", (user_id,))
                conn.commit()

                # Проверяем подсказку после 50 попыток
                c.execute("SELECT COUNT(*) FROM attempts WHERE user_id=?", (user_id,))
                total_attempts = c.fetchone()[0]
                c.execute("SELECT last_hint_threshold FROM users WHERE user_id=?", (user_id,))
                last_hint = c.fetchone()[0] or 0
                curr = (total_attempts // 50) * 50
                if curr >= 50 and curr > last_hint:
                    c.execute("UPDATE users SET last_hint_threshold=? WHERE user_id=?", (curr, user_id))
                    hint = "БОЛЬШЕ" if int(text) > int(SECRET_CODE) else "МЕНЬШЕ"
                    self.send_message(user_id, f"📊 После {total_attempts} попыток: твой код {text} {hint} загаданного")
                    print(f"💡 Подсказка отправлена пользователю {user_id}")
                conn.commit()

                attempts_left = total - attempts_today - 1
                self.send_comment_reply(event.post_id, event.comment_id,
                                        f"❌ Неверный код! Осталось попыток на сегодня: {attempts_left}")
                print(f"❌ Неверный код от {user_id}, осталось {attempts_left} попыток")

            conn.close()

        except Exception as e:
            print(f"❌ Ошибка при обработке комментария: {e}")

    def run(self):
        print("🚀 Бот запущен и слушает события...")
        print("Ожидание комментариев...")
        while True:
            try:
                for event in self.longpoll.listen():
                    if event.type == VkEventType.WALL_REPLY_NEW:
                        self.handle_comment(event)
            except Exception as e:
                print(f"❌ Ошибка в главном цикле: {e}")
                print("Переподключение через 5 секунд...")
                time.sleep(5)


if __name__ == "__main__":
    print("🔄 Инициализация бота...")
    bot = VKBot(VK_TOKEN)
    bot.run()