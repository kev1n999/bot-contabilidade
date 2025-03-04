import json
import discord
from discord.ext import commands
from cogs.tickets.modals.modals import AvaliacaoModal, Buttons, ticket_historic, gerar_html  
from datetime import datetime

# CONFIGURAçÔES DA CATEGORIA DE TICKETS
with open("config/config.json", "r") as config:
    file = json.load(config)

# CATEGORIAS
CATEGORIES = file["categorys"]

comercial = CATEGORIES["comercial"]
contabil = CATEGORIES["contabil"]
RH = CATEGORIES["rh"]
Fiscal = CATEGORIES["fiscal"]
certificado_digital = CATEGORIES["certificado_digital"]
Consultoria = CATEGORIES["consultoria"]
marcas_e_patentes = CATEGORIES["registro_de_marcas_patentes"]
orcamento = CATEGORIES["orcamento"]

#ticket_counter = 1

# OPÇÔES DE ATENDIMENTO
class SelectMenuOptions(discord.ui.Select):
    def __init__(self, custom_id="select_menu_options"):
        super().__init__(placeholder="Selecione uma opção", custom_id=custom_id)
        self.comercial = discord.SelectOption(
            label="Comercial",
            description=None 
        )
        self.contabil = discord.SelectOption(
            label="Contábil",
            description="Lançamentos de entrada e saida, balanço patrimonial"
        )
        self.rh = discord.SelectOption(
            label="RH",
            description="Gestão de pessoas, folha de pagamento, rescisão trabalhistas, homologação..."
        )
        self.fiscal = discord.SelectOption(
            label="Fiscal",
            description="Apuração de impostos, envio das obrigações mensais, controle de entrada e saída"
        )
        self.certificadoDigital = discord.SelectOption(
            label="Certificado Digital",
            description="Venda, emissão e validação de certificação digital"
        )
        self.consultoria = discord.SelectOption(
            label="Consultoria",
            description="Consultoria financeira e empresarial"
        )
        self.marcas_patentes = discord.SelectOption(
            label="Marcas e patentes",
            description="Processos que envolvem o registro da sua marca"
        )
        
        self.options.append(self.comercial)
        self.options.append(self.contabil)
        self.options.append(self.rh)
        self.options.append(self.fiscal)
        self.options.append(self.certificadoDigital)
        self.options.append(self.consultoria)
        self.options.append(self.marcas_patentes)
        self.count = 1
        
    async def callback(self, interaction):
        #global ticket_counter

        ticket_name = f"ticket-{interaction.user}"
        
        while discord.utils.get(interaction.guild.text_channels, name=ticket_name):
            ticket_counter += 1
            ticket_name = f"ticket-{ticket_counter}"

        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(send_messages=True, view_channel=True)
        }
        ticket_id = None 
        
        if self.values[0] == "Comercial":
            ticket_id = comercial 
        elif self.values[0] == "Contábil":
            ticket_id = contabil
        elif self.values[0] == "RH":
            ticket_id = RH 
        elif self.values[0] == "Fiscal":
            ticket_id = Fiscal 
        elif self.values[0] == "Certificado Digital":
            ticket_id = certificado_digital    
        elif self.values[0] == "Consultoria":
            ticket_id = Consultoria
        elif self.values[0] == "Marcas e patentes":
            ticket_id = marcas_e_patentes
            
        ticket_channel = await interaction.guild.create_text_channel(ticket_name, category=discord.utils.get(interaction.guild.categories, id=ticket_id), overwrites=overwrites)

        ticket_historic[ticket_channel.id] = {
            "user": interaction.user.name,
            "user_id": interaction.user.id,
            "data": datetime.now(),
            "messages": [{"author": "Sistema", "content": f"Ticket aberto por {interaction.user.name}", "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S')}],
            "feedback": None,
            "nota": None
        }

        embed = discord.Embed(title="📩  Novo ticket", description=f"**Usuário:** {interaction.user.mention}", color=0x6A0DAD)
        embed.add_field(name="Opção escolhida", value=f"`{self.values[0]}`", inline=True)
        embed.set_footer(text="Espere para ser atendido")
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        
        await interaction.response.send_message(content=f"Seu ticket para {self.values[0]} foi criado em {ticket_channel.mention}", ephemeral=True)
        await ticket_channel.send(embed=embed, view=Buttons(interaction.user))
        await self.reset_select(interaction)
        
        #ticket_counter += 1
        
    async def reset_select(self, interaction:discord.Interaction):
        select = SelectMenuOptions()  

        view = discord.ui.View(timeout=None)
        view.add_item(select)
        embed = discord.Embed(title="Central de suporte", description="""
**Nessa sessão você pode entrar em contato com a nossa equipe.**\n\n**Horário de atendimento**\n・Segunda a Sabádo das **8h às 18h**\nAguarde ser atendido.\n""", color=0xFFFFFF)
        desc = """
・**Contábil**
・**RH**
・**Fiscal**
・**Certificado Digital**
・**Consultoria**
・**Registro de marcas e patentes**"""

        embed.add_field(name="CONHEÇA NOSSOS SERVIÇOS", value=desc, inline=True)
        embed.set_footer(text="Escolha uma opção")
        embed.set_thumbnail(url=interaction.guild.icon.url)
        embed.set_footer(text=interaction.guild.name, icon_url=interaction.guild.me._user.display_avatar.url)
        
        await interaction.message.edit(embed=embed, view=view)
        
class TicketSystem(commands.Cog):
    def __init__(self, bot):
        self.bot = bot 
    
    @commands.Cog.listener()
    async def on_message(self, message):
        if message.channel.id in ticket_historic:
            # Adiciona a mensagem ao histórico
            ticket_historic[message.channel.id]["messages"].append({
                "author": message.author.name,
                "content": message.content,
                "timestamp": message.created_at.strftime("%Y-%m-%d %H:%M:%S")
            })
    
    @commands.has_permissions(administrator=True)
    @commands.command(name="abrir")
    async def ticket(self, ctx, arg = None):
        if arg is None:
            view = discord.ui.View(timeout=None)
            view.add_item(SelectMenuOptions())
            
            embed = discord.Embed(title="Central de suporte", description="""
**Nessa sessão você pode entrar em contato com a nossa equipe.**\n\n**Horário de atendimento**\n・Segunda a Sabádo das **8h às 18h**\nAguarde ser atendido.\n""", color=0xFFFFFF)
            desc = """
・**Contábil**
・**RH**
・**Fiscal**
・**Certificado Digital**
・**Consultoria**
・**Registro de marcas e patentes**"""

            embed.add_field(name="CONHEÇA NOSSOS SERVIÇOS", value=desc, inline=True)
            embed.set_footer(text="Escolha uma opção")
            embed.set_thumbnail(url=ctx.guild.icon.url)
            embed.set_footer(text=ctx.guild.name, icon_url=self.bot.user.display_avatar.url)
            
            await ctx.message.delete()
            await ctx.send(embed=embed, view=view)
            return 
        
        if arg == "orçamento" or arg == "orcamento":
            embed = discord.Embed(title="Central de suporte", description="""
**Nessa sessão você pode entrar em contato com a nossa equipe.**\n\n**Horário de atendimento**\n・Segunda a Sabádo das **8h às 18h**\n**FAÇA JÁ SEU ORÇAMENTO.**\n""", color=0xFFFFFF)
            desc = """
・**Contábil**
・**RH**
・**Fiscal**
・**Certificado Digital**
・**Consultoria**
・**Registro de marcas e patentes**"""

            embed.add_field(name="TRABALHAMOS COM:", value=desc, inline=True)
            embed.set_footer(text="Escolha uma opção")
            embed.set_thumbnail(url=ctx.guild.icon.url)
            embed.set_footer(text=ctx.guild.name, icon_url=self.bot.user.display_avatar.url)
            await ctx.send(view=discord.ui.View(OrcamentoButton()), embed=embed)
            await ctx.message.delete()
        
class OrcamentoButton(discord.ui.Button):
    def __init__(self, custom_id="orcamento_button"):
        super().__init__(custom_id=custom_id, label="Fazer orçamento", style=discord.ButtonStyle.blurple)
    
    async def callback(self, interaction:discord.Interaction):
        categorie_id = discord.utils.get(interaction.guild.categories, id=orcamento)
        overwrites = { interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False), interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True )}
        ticket_channel = await interaction.guild.create_text_channel(f"ticket-{interaction.user}", overwrites=overwrites, category=categorie_id)

        ticket_historic[ticket_channel.id] = {
            "user": interaction.user.name,
            "user_id": interaction.user.id,
            "data": datetime.now(),
            "messages": [{"author": "Sistema", "content": f"Ticket aberto por {interaction.user.name}", "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S')}],
            "feedback": None,
            "nota": None
        }
        
        await interaction.response.send_message(ephemeral=True, content="Seu ticket foi aberto com sucesso em {}".format(ticket_channel.mention))
        embed = discord.Embed(title="📩  Novo ticket", description=f"**Usuário:** {interaction.user.mention}", color=0x6A0DAD)
        embed.add_field(name="Opção escolhida", value=f"`Orçamento`", inline=True)
        embed.set_footer(text="Espere para ser atendido")
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        
        await ticket_channel.send(embed=embed, view=Buttons(user=interaction.user))
        
def setup(bot):
    bot.add_cog(TicketSystem(bot))
