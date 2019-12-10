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
        self.blacklist = set()

    async def on_ready(self):
        print('Logged in as')
        print(self.user.name)
        print(self.user.id)
        print('------')

    async def request_message_scores(self, message):
        url = PERSPECTIVE_URL + '?key=' + self.ps_key
        data_dict = {
            'comment': {'text': message},
            'languages': ['en'],
            'requestedAttributes': {'SEVERE_TOXICITY': {}, 'PROFANITY': {},
                                    'IDENTITY_ATTACK': {}, 'THREAT': {},
                                   },
            'doNotStore': True
        }
        async with self.http_session.post(url, json=data_dict) as response:
            if response.status == 200:
                response_dict = await response.json()
        
        scores = {}
        for attr in response_dict["attributeScores"]:
            scores[attr] = response_dict["attributeScores"][attr]["summaryScore"]["value"]

        return scores
        # return json.dumps(response_dict, indent=2)

    def score_to_emoji(self, score):
        if score < 0 or score > 1:
            return '🚩' # indicates an invalid score
        else:
            return EMOJI_DIGITS[floor(score * 10)]


    async def forward_to_mods(self, msg_scores, message, reported=False, bl_phrases=None):
        report_string = "Received report for:\n" if reported else "Flagged:\n"
        report_string += "> {}\nfrom user {} in channel {}.\n"
        if bl_phrases:
            report_string += "Contains blacklisted phrases: `{}`\n".format("` `".join(bl_phrases))
        report_string += self.construct_summary(msg_scores)
        await self.get_channel(MOD_CHANNEL).send(
            report_string.format(message.content,
                                 message.author.mention,
                                 message.channel.mention))
        return


    async def handle_report(self, report, reported_msg_id):
        reporter = report.author
        reported_msg = await report.channel.fetch_message(reported_msg_id)
        reported_user = reported_msg.author
        # delete evidence of the report (not ideal) and act on it
        await report.delete()
        if reported_user.id == self.user.id:
            await report.channel.send(reporter.mention + ", please refrain from reporting my moderation messages.")
            return

        # currently mod channel is hard-coded
        # forward message to mod channel, re-request message scores and send as well
        msg_scores = await self.request_message_scores(reported_msg.content)
        await self.forward_to_mods(msg_scores, reported_msg, True)

        #await report.channel.send("Received report for:\n```{}```".format(reported_msg.content))

    def construct_summary(self, msg_scores):
        score_summary = "```\n"
        for attr, score in sorted(msg_scores.items()):
            if score > 0.8:
                indicator = EMOJI_ALERT
            elif score > 0.5:
                indicator = EMOJI_WARNING
            else:
                indicator = EMOJI_OK
            score_summary += "{:18}{} {:4.1f}\n".format(attr + ":", indicator, score*100)
        score_summary += "```"
        return score_summary
    
    async def handle_bl_command(self, action, phrase, command_msg):
        if action == "add":
            if phrase in self.blacklist:
                response = "`{}` is already in the blacklist.".format(phrase)
            else:
                self.blacklist.add(phrase)
                response = "Added `{}` to the blacklist.".format(phrase)
        elif action == "del":
            if phrase not in self.blacklist:
                response = "`{}` was not found in the blacklist.".format(phrase)
            else:
                self.blacklist.remove(phrase)
                response = "Successfully removed `{}` from the blacklist.".format(phrase)
        elif action == "show":
            if not self.blacklist:
                response = "The blacklist is currently empty."
            else:
                response = "Here are all the phrases in the blacklist:\n"
                response += "```\n{}\n```".format("\n".join(self.blacklist))
        else:
            response = "Unrecognized blacklist command. Options are `add`, `del`, and `show`."
        await command_msg.channel.send(response)

    def get_blacklisted_phrases(self, text):
        matches = []
        for phrase in self.blacklist:
            if re.search(r"\b{}\b".format(phrase), text, re.IGNORECASE):
                matches.append(phrase)
        return matches

    def check_needs_moderation(self, msg_scores):
        #TODO: read in from config file?
        #TODO: profanity tie-breaks
        thresholds = { 'SEVERE_TOXICITY': 0.75, 'IDENTITY_ATTACK': 0.5, 'THREAT': 0.5 }
        needs_moderation = False
        for attr, score in msg_scores.items():
            if attr in thresholds and score > thresholds[attr]:
                    needs_moderation = True
        return needs_moderation


    async def on_message(self, message):
        # we don't want the bot to reply to itself or monitor the feedback channel
        if message.author.id == self.user.id or message.channel.id in UNMONITORED_CHANNELS:
            return

        # Commands
        report_match = re.search(r"^!report (\d+)", message.content)
        if report_match:
            reported_msg_id = report_match.group(1)
            await self.handle_report(message, reported_msg_id)
            return
        
        eval_match = re.search(r"^!eval (.+)", message.content)
        if eval_match:
            to_evaluate = eval_match.group(1)
            msg_scores = await self.request_message_scores(to_evaluate)
            await message.channel.send(self.construct_summary(msg_scores))
            return
        
        bl_command_match = re.search(r"^!bl (\w+)(?: (.+))?", message.content)
        if bl_command_match:
            action, phrase = bl_command_match.group(1), bl_command_match.group(2)
            if action in {"add", "del"} and not phrase:
                await message.channel.send("Please specify a phrase.")
                return
            await self.handle_bl_command(action, phrase, message)
            return

        # Evaluate message
        msg_scores = await self.request_message_scores(message.content)
        bl_phrases = self.get_blacklisted_phrases(message.content)

        if bl_phrases or self.check_needs_moderation(msg_scores):
            await self.forward_to_mods(msg_scores, message, bl_phrases=bl_phrases)
            return

        # add reaction based on message score
        # score = response_dict["attributeScores"]["SEVERE_TOXICITY"]["summaryScore"]["value"]
        # await message.add_reaction(self.score_to_emoji(score))

    # overwrite close method to clean up our objects as well
    async def close(self):
        await super().close()
        await self.http_session.close()

client = Perspectron(os.environ['PERSPECTIVE_KEY'])
client.run(os.environ['DISCORD_KEY'])
