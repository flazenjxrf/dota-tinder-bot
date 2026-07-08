from aiogram.types import Message, CallbackQuery, InputMediaPhoto
from aiogram.exceptions import TelegramBadRequest


def _is_invalid_photo_error(exc: TelegramBadRequest) -> bool:
    message = (exc.message or "").lower()
    return "wrong file identifier" in message or "http url specified" in message


async def send_profile_card(
    message_or_callback: Message | CallbackQuery,
    photo_file_id: str,
    caption: str,
    reply_markup,
):
    """Отправляет карточку анкеты. При битом file_id показывает текст без фото."""
    fallback_caption = f"{caption}\n\n⚠️ <i>Фото этой анкеты недоступно.</i>"

    if isinstance(message_or_callback, CallbackQuery):
        message = message_or_callback.message
        try:
            media = InputMediaPhoto(media=photo_file_id, caption=caption, parse_mode="HTML")
            await message.edit_media(media=media, reply_markup=reply_markup)
            return
        except TelegramBadRequest as exc:
            if not _is_invalid_photo_error(exc):
                raise
            await message.delete()
            await message.answer(fallback_caption, reply_markup=reply_markup)
            return

    try:
        await message_or_callback.answer_photo(
            photo=photo_file_id,
            caption=caption,
            reply_markup=reply_markup,
        )
    except TelegramBadRequest as exc:
        if not _is_invalid_photo_error(exc):
            raise
        await message_or_callback.answer(fallback_caption, reply_markup=reply_markup)
