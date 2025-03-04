import asyncio 
import discord
from discord.ui import Modal, InputText, View, Button
from datetime import datetime
from json import load 
from database.database import Database
from ...bate_ponto.bate_ponto import criar_planilha_nota, authenticate_google_sheets, get_recomendacao, criar_planilha_avaliacao

db = Database("staffs")
cursor = db.cursor 

cursor.execute("CREATE TABLE IF NOT EXISTS Staffs (ticket_channel_id INTEGER, staff_id INTEGER)")
cursor.execute("CREATE TABLE IF NOT EXISTS Avaliacoes (staff_id INTEGER, client_id INTEGER, nota TEXT, recomenda TEXT)")
cursor.execute('''
CREATE TABLE IF NOT EXISTS recomendacoes (
    user_id INTEGER PRIMARY KEY,
    sim INTEGER DEFAULT 0,
    nao INTEGER DEFAULT 0
)
''')

db.db.commit()

def atualizar_recomendacao(user_id, recomendacao):
    # Verifica se o usuário já tem um registro na tabela de recomendacoes
    cursor.execute("SELECT sim, nao FROM recomendacoes WHERE user_id = ?", (user_id,))
    resultado = cursor.fetchone()

    if resultado:
        sim, nao = resultado
        if recomendacao == "sim":
            sim += 1
        elif recomendacao == "nao":
            nao += 1
        # Atualiza os valores de sim ou nao no banco de dados
        cursor.execute("UPDATE recomendacoes SET sim = ?, nao = ? WHERE user_id = ?", (sim, nao, user_id))
        
    else:
        # Cria um novo registro com a primeira recomendação
        cursor.execute("INSERT INTO recomendacoes (user_id, sim, nao) VALUES (?, ?, ?)", 
                       (user_id, 1 if recomendacao == "sim" else 0, 1 if recomendacao == "nao" else 0))

    db.db.commit()
    
with open("config/config.json", "r") as config:
    file = load(config)

STAFF_ROLE = file["staff_role"]
TRANSCRIPT_CHANNEL = file["canal_transcripts"]

# --> REGISTRO <-- 
ticket_historic = {}

class NotaSelect(discord.ui.Select):
    def __init__(self, ticket_channel, staff):
        self.ticket_channel = ticket_channel
        self.staff = staff 
        
        options = [
            discord.SelectOption(label="Bom", value="Bom"),
            discord.SelectOption(label="Ruim", value="Ruim"),
            discord.SelectOption(label="Excelente", value="Excelente"),
        ]
        super().__init__(placeholder="Como você nos avalia?", options=options)
        
    async def callback(self, interaction: discord.Interaction):
        nota = self.values[0]
        ticket_historic[self.ticket_channel.id]["nota"] = nota
        await gerar_html(ticket_historic[self.ticket_channel.id], interaction.user)
        
        nota_map = {"Bom": 0, "Ruim": 1, "Excelente": 2}
        nota_numerica = nota_map.get(nota, None)
        if nota_numerica is not None:
            criar_planilha_nota(authenticate_google_sheets(), user=self.staff.name, user_id=self.staff.id, nota=nota_numerica)
        
        await interaction.channel.set_permissions(interaction.user, view_channel=False, send_messages=False)
        await self.ticket_channel.send("Este ticket foi fechado pelo cliente.")
        
class AvaliacaoModal(Modal):
    def __init__(self, ticket_channel, user, staff):
        super().__init__(title="Deixe uma avaliação")
        self.ticket_channel = ticket_channel
        self.user = user
        self.staff = staff 
        
        self.feedback = InputText(
            label="Deixe um feedback",
            placeholder="Descreva o que você achou do atendimento",
            style=discord.InputTextStyle.long,
            required=True
        )
        self.recomenda = InputText(
            label="Indicaria nosso escritório? Sim ou Não",
            placeholder="Digite Sim ou Não",
            style=discord.InputTextStyle.singleline,
            required=True 
        )

        self.add_item(self.feedback)
        self.add_item(self.recomenda)

    async def callback(self, interaction: discord.Interaction):
        if self.ticket_channel.id not in ticket_historic:
            await interaction.response.send_message("Erro: O histórico deste ticket não foi encontrado.", ephemeral=True)
            return

        # Salva a avaliação e feedback
        feedback = self.feedback.value
        recomenda = self.recomenda.value
        
        validas = ["sim", "não", "nao", "claro", "com certeza"]
        
        if (recomenda.lower() not in validas):
            await interaction.response.send_message(f"{interaction.user.mention}\n⚠ **Você deve responder apenas `sim ou não` ao recomendar nosso escritório! Tente avaliar novamente.**", ephemeral=True)
            await interaction.response.send_modal(self)
            return 

        # Atualizando o histórico de avaliação
        ticket_historic[self.ticket_channel.id]["feedback"] = feedback
        
        ticket_historic[self.ticket_channel.id]["recomenda"] = "Sim" if recomenda.lower() in ["sim", "claro", "com certeza"] else recomenda
        
        # Salva a avaliação no banco de dados
        cursor.execute("INSERT INTO Avaliacoes (staff_id, client_id, nota, recomenda) VALUES (?, ?, ?, ?)", (self.ticket_channel.id, interaction.user.id, ticket_historic[self.ticket_channel.id]["nota"], recomenda))
        db.db.commit()
        
        # Atualiza a recomendação no banco de dados
        recomendacao = "sim" if recomenda.lower() in ["sim", "claro", "com certeza"] else "nao"
        atualizar_recomendacao(self.staff.id, recomendacao)
        
        await interaction.response.send_message(view=View(NotaSelect(self.ticket_channel, self.staff)), ephemeral=True)

        sim, nao = get_recomendacao(user_id=self.staff.id)
        criar_planilha_avaliacao(authenticate_google_sheets(), sim=sim, nao=nao)
        
# BOTÃO PARA O FECHAMENTO DO TICKET
class Buttons(View):
    def __init__(self, user):
        super().__init__(timeout=None)
        self.user = user
        self.staff_assumiu = None 
        
    @discord.ui.button(label="Fechar Ticket(Cliente)", style=discord.ButtonStyle.red)
    async def close_ticket(self, button: Button, interaction: discord.Interaction):
        if interaction.user != self.user:
            return 
        
        # Envia o modal de avaliação
        modal = AvaliacaoModal(ticket_channel=interaction.channel, user=self.user, staff=self.staff_assumiu)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Desativar Ticket(Staff)", style=discord.ButtonStyle.blurple)
    async def desable_ticket(self, button: Button, interaction: discord.Interaction):
        has_permission = any(role.id == STAFF_ROLE for role in interaction.user.roles)
        if not has_permission:
            await interaction.response.send_message("Você não tem permissão para desativar este ticket.", ephemeral=True)
            return
        
        await interaction.channel.delete()

    @discord.ui.button(label="Assumir(Staff)", style=discord.ButtonStyle.green)
    async def assumir(self, button: Button, interaction: discord.Interaction):
        has_permission = any(role.id == STAFF_ROLE for role in interaction.user.roles)
        if not has_permission:
            return
        
        await interaction.response.send_message("Você assumiu este ticket. Pode continuar seu atendimento!", ephemeral=True)
        self.staff_assumiu = interaction.user
        cursor.execute("INSERT INTO Staffs VALUES(?, ?)", (interaction.channel.id, self.staff_assumiu.id))
        db.db.commit()
        ticket_historic[interaction.channel.id]["staff"] = interaction.user 
        button.disabled = True 
        await interaction.message.edit(view=self, content=f"Ticket assumido por: {self.staff_assumiu.mention}")

        
# FUNÇÃO PARA SALVAR AS INFORMAÇÔES DO TICKET EM UM ARQUIVO HTML
async def gerar_html(ticket_data, user):
    trasncript_channel = discord.utils.get(user.guild.channels, id=TRANSCRIPT_CHANNEL)
    user_name = ticket_data["user"]
    user_id = ticket_data["user_id"]
    created_at = ticket_data["data"].strftime("%Y-%m-%d %H:%M:%S")
    feedback = ticket_data["feedback"]
    nota = ticket_data["nota"]
    recomenda = ticket_data["recomenda"]
    staff_avalido = ticket_data["staff"]
    # REGISTRA AS MENSAGENS TROCADAS NO CANAL ATUAL DO TICKET
    messages_html = ""
    for msg in ticket_data["messages"]:
        messages_html += f"<p><b>{msg['author']}:</b> {msg['content']} <i>({msg['timestamp']})</i></p>"
    
    html_content = f"""
    <html>
        <head>
            <title>Ticket - {user_name}</title>
            <style>
                /* Reset de estilos básicos */
                * {{
                    margin: 0;
                    padding: 0;
                    box-sizing: border-box;
                }}
                body {{
                    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                    background-color: #1e2a47;
                    color: #333;
                    line-height: 1.6;
                    padding: 30px 0;
                }}
                h1 {{
                    background-color: #007bff;
                    color: white;
                    text-align: center;
                    padding: 15px;
                    border-radius: 10px 10px 0 0;
                    margin-bottom: 20px;
                    font-size: 2em;
                    letter-spacing: 1px;
                }}
                h2 {{
                    color: #333;
                    margin-top: 20px;
                    font-size: 1.5em;
                    text-align: center;
                }}
                .container {{
                    width: 80%;
                    max-width: 900px;
                    margin: 0 auto;
                    background-color: #ffffff;
                    padding: 20px;
                    border-radius: 10px;
                    box-shadow: 0 4px 8px rgba(0, 0, 0, 0.1);
                    transition: transform 0.3s ease, box-shadow 0.3s ease;
                }}
                .container:hover {{
                    transform: translateY(-5px);
                    box-shadow: 0 8px 16px rgba(0, 0, 0, 0.15);
                }}
                .ticket-info {{
                    background-color: #e9f1ff;
                    padding: 20px;
                    border-radius: 8px;
                    margin-bottom: 30px;
                    box-shadow: 0 2px 6px rgba(0, 0, 0, 0.1);
                }}
                .ticket-info b {{
                    color: #007bff;
                }}
                .messages {{
                    border-top: 2px solid #f1f1f1;
                    padding-top: 20px;
                }}
                .message {{
                    background-color: #f8f8f8;
                    padding: 15px;
                    margin-bottom: 15px;
                    border-radius: 8px;
                    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
                    transition: background-color 0.3s ease;
                }}
                .message:hover {{
                    background-color: #f1f1f1;
                }}
                .message b {{
                    color: #007bff;
                    font-weight: bold;
                }}
                .timestamp {{
                    font-size: 12px;
                    color: #888;
                    display: block;
                    margin-top: 5px;
                }}
                /* Botão interativo */
                .button {{
                    display: inline-block;
                    background-color: #28a745;
                    color: white;
                    padding: 12px 30px;
                    font-size: 16px;
                    border-radius: 8px;
                    text-align: center;
                    text-decoration: none;
                    cursor: pointer;
                    margin: 10px 0;
                    transition: background-color 0.3s ease, transform 0.2s ease;
                }}
                .button:hover {{
                    background-color: #218838;
                    transform: translateY(-3px);
                }}
                .button:active {{
                    transform: translateY(1px);
                }}
                /* Estilo para o footer */
                footer {{
                    text-align: center;
                    color: #777;
                    font-size: 14px;
                    margin-top: 40px;
                }}
                footer a {{
                    color: #007bff;
                    text-decoration: none;
                }}
                footer a:hover {{
                    text-decoration: underline;
                }}
            </style>
        </head>
        <body>
            <h1>📄 Histórico de Atendimento</h1>
            <div class="container">
                <div class="ticket-info">
                    <p><b>Cliente/Usuário:</b> {user_name} ({user_id})</p>
                    <p><b>Abertura:</b> {created_at}</p>
                    <p><b>Nota:</b> {nota}</p> <p><b>STAFF:</b> {staff_avalido}</p>
                    <p><b>Feedback:</b> {feedback}</p>
                    <p><b>Indica nosso escritório?</b> {recomenda}</p>
                </div>
                <h2>📨 Mensagens:</h2>
                <div class="messages">
                    {messages_html}
                </div>
            </div>
            <footer>
                <p>&copy; 2025 - Obrigado pela avaliação!</p>
            </footer>
        </body>
    </html>
    """ 

    # SALVA O ARQUIVO HTML
    file_name = f"ticket_{user_id}.html"
    with open(file_name, "w", encoding="utf-8") as file:
        file.write(html_content)

    # ENVIA O ARQUIVO PARA O USUÁRIO/CLIENTE
    try:
        await trasncript_channel.send(content="Aqui está o histórico do seu ticket:", file=discord.File(file_name))
    except Exception as e:
        print(f"Erro ao enviar DM para {user.name}: {e}")

def setup(bot):
    return 