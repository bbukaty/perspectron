import aiohttp
import discord
import json
import os
import re
from math import floor

PERSPECTIVE_URL = 'https://commentanalyzer.googleapis.com/v1alpha1/comments:analyze'

EMOJI_DIGITS = ["0️⃣", "1️⃣","2️⃣","3️⃣","4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣"]
EMOJI_OK, EMOJI_WARNING, EMOJI_ALERT = "⬜", "🟧", "🟥"

UNMONITORED_CHANNELS = [653404020005797903, 649411727745744907]

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

    async def request_message_score(self, message):
        url = PERSPECTIVE_URL + '?key=' + self.ps_key
        data_dict = {
            'comment': {'text': message},
            'languages': ['en'],
            'requestedAttributes': {'TOXICITY': {}, 'SEVERE_TOXICITY': {},
                                    'IDENTITY_ATTACK': {}, 'THREAT': {},
                                    'FLIRTATION': {}, 'PROFANITY': {}},
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
    
    async def handle_report(self, report, reported_msg_id):
        reporter = report.author
        reported_msg = await report.channel.fetch_message(reported_msg_id)
        reported_user = reported_msg.author
        # delete evidence of the report (not ideal) and act on it
        await report.delete()
        if reported_user.id == self.user.id:
            await report.channel.send(reporter.mention + ", please refrain from reporting my moderation messages.")
            return
        await report.channel.send("Received report for:\n```{}```".format(reported_msg.content))
            

    def construct_summary(self, response_dict):
        score_summary = "```\n"
        attributes = sorted(response_dict["attributeScores"].keys())
        for attr in attributes:
            value = response_dict["attributeScores"][attr]["summaryScore"]["value"]
            if value > 0.8:
                indicator = EMOJI_ALERT
            elif value > 0.5:
                indicator = EMOJI_WARNING
            else:
                indicator = EMOJI_OK
            score_summary += "{:18}{} {:4.1f}\n".format(attr + ":", indicator, value*100)
        score_summary += "```"
        return score_summary

    async def on_message(self, message):
        # we don't want the bot to reply to itself or monitor the feedback channel
        if message.author.id == self.user.id or message.channel.id in UNMONITORED_CHANNELS:
            return
        
        report_match = re.search(r"^!report (\d+)", message.content)
        if report_match:
            await self.handle_report(message, report_match.group(1))
            return

        response_dict = await self.request_message_score(message.content)
        await message.channel.send(self.construct_summary(response_dict))

        # add reaction based on message score
        # score = response_dict["attributeScores"]["SEVERE_TOXICITY"]["summaryScore"]["value"]
        # await message.add_reaction(self.score_to_emoji(score))

    # overwrite close method to clean up our objects as well
    async def close(self):
        await super().close()
        await self.http_session.close()

client = Perspectron(os.environ['PERSPECTIVE_KEY'])
client.run(os.environ['DISCORD_KEY'])
