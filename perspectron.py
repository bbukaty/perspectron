import discord
import json
import os
import requests

class Perspectron(discord.Client):
    def __init__(self, perspective_key):
        super().__init__()
        self.ps_key = perspective_key

    async def score_message(self, message):
        url = ('https://commentanalyzer.googleapis.com/v1alpha1/comments:analyze' +    
            '?key=' + self.ps_key)
        data_dict = {
            'comment': {'text': message},
            'languages': ['en'],
            'requestedAttributes': {'TOXICITY': {}},
            'doNotStore': True
        }
        response = requests.post(url=url, data=json.dumps(data_dict)) 
        response_dict = json.loads(response.content)
        return response_dict["attributeScores"]["TOXICITY"]["summaryScore"]["value"]
        # return json.dumps(response_dict, indent=2)

    async def on_ready(self):
        print('Logged in as')
        print(self.user.name)
        print(self.user.id)
        print('------')

    async def on_message(self, message):
        # we do not want the bot to reply to itself
        if message.author.id == self.user.id:
            return

        score = await self.score_message(message.content)
        await message.channel.send(str(score))

client = Perspectron(os.environ['PERSPECTIVE_KEY'])
client.run(os.environ['DISCORD_KEY'])
