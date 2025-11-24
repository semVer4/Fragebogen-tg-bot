#!/usr/bin/env python3
# coding: utf-8

import json
import logging
import os
from typing import List
from telegram import InputMediaPhoto

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ConversationHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# -------------------- Логирование --------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# -------------------- Состояния --------------------
(
    START_MENU,
    RATE_PHOTO,
    AFTER_RATING,
    CITY_CHOICE,
    OTHER_CITY,
    INVITE_DEEP,
    DEEP_BLOCK1,
    DEEP_BLOCK2,
    DEEP_BLOCK3,
    DEEP_BLOCK4,
) = range(10)

# ===== DEBUG HANDLER TO GET REAL FILE_ID =====
async def debug_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    photo = update.message.photo[-1]
    await update.message.reply_text(
        f"file_id: {photo.file_id}\n"
        f"file_unique_id: {photo.file_unique_id}"
    )


# -------------------- Утилиты --------------------
def load_results() -> List[dict]:
    if not os.path.exists(DATA_FILE):
        return []
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []

def save_result(entry: dict):
    data = load_results()
    data.append(entry)
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def get_photo_for_user(user_id: int) -> str:
    if not PHOTO_IDS:
        return ""
    return PHOTO_IDS[user_id % len(PHOTO_IDS)]

# -------------------- Клавиатуры --------------------
def build_menu_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("🔥 Оценить фото", callback_data="menu_rate")],
        [InlineKeyboardButton("❓ Что за эксперимент?", callback_data="menu_about")],
    ]
    return InlineKeyboardMarkup(keyboard)

def build_about_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data="menu_back")]])

def build_rating_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [
            InlineKeyboardButton("❤️ Нравится", callback_data="rate_1"),
            InlineKeyboardButton("💛 Скорее нравится", callback_data="rate_2"),
        ],
        [
            InlineKeyboardButton("💙 Скорее не нравится", callback_data="rate_3"),
            InlineKeyboardButton("💔 Не нравится", callback_data="rate_4"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)

def multi_select_keyboard(options: List[str], selected: List[str], allow_skip=True) -> InlineKeyboardMarkup:
    kb = []
    for opt in options:
        mark = "✅ " if opt in selected else ""
        kb.append([InlineKeyboardButton(f"{mark}{opt}", callback_data=f"toggle::{opt}")])
    bottom = [InlineKeyboardButton("➡️ Пропустить", callback_data="details_next")] if allow_skip else [InlineKeyboardButton("➡️ Дальше", callback_data="details_next")]
    kb.append(bottom)
    return InlineKeyboardMarkup(kb)

def single_choice_keyboard(options: List[str]) -> InlineKeyboardMarkup:
    kb = [[InlineKeyboardButton(opt, callback_data=f"city::{opt}")] for opt in options]
    kb.append([InlineKeyboardButton("Другой город", callback_data="city::OTHER")])
    return InlineKeyboardMarkup(kb)

def deep_multiselect_keyboard(options: List[str], selected: List[str]) -> InlineKeyboardMarkup:
    kb = []
    for opt in options:
        mark = "✅ " if opt in selected else ""
        kb.append([InlineKeyboardButton(f"{mark}{opt}", callback_data=f"deep_toggle::{opt}")])
    kb.append([InlineKeyboardButton("➡️ Дальше", callback_data="deep_next")])
    return InlineKeyboardMarkup(kb)

# -------------------- Обработчики --------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Стартовое сообщение — главное меню."""
    user = update.effective_user
    context.user_data.clear()
    context.user_data["uid"] = user.id
    text = (
        "Привет! Это эксперимент «Самцыч».\n\n"
        "Здесь ты можешь анонимно оценить фото и помочь собрать \n\n"
        "портрет идеального парня для разных городов."
    )
    # отправляем как обычное сообщение
    if update.message:
        await update.message.reply_text(text, reply_markup=build_menu_keyboard())
    else:
        await context.bot.send_message(chat_id=update.effective_chat.id, text=text, reply_markup=build_menu_keyboard())
    return START_MENU

async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    logger.info("menu_callback: %s", query.data)
    data = query.data

    if data == "menu_about":
        about_text = (
            "Егор (Самцыч) изучает, какие типажи нравятся девушкам в разных городах.\n"
            "Ты кликаешь — мы собираем статистику — в канале появляются выводы и «портреты идеалов».\n\n"
            "Всё анонимно и занимает меньше минуты."
        )
        await query.edit_message_text(about_text, reply_markup=build_about_keyboard())
        return START_MENU

    if data == "menu_back":
        await query.edit_message_text("Привет! Это эксперимент «Самцыч».\n\nЗдесь ты можешь анонимно оценить фото и помочь собрать\n\nпортрет идеального парня для разных городов.", reply_markup=build_menu_keyboard())
        return START_MENU

    if data == "menu_rate":
        uid = context.user_data.get("uid", 0)

        # берём две фотки
        photos = PHOTO_IDS[:2]   # первые две из списка

        # удаляем сообщение с меню
        try:
            await query.message.delete()
        except:
            pass

        # отправляем альбом
        album = [
            InputMediaPhoto(media=p, caption="Оцени фото 👇\n\nТвой выбор анонимен." if i == 0 else None)
            for i, p in enumerate(photos)
        ]

        sent_messages = await context.bot.send_media_group(
            chat_id=query.message.chat_id,
            media=album
        )

        # сохраняем id первой фотки (к которой будет прикреплена оценка)
        main_photo_msg_id = sent_messages[0].message_id
        context.user_data["current_photo"] = photos[0]
        context.user_data["photo_message_id"] = main_photo_msg_id

        # отправляем кнопки отдельным сообщением
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="Выбери:",
            reply_markup=build_rating_keyboard()
        )
        return RATE_PHOTO

    # fallback
    await query.edit_message_text("Неизвестная команда. Вернись в меню.", reply_markup=build_menu_keyboard())
    return START_MENU

async def rating_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    logger.info("rating_callback: %s", query.data)
    data = query.data
    if not data.startswith("rate_"):
        await query.edit_message_text("Непонятная команда.")
        return START_MENU

    rating_map = {
        "rate_1": "❤️ Нравится",
        "rate_2": "💛 Скорее нравится",
        "rate_3": "💙 Скорее не нравится",
        "rate_4": "💔 Не нравится",
    }
    rating_label = rating_map.get(data, "Неизвестно")
    context.user_data["rating"] = rating_label

    if data in ("rate_1", "rate_2"):
        options = ["🙂 Улыбка", "👀 Глаза", "🌿 Вайб / энергетика", "👔 Стиль одежды",
                   "🙂 Черты лица", "💪 Телосложение", "🧍‍♂️ Осанка", "⭐️ Просто понравился"]
        context.user_data["details_positive_options"] = options
        context.user_data["details_selected"] = []
        # пытаемся редактировать подпись к фото, если не выйдет — отправим новое сообщение
        try:
            await query.edit_message_caption(
                caption=f"Ты выбрал: {rating_label}\n\nА что понравилось больше всего? Можно выбрать несколько вариантов.",
                reply_markup=multi_select_keyboard(options, []),
            )
        except Exception:
            await context.bot.send_message(chat_id=query.message.chat_id,
                                           text=f"Ты выбрал: {rating_label}\n\nА что понравилось больше всего? Можно выбрать несколько вариантов.",
                                           reply_markup=multi_select_keyboard(options, []))
        return AFTER_RATING
    else:
        options = ["👔 Стиль", "🙂 Лицо / мимика", "🧍‍♂️ Осанка", "🧢 Прическа / волосы",
                   "🤷 Не мой типаж", "🔞 Слишком молодой", "📅 Слишком взрослый", "❌ Просто не зашёл"]
        context.user_data["details_negative_options"] = options
        context.user_data["details_selected"] = []
        try:
            await query.edit_message_caption(
                caption=f"Ты выбрал: {rating_label}\n\nА что больше всего не зашло? Можно выбрать несколько вариантов.",
                reply_markup=multi_select_keyboard(options, []),
            )
        except Exception:
            await context.bot.send_message(chat_id=query.message.chat_id,
                                           text=f"Ты выбрал: {rating_label}\n\nА что больше всего не зашло? Можно выбрать несколько вариантов.",
                                           reply_markup=multi_select_keyboard(options, []))
        return AFTER_RATING

async def details_toggle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    logger.info("details_toggle_callback: %s", query.data)
    data = query.data

    if data == "details_next":
        # переход к выбору города
        try:
            await query.edit_message_caption(
                caption="Спасибо! Теперь, из какого ты города? Это нужно, чтобы собрать карту предпочтений.",
                reply_markup=single_choice_keyboard(["Минск", "Гродно", "Гомель", "Могилёв", "Брест"]),
            )
        except Exception:
            await context.bot.send_message(chat_id=query.message.chat_id,
                                           text="Спасибо! Теперь, из какого ты города? Это нужно, чтобы собрать карту предпочтений.",
                                           reply_markup=single_choice_keyboard(["Минск", "Гродно", "Гомель", "Могилёв", "Брест"]))
        return CITY_CHOICE

    if data.startswith("toggle::"):
        opt = data.split("::", 1)[1]
        sel = context.user_data.get("details_selected", [])
        if opt in sel:
            sel.remove(opt)
        else:
            sel.append(opt)
        context.user_data["details_selected"] = sel
        options = context.user_data.get("details_positive_options") or context.user_data.get("details_negative_options") or []
        try:
            await query.edit_message_reply_markup(reply_markup=multi_select_keyboard(options, sel))
        except Exception:
            await context.bot.send_message(chat_id=query.message.chat_id, text="Обновлено.", reply_markup=multi_select_keyboard(options, sel))
        return AFTER_RATING

    await query.answer("Неизвестная команда в деталях.")
    return AFTER_RATING

async def city_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    logger.info("city_callback: %s", query.data)
    data = query.data
    if not data.startswith("city::"):
        await query.answer("Ошибка выбора города")
        return CITY_CHOICE
    city = data.split("::", 1)[1]
    if city == "OTHER":
        # просим текстовый ввод
        try:
            await query.edit_message_text("Напиши, пожалуйста, название твоего города (текстово).")
        except Exception:
            await context.bot.send_message(chat_id=query.message.chat_id, text="Напиши, пожалуйста, название твоего города (текстово).")
        return OTHER_CITY
    else:
        context.user_data["city"] = city
        context.user_data["details"] = context.user_data.get("details_selected", [])
        try:
            await query.edit_message_text(
                "Можешь помочь составить образ своего идеального парня?✨\nМини-опрос — 20–30 секунд. Можно выбрать несколько вариантов.",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("🔥 Да, хочу", callback_data="invite_yes"),
                      InlineKeyboardButton("❌ Нет, спасибо", callback_data="invite_no")]]
                ),
            )
        except Exception:
            await context.bot.send_message(chat_id=query.message.chat_id,
                                           text="Можешь помочь составить образ своего идеального парня?✨\nМини-опрос — 20–30 секунд. Можно выбрать несколько вариантов.",
                                           reply_markup=InlineKeyboardMarkup(
                                               [[InlineKeyboardButton("🔥 Да, хочу", callback_data="invite_yes"),
                                                 InlineKeyboardButton("❌ Нет, спасибо", callback_data="invite_no")]]
                                           ))
        return INVITE_DEEP

async def other_city_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    logger.info("other_city_text: %s", text)
    context.user_data["city"] = text
    context.user_data["details"] = context.user_data.get("details_selected", [])
    await update.message.reply_text(
        "Можешь помочь составить образ своего идеального парня?✨\nММини-опрос — 20–30 секунд. Можно выбрать несколько вариантов.",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("🔥 Да, хочу", callback_data="invite_yes"),
              InlineKeyboardButton("❌ Нет, спасибо", callback_data="invite_no")]]
        ),
    )
    return INVITE_DEEP

async def invite_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    logger.info("invite_callback: %s", query.data)
    data = query.data
    if data == "invite_no":
        entry = {
            "user_id": context.user_data.get("uid"),
            "photo": context.user_data.get("current_photo"),
            "rating": context.user_data.get("rating"),
            "details": context.user_data.get("details", []),
            "city": context.user_data.get("city"),
            "deep": None,
        }
        save_result(entry)
        await notify_admins(context, entry)
        await query.edit_message_text("Спасибо! Твои ответы уйдут в «Самцыч» и помогут создать портрет\n\nидеального парня в твоём городе.\n\nКнопка: 📊 Перейти в канал", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📊 Перейти в канал", url="https://t.me/sam_tich")]]))
        return ConversationHandler.END

    if data == "invite_yes":
        context.user_data.setdefault("deep", {})
        options = [
            "Мягкие черты", "Выраженные скулы", "Широкая челюсть", "Узкое лицо", "Круглое лицо",
            "Светлая кожа", "Тёмная кожа", "Волосы: короткие", "Волосы: длинные", "Не важно"
        ]
        context.user_data["deep_block1_selected"] = []
        await query.edit_message_text("Какие черты лица тебе нравятся? Выбери всё, что подходит.", reply_markup=deep_multiselect_keyboard(options, []))
        return DEEP_BLOCK1

    await query.answer("Неизвестная команда.")
    return INVITE_DEEP

async def deep_toggle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    logger.info("deep_toggle_callback: %s", query.data)
    data = query.data

    # блок 1
    if data.startswith("deep_toggle::") and context.user_data.get("deep_block1_selected") is not None:
        opt = data.split("::", 1)[1]
        sel = context.user_data.get("deep_block1_selected", [])
        if opt in sel:
            sel.remove(opt)
        else:
            sel.append(opt)
        context.user_data["deep_block1_selected"] = sel
        options = [
            "Мягкие черты", "Выраженные скулы", "Широкая челюсть", "Узкое лицо", "Круглое лицо",
            "Светлая кожа", "Тёмная кожа", "Волосы: короткие", "Волосы: длинные", "Не важно"
        ]
        try:
            await query.edit_message_reply_markup(reply_markup=deep_multiselect_keyboard(options, sel))
        except Exception:
            await context.bot.send_message(chat_id=query.message.chat_id, text="Обновлено.", reply_markup=deep_multiselect_keyboard(options, sel))
        return DEEP_BLOCK1

    if data == "deep_next" and context.user_data.get("deep_block1_selected") is not None:
        context.user_data["deep"]["block1"] = context.user_data.get("deep_block1_selected", [])
        options2 = ["Худощавый", "Средний", "Спортивный", "Крепкий", "Не важно"]
        kb2 = InlineKeyboardMarkup([[InlineKeyboardButton(opt, callback_data=f"deep2::{opt}")] for opt in options2] + [[InlineKeyboardButton("➡️ Дальше", callback_data="deep2_next")]])
        await query.edit_message_text("Какое телосложение тебе ближе?", reply_markup=kb2)
        context.user_data.pop("deep_block1_selected", None)
        return DEEP_BLOCK2

    # блок 2
    if data.startswith("deep2::"):
        choice = data.split("::", 1)[1]
        context.user_data["deep"]["block2"] = choice
        options3 = ["Кежуал", "Спортивный", "Офисный (рубашка/пиджак)", "Уличный / streetwear",
                    "Минимализм", "Творческий", "Гранж / рок", "Брутальный", "Аккуратный, ухоженный", "Не важно"]
        context.user_data["deep_block3_selected"] = []
        await query.edit_message_text("В каком стиле парень выглядит привлекательнее?", reply_markup=deep_multiselect_keyboard(options3, []))
        return DEEP_BLOCK3

    # блок 3
    if data.startswith("deep_toggle::") and context.user_data.get("deep_block3_selected") is not None:
        opt = data.split("::", 1)[1]
        sel = context.user_data.get("deep_block3_selected", [])
        if opt in sel:
            sel.remove(opt)
        else:
            sel.append(opt)
        context.user_data["deep_block3_selected"] = sel
        options3 = ["Кежуал", "Спортивный", "Офисный (рубашка/пиджак)", "Уличный / streetwear",
                    "Минимализм", "Творческий", "Гранж / рок", "Брутальный", "Аккуратный, ухоженный", "Не важно"]
        try:
            await query.edit_message_reply_markup(reply_markup=deep_multiselect_keyboard(options3, sel))
        except Exception:
            await context.bot.send_message(chat_id=query.message.chat_id, text="Обновлено.", reply_markup=deep_multiselect_keyboard(options3, sel))
        return DEEP_BLOCK3

    if data == "deep_next" and context.user_data.get("deep_block3_selected") is not None:
        context.user_data["deep"]["block3"] = context.user_data.get("deep_block3_selected", [])
        context.user_data.pop("deep_block3_selected", None)
        options4 = ["Добрый", "Уверенный", "Спокойный", "Харизматичный", "Заботливый",
                    "Дерзкий / хулиган", "Интеллектуальный", "Весёлый / лёгкий", "Серьёзный",
                    "Интровертный", "Экстравертный"]
        context.user_data["deep_block4_selected"] = []
        await query.edit_message_text("Какой вайб (атмосфера) тебя привлекает больше всего?", reply_markup=deep_multiselect_keyboard(options4, []))
        return DEEP_BLOCK4

    # блок 4
    if data.startswith("deep_toggle::") and context.user_data.get("deep_block4_selected") is not None:
        opt = data.split("::", 1)[1]
        sel = context.user_data.get("deep_block4_selected", [])
        if opt in sel:
            sel.remove(opt)
        else:
            sel.append(opt)
        context.user_data["deep_block4_selected"] = sel
        options4 = ["Добрый", "Уверенный", "Спокойный", "Харизматичный", "Заботливый",
                    "Дерзкий / хулиган", "Интеллектуальный", "Весёлый / лёгкий", "Серьёзный",
                    "Интровертный", "Экстравертный"]
        try:
            await query.edit_message_reply_markup(reply_markup=deep_multiselect_keyboard(options4, sel))
        except Exception:
            await context.bot.send_message(chat_id=query.message.chat_id, text="Обновлено.", reply_markup=deep_multiselect_keyboard(options4, sel))
        return DEEP_BLOCK4

    if data == "deep_next" and context.user_data.get("deep_block4_selected") is not None:
        context.user_data["deep"]["block4"] = context.user_data.get("deep_block4_selected", [])
        entry = {
            "user_id": context.user_data.get("uid"),
            "photo": context.user_data.get("current_photo"),
            "rating": context.user_data.get("rating"),
            "details": context.user_data.get("details", []),
            "city": context.user_data.get("city"),
            "deep": context.user_data.get("deep"),
        }
        save_result(entry)
        await notify_admins(context, entry)
        try:
            await query.edit_message_text("Спасибо!\nТвои ответы уйдут в «Самцыч» и помогут создать портрет идеального парня в твоём городе.",
                                          reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📊 Перейти в канал", url="https://t.me/sam_tich")]]))
        except Exception:
            pass
        return ConversationHandler.END

    await query.answer("Неизвестная команда (deep).")
    return DEEP_BLOCK1

async def notify_admins(context: ContextTypes.DEFAULT_TYPE, entry: dict):
    text = (
        f"Новый ответ:\n"
        f"Пользователь ID: {entry.get('user_id')}\n\n"
        f"Фото: {entry.get('photo')}\n"
        f"Оценка: {entry.get('rating')}\n"
        f"Детали: {', '.join(entry.get('details') or [])}\n"
        f"Город: {entry.get('city')}\n"
        f"Глубокие ответы: {json.dumps(entry.get('deep'), ensure_ascii=False)}"
    )
    for admin in ADMIN_IDS:
        try:
            await context.bot.send_message(chat_id=admin, text=text)
        except Exception:
            logger.exception("Не удалось отправить админу %s", admin)

async def fallback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message:
        await update.message.reply_text("Используй меню для начала или /start.")
    return ConversationHandler.END

async def unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Команда не распознана. Используй /start чтобы начать.")

# -------------------- ConversationHandler --------------------
def build_conv_handler():
    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            START_MENU: [CallbackQueryHandler(menu_callback, pattern=r"^menu_")],
            RATE_PHOTO: [CallbackQueryHandler(rating_callback, pattern=r"^rate_")],
            AFTER_RATING: [CallbackQueryHandler(details_toggle_callback, pattern=r"^(toggle::|details_next)")],
            CITY_CHOICE: [CallbackQueryHandler(city_callback, pattern=r"^city::")],
            OTHER_CITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, other_city_text)],
            INVITE_DEEP: [CallbackQueryHandler(invite_callback, pattern=r"^invite_")],
            DEEP_BLOCK1: [CallbackQueryHandler(deep_toggle_callback, pattern=r"^(deep_toggle::|deep_next)")],
            DEEP_BLOCK2: [CallbackQueryHandler(deep_toggle_callback, pattern=r"^deep2::")],
            DEEP_BLOCK3: [CallbackQueryHandler(deep_toggle_callback, pattern=r"^(deep_toggle::|deep_next)")],
            DEEP_BLOCK4: [CallbackQueryHandler(deep_toggle_callback, pattern=r"^(deep_toggle::|deep_next)")],
        },
        fallbacks=[CommandHandler("start", start), MessageHandler(filters.TEXT & ~filters.COMMAND, fallback)],
        allow_reentry=True,
        persistent=False,
        per_chat=True,  # important: track conversation per chat so callbacks + messages both work
    )
    return conv

# -------------------- Main --------------------
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    conv = build_conv_handler()
    app.add_handler(conv)
    # Этот хендлер ставим ВЫШЕ ConversationHandler,
# чтобы он всегда ловил фото
    app.add_handler(MessageHandler(filters.PHOTO, debug_photo))
    app.add_handler(CommandHandler("start", start))  # extra safety
    # глобальный ловец неожиданных callback'ов — полезно для отладки
    async def global_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.callback_query:
            logger.info("GLOBAL callback: %s", update.callback_query.data)
            await update.callback_query.answer()
    app.add_handler(CallbackQueryHandler(global_cb))
    app.add_handler(MessageHandler(filters.COMMAND, unknown))

    logger.info("Бот запущен!")
    app.run_polling()

if __name__ == "__main__":
    main()
