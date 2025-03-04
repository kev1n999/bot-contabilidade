import os 
import json 
import discord 
from discord.ext import commands 
from dotenv import load_dotenv
from cogs.tickets.ticket import SelectMenuOptions, OrcamentoButton

load_dotenv()

with open("config/config.json", "r") as config:
    file = json.load(config)

PREFIX = file["prefix"]
WELCOME_CHANNEL = file["canal_boasvindas"]

class PersistentView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(SelectMenuOptions())
        self.add_item(OrcamentoButton())
        
client = commands.Bot(command_prefix=PREFIX, intents=discord.Intents.all())
    
@client.event 
async def on_ready():
    print("Bot online!")
    
    client.add_view(PersistentView())

@client.event
async def on_member_join(member):
    channel = member.guild.get_channel(WELCOME_CHANNEL)

    if channel:
        embed = discord.Embed(
            title="Bem-vindo(a) à Central de Atendimento EMC! ❤️",
            description=(
                f"""
Olá {member.mention}, é um prazer ter você aqui!

Caso **AINDA NÃO SEJA NOSSO CLIENTE**, clique aqui: <#1336794744021323869>.
Caso já seja nosso **CLIENTE**, e precisa de um orçamento, cliquei aqui: <#1336851103542808596>."""
            ),
            color=discord.Color.from_rgb(245, 245, 245)  
        )
        embed.set_thumbnail(url=member.avatar.url if member.avatar else member.default_avatar.url)

        embed.set_footer(
            text="EMC - Escritório Massias de Contabilidade",
            icon_url=member.avatar.url if member.avatar else member.default_avatar.url
        )

        await channel.send(embed=embed)
        
def load_cogs(folder):
    for subfolder in os.listdir(folder):
        for file in os.listdir(f"{folder}/{subfolder}"):
            if (file.endswith(".py")):
                client.load_extension(f"{folder}.{subfolder}.{file[:-3]}")

if __name__ == "__main__":
    load_cogs("cogs")
    client.run(os.getenv("BOT_TOKEN"))