from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BufferedInputFile, CallbackQuery, KeyboardButton, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder

from app.services.clients_table import ClientsTableService
from app.utils.files import FileStateError
from app.services.wg_manager import GeneratedClient, WgConfigError, WireGuardManager


router = Router()


class NewConfStates(StatesGroup):
    waiting_for_owner = State()
    waiting_for_device = State()
    waiting_for_format = State()


class RenameStates(StatesGroup):
    waiting_for_new_name = State()


def main_menu_keyboard():
    builder = ReplyKeyboardBuilder()
    builder.row(KeyboardButton(text="New conf"), KeyboardButton(text="List confs"))
    builder.row(KeyboardButton(text="Revoke conf"), KeyboardButton(text="Rename conf"))
    return builder.as_markup(resize_keyboard=True)


def format_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text=".conf", callback_data="new_conf:format:conf")
    builder.button(text=".vpn", callback_data="new_conf:format:vpn")
    return builder.as_markup()


def clients_keyboard(clients: list[dict], action: str):
    builder = InlineKeyboardBuilder()
    for index, client in enumerate(clients):
        label = ClientsTableService.client_name(client) or client.get("clientId") or f"Client {index + 1}"
        builder.button(text=label[:60], callback_data=f"{action}:{index}")
    builder.adjust(1)
    return builder.as_markup()


def _clients_list_text(clients: list[dict]) -> str:
    if not clients:
        return "Клиентов пока нет."
    lines = ["Список клиентов:"]
    for index, client in enumerate(clients, start=1):
        lines.append(
            f"{index}. {ClientsTableService.client_name(client)} | "
            f"{client.get('clientId', '—')} | "
            f"{ClientsTableService.creation_date(client)}"
        )
    return "\n".join(lines)


def _sanitize_filename(name: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in ("-", "_") else "_" for char in name)
    return cleaned.strip("_") or "client"


@router.message(CommandStart())
async def start_handler(message: Message) -> None:
    await message.answer("Главное меню:", reply_markup=main_menu_keyboard())


@router.message(F.text == "New conf")
async def new_conf_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(NewConfStates.waiting_for_owner)
    await message.answer("Для кого создать конфиг?")


@router.message(NewConfStates.waiting_for_owner)
async def new_conf_owner(message: Message, state: FSMContext) -> None:
    owner = (message.text or "").strip()
    if not owner:
        await message.answer("Имя не должно быть пустым. Введите, для кого конфиг.")
        return
    await state.update_data(owner=owner)
    await state.set_state(NewConfStates.waiting_for_device)
    await message.answer("Для какого устройства?")


@router.message(NewConfStates.waiting_for_device)
async def new_conf_device(message: Message, state: FSMContext) -> None:
    device = (message.text or "").strip()
    if not device:
        await message.answer("Название устройства не должно быть пустым. Введите устройство.")
        return
    await state.update_data(device=device)
    await state.set_state(NewConfStates.waiting_for_format)
    await message.answer("В каком формате выдать конфиг?", reply_markup=format_keyboard())


@router.callback_query(F.data.startswith("new_conf:format:"))
async def new_conf_format(
    callback: CallbackQuery,
    state: FSMContext,
    wg_manager: WireGuardManager,
) -> None:
    data = await state.get_data()
    owner = (data.get("owner") or "").strip()
    device = (data.get("device") or "").strip()
    if not owner or not device:
        await callback.answer("Сценарий истек. Начните заново.", show_alert=True)
        await state.clear()
        return

    file_format = callback.data.rsplit(":", 1)[-1]
    await callback.answer()
    await callback.message.answer("Создаю конфиг и обновляю WireGuard...")

    try:
        result = wg_manager.create_client(owner, device)
    except (WgConfigError, FileStateError, ValueError) as exc:
        await callback.message.answer(f"Не удалось создать конфиг:\n{exc}", reply_markup=main_menu_keyboard())
        await state.clear()
        return

    await _send_generated_file(callback.message, result, file_format)
    await callback.message.answer(
        "Конфиг создан.",
        reply_markup=main_menu_keyboard(),
    )
    await state.clear()


async def _send_generated_file(message: Message, result: GeneratedClient, file_format: str) -> None:
    client_name = ClientsTableService.client_name(result.client_record)
    filename_base = _sanitize_filename(client_name)
    if file_format == "vpn":
        payload = result.vpn_uri.encode("utf-8")
        filename = f"{filename_base}.vpn"
    else:
        payload = result.native_conf.encode("utf-8")
        filename = f"{filename_base}.conf"

    document = BufferedInputFile(payload, filename=filename)
    await message.answer_document(
        document=document,
        caption=(
            f"clientName: {client_name}\n"
            f"clientId: {result.client_record['clientId']}\n"
            f"clientIp: {result.client_record['clientIp']}"
        ),
    )


@router.message(F.text == "List confs")
async def list_confs(message: Message, wg_manager: WireGuardManager) -> None:
    try:
        clients = wg_manager.list_clients()
    except (WgConfigError, FileStateError, ValueError) as exc:
        await message.answer(f"Не удалось прочитать clientsTable:\n{exc}", reply_markup=main_menu_keyboard())
        return
    await message.answer(_clients_list_text(clients), reply_markup=main_menu_keyboard())


@router.message(F.text == "Revoke conf")
async def revoke_start(message: Message, wg_manager: WireGuardManager) -> None:
    try:
        clients = wg_manager.list_clients()
    except (WgConfigError, FileStateError, ValueError) as exc:
        await message.answer(f"Не удалось прочитать clientsTable:\n{exc}")
        return
    if not clients:
        await message.answer("Клиентов для удаления нет.", reply_markup=main_menu_keyboard())
        return
    await message.answer("Выберите клиента для удаления:", reply_markup=clients_keyboard(clients, "revoke"))


@router.callback_query(F.data.startswith("revoke:"))
async def revoke_selected(callback: CallbackQuery, wg_manager: WireGuardManager) -> None:
    try:
        index = int(callback.data.split(":", 1)[1])
        clients = wg_manager.list_clients()
        client = clients[index]
        deleted = wg_manager.revoke_client(str(client["clientId"]))
    except (ValueError, IndexError, KeyError, WgConfigError, FileStateError) as exc:
        await callback.answer()
        await callback.message.answer(f"Не удалось удалить конфиг:\n{exc}", reply_markup=main_menu_keyboard())
        return

    await callback.answer("Конфиг отозван.")
    await callback.message.answer(
        f"Удален клиент: {ClientsTableService.client_name(deleted)}",
        reply_markup=main_menu_keyboard(),
    )


@router.message(F.text == "Rename conf")
async def rename_start(message: Message, wg_manager: WireGuardManager) -> None:
    try:
        clients = wg_manager.list_clients()
    except (WgConfigError, FileStateError, ValueError) as exc:
        await message.answer(f"Не удалось прочитать clientsTable:\n{exc}")
        return
    if not clients:
        await message.answer("Клиентов для переименования нет.", reply_markup=main_menu_keyboard())
        return
    await message.answer("Выберите клиента для переименования:", reply_markup=clients_keyboard(clients, "rename"))


@router.callback_query(F.data.startswith("rename:"))
async def rename_selected(
    callback: CallbackQuery,
    state: FSMContext,
    wg_manager: WireGuardManager,
) -> None:
    try:
        index = int(callback.data.split(":", 1)[1])
        clients = wg_manager.list_clients()
        client = clients[index]
    except (ValueError, IndexError, KeyError, WgConfigError, FileStateError) as exc:
        await callback.answer()
        await callback.message.answer(f"Не удалось выбрать клиента:\n{exc}", reply_markup=main_menu_keyboard())
        return

    await state.clear()
    await state.set_state(RenameStates.waiting_for_new_name)
    await state.update_data(client_id=str(client["clientId"]))
    await callback.answer()
    await callback.message.answer(
        f"Введите новое имя для {ClientsTableService.client_name(client)}:"
    )


@router.message(RenameStates.waiting_for_new_name)
async def rename_apply(message: Message, state: FSMContext, wg_manager: WireGuardManager) -> None:
    new_name = (message.text or "").strip()
    if not new_name:
        await message.answer("Новое имя не должно быть пустым.")
        return
    data = await state.get_data()
    client_id = str(data.get("client_id", "")).strip()
    if not client_id:
        await message.answer("Сценарий истек. Начните заново.", reply_markup=main_menu_keyboard())
        await state.clear()
        return
    try:
        updated = wg_manager.rename_client(client_id, new_name)
    except (ValueError, WgConfigError, FileStateError) as exc:
        await message.answer(f"Не удалось переименовать клиента:\n{exc}", reply_markup=main_menu_keyboard())
        await state.clear()
        return

    await message.answer(
        f"Новое имя сохранено: {ClientsTableService.client_name(updated)}",
        reply_markup=main_menu_keyboard(),
    )
    await state.clear()
