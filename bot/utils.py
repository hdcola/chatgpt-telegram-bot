# SPDX-License-Identifier: MIT

# Copyright (c) 2023 scmanjarrez. All rights reserved.
# This work is licensed under the terms of the MIT license.

import asyncio
import html
import io
import json
import logging
import re
import traceback
from functools import partial
from pathlib import Path
from typing import Any, Dict, List, Tuple, Union

import aiohttp
import database as db
import edge_tts
from aiohttp.web import HTTPException
from dateutil.parser import isoparse
from EdgeGPT import Chatbot, ConversationStyle
from telegram import (InlineKeyboardButton, InlineKeyboardMarkup, Message,
                      Update, constants)
from telegram.constants import ParseMode
from telegram.error import BadRequest
from telegram.ext import ContextTypes

PATH = {"dir": "config", "cookies": "cookies.json",
        "config": "config.json", "database": "users.db"}
DATA = {"config": None, "tts": None, "msg": {}}
CONV = {}
LOG_FILT = ["Removed job", "Added job", "Job", "Running job"]
REF = re.compile(r"\[\^(\d+)\^\]")
REF_SP = re.compile(r"(\w+)(\[\^\d+\^\])")
BCODE = re.compile(r"(?<!\()(```+)")
BCODE_LANG = re.compile(r"((```+)\w*\n*)")
CODE = re.compile(r"(?<!\()(`+)(.+?)\1(?!\))")
BOLD = re.compile(r"(?<![\(`])(?:\*\*([^*`]+?)\*\*|__([^_`]+?)__)")
ITA = re.compile(r"(?<![\(`\*_])(?:\*([^*`]+?)\*|_([^_``]+?)_)")
DEBUG = False
ASR_API = "https://api.assemblyai.com/v2"


class NoLog(logging.Filter):
    def filter(self, record):
        logged = True
        for lf in LOG_FILT:
            if lf in record.getMessage():
                logged = False
                break
        return logged


def rename_files() -> None:
    cwd = Path(".")
    tmp = cwd.joinpath(".allowed.txt")
    if tmp.exists():
        for _cid in tmp.read_text().split():
            db.add_user(int(_cid))
        tmp.unlink()
    cfg = Path(PATH["dir"])
    for k, v in PATH.items():
        if k not in ("dir", "database"):
            tmp = cwd.joinpath(f".{v}")
            if tmp.exists():
                tmp.rename(cfg.joinpath(v))


def set_up() -> None:
    Path(PATH["dir"]).mkdir(exist_ok=True)
    db.setup_db()
    rename_files()
    with open(path("config")) as f:
        DATA["config"] = json.load(f)
    try:
        logging.getLogger().setLevel(settings("log_level").upper())
    except KeyError:
        pass


def settings(key: str) -> str:
    return DATA["config"]["settings"][key]


def path(key: str) -> str:
    return Path(PATH["dir"]).joinpath(PATH[key])


def exists(key: str) -> bool:
    return Path(".").joinpath(f".{PATH[key]}").exists() or path(key).exists()


def passwd_correct(passwd: str) -> bool:
    return passwd == DATA["config"]["chats"]["password"]


def cid(update: Update) -> int:
    return update.effective_chat.id


def is_group(update: Update) -> bool:
    return update.effective_chat.id < 0


def button(buttons) -> List[InlineKeyboardButton]:
    return [InlineKeyboardButton(bt[0], callback_data=bt[1]) for bt in buttons]


def markup(buttons: List[List[InlineKeyboardButton]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(buttons)


def button_query(update: Update, index: str) -> str:
    for (kb,) in update.effective_message.reply_markup.inline_keyboard:
        if kb.callback_data == f"response_{index}":
            return kb.text


def chunk(lst: List[str], size: int = 6) -> List[str]:
    for idx in range(0, len(lst), size):
        yield lst[idx: idx + size]


async def list_voices() -> Dict[str, Dict[str, List[str]]]:
    if DATA["tts"] is None:
        DATA["tts"] = {}
        voices = await edge_tts.list_voices()
        for vc in voices:
            lang = vc["Locale"].split("-")[0]
            gend = vc["Gender"]
            if lang not in DATA["tts"]:
                DATA["tts"][lang] = {}
            if gend not in DATA["tts"][lang]:
                DATA["tts"][lang][gend] = []
            DATA["tts"][lang][gend].append(vc["ShortName"])
    return DATA["tts"]


async def send(
    update: Update,
    text: str,
    quote: bool = False,
    reply_markup: InlineKeyboardMarkup = None,
) -> Message:
    return await update.effective_message.reply_html(
        text,
        disable_web_page_preview=True,
        quote=quote,
        reply_markup=reply_markup,
    )


async def edit(
    update: Update, text: str, reply_markup: InlineKeyboardMarkup = None
) -> None:
    try:
        await update.callback_query.edit_message_text(
            text,
            ParseMode.HTML,
            reply_markup=reply_markup,
            disable_web_page_preview=True,
        )
    except BadRequest as br:
        if not str(br).startswith("Message is not modified:"):
            print(
                f"***  Exception caught in edit "
                f"({update.effective_message.chat.id}): ",
                br,
            )
            traceback.print_stack()


async def send_action(context: ContextTypes.DEFAULT_TYPE) -> None:
    await context.bot.send_chat_action(context.job.chat_id, context.job.data)


async def automatic_speech_recognition(data: bytearray) -> str:
    text = "Could not connect to AssemblyAI API. Try again later."
    try:
        async with aiohttp.ClientSession(
            headers={"authorization": settings("assemblyai_token")}
        ) as session:
            async with session.post(f"{ASR_API}/upload", data=data) as req:
                resp = await req.json()
                upload = {"audio_url": resp["upload_url"]}
            async with session.post(
                f"{ASR_API}/transcript", json=upload
            ) as req:
                resp = await req.json()
                upload_id = resp["id"]
                status = resp["status"]
                while status not in ("completed", "error"):
                    async with session.get(
                        f"{ASR_API}/transcript/{upload_id}"
                    ) as req:
                        resp = await req.json()
                        status = resp["status"]
                        if DEBUG:
                            logging.getLogger("EdgeGPT-ASR").info(
                                f"{upload_id}: {status}"
                            )
                        await asyncio.sleep(5)
                text = resp["text"]
    except HTTPException:
        pass
    return text
