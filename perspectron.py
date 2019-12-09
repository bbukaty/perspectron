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
MOD_CHANNEL = 649411727745744907

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


    async def forward_to_mods(self, response_dict, message, reported=False):
        #TODO: cleaner formatting
        report_string = "\n\n"
        if reported:
            report_string += "Received report for:"
        else:
            report_string += "Perpective flagged:"
        report_string += "\n```{}```from user {} in channel {}.\n"
        await self.get_channel(MOD_CHANNEL).send(
            report_string.format(message.content,
                                 message.author.name,
                                 message.channel.name))
        await self.get_channel(MOD_CHANNEL).send(self.construct_summary(response_dict))
        return


    async def handle_report(self, report, reported_msg_id):
        print("handling report?")
        reporter = report.author
        reported_msg = await report.channel.fetch_message(reported_msg_id)
        reported_user = reported_msg.author
        # delete evidence of the report (not ideal) and act on it
        await report.delete()
        if reported_user.id == self.user.id:
            await report.channel.send(reporter.mention + ", please refrain from reporting my moderation messages.")
            return

        # currently mod channel is hard-coded
        # forward message and score to mod channel
        response_dict = await self.request_message_score(reported_msg.content)
        await self.forward_to_mods(response_dict, reported_msg, True)

        #await report.channel.send("Received report for:\n```{}```".format(reported_msg.content))


    def get_attribute(self, response_dict, attr):
        return response_dict["attributeScores"][attr]["summaryScore"]["value"]


    def construct_summary(self, response_dict):
        score_summary = "```\n"
        attributes = sorted(response_dict["attributeScores"].keys())
        for attr in attributes:
            # value = response_dict["attributeScores"][attr]["summaryScore"]["value"]
            value = self.get_attribute(response_dict, attr)
            if value > 0.8:
                indicator = EMOJI_ALERT
            elif value > 0.5:
                indicator = EMOJI_WARNING
            else:
                indicator = EMOJI_OK
            score_summary += "{:18}{} {:4.1f}\n".format(attr + ":", indicator, value*100)
        score_summary += "```"
        return score_summary



    def check_needs_moderation(self, response_dict):
        #TODO: read in from config file?
        #TODO: profanity tie-breaks
        thresholds = { 'SEVERE_TOXICITY': 0.5, 'IDENTITY_ATTACK': 0.5, 'THREAT': 0.5 }
        attributes = sorted(response_dict["attributeScores"].keys())
        needs_moderation = False
        for attr in attributes:
            if attr in thresholds:
                if self.get_attribute(response_dict, attr) > thresholds[attr]:
                    needs_moderation = True
        return needs_moderation


    async def on_message(self, message):
        # we don't want the bot to reply to itself or monitor the feedback channel
        if message.author.id == self.user.id or message.channel.id in UNMONITORED_CHANNELS:
            return

        report_match = re.search(r"^!report (\d+)", message.content)
        if report_match:
            await self.handle_report(message, report_match.group(1))
            return

        response_dict = await self.request_message_score(message.content)
        if self.check_needs_moderation(response_dict):
            await self.forward_to_mods(response_dict, message)

        # add reaction based on message score
        # score = response_dict["attributeScores"]["SEVERE_TOXICITY"]["summaryScore"]["value"]
        # await message.add_reaction(self.score_to_emoji(score))

    # overwrite close method to clean up our objects as well
    async def close(self):
        await super().close()
        await self.http_session.close()

client = Perspectron(os.environ['PERSPECTIVE_KEY'])
client.run(os.environ['DISCORD_KEY'])
