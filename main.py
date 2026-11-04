import os
import json
import discord
import datetime
from discord import app_commands
from discord.ext import commands

# Configurar intents
intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True

class MusicBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)
        self.music_dir = "./MusicBot/music_storage"
        self.db_file = "./MusicBot/songs.json"
        
        # Crear la carpeta MusicBot si no existe
        os.makedirs("./MusicBot", exist_ok=True)
        
        # Crear la carpeta de música si no existe
        if not os.path.exists(self.music_dir):
            os.makedirs(self.music_dir)
            
        # Crear el archivo JSON de registro si no existe
        if not os.path.exists(self.db_file):
            self.save_songs({})

    def load_songs(self):
        try:
            with open(self.db_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return {}

    def save_songs(self, data):
        with open(self.db_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)

    async def setup_hook(self):
        # Sincronizar los comandos barra con Discord
        await self.tree.sync()
        print("¡Comandos barra (Slash Commands) sincronizados!")

bot = MusicBot()

@bot.event
async def on_ready():
    print(f"¡Bot conectado como {bot.user}!")

# --- AUTOCOMPLETADO PARA EL NOMBRE DE LA MÚSICA ---
async def song_autocomplete(interaction: discord.Interaction, current: str):
    songs = bot.load_songs()
    return [
        app_commands.Choice(name=name, value=name)
        for name in songs.keys() if current.lower() in name.lower()
    ][:25]

# --- COMANDO PARA SUBIR Y REGISTRAR MÚSICA ---
@bot.tree.command(name="agregar", description="Sube un archivo de música para que todos puedan reproducirlo")
@app_commands.describe(
    archivo="Selecciona tu archivo de audio (.mp3, .wav, .ogg)",
    nombre="El nombre corto con el que se guardará (ej: electro1)",
    artista="Nombre del artista o autor de la música (opcional)"
)
async def agregar(interaction: discord.Interaction, archivo: discord.Attachment, nombre: str, artista: str = "Desconocido"):
    if not archivo.filename.lower().endswith((".mp3", ".wav", ".ogg", ".flac", ".m4a")):
        await interaction.response.send_message("❌ Formato no válido. Sube un archivo de música compatible.", ephemeral=True)
        return

    nombre_lower = nombre.lower().strip()
    songs = bot.load_songs()

    if nombre_lower in songs:
        await interaction.response.send_message(f"⚠️ Ya existe una canción registrada con el nombre `{nombre}`.", ephemeral=True)
        return

    await interaction.response.defer(thinking=True)

    file_path = os.path.join(bot.music_dir, f"{nombre_lower}_{archivo.filename}")
    await archivo.save(file_path)

    # Obtenemos la fecha y hora actual en formato legible
    fecha_actual = datetime.datetime.now().strftime("%d/%m/%Y a las %H:%M")

    # Guardamos todos los nuevos datos en el JSON
    songs[nombre_lower] = {
        "path": file_path,
        "filename": archivo.filename,
        "uploader": interaction.user.name,
        "artist": artista.strip(),
        "date": fecha_actual,
        "plays": 0,
        "ratings": []  # Lista para guardar las calificaciones de 1 a 5 estrellas
    }
    bot.save_songs(songs)

    await interaction.followup.send(f"✅ ¡Canción **{nombre}** de *{artista}* guardada con éxito!")

# --- COMANDO PARA REPRODUCIR LA MÚSICA ---
@bot.tree.command(name="reproducir", description="Reproduce una música guardada en el canal de voz")
@app_commands.describe(nombre="Nombre de la canción guardada")
@app_commands.autocomplete(nombre=song_autocomplete)
async def reproducir(interaction: discord.Interaction, nombre: str):
    if not interaction.user.voice or not interaction.user.voice.channel:
        await interaction.response.send_message("❌ ¡Tienes que estar conectado a un canal de voz primero!", ephemeral=True)
        return

    songs = bot.load_songs()
    nombre_lower = nombre.lower().strip()

    if nombre_lower not in songs:
        await interaction.response.send_message(f"❌ No encontré ninguna canción con el nombre `{nombre}`.", ephemeral=True)
        return

    song_info = songs[nombre_lower]
    file_path = song_info["path"]

    if not os.path.exists(file_path):
        await interaction.response.send_message("❌ El archivo físico ya no se encuentra en el almacenamiento del bot.", ephemeral=True)
        return

    # 1. Diferimos la respuesta de inmediato para evitar que expire el tiempo de Discord
    await interaction.response.defer(thinking=True)

    voice_client = interaction.guild.voice_client
    channel = interaction.user.voice.channel

    if voice_client is None:
        voice_client = await channel.connect()
    elif voice_client.channel != channel:
        await voice_client.move_to(channel)

    if voice_client.is_playing() or voice_client.is_paused():
        voice_client.stop()

    try:
        # Sumar una reproducción
        song_info["plays"] = song_info.get("plays", 0) + 1
        bot.save_songs(songs)

        executable_path = os.path.join(".", "MusicBot", "ffmpeg", "ffmpeg.exe")
        source = discord.FFmpegPCMAudio(file_path, executable=executable_path)
        
        voice_client.play(source, after=lambda e: print(f"Terminó la reproducción: {e}"))
        
        # 2. Usamos followup en lugar de response.send_message
        artista = song_info.get('artist', 'Desconocido')
        await interaction.followup.send(f"🎵 Reproduciendo: **{nombre}** - *{artista}* (Subida por *{song_info['uploader']}*)")
    except Exception as e:
        await interaction.followup.send(f"❌ Hubo un eror al reproducir el audio: {e}")

# --- COMANDO PARA PAUSAR / REANUDAR LA MÚSICA ---
@bot.tree.command(name="pausa", description="Pausa o reanuda la música actual sin detenerla")
async def pausa(interaction: discord.Interaction):
    voice_client = interaction.guild.voice_client
    if not voice_client:
        await interaction.response.send_message("❌ El bot no está en ningún canal de voz.", ephemeral=True)
        return

    if voice_client.is_playing():
        voice_client.pause()
        await interaction.response.send_message("⏸️ Música pausada.")
    elif voice_client.is_paused():
        voice_client.resume()
        await interaction.response.send_message("▶️ Música reanudada.")
    else:
        await interaction.response.send_message("❌ No hay nada reproduciéndose en este momento.", ephemeral=True)

# --- COMANDO PARA CAMBIAR A OTRA MÚSICA DE LA LISTA ---
@bot.tree.command(name="cambiar", description="Cambia inmediatamente a otra música de la lista")
@app_commands.describe(nombre="Nombre de la nueva canción guardada")
@app_commands.autocomplete(nombre=song_autocomplete)
async def cambiar(interaction: discord.Interaction, nombre: str):
    if not interaction.user.voice or not interaction.user.voice.channel:
        await interaction.response.send_message("❌ ¡Tienes que estar conectado a un canal de voz primero!", ephemeral=True)
        return

    voice_client = interaction.guild.voice_client
    if not voice_client or not voice_client.is_connected():
        await interaction.response.send_message("❌ El bot no está conectado a ningún canal de voz. Usa `/reproducir` primero.", ephemeral=True)
        return

    songs = bot.load_songs()
    nombre_lower = nombre.lower().strip()

    if nombre_lower not in songs:
        await interaction.response.send_message(f"❌ No encontré ninguna canción con el nombre `{nombre}`.", ephemeral=True)
        return

    song_info = songs[nombre_lower]
    file_path = song_info["path"]

    if not os.path.exists(file_path):
        await interaction.response.send_message("❌ El archivo físico ya no se encuentra en el almacenamiento del bot.", ephemeral=True)
        return

    # Diferimos la respuesta
    await interaction.response.defer(thinking=True)

    channel = interaction.user.voice.channel
    if voice_client.channel != channel:
        await voice_client.move_to(channel)

    if voice_client.is_playing() or voice_client.is_paused():
        voice_client.stop()

    try:
        # Sumar una reproducción
        song_info["plays"] = song_info.get("plays", 0) + 1
        bot.save_songs(songs)

        executable_path = os.path.join(".", "MusicBot", "ffmpeg", "ffmpeg.exe")
        source = discord.FFmpegPCMAudio(file_path, executable=executable_path)
        
        voice_client.play(source, after=lambda e: print(f"Terminó la reproducción: {e}"))
        
        artista = song_info.get('artist', 'Desconocido')
        await interaction.followup.send(f"🔄 Cambiado a: **{nombre}** - *{artista}* (Subida por *{song_info['uploader']}*)")
    except Exception as e:
        await interaction.followup.send(f"❌ Hubo un error al cambiar la música: {e}")

# --- COMANDO PARA VER LA LISTA DE CANCIONES ---
@bot.tree.command(name="lista", description="Muestra todas las canciones guardadas en el bot")
async def lista(interaction: discord.Interaction):
    songs = bot.load_songs()
    if not songs:
        await interaction.response.send_message("📭 Aún no hay canciones guardadas.", ephemeral=True)
        return

    descripcion = ""
    for name, info in songs.items():
        artista = info.get('artist', 'Desconocido')
        uploader = info.get('uploader', 'Desconocido')
        fecha = info.get('date', 'Fecha desconocida')
        reproducciones = info.get('plays', 0)
        
        # Calcular promedio de estrellas si tiene ratings
        ratings = info.get('ratings', [])
        if ratings:
            promedio = sum(ratings) / len(ratings)
            estrellas = f"⭐ {promedio:.1f} ({len(ratings)})"
        else:
            estrellas = "⭐ Sin calificar"

        descripcion += f"• **{name}** - *{artista}*\n  └ Subido por: **{uploader}** | 📅 {fecha} | 🎧 {reproducciones} reps | {estrellas}\n\n"

    embed = discord.Embed(title="🎵 Catálogo de Música en el Bot", description=descripcion, color=discord.Color.purple())
    await interaction.response.send_message(embed=embed)

# --- COMANDO PARA DETENER Y SALIR ---
@bot.tree.command(name="detener", description="Detiene la música y desconecta al bot del canal de voz")
async def detener(interaction: discord.Interaction):
    if interaction.guild.voice_client:
        await interaction.guild.voice_client.disconnect()
        await interaction.response.send_message("🛑 Música detenida y bot desconectado.")
    else:
        await interaction.response.send_message("❌ El bot no está en ningún canal de voz.", ephemeral=True)

# --- COMANDO PARA CALIFICAR UNA CANCIÓN ---
@bot.tree.command(name="calificar", description="Califica una canción del 1 al 5 estrellas")
@app_commands.describe(nombre="Nombre de la canción", estrellas="Puntuación de 1 a 5")
@app_commands.autocomplete(nombre=song_autocomplete)
@app_commands.choices(estrellas=[
    app_commands.Choice(name="⭐ 1 Estrella", value=1),
    app_commands.Choice(name="⭐⭐ 2 Estrellas", value=2),
    app_commands.Choice(name="⭐⭐⭐ 3 Estrellas", value=3),
    app_commands.Choice(name="⭐⭐⭐⭐ 4 Estrellas", value=4),
    app_commands.Choice(name="⭐⭐⭐⭐⭐ 5 Estrellas", value=5),
])
async def calificar(interaction: discord.Interaction, nombre: str, estrellas: int):
    songs = bot.load_songs()
    nombre_lower = nombre.lower().strip()

    if nombre_lower not in songs:
        await interaction.response.send_message(f"❌ No encontré la canción `{nombre}`.", ephemeral=True)
        return

    # Añadimos la estrella a la lista de calificaciones de la canción
    songs[nombre_lower].setdefault("ratings", []).append(estrellas)
    bot.save_songs(songs)

    await interaction.response.send_message(f"🌟 ¡Gracias! Has calificado a **{nombre}** con **{estrellas} estrellas**.", ephemeral=True)

# --- COMANDO PARA VER EL TOP DE MÚSICAS ---
@bot.tree.command(name="top", description="Muestra las mejores canciones (por rating y reproducciones)")
async def top(interaction: discord.Interaction):
    songs = bot.load_songs()
    if not songs:
        await interaction.response.send_message("📭 Aún no hay canciones registradas.", ephemeral=True)
        return

    # Lógica para ordenar: calculamos un puntaje combinando rating promedio y reproducciones
    lista_ordenada = []
    for name, info in songs.items():
        plays = info.get("plays", 0)
        ratings = info.get("ratings", [])
        avg_rating = (sum(ratings) / len(ratings)) if ratings else 0.0
        
        # Fórmula de puntuación mixta (peso al rating y peso a las reproducciones)
        score = (avg_rating * 10) + plays
        lista_ordenada.append((name, info, avg_rating, plays, score))

    # Ordenar de mayor a menor puntaje y tomar las 3 primeras
    lista_ordenada.sort(key=lambda x: x[4], reverse=True)
    top_tres = lista_ordenada[:3]

    descripcion = ""
    for i, (name, info, avg_rating, plays, _) in enumerate(top_tres, 1):
        artista = info.get('artist', 'Desconocido')
        estrellas_txt = f"{avg_rating:.1f} ⭐" if avg_rating > 0 else "Sin calificar"
        descripcion += f"**#{i}** 🎵 **{name}** - *{artista}*\n  └ 🎧 Reproducciones: **{plays}** | ⭐ Rating: **{estrellas_txt}**\n\n"

    embed = discord.Embed(title="🏆 Top 3 Mejores Músicas", description=descripcion, color=discord.Color.gold())
    await interaction.response.send_message(embed=embed)

# --- COMANDO PARA ELIMINAR UNA MÚSICA ---
@bot.tree.command(name="eliminar", description="Elimina una canción del bot permanentemente")
@app_commands.describe(nombre="Nombre de la canción a eliminar")
@app_commands.autocomplete(nombre=song_autocomplete)
async def eliminar(interaction: discord.Interaction, nombre: str):
    songs = bot.load_songs()
    nombre_lower = nombre.lower().strip()

    if nombre_lower not in songs:
        await interaction.response.send_message(f"❌ No encontré ninguna canción llamada `{nombre}`.", ephemeral=True)
        return

    song_info = songs[nombre_lower]
    file_path = song_info["path"]

    # Borrar archivo físico si existe
    if os.path.exists(file_path):
        try:
            os.remove(file_path)
        except Exception as e:
            print(f"No se pudo borrar el archivo físico: {e}")

    # Borrar del diccionario y guardar JSON
    del songs[nombre_lower]
    bot.save_songs(songs)

    await interaction.response.send_message(f"🗑️ La canción **{nombre}** ha sido eliminada exitosamente del bot.")

# Token de tu bot de Discord
bot.run("")
