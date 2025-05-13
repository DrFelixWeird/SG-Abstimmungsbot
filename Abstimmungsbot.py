import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime, timedelta
import os
import csv
import joblib

TOKEN = 'Blablablabla'
GUILD_ID = 531217410246574107  # Die Server-ID
ROLE_ID = 1369781934598783068   # ID der Rolle für @Ping
DUMP_NAME = "data.sav"

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

# Laufzeit-Speicher
try:
    abstimmungen = joblib.load(DUMP_NAME)
except:
    abstimmungen = {}  # {sg_nummer: AbstimmungsView}
    joblib.dump(abstimmungen, DUMP_NAME)
    

class AbstimmungsView(discord.ui.View):
    def __init__(self, sg_nummer, frage, anonym, ersteller, dauer_stunden):
        super().__init__(timeout=dauer_stunden * 3600)
        self.sg_nummer = sg_nummer
        self.frage = frage
        self.anonym = anonym
        self.ersteller = ersteller
        self.votes = {}  # user_id: (name, choice)
        self.channel = None
        self.message = None
        self.status = "completed"
        self.dauer_stunden = dauer_stunden

    def filename(self):
        name_clean = self.frage.replace(" ", "_").replace("/", "_")[:30]
        mode = "anonym" if self.anonym else "public"
        return f"SG{self.sg_nummer}_{name_clean}_{mode}_{self.dauer_stunden}h_{self.status}.csv"

    async def on_timeout(self):
        if self.status == "completed":
            await self.post_results()

    def save_to_csv(self):
        os.makedirs("Abstimmungen", exist_ok=True)
        filepath = os.path.join("Abstimmungen", self.filename())

        with open(filepath, "w", newline='', encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["User", "Stimme"])
            for _, (name, choice) in self.votes.items():
                writer.writerow([name if not self.anonym else "Anonym", choice])

        print(f"CSV gespeichert: {filepath}")

    async def post_results(self):
        ergebnisse = {"Ja": [], "Nein": [], "Enthaltung": []}
        for _, (name, choice) in self.votes.items():
            ergebnisse[choice].append(name if not self.anonym else None)

        result_lines = []
        for entscheidung in ["Ja", "Nein", "Enthaltung"]:
            stimmen = ergebnisse[entscheidung]
            count = len(stimmen)
            if self.anonym:
                result_lines.append(f"{count}x {entscheidung}")
            else:
                namen = ', '.join(stimmen) if stimmen else '%'
                result_lines.append(f"{count}x {entscheidung} ({namen})")

        hinweis = ""
        if self.status == "premature":
            hinweis = "\n⚠️ Die Abstimmung wurde vorzeitig beendet."
        elif self.status == "aborted":
            hinweis = "\n⚠️ Die Abstimmung wurde ohne Ergebnis abgebrochen."

        await self.channel.send(f"**Abstimmung SG{self.sg_nummer} beendet. Ergebnis:**\n" + "\n".join(result_lines) + hinweis)
        self.save_to_csv()

    async def abstimmen(self, interaction, entscheidung):
        user = interaction.user
        self.votes[user.id] = (user.name, entscheidung)
        await interaction.response.send_message(f"Du hast '{entscheidung}' gewählt.", ephemeral=True)

    @discord.ui.button(label="Ja", style=discord.ButtonStyle.success)
    async def ja(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.abstimmen(interaction, "Ja")

    @discord.ui.button(label="Nein", style=discord.ButtonStyle.danger)
    async def nein(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.abstimmen(interaction, "Nein")

    @discord.ui.button(label="Enthaltung", style=discord.ButtonStyle.secondary)
    async def enthaltung(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.abstimmen(interaction, "Enthaltung")


@bot.event
async def on_ready():
    print(f"Bot online: {bot.user}")
    await bot.tree.sync(guild=discord.Object(id=GUILD_ID))
    print("Slash-Commands synchronisiert")


@bot.tree.command(name="abstimmung", description="Starte eine SG-Abstimmung", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(
    nummer="SG-Nummer der Abstimmung, z. B. 042",
    servername="Name des Servers",
    anonym="Soll die Abstimmung anonym sein? (Standard: nein/false)",
    dauer="Abstimmungsdauer in Stunden (Standard: 42)"
)
async def abstimmung(interaction: discord.Interaction, nummer: int, servername: str, anonym: bool = False, dauer: int = 42):
    sg_nummer = str(nummer).zfill(3)

    if sg_nummer in abstimmungen:
        await interaction.response.send_message(f"❌ Abstimmung SG{sg_nummer} existiert bereits.", ephemeral=True)
        return

    deadline = datetime.now() + timedelta(hours=dauer)
    deadline_str = deadline.strftime("%d.%m.%Y %H:%M")

    frage = f"Soll der Server **{servername}** in die Servergemeinschaft aufgenommen werden? (Dauer: {dauer} h)\n**Deadline:** {deadline_str}\n{'**Anonyme** Abstimmung' if anonym else '**Öffentliche** Abstimmung'}"

    embed = discord.Embed(
        title=f"SG {sg_nummer}",
        description=frage,
        color=discord.Color.blue()
    )

    view = AbstimmungsView(sg_nummer, servername, anonym, interaction.user, dauer)
    view.channel = interaction.channel

    await interaction.response.send_message(embed=embed, view=view)
    view.message = await interaction.original_response()

    # Rollenping separat
    await interaction.channel.send(f"<@&{ROLE_ID}>")

    abstimmungen[sg_nummer] = view
    joblib.dump(abstimmungen, DUMP_NAME)


@bot.tree.command(name="abstimmung_frei", description="Starte eine freie Abstimmung", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(
    nummer="Abstimmungskennung, z. B. 999",
    frage="Was soll gefragt werden?",
    anonym="Anonyme Abstimmung?",
    dauer="Dauer in Stunden (Standard: 42)"
)
async def abstimmung_frei(interaction: discord.Interaction, nummer: int, frage: str, anonym: bool = False, dauer: int = 42):
    sg_nummer = str(nummer).zfill(3)

    if sg_nummer in abstimmungen:
        await interaction.response.send_message(f"❌ Abstimmung SG{sg_nummer} existiert bereits.", ephemeral=True)
        return

    deadline = datetime.now() + timedelta(hours=dauer)
    deadline_str = deadline.strftime("%d.%m.%Y %H:%M")

    embed = discord.Embed(
        title=f"SG {sg_nummer}",
        description=f"{frage}\n**Deadline:** {deadline_str}\n{'**Anonyme** Abstimmung' if anonym else '**Öffentliche** Abstimmung'}",
        color=discord.Color.green()
    )

    view = AbstimmungsView(sg_nummer, frage, anonym, interaction.user, dauer)
    view.channel = interaction.channel

    await interaction.response.send_message(embed=embed, view=view)
    await interaction.channel.send(f"<@&{ROLE_ID}>")

    abstimmungen[sg_nummer] = view
    joblib.dump(abstimmungen, DUMP_NAME)


@bot.tree.command(name="abstimmung_beenden", description="Beende eine laufende Abstimmung", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(nummer="SG-Nummer der Abstimmung")
async def abstimmung_beenden(interaction: discord.Interaction, nummer: int):
    sg_nummer = str(nummer).zfill(3)
    view = abstimmungen.get(sg_nummer)

    if not view:
        await interaction.response.send_message("Abstimmung nicht gefunden.", ephemeral=True)
        return
    if interaction.user.id != view.ersteller.id:
        await interaction.response.send_message("Nur der Ersteller darf diese Abstimmung vorzeitig beenden.", ephemeral=True)
        return

    view.status = "premature"
    await interaction.response.send_message("✅ Abstimmung wird vorzeitig beendet.", ephemeral=True)
    await view.post_results()
    view.stop()
    abstimmungen.pop(sg_nummer, None)
    joblib.dump(abstimmungen, DUMP_NAME)


@bot.tree.command(name="abstimmung_abbrechen", description="Brich eine Abstimmung ohne Ergebnis ab", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(nummer="SG-Nummer der Abstimmung")
async def abstimmung_abbrechen(interaction: discord.Interaction, nummer: int):
    sg_nummer = str(nummer).zfill(3)
    view = abstimmungen.get(sg_nummer)

    if not view:
        await interaction.response.send_message("Abstimmung nicht gefunden.", ephemeral=True)
        return
    if interaction.user.id != view.ersteller.id:
        await interaction.response.send_message("Nur der Ersteller darf diese Abstimmung abbrechen.", ephemeral=True)
        return

    view.status = "aborted"
    await interaction.response.send_message("✅ Abstimmung wurde abgebrochen. Kein Ergebnis wird veröffentlicht.", ephemeral=True)
    view.save_to_csv()
    view.stop()
    abstimmungen.pop(sg_nummer, None)
    joblib.dump(abstimmungen, DUMP_NAME)


@bot.tree.command(name="meine_abstimmungen", description="Zeigt deine laufenden Abstimmungen", guild=discord.Object(id=GUILD_ID))
async def meine_abstimmungen(interaction: discord.Interaction):
    eigene = [key for key, view in abstimmungen.items() if view.ersteller.id == interaction.user.id]

    if not eigene:
        await interaction.response.send_message("Du hast keine aktiven Abstimmungen.", ephemeral=True)
        return

    msg = "**Deine aktiven Abstimmungen:**\n" + "\n".join(f"- SG{sg}" for sg in eigene)
    await interaction.response.send_message(msg, ephemeral=True)


bot.run(TOKEN)
