import aiohttp
import discord
import json
import os
import requests
from math import floor

EMOJI_DIGITS = ["0️⃣", "1️⃣","2️⃣","3️⃣","4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣"]
PERSPECTIVE_URL = 'https://commentanalyzer.googleapis.com/v1alpha1/comments:analyze'

class Perspectron(discord.Client):
    def __init__(self, perspective_key):
        super().__init__()
        self.http_session = aiohttp.ClientSession()
        self.ps_key = perspective_key

    async def on_ready(self):
        print('Logged in as')
        print(self.user.name)
        print(self.user.id)
        print('------')

    async def score_message(self, message):
        url = PERSPECTIVE_URL + '?key=' + self.ps_key
        data_dict = {
            'comment': {'text': message},
            'languages': ['en'],
            'requestedAttributes': {'TOXICITY': {}},
            'doNotStore': True
        }
        async with self.http_session.post(url, json=data_dict) as response:
            if response.status == 200:
                response_dict = await response.json()
        return response_dict["attributeScores"]["TOXICITY"]["summaryScore"]["value"]
        # return json.dumps(response_dict, indent=2)

    def score_to_emoji(self, score):
        if score < 0 or score > 1:
            return '🚩' # indicates an invalid score
        else:
            return EMOJI_DIGITS[floor(score * 10)]

    async def on_message(self, message):
        # we don't want the bot to reply to itself
        if message.author.id == self.user.id:
            return

        score = await self.score_message(message.content)
        await message.add_reaction(self.score_to_emoji(score))
        # await message.channel.send(str(score))

    # overwrite close method to clean up our objects as well
    async def close(self):
        await super().close()
        await self.http_session.close()

client = Perspectron(os.environ['PERSPECTIVE_KEY'])
client.run(os.environ['DISCORD_KEY'])
