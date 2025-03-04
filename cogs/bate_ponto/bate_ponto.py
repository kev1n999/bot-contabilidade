import os
import pickle
import json 
import discord
from discord.ext import commands
from discord.ui import View
from datetime import datetime, timedelta
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from database.database import Database

db = Database("bateponto")
cursor = db.cursor


with open("config/config.json", "r") as config:
    file = json.load(config)

# CATEGORIAS
STAFF_ROLE_ID = file["staff_role"]


SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
SHEET_ID = file["sheet_id"]


def horario_brasilia():
    return datetime.utcnow() - timedelta(hours=3)


cursor.execute("""
CREATE TABLE IF NOT EXISTS ponto (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    inicio TEXT NOT NULL,
    termino TEXT,
    tempo_trabalhado TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS pausas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    ponto_id INTEGER NOT NULL,
    pausa TEXT NOT NULL,
    retorno TEXT,
    FOREIGN KEY (ponto_id) REFERENCES ponto (id)
)
""")

cursor.execute('''
CREATE TABLE IF NOT EXISTS recomendacoes (
    user_id INTEGER PRIMARY KEY,
    sim INTEGER DEFAULT 0,
    nao INTEGER DEFAULT 0
)
''')

db.db.commit()


db_avaliacao = Database("staffs")
db_avaliacao_cursor = db_avaliacao.cursor

def get_recomendacao(user_id):
    db_avaliacao_cursor.execute("SELECT sim, nao FROM recomendacoes WHERE user_id = ?", (user_id,))
    recomendacoes = db_avaliacao_cursor.fetchone()
    sim = recomendacoes[0] if recomendacoes else 0
    nao = recomendacoes[1] if recomendacoes else 0
    return sim, nao

def criar_planilha_avaliacao(service, nome_planilha="recomendações", sim=0, nao=0):
    # Recupera a lista de abas (sheets) existentes na planilha
    planilha = service.spreadsheets().get(spreadsheetId=SHEET_ID).execute()
    abas_existentes = [sheet['properties']['title'] for sheet in planilha['sheets']]

    # Verifica se a aba já existe
    if nome_planilha in abas_existentes:
        print(f"Aba '{nome_planilha}' já existe. Atualizando valores...")
    else:
        # Adiciona uma nova aba na planilha
        service.spreadsheets().batchUpdate(
            spreadsheetId=SHEET_ID,
            body={
                "requests": [
                    {
                        "addSheet": {
                            "properties": {
                                "title": nome_planilha
                            }
                        }
                    }
                ]
            }
        ).execute()
        print(f"Aba '{nome_planilha}' criada com sucesso.")

    # Define os valores iniciais a serem inseridos
    valores_iniciais = [
        ['Avaliação', 'Quantidade'],
        ['Sim', sim],
        ['Não', nao]
    ]
    
    # Atualiza os valores na aba
    service.spreadsheets().values().update(
        spreadsheetId=SHEET_ID,
        range=f'{nome_planilha}!A1',
        valueInputOption='RAW',
        body={'values': valores_iniciais}
    ).execute()

    # URL da planilha
    planilha_url = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}"
    print(f"Planilha atualizada com sucesso: {planilha_url}")

    
def criar_planilha_nota(service, nome_planilha="notas", user=None, user_id=None, nota=None):
    # Verifica se a planilha já existe
    sheets_metadata = service.spreadsheets().get(spreadsheetId=SHEET_ID).execute()
    sheets_titles = [sheet['properties']['title'] for sheet in sheets_metadata.get('sheets', [])]

    if nome_planilha not in sheets_titles:
        # Adiciona uma nova aba na planilha existente
        service.spreadsheets().batchUpdate(
            spreadsheetId=SHEET_ID,
            body={
                "requests": [
                    {
                        "addSheet": {
                            "properties": {
                                "title": nome_planilha
                            }
                        }
                    }
                ]
            }
        ).execute()

        valores_iniciais = [
            ['Nome', 'ID do Usuário', 'Bom', 'Ruim', 'Excelente'],
            [user, f'{user_id}', 0, 0, 0],
        ]

        if isinstance(nota, int) and 0 <= nota <= 2:  
            valores_iniciais[1][nota + 2] = 1  

        service.spreadsheets().values().update(
            spreadsheetId=SHEET_ID,
            range=f'{nome_planilha}!A1',
            valueInputOption='RAW',
            body={'values': valores_iniciais}
        ).execute()

    else:
        # Atualiza a contagem da nota recebida na planilha existente
        valores = service.spreadsheets().values().get(
            spreadsheetId=SHEET_ID,
            range=f'{nome_planilha}!A2:G'
        ).execute().get('values', [])

        user_found = False  # Flag para verificar se o usuário foi encontrado

        for linha in valores:
            if linha[1] == f'{user_id}':
                user_found = True
                # Verifica se 'nota' está dentro do intervalo válido
                if isinstance(nota, int) and 0 <= nota <= 2:
                    # Incrementa a contagem da nota
                    linha[int(nota) + 2] = str(int(linha[int(nota) + 2]) + 1)
                break

        if not user_found:
            # Se o usuário não foi encontrado, cria uma nova linha
            nova_linha = [user, f'{user_id}', 0, 0, 0]
            if isinstance(nota, int) and 0 <= nota <= 2:
                nova_linha[nota + 2] = 1  # Marca a primeira avaliação recebida
            valores.append(nova_linha)

        service.spreadsheets().values().update(
            spreadsheetId=SHEET_ID,
            range=f'{nome_planilha}!A2',  # Atualiza a partir da célula A2
            valueInputOption='RAW',
            body={'values': valores}
        ).execute()

    # URL da planilha
    planilha_url = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}"
    print(f"Planilha criada/atualizada com sucesso: {planilha_url}")

    
def authenticate_google_sheets():
    creds = None
    if os.path.exists('token.pickle'):
        with open('token.pickle', 'rb') as token:
            creds = pickle.load(token)
    if not creds or not creds.valid:
        creds = Credentials.from_service_account_file(
            'config/hallowed-tea-387701-34bbaf2630f4.json', scopes=SCOPES)
        with open('token.pickle', 'wb') as token:
            pickle.dump(creds, token)
    return build('sheets', 'v4', credentials=creds)


def write_to_user_sheet(display_name, user_id, data, inicio, termino, pausas_formatadas, tempo_trabalhado):
    try:
        service = authenticate_google_sheets()
        sheet = service.spreadsheets()

        sheets_metadata = sheet.get(spreadsheetId=SHEET_ID).execute()
        sheets_titles = [sheet['properties']['title'] for sheet in sheets_metadata.get('sheets', [])]

        if display_name not in sheets_titles:
            sheet.batchUpdate(
                spreadsheetId=SHEET_ID,
                body={
                    "requests": [
                        {
                            "addSheet": {
                                "properties": {
                                    "title": display_name
                                }
                            }
                        }
                    ]
                }
            ).execute()

            header_values = [["Data", "Nome", "ID do Usuário", "Início", "Término", "Horários de Pausa", "Tempo Trabalhado"]]
            sheet.values().update(
                spreadsheetId=SHEET_ID,
                range=f"{display_name}!A1",
                valueInputOption="RAW",
                body={"values": header_values}
            ).execute()

        if isinstance(pausas_formatadas, list):
            pausas_formatadas = "\n".join(pausas_formatadas)
        if pausas_formatadas == []:
            pausas_formatadas = "-"

        # Dados para o novo registro
        values = [[data, display_name, f"'{user_id}", inicio, termino, pausas_formatadas, tempo_trabalhado]]
        sheet.values().append(
            spreadsheetId=SHEET_ID,
            range=f"{display_name}!A1",
            valueInputOption="RAW",
            body={"values": values}
        ).execute()

        # Atualiza a coluna de total
        sheet_data = sheet.values().get(
            spreadsheetId=SHEET_ID,
            range=f"{display_name}!G:G"
        ).execute()

        total_rows = len(sheet_data.get("values", [])) + 1
        formula_range = f"{display_name}!G{total_rows}"
        sheet.values().update(
            spreadsheetId=SHEET_ID,
            range=formula_range,
            valueInputOption="USER_ENTERED",
            body={"values": [[f"=SOMA(G2:G{total_rows - 1})"]]}).execute()
    except Exception as e:
        print(f"Erro ao gravar na planilha do Google: {e}")


class PontoView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Iniciar", style=discord.ButtonStyle.success, custom_id="ponto_iniciar")
    async def iniciar_ponto(self, button: discord.ui.Button, interaction: discord.Interaction):
        user_id = interaction.user.id
        inicio = horario_brasilia()

        cursor.execute("SELECT inicio FROM ponto WHERE user_id = ? AND termino IS NULL", (user_id,))
        registro = cursor.fetchone()
        if registro:
            await interaction.response.send_message(
                "Você já iniciou o ponto! Por favor, encerre o ponto atual antes de iniciar um novo.",
                ephemeral=True
            )
            return

        try:
            cursor.execute("INSERT INTO ponto (user_id, inicio) VALUES (?, ?)", (user_id, inicio))
            db.db.commit()

            await interaction.response.send_message(f"Seu ponto foi iniciado às {inicio.strftime('%H:%M')}.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"Erro ao iniciar o ponto: {e}", ephemeral=True)

    @discord.ui.button(label="Pausar", style=discord.ButtonStyle.secondary, custom_id="ponto_pausar")
    async def pausar_ponto(self, button: discord.ui.Button, interaction: discord.Interaction):
        user_id = interaction.user.id

        try:
            cursor.execute("SELECT id FROM ponto WHERE user_id = ? AND termino IS NULL", (user_id,))
            ponto_id = cursor.fetchone()

            cursor.execute("SELECT id FROM pausas WHERE user_id = ? AND retorno IS NULL", (user_id,))
            pausa = cursor.fetchone()

            if pausa:
                await interaction.response.send_message(
                    "Você já está com o ponto pausado. Retome antes de pausar novamente.",
                    ephemeral=True
                )
                return

            if not ponto_id:
                await interaction.response.send_message(
                    "Você não iniciou nenhum ponto para pausar.",
                    ephemeral=True
                )
                return

            pausa = horario_brasilia()
            ponto_id = ponto_id[0]
            cursor.execute(
                "INSERT INTO pausas (user_id, ponto_id, pausa) VALUES (?, ?, ?)",
                (user_id, ponto_id, pausa)
            )
            db.db.commit()

            await interaction.response.send_message(f"Ponto pausado às {pausa.strftime('%H:%M')}.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"Erro ao pausar o ponto: {e}", ephemeral=True)

    @discord.ui.button(label="Retomar", style=discord.ButtonStyle.primary, custom_id="ponto_retornar")
    async def retomar_ponto(self, button: discord.ui.Button, interaction: discord.Interaction):
        user_id = interaction.user.id

        try:
            cursor.execute("SELECT id FROM pausas WHERE user_id = ? AND retorno IS NULL", (user_id,))
            pausa_id = cursor.fetchone()

            if not pausa_id:
                await interaction.response.send_message(
                    "Você não possui nenhuma pausa para retomar.",
                    ephemeral=True
                )
                return

            retorno = horario_brasilia()
            pausa_id = pausa_id[0]
            cursor.execute("UPDATE pausas SET retorno = ? WHERE id = ?", (retorno, pausa_id))
            db.db.commit()

            await interaction.response.send_message(f"Ponto retomado às {retorno.strftime('%H:%M')}.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"Erro ao retomar o ponto: {e}", ephemeral=True)

    @discord.ui.button(label="Encerrar", style=discord.ButtonStyle.danger, custom_id="ponto_encerrar")
    async def encerrar_ponto(self, button: discord.ui.Button, interaction: discord.Interaction):
        await interaction.response.defer()
        user_id = interaction.user.id
        termino = horario_brasilia()
        
        try:
            cursor.execute("SELECT id, inicio FROM ponto WHERE user_id = ? AND termino IS NULL", (user_id,))
            registro = cursor.fetchone()

            if not registro:
                await interaction.response.send_message(
                    "Você não possui nenhum ponto iniciado para encerrar.",
                    ephemeral=True
                )
                return

            ponto_id, inicio = registro
            inicio = datetime.fromisoformat(inicio)

            cursor.execute("SELECT pausa, retorno FROM pausas WHERE user_id = ? AND ponto_id = ?", (user_id, ponto_id))
            pausas = cursor.fetchall()

            total_pausa = timedelta()  
            pausas_formatadas = [] 

            for pausa, retorno in pausas:
                pausa_dt = datetime.fromisoformat(pausa)
                retorno_dt = datetime.fromisoformat(retorno) if retorno else None

                if retorno_dt:
                    total_pausa += retorno_dt - pausa_dt
                pausas_formatadas.append(f"{pausa_dt.strftime('%H:%M')} às {retorno_dt.strftime('%H:%M') if retorno_dt else '-'}")

            if not pausas_formatadas:
                pausas_formatadas = ["-"]
            else:
                pausas_formatadas = "\n".join(pausas_formatadas)

            duracao = termino - inicio - total_pausa
            tempo_trabalhado = f"{duracao.seconds // 3600}h {duracao.seconds % 3600 // 60}m"

            cursor.execute("UPDATE ponto SET termino = ?, tempo_trabalhado = ? WHERE id = ?", (termino, tempo_trabalhado, ponto_id))
            db.db.commit()

            display_name = interaction.user.display_name
            data = horario_brasilia().strftime("%d/%m/%Y")
    
            write_to_user_sheet(display_name, user_id, data, inicio.strftime('%H:%M'), termino.strftime('%H:%M'), pausas_formatadas, tempo_trabalhado)
            
            mensagem = (
                f"Seu ponto foi encerrado!\n"
                f"Data: {data}\n"
                f"Horário de início: {inicio.strftime('%H:%M')}\n"
                f"Horário de término: {termino.strftime('%H:%M')}\n"
                f"Horários de pausa:\n{pausas_formatadas}\n"
                f"Tempo trabalhado: {tempo_trabalhado}\n"
            )
            
            await interaction.followup.send(mensagem, ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"Erro ao encerrar o ponto: {e}", ephemeral=True)

class BatePontoCommand(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="ponto")
    async def ponto_command(self, ctx):        
        if discord.utils.get(ctx.author.roles, id=STAFF_ROLE_ID) is None:
            await ctx.send(f"❌ Você não tem permissão para usar este comando. Este recurso é restrito a membros com o cargo necessário.")
            return

        embed = discord.Embed(
            title="🕒 Gerenciamento de Ponto de Trabalho",
            description="Use os botões abaixo para registrar seu ponto.",
            color=discord.Color.from_rgb(245, 245, 245)
        )
        embed.set_footer(text="Sistema de Ponto Automático • Organize seu tempo com eficiência")

        view = PontoView()
        await ctx.send(embed=embed, view=view)

def setup(bot):
    bot.add_cog(BatePontoCommand(bot))