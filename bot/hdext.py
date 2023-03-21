import io

import edge_tts
from telegram import Update
from telegram.ext import ContextTypes


async def conv_voice(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    text = " ".join(context.args)
    if not text:
        await update.effective_message.reply_text(
            "Please use '/v message' to send the message you want to convert to speech"
        )
        return
    send_voice(update, text)


async def send_voice(update: Update, text: str) -> None:
    comm = edge_tts.Communicate(text, "zh-CN-liaoning-XiaobeiNeural")
    with io.BytesIO() as out:
        async for message in comm.stream():
            if message["type"] == "audio":
                out.write(message["data"])
        out.seek(0)
        await update.effective_message.reply_voice(out)
