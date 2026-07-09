from datetime import datetime
from html import escape

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery

from bot.config import ADMIN_IDS
from bot.database.models import ReportReason, User, BannedUser
from bot.database.requests import (
    get_profile_stats,
    get_pending_reports_count,
    get_pending_report_ids,
    get_report_by_id,
    get_users_by_ids,
    reject_report,
    ban_user,
    unban_user,
    get_banned_users_count,
    get_banned_user_at_index,
)
from bot.filters.admin import IsAdmin
from bot.keyboards.inline import (
    AdminMenuCallback,
    AdminReportNavCallback,
    AdminReportActionCallback,
    AdminBanNavCallback,
    AdminUnbanCallback,
    get_admin_menu_keyboard,
    get_admin_reports_nav_keyboard,
    get_admin_back_keyboard,
    get_admin_bans_keyboard,
    REPORT_REASON_LABELS,
)
from bot.utils.profile_display import send_profile_card
from bot.handlers.profile import make_profile_caption

router = Router()
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())


def _format_user_ref(user: User | None, telegram_id: int) -> str:
    if user and user.username:
        return f"@{escape(user.username)} (<code>{telegram_id}</code>)"
    return f"<code>{telegram_id}</code>"


def _format_report_header(
    report_id: int,
    reporter: User | None,
    from_user_id: int,
    reason: ReportReason,
    created_at: datetime,
    comment: str | None = None,
) -> str:
    reason_label = REPORT_REASON_LABELS.get(reason.value, reason.value)
    date_str = created_at.strftime("%d.%m.%Y %H:%M UTC")
    text = (
        f"🚨 <b>Жалоба #{report_id}</b>\n\n"
        f"👤 От: {_format_user_ref(reporter, from_user_id)}\n"
        f"📋 Причина: {reason_label}\n"
    )
    if comment:
        text += f"💬 Комментарий: <i>{escape(comment)}</i>\n"
    text += f"🕐 Дата: {date_str}\n\n<b>Анкета нарушителя:</b>"
    return text


async def _send_admin_menu(target: Message, edit: bool = False):
    pending = await get_pending_reports_count()
    banned_count = await get_banned_users_count()
    text = (
        "🛠 <b>Админ-панель</b>\n\n"
        f"Ожидают рассмотрения: <b>{pending}</b> жалоб(ы)\n"
        f"Забанено: <b>{banned_count}</b>\n\n"
        "Выбери раздел:"
    )
    keyboard = get_admin_menu_keyboard(pending, banned_count)
    if edit:
        await target.edit_text(text, reply_markup=keyboard)
    else:
        await target.answer(text, reply_markup=keyboard)


async def _send_stats(target: Message, edit: bool = False):
    stats = await get_profile_stats()
    pending = await get_pending_reports_count()
    text = (
        "📊 <b>Статистика анкет</b>\n\n"
        f"✅ Активных: <b>{stats['active']}</b>\n"
        f"⏸ Скрытых: <b>{stats['hidden']}</b>\n"
        f"🚫 Заблокированных: <b>{stats['banned']}</b>\n"
        f"📝 Незавершённых: <b>{stats['incomplete']}</b>\n"
        f"━━━━━━━━━━━━━━━\n"
        f"👥 Зарегистрировано: <b>{stats['registered']}</b>\n"
        f"📦 Всего записей: <b>{stats['total']}</b>\n\n"
        f"🚨 Жалоб в очереди: <b>{pending}</b>"
    )
    keyboard = get_admin_back_keyboard()
    if edit:
        await target.edit_text(text, reply_markup=keyboard)
    else:
        await target.answer(text, reply_markup=keyboard)


async def _show_report_at_index(message: Message, index: int, edit: bool = False):
    report_ids = await get_pending_report_ids()
    total = len(report_ids)

    if total == 0:
        text = "✅ Нет жалоб, ожидающих рассмотрения."
        keyboard = get_admin_back_keyboard()
        if edit:
            await message.edit_text(text, reply_markup=keyboard)
        else:
            await message.answer(text, reply_markup=keyboard)
        return

    index = min(max(index, 0), total - 1)
    report_id = report_ids[index]
    report = await get_report_by_id(report_id)
    if not report:
        await _send_admin_menu(message, edit=edit)
        return

    users = await get_users_by_ids([report.from_user_id, report.to_user_id])
    reporter = users.get(report.from_user_id)
    accused = users.get(report.to_user_id)

    header = _format_report_header(
        report.id,
        reporter,
        report.from_user_id,
        report.reason,
        report.created_at,
        report.comment,
    )
    keyboard = get_admin_reports_nav_keyboard(report.id, index, total)

    if accused:
        caption = f"{header}\n\n{make_profile_caption(accused)}"
        if edit:
            try:
                await message.delete()
            except Exception:
                pass
            await send_profile_card(message, accused.photo_file_id, caption, keyboard)
        else:
            await send_profile_card(message, accused.photo_file_id, caption, keyboard)
    else:
        text = (
            f"{header}\n\n"
            f"⚠️ Анкета пользователя <code>{report.to_user_id}</code> не найдена "
            f"(возможно, уже удалена)."
        )
        if edit:
            await message.edit_text(text, reply_markup=keyboard)
        else:
            await message.answer(text, reply_markup=keyboard)


def _format_banned_user_header(banned: BannedUser, user: User | None, index: int, total: int) -> str:
    date_str = banned.banned_at.strftime("%d.%m.%Y %H:%M UTC")
    text = (
        f"🚫 <b>Забаненный пользователь</b> ({index + 1}/{total})\n\n"
        f"👤 ID: <code>{banned.telegram_id}</code>\n"
    )
    if user:
        text += f"📛 Анкета: <b>{escape(user.name)}</b>"
        if user.username:
            text += f" (@{escape(user.username)})"
        text += "\n"
    else:
        text += "📛 Анкета: <i>удалена</i>\n"
    if banned.reason:
        text += f"📋 Причина: <i>{escape(banned.reason)}</i>\n"
    text += f"🕐 Забанен: {date_str}\n"
    text += f"👮 Админ: <code>{banned.banned_by}</code>"
    return text


async def _show_banned_at_index(message: Message, index: int, edit: bool = False):
    banned, user, total = await get_banned_user_at_index(index)

    if total == 0:
        text = "✅ Нет забаненных пользователей."
        keyboard = get_admin_back_keyboard()
        if edit:
            await message.edit_text(text, reply_markup=keyboard)
        else:
            await message.answer(text, reply_markup=keyboard)
        return

    index = min(max(index, 0), total - 1)
    banned, user, total = await get_banned_user_at_index(index)
    if not banned:
        await _send_admin_menu(message, edit=edit)
        return

    header = _format_banned_user_header(banned, user, index, total)
    keyboard = get_admin_bans_keyboard(banned.telegram_id, index, total)

    if user:
        caption = f"{header}\n\n{make_profile_caption(user)}"
        if edit:
            try:
                await message.delete()
            except Exception:
                pass
            await send_profile_card(message, user.photo_file_id, caption, keyboard)
        else:
            await send_profile_card(message, user.photo_file_id, caption, keyboard)
    else:
        text = header
        if edit:
            await message.edit_text(text, reply_markup=keyboard)
        else:
            await message.answer(text, reply_markup=keyboard)


@router.message(Command("admin"))
async def cmd_admin(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    await _send_admin_menu(message)


@router.callback_query(AdminMenuCallback.filter())
async def admin_menu_callback(callback: CallbackQuery, callback_data: AdminMenuCallback):
    if callback_data.action == "menu":
        await _send_admin_menu(callback.message, edit=True)
    elif callback_data.action == "stats":
        await _send_stats(callback.message, edit=True)
    elif callback_data.action == "reports":
        await _show_report_at_index(callback.message, 0, edit=True)
    elif callback_data.action == "bans":
        await _show_banned_at_index(callback.message, 0, edit=True)
    await callback.answer()


@router.callback_query(AdminReportNavCallback.filter())
async def admin_report_nav(callback: CallbackQuery, callback_data: AdminReportNavCallback):
    await _show_report_at_index(callback.message, callback_data.index, edit=True)
    await callback.answer()


@router.callback_query(F.data == "admin_reports_counter")
async def admin_reports_counter(callback: CallbackQuery):
    await callback.answer()


@router.callback_query(AdminReportActionCallback.filter())
async def admin_report_action(
    callback: CallbackQuery,
    callback_data: AdminReportActionCallback,
):
    report = await get_report_by_id(callback_data.report_id)
    if not report:
        await callback.answer("Жалоба не найдена.", show_alert=True)
        return

    if callback_data.action == "reject":
        success = await reject_report(callback_data.report_id)
        if success:
            await callback.answer("Жалоба отклонена.")
        else:
            await callback.answer("Жалоба уже обработана.", show_alert=True)
    elif callback_data.action == "ban":
        reason_label = REPORT_REASON_LABELS.get(report.reason.value, report.reason.value)
        ban_reason = f"Жалоба #{report.id}: {reason_label}"
        if report.comment:
            ban_reason += f" — {report.comment}"
        banned = await ban_user(
            report.to_user_id,
            callback.from_user.id,
            reason=ban_reason,
        )
        if banned:
            await callback.answer("Пользователь заблокирован.")
        else:
            await callback.answer("Пользователь уже заблокирован.", show_alert=True)

    await _show_report_at_index(callback.message, callback_data.index, edit=True)


@router.callback_query(AdminBanNavCallback.filter())
async def admin_ban_nav(callback: CallbackQuery, callback_data: AdminBanNavCallback):
    await _show_banned_at_index(callback.message, callback_data.index, edit=True)
    await callback.answer()


@router.callback_query(F.data == "admin_bans_counter")
async def admin_bans_counter(callback: CallbackQuery):
    await callback.answer()


@router.callback_query(AdminUnbanCallback.filter())
async def admin_unban_user(callback: CallbackQuery, callback_data: AdminUnbanCallback):
    telegram_id = callback_data.telegram_id
    success = await unban_user(telegram_id)

    if success:
        await callback.answer("Пользователь разбанен.")
        try:
            await callback.bot.send_message(
                telegram_id,
                "✅ <b>Твой аккаунт разблокирован.</b>\n\n"
                "Можешь снова пользоваться ботом — отправь /start.",
            )
        except Exception:
            pass
    else:
        await callback.answer("Пользователь не найден в списке банов.", show_alert=True)

    await _show_banned_at_index(callback.message, callback_data.index, edit=True)


async def notify_admins_new_report(
    bot,
    report_id: int,
    from_user_id: int,
    to_user_id: int,
    reason_key: str,
    comment: str | None = None,
):
    if not ADMIN_IDS:
        return

    users = await get_users_by_ids([from_user_id, to_user_id])
    reporter = users.get(from_user_id)
    accused = users.get(to_user_id)
    reason_label = REPORT_REASON_LABELS.get(reason_key, reason_key)

    text = (
        f"🆕 <b>Новая жалоба #{report_id}</b>\n\n"
        f"От: {_format_user_ref(reporter, from_user_id)}\n"
        f"На: {_format_user_ref(accused, to_user_id)}\n"
        f"Причина: {reason_label}\n"
    )
    if comment:
        text += f"Комментарий: <i>{escape(comment)}</i>\n"
    text += "\nОткрой /admin для рассмотрения."

    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(admin_id, text)
        except Exception:
            pass
