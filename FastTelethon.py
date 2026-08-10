import asyncio
import os
import math
from telethon import TelegramClient
from telethon.tl import types, functions

# Custom part size helper function (Fix for Telethon update error)
def get_part_size(file_size: int) -> int:
    if file_size <= 100 * 1024 * 1024:
        return 128  # 128 KB
    elif file_size <= 500 * 1024 * 1024:
        return 256  # 256 KB
    else:
        return 512  # 512 KB

class ParallelTransferrer:
    def __init__(self, client: TelegramClient, connection_count: int = 4):
        self.client = client
        self.connection_count = connection_count
        self.connections = []

    async def _get_connections(self):
        if not self.connections:
            for _ in range(self.connection_count):
                dc_id = self.client.session.dc_id
                sender = await self.client._create_exported_sender(dc_id)
                await sender.connect()
                self.connections.append(sender)
        return self.connections

    async def upload_file(self, file_path: str, progress_callback=None):
        file_size = os.path.getsize(file_path)
        part_size_kb = get_part_size(file_size)
        part_size = part_size_kb * 1024
        part_count = math.ceil(file_size / part_size)
        file_id = int.from_bytes(os.urandom(8), byteorder="big", signed=True)
        is_large = file_size > 10 * 1024 * 1024

        senders = await self._get_connections()
        sender_count = len(senders)

        uploaded_parts = 0
        lock = asyncio.Lock()

        async def upload_part(part_index, part_data, sender):
            nonlocal uploaded_parts
            if is_large:
                req = functions.upload.SaveBigFilePartRequest(
                    file_id=file_id,
                    file_part=part_index,
                    file_total_parts=part_count,
                    bytes=part_data
                )
            else:
                req = functions.upload.SaveFilePartRequest(
                    file_id=file_id,
                    file_part=part_index,
                    bytes=part_data
                )
            await sender(req)
            async with lock:
                uploaded_parts += 1
                if progress_callback:
                    await progress_callback(uploaded_parts * part_size, file_size)

        tasks = []
        with open(file_path, "rb") as f:
            for part_index in range(part_count):
                part_data = f.read(part_size)
                sender = senders[part_index % sender_count]
                tasks.append(upload_part(part_index, part_data, sender))
                if len(tasks) >= sender_count * 2:
                    await asyncio.gather(*tasks)
                    tasks = []

            if tasks:
                await asyncio.gather(*tasks)

        if is_large:
            return types.InputFileBig(id=file_id, parts=part_count, name=os.path.basename(file_path))
        else:
            return types.InputFile(id=file_id, parts=part_count, name=os.path.basename(file_path), md5_checksum="")
