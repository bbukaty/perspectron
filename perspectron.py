import aiohttp
import discord
import json
import os
import re
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
            'requestedAttributes': {'TOXICITY': {}, 'SEVERE_TOXICITY': {},
                                    'IDENTITY_ATTACK': {}, 'THREAT': {},
                                    'FLIRTATION': {}},
            'doNotStore': True
        }
        async with self.http_session.post(url, json=data_dict) as response:
            if response.status == 200:
                response_dict = await response.json()
        return response_dict
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
        
        report = re.search(r"^!report (\d+)", message.content)
        if report:
            reporter = message.author
            reported_msg = await message.channel.fetch_message(report.group(1))
            reported_user = reported_msg.author
            # delete evidence of the report (not ideal) and act on it
            await message.delete()
            if reported_user.id == self.user.id:
                await message.channel.send(reporter.mention + ", please refrain from reporting my moderation messages.")
                return
            await message.channel.send("Received report for:\n```{}```".format(reported_msg.content))
            return

        response_dict = await self.score_message(message.content)

        score_summary = ""
        for attr in sorted(response_dict["attributeScores"].keys()):
            indent = 18 - len(attr) #18 is a nice indent size for these keywords
            score_summary += attr + ":"
            for i in range(indent):
                score_summary += " "
            score_summary += str(response_dict["attributeScores"][attr]["summaryScore"]["value"]) + "\n"


        # await message.channel.send("```"+json.dumps(response_dict, indent=2)+"```")
        await message.channel.send("```"+score_summary+"```")


        score = response_dict["attributeScores"]["SEVERE_TOXICITY"]["summaryScore"]["value"]
        await message.add_reaction(self.score_to_emoji(score))
        # await message.channel.send(str(score))

    # overwrite close method to clean up our objects as well
    async def close(self):
        await super().close()
        await self.http_session.close()

client = Perspectron(os.environ['PERSPECTIVE_KEY'])
client.run(os.environ['DISCORD_KEY'])
