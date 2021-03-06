#!/usr/bin/env python

import logging
import threading
import time

import telebot
from telebot import apihelper
from telebot.types import Message

import config
import database
import localizationdic as ld
from user_request_process import RequestSteps, UserRequestProcess

logger = telebot.logger
telebot.logger.setLevel(logging.INFO)

log = logging.getLogger('bot')
formatter = logging.Formatter("%(asctime)s %(levelname)s %(funcName)s(%(lineno)d): %(message)s")
handler = logging.StreamHandler()
handler.setFormatter(formatter)
log.addHandler(handler)
log.setLevel(logging.DEBUG)

apihelper.proxy = config.proxy
bot = telebot.TeleBot(config.token)
db = database.DB()

masterChatId = db.GetMasterChatId()
masterChatAdmins = []
userProcesses = {}

# if masterChatId != 0:
#     try:
#         masterChatAdmins = bot.get_chat_administrators(masterChatId)
#     except:
#         masterChatAdmins = []
#         masterChatId = 0
# else:
#     masterChatAdmins = []


def clean_db():
    while True:
        log.info("DB cleaning")
        db.DeleteOldRequests()
        time.sleep(86400)


@bot.message_handler(content_types=["text"])
def handle_messages(message: Message):
    if message.chat.type == "supergroup" or message.chat.type == "group":
        handle_group_message(message)
    elif message.chat.type == "private":
        handle_private_message(message)


@bot.callback_query_handler(func=lambda call: True)
def handle_callback_query(call):
    data = call.data
    username = call.from_user.username
    log.info('callback query from %s: %s', username, data)
    if not (username in userProcesses):
        userProcesses[username] = UserRequestProcess(bot, db, username, call.message.chat.id)

    userProcesses[username].ProcessMessage(data)
    try:
        bot.answer_callback_query(call.id)
    except Exception as ex:
        log.info("Exception during request {0} from {1}. Message: {2}".format(data, username, str(ex)))


def handle_group_message(message: Message):
    masterChatId = db.GetMasterChatId()
    if masterChatId != 0:
        masterChatAdmins = bot.get_chat_administrators(masterChatId)
    else:
        masterChatAdmins = []

    if message.text.startswith("/setmasterchat"):
        if masterChatId != 0 and (masterChatId != message.chat.id):
            return
        if not message.from_user.username or len(message.from_user.username) == 0:
            bot.send_message(
                message.chat.id,
                """Установите сначала никнейм в телеграме
Set 'username' first please""",
            )
            return
        if masterChatId == 0:
            masterChatId = message.chat.id
            masterChatAdmins = bot.get_chat_administrators(masterChatId)
            administrators = [user.user.username for user in masterChatAdmins]
            if message.from_user.username not in administrators:
                masterChatId = 0
                masterChatAdmins = []
                return
        log.info("setting masterchat by %s request", message.from_user.username)
        db.SetMasterChatId(masterChatId)
        bot.send_message(masterChatId, "Done")
    elif message.text.startswith("/list"):
        if masterChatId == 0 or len(masterChatAdmins) == 0:
            return
        if not message.from_user.username or len(message.from_user.username) == 0:
            bot.send_message(
                message.chat.id,
                """Установите сначала никнейм в телеграме
Set 'username' first please""",
            )
            return
        administrators = [user.user.username for user in masterChatAdmins]
        if message.from_user.username not in administrators:
            return
        reqList = db.GetAllFormattedRequests(message.from_user.username, 0, 50)
        if len(reqList) == 0:
            bot.send_message(message.chat.id, ld.get_translate(db, message.from_user.username, ld.EmptyKey))
        else:
            idx = 0
            reqCount = len(reqList)
            while idx < reqCount:
                count = min(10, reqCount - idx)
                lst = reqList[idx : idx + count]  # noqa: E203
                msg = "\n\n".join(lst)
                bot.send_message(message.chat.id, msg, parse_mode="HTML")
                idx += 10
    elif message.text.startswith("/register"):
        if masterChatId == 0:
            return
        if not message.from_user.username or len(message.from_user.username) == 0:
            bot.send_message(
                message.chat.id,
                """Установите сначала никнейм в телеграме
Set 'username' first please""",
            )
            return
        if db.IsUserRegistered(message.from_user.username):
            bot.send_message(
                message.chat.id,
                ld.get_translate(db, message.from_user.username, ld.UsernameAlreadyRegisteredKey).format(
                    message.from_user.username
                ),
            )
            return
        log.info('Registering %s', message.from_user.username)
        db.AddUser(message.from_user.username)
        bot.send_message(
            message.chat.id,
            """{0} зарегистрирован
{0} has been registered""".format(
                message.from_user.username
            ),
        )
    elif message.text.startswith("/unregister"):
        if masterChatId == 0 or len(masterChatAdmins) == 0:
            return
        if not message.from_user.username or len(message.from_user.username) == 0:
            bot.send_message(
                message.chat.id,
                """Установите сначала никнейм в телеграме
Set 'username' first please""",
            )
            return
        administrators = [user.user.username for user in masterChatAdmins]
        if message.from_user.username not in administrators:
            return
        username = message.text.replace("/unregister", "").strip(' ').strip('@')
        if len(username) == 0:
            bot.send_message(
                message.chat.id,
                """Введите пожалуйста команду в виде <b>/unregister 'username'</b>
Please, enter command as <b>/unregister 'username'</b>""",
                parse_mode="HTML",
            )
            return
        if not db.IsUserRegistered(username):
            bot.send_message(message.chat.id, "User {0} is not registered".format(username))
            return
        db.DeleteUser(username)
        bot.send_message(message.chat.id, "User {0} was deleted".format(username))
    elif message.text.startswith("/escrowlist"):
        escrowList = db.GetEscrowList()
        if len(escrowList) == 0:
            bot.send_message(message.chat.id, ld.get_translate(db, message.from_user.username, ld.EmptyKey))
            return
        result = "\n".join(escrowList)
        bot.send_message(message.chat.id, result, parse_mode="HTML")
    elif message.text.startswith("/stats"):
        if masterChatId == 0 or len(masterChatAdmins) == 0:
            return
        if not message.from_user.username or len(message.from_user.username) == 0:
            bot.send_message(
                message.chat.id,
                """Установите сначала никнейм в телеграме
Set 'username' first please""",
            )
            return
        administrators = [user.user.username for user in masterChatAdmins]
        if message.from_user.username not in administrators:
            return
        usersCount = db.GetUsersCount()
        usersWithNotif = db.GetUsersCountWithNotifications()
        result = "\nusers: {0}\nwith notifications: {1}".format(usersCount, usersWithNotif)
        bot.send_message(message.chat.id, result)
    elif message.text.startswith("/blockbyreqid"):
        if masterChatId == 0 or len(masterChatAdmins) == 0:
            return
        if not message.from_user.username or len(message.from_user.username) == 0:
            bot.send_message(
                message.chat.id,
                """Установите сначала никнейм в телеграме
Set 'username' first please""",
            )
            return
        administrators = [user.user.username for user in masterChatAdmins]
        if message.from_user.username not in administrators:
            return
        reqId = message.text.replace("/blockbyreqid", "").strip(' ').strip('@')
        if len(reqId) == 0:
            bot.send_message(
                message.chat.id,
                """Введите пожалуйста команду в виде <b>/blockbyreqid 'req id'</b>
Please, enter command as <b>/blockbyreqid 'req id'</b>""",
                parse_mode="HTML",
            )
            return
        db.AddUserToBlackListByReqId(int(reqId))
        bot.send_message(message.chat.id, "Request with id {0} was deleted".format(reqId))
    '''else:
        usage = """<b>Использование:</b>
/setmasterchat - Зарегистрировать мастер-чат(админ)
/list   - Вывод списка заявок (админ)
/register - зарегистрироваться
/escrowlist - Вывод списка гарантов
/unregister 'username' - удалить юзера (админ)
/blockbyreqid 'req id' - удалить заявку и добавить юзера в черный список
"""
        bot.send_message(message.chat.id, usage, parse_mode="HTML")'''


def handle_private_message(message: Message):
    log.info('private message from %s: %s', message.from_user.username, message.text)
    if db.IsUserInBlacklist(message.from_user.id):
        bot.send_message(
            message.chat.id,
            """Вы в черном списке!
You are in blacklist!""",
        )
        return
    if message.from_user.username is None or len(message.from_user.username) == 0:
        bot.send_message(
            message.chat.id,
            """Вам сначала нужно установить никнейм в телеграме.
You need to set your username in Telegram first.""",
        )
        return

    username = message.from_user.username
    if not db.IsUserRegistered(username):
        db.AddUser(username)

    db.SetUserChatId(username, message.chat.id)
    db.UpdateUser(username, message.from_user.id)
    if message.text.startswith("/start"):
        if not (username in userProcesses):
            userProcesses[username] = UserRequestProcess(bot, db, username, message.chat.id)
        req = userProcesses[username]
        if req.currentStep == RequestSteps.Start:
            req.Start()
        else:
            req.ProcessMessage("/start")
    elif (username in userProcesses) and (
        (userProcesses[username].currentStep != RequestSteps.Start) or message.text == "⬅️" or message.text == "➡️"
    ):
        userProcesses[username].ProcessMessage(message.text)
    else:
        usage = """<b>Использование:</b>
/start   - Начало процесса

<b>Usage:</b>
/start - start process"""
        bot.send_message(message.chat.id, usage, parse_mode="HTML")


if __name__ == '__main__':
    cleaner = threading.Thread(target=clean_db, daemon=True)
    cleaner.start()
    bot.polling(none_stop=True, timeout=60)
