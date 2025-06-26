import discord
from discord.ext import commands
from discord import app_commands
import os
import asyncio
import logging
from music_player import MusicPlayer
from queue_manager import QueueManager
from spotify_handler import SpotifyHandler
from utils import create_embed, is_url, extract_video_id

# Load Opus library for Discord voice
discord.opus.load_opus('/nix/store/235dxwql4lqrfjfhqrld8i3pwcffhwxf-libopus-1.4/lib/libopus.so')
if not discord.opus.is_loaded():
    raise RuntimeError('Opus library failed to load')

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Bot configuration
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN', 'your_discord_token_here')
SPOTIFY_CLIENT_ID = os.getenv('SPOTIFY_CLIENT_ID', 'your_spotify_client_id')
SPOTIFY_CLIENT_SECRET = os.getenv('SPOTIFY_CLIENT_SECRET', 'your_spotify_client_secret')

# Bot setup
intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
bot = commands.Bot(command_prefix='!', intents=intents)

# Global managers
queue_managers = {}  # Guild ID -> QueueManager
music_players = {}   # Guild ID -> MusicPlayer
spotify_handler = SpotifyHandler(SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET)

@bot.event
async def on_ready():
    logger.info(f'{bot.user} has connected to Discord!')
    try:
        synced = await bot.tree.sync()
        logger.info(f"Synced {len(synced)} slash command(s)")
    except Exception as e:
        logger.error(f"Failed to sync slash commands: {e}")
    await bot.change_presence(activity=discord.Game(name="!commands for help"))

@bot.event
async def on_guild_remove(guild):
    """Clean up when bot is removed from a guild"""
    guild_id = guild.id
    if guild_id in queue_managers:
        del queue_managers[guild_id]
    if guild_id in music_players:
        await music_players[guild_id].cleanup()
        del music_players[guild_id]

def get_queue_manager(guild_id):
    """Get or create queue manager for guild"""
    if guild_id not in queue_managers:
        queue_managers[guild_id] = QueueManager()
    return queue_managers[guild_id]

def get_music_player(guild_id):
    """Get or create music player for guild"""
    if guild_id not in music_players:
        music_players[guild_id] = MusicPlayer(bot)
    return music_players[guild_id]

@bot.command(name='join')
async def join_voice(ctx):
    """Join the user's voice channel"""
    if not ctx.author.voice:
        embed = create_embed("Error", "You need to be in a voice channel!", discord.Color.red())
        await ctx.send(embed=embed)
        return

    channel = ctx.author.voice.channel
    player = get_music_player(ctx.guild.id)
    
    try:
        await player.connect(channel)
        embed = create_embed("Joined", f"Connected to {channel.name}", discord.Color.green())
        await ctx.send(embed=embed)
    except Exception as e:
        embed = create_embed("Error", f"Failed to join voice channel: {str(e)}", discord.Color.red())
        await ctx.send(embed=embed)

@bot.command(name='leave')
async def leave_voice(ctx):
    """Leave the voice channel"""
    player = get_music_player(ctx.guild.id)
    queue_manager = get_queue_manager(ctx.guild.id)
    
    if not player.voice_client:
        embed = create_embed("Error", "Not connected to a voice channel!", discord.Color.red())
        await ctx.send(embed=embed)
        return

    await player.disconnect()
    queue_manager.clear()
    embed = create_embed("Disconnected", "Left the voice channel and cleared the queue", discord.Color.orange())
    await ctx.send(embed=embed)

@bot.command(name='play')
async def play_music(ctx, *, query=None):
    """Play music from various sources"""
    if not query and not ctx.message.attachments:
        embed = create_embed("Error", "Please provide a search query, URL, or upload an MP3 file!", discord.Color.red())
        await ctx.send(embed=embed)
        return

    if not ctx.author.voice or not ctx.author.voice.channel:
        embed = create_embed("Error", "You need to be in a voice channel!", discord.Color.red())
        await ctx.send(embed=embed)
        return

    player = get_music_player(ctx.guild.id)
    queue_manager = get_queue_manager(ctx.guild.id)

    # Auto-join if not connected
    if not player.voice_client:
        try:
            await player.connect(ctx.author.voice.channel)
        except Exception as e:
            embed = create_embed("Error", f"Failed to join voice channel: {str(e)}", discord.Color.red())
            await ctx.send(embed=embed)
            return

    # Handle file upload
    if ctx.message.attachments:
        attachment = ctx.message.attachments[0]
        if attachment.filename.lower().endswith('.mp3'):
            try:
                # Download the file temporarily
                temp_path = f"temp_{ctx.guild.id}_{attachment.filename}"
                await attachment.save(temp_path)
                
                song_info = {
                    'title': attachment.filename[:-4],  # Remove .mp3 extension
                    'url': temp_path,
                    'duration': 'Unknown',
                    'source': 'upload',
                    'temp_file': True
                }
                
                queue_manager.add_song(song_info)
                embed = create_embed("Added to Queue", f"**{song_info['title']}** (Uploaded file)", discord.Color.blue())
                await ctx.send(embed=embed)
                
                if not player.is_playing():
                    await play_next_song(ctx.guild.id)
                    
            except Exception as e:
                embed = create_embed("Error", f"Failed to process uploaded file: {str(e)}", discord.Color.red())
                await ctx.send(embed=embed)
        else:
            embed = create_embed("Error", "Only MP3 files are supported for upload!", discord.Color.red())
            await ctx.send(embed=embed)
        return

    # Handle Spotify URLs
    if query and 'spotify.com' in query:
        await ctx.send("🔍 Processing Spotify link...")
        try:
            spotify_data = await spotify_handler.get_track_info(query)
            if spotify_data['type'] == 'track':
                # Convert to YouTube search
                search_query = f"{spotify_data['artist']} - {spotify_data['name']}"
                song_info = await player.get_youtube_info(search_query)
                if song_info:
                    song_info['spotify_info'] = spotify_data
                    queue_manager.add_song(song_info)
                    embed = create_embed("Added to Queue", f"**{song_info['title']}** (from Spotify)", discord.Color.green())
                    await ctx.send(embed=embed)
                else:
                    embed = create_embed("Error", "Could not find this track on YouTube", discord.Color.red())
                    await ctx.send(embed=embed)
                    return
            elif spotify_data['type'] == 'playlist':
                added_count = 0
                for track in spotify_data['tracks']:
                    search_query = f"{track['artist']} - {track['name']}"
                    song_info = await player.get_youtube_info(search_query)
                    if song_info:
                        song_info['spotify_info'] = track
                        queue_manager.add_song(song_info)
                        added_count += 1
                
                embed = create_embed("Playlist Added", f"Added {added_count} songs from Spotify playlist", discord.Color.green())
                await ctx.send(embed=embed)
        except Exception as e:
            embed = create_embed("Error", f"Failed to process Spotify link: {str(e)}", discord.Color.red())
            await ctx.send(embed=embed)
            return
    else:
        # Handle YouTube URLs and search queries
        await ctx.send("🔍 Searching...")
        try:
            if query and 'playlist' in query and 'youtube.com' in query:
                # Handle YouTube playlist
                songs = await player.get_playlist_info(query)
                added_count = len(songs)
                for song in songs:
                    queue_manager.add_song(song)
                embed = create_embed("Playlist Added", f"Added {added_count} songs to the queue", discord.Color.green())
                await ctx.send(embed=embed)
            else:
                # Handle single video or search
                song_info = await player.get_youtube_info(query)
                if song_info:
                    queue_manager.add_song(song_info)
                    embed = create_embed("Added to Queue", f"**{song_info['title']}**", discord.Color.blue())
                    await ctx.send(embed=embed)
                else:
                    embed = create_embed("Error", "Could not find any results", discord.Color.red())
                    await ctx.send(embed=embed)
                    return
        except Exception as e:
            embed = create_embed("Error", f"Failed to process request: {str(e)}", discord.Color.red())
            await ctx.send(embed=embed)
            return

    # Start playing if nothing is currently playing
    if not player.is_playing():
        await play_next_song(ctx.guild.id)

async def play_next_song(guild_id):
    """Play the next song in the queue"""
    player = get_music_player(guild_id)
    queue_manager = get_queue_manager(guild_id)
    
    if queue_manager.is_empty():
        # Start disconnect timer
        await asyncio.sleep(60)  # Wait 1 minute
        if queue_manager.is_empty() and not player.is_playing():
            await player.disconnect()
        return

    song = queue_manager.get_next_song()
    if song:
        try:
            await player.play_song(song, lambda: play_next_song(guild_id))
        except Exception as e:
            logger.error(f"Error playing song: {e}")
            await play_next_song(guild_id)  # Try next song

@bot.command(name='skip')
async def skip_song(ctx):
    """Skip the current song"""
    player = get_music_player(ctx.guild.id)
    
    if not player.voice_client or not player.is_playing():
        embed = create_embed("Error", "Nothing is currently playing!", discord.Color.red())
        await ctx.send(embed=embed)
        return

    player.voice_client.stop()
    embed = create_embed("Skipped", "⏭️ Skipped to the next song", discord.Color.orange())
    await ctx.send(embed=embed)

@bot.command(name='pause')
async def pause_music(ctx):
    """Pause the music"""
    player = get_music_player(ctx.guild.id)
    
    if not player.voice_client or not player.is_playing():
        embed = create_embed("Error", "Nothing is currently playing!", discord.Color.red())
        await ctx.send(embed=embed)
        return

    player.voice_client.pause()
    embed = create_embed("Paused", "⏸️ Music paused", discord.Color.yellow())
    await ctx.send(embed=embed)

@bot.command(name='resume')
async def resume_music(ctx):
    """Resume the music"""
    player = get_music_player(ctx.guild.id)
    
    if not player.voice_client:
        embed = create_embed("Error", "Not connected to a voice channel!", discord.Color.red())
        await ctx.send(embed=embed)
        return

    if player.voice_client.is_paused():
        player.voice_client.resume()
        embed = create_embed("Resumed", "▶️ Music resumed", discord.Color.green())
        await ctx.send(embed=embed)
    else:
        embed = create_embed("Error", "Music is not paused!", discord.Color.red())
        await ctx.send(embed=embed)

@bot.command(name='stop')
async def stop_music(ctx):
    """Stop music and clear the queue"""
    player = get_music_player(ctx.guild.id)
    queue_manager = get_queue_manager(ctx.guild.id)
    
    if player.voice_client:
        player.voice_client.stop()
    
    queue_manager.clear()
    embed = create_embed("Stopped", "⏹️ Music stopped and queue cleared", discord.Color.red())
    await ctx.send(embed=embed)

@bot.command(name='queue')
async def show_queue(ctx):
    """Show the current queue"""
    queue_manager = get_queue_manager(ctx.guild.id)
    player = get_music_player(ctx.guild.id)
    
    embed = discord.Embed(title="🎵 Music Queue", color=discord.Color.blue())
    
    # Current song
    current_song = queue_manager.get_current_song()
    if current_song and player.is_playing():
        embed.add_field(
            name="🎶 Now Playing",
            value=f"**{current_song['title']}**\nDuration: {current_song.get('duration', 'Unknown')}",
            inline=False
        )
    
    # Queue
    upcoming = queue_manager.get_queue_list()
    if upcoming:
        queue_text = ""
        for i, song in enumerate(upcoming[:10], 1):  # Show max 10 songs
            queue_text += f"{i}. **{song['title']}** ({song.get('duration', 'Unknown')})\n"
        
        if len(upcoming) > 10:
            queue_text += f"\n... and {len(upcoming) - 10} more songs"
        
        embed.add_field(name="📋 Up Next", value=queue_text, inline=False)
    else:
        if not current_song:
            embed.add_field(name="📋 Queue", value="Queue is empty", inline=False)
    
    embed.set_footer(text=f"Total songs in queue: {len(upcoming)}")
    await ctx.send(embed=embed)

@bot.command(name='upload')
async def upload_command(ctx):
    """Instructions for uploading files"""
    embed = create_embed(
        "File Upload", 
        "To upload an MP3 file, use the `!play` command and attach your MP3 file to the message!",
        discord.Color.blue()
    )
    await ctx.send(embed=embed)

@bot.command(name='commands')
async def help_command(ctx):
    """Show help information"""
    embed = discord.Embed(title="🎵 Music Bot Commands", color=discord.Color.blue())
    
    commands_list = [
        ("!join", "Join your voice channel"),
        ("!leave", "Leave the voice channel"),
        ("!play <query/URL>", "Play music from YouTube, Spotify, or upload MP3"),
        ("!skip", "Skip the current song"),
        ("!pause", "Pause the music"),
        ("!resume", "Resume the music"),
        ("!stop", "Stop music and clear queue"),
        ("!queue", "Show the current queue"),
        ("!upload", "Instructions for uploading MP3 files")
    ]
    
    for command, description in commands_list:
        embed.add_field(name=command, value=description, inline=False)
    
    embed.set_footer(text="Supports YouTube URLs, playlists, Spotify links, and MP3 uploads!")
    await ctx.send(embed=embed)

# ================ SLASH COMMANDS ================

@bot.tree.command(name="play", description="Play music from YouTube, Spotify, or search query")
@app_commands.describe(query="Song name, YouTube/Spotify URL, or search query")
async def slash_play(interaction: discord.Interaction, query: str):
    """Slash command version of play"""
    await interaction.response.defer()
    
    if not interaction.user.voice or not interaction.user.voice.channel:
        embed = create_embed("Error", "You need to be in a voice channel!", discord.Color.red())
        await interaction.followup.send(embed=embed)
        return

    player = get_music_player(interaction.guild.id)
    queue_manager = get_queue_manager(interaction.guild.id)

    # Auto-join if not connected
    if not player.voice_client:
        try:
            await player.connect(interaction.user.voice.channel)
        except Exception as e:
            embed = create_embed("Error", f"Failed to join voice channel: {str(e)}", discord.Color.red())
            await interaction.followup.send(embed=embed)
            return

    # Process query with optimized handling
    try:
        songs = []
        if is_url(query):
            from utils import is_youtube_url, is_spotify_url
            if is_youtube_url(query):
                if 'playlist' in query:
                    songs = await player.get_playlist_info(query)
                else:
                    song_info = await player.get_youtube_info(query)
                    if song_info:
                        songs = [song_info]
            elif is_spotify_url(query):
                songs = await spotify_handler.get_track_info(query)
        else:
            # Optimized search query
            song_info = await player.get_youtube_info(f"ytsearch:{query}")
            if song_info:
                songs = [song_info]

        if not songs:
            embed = create_embed("Error", "No results found!", discord.Color.red())
            await interaction.followup.send(embed=embed)
            return

        # Add to queue
        for song in songs:
            queue_manager.add_song(song)

        if len(songs) == 1:
            embed = create_embed("Added to Queue", f"**{songs[0]['title']}**", discord.Color.green())
        else:
            embed = create_embed("Added to Queue", f"Added {len(songs)} songs to queue", discord.Color.green())
        
        await interaction.followup.send(embed=embed)

        # Start playing if not already
        if not player.is_playing():
            await play_next_song(interaction.guild.id)

    except Exception as e:
        logger.error(f"Error in slash play command: {e}")
        embed = create_embed("Error", f"An error occurred: {str(e)}", discord.Color.red())
        await interaction.followup.send(embed=embed)

@bot.tree.command(name="skip", description="Skip the current song")
async def slash_skip(interaction: discord.Interaction):
    """Slash command version of skip"""
    player = get_music_player(interaction.guild.id)
    
    if not player.voice_client or not player.voice_client.is_playing():
        embed = create_embed("Error", "Nothing is currently playing!", discord.Color.red())
        await interaction.response.send_message(embed=embed)
        return
    
    current_song = player.current_song
    player.voice_client.stop()
    
    if current_song:
        embed = create_embed("Skipped", f"**{current_song['title']}**", discord.Color.blue())
    else:
        embed = create_embed("Skipped", "Current song", discord.Color.blue())
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="pause", description="Pause the music")
async def slash_pause(interaction: discord.Interaction):
    """Slash command version of pause"""
    player = get_music_player(interaction.guild.id)
    
    if not player.voice_client or not player.voice_client.is_playing():
        embed = create_embed("Error", "Nothing is currently playing!", discord.Color.red())
        await interaction.response.send_message(embed=embed)
        return
    
    player.voice_client.pause()
    embed = create_embed("Paused", "Music has been paused", discord.Color.orange())
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="resume", description="Resume the music")
async def slash_resume(interaction: discord.Interaction):
    """Slash command version of resume"""
    player = get_music_player(interaction.guild.id)
    
    if not player.voice_client or not player.voice_client.is_paused():
        embed = create_embed("Error", "Music is not paused!", discord.Color.red())
        await interaction.response.send_message(embed=embed)
        return
    
    player.voice_client.resume()
    embed = create_embed("Resumed", "Music has been resumed", discord.Color.green())
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="queue", description="Show the current music queue")
async def slash_queue(interaction: discord.Interaction):
    """Slash command version of queue"""
    queue_manager = get_queue_manager(interaction.guild.id)
    
    embed = create_embed("Music Queue", "", discord.Color.blue())
    
    current_song = queue_manager.get_current_song()
    if current_song:
        embed.add_field(name="Now Playing", value=current_song['title'], inline=False)
    
    upcoming = queue_manager.get_queue_list()
    if upcoming:
        queue_list = []
        for i, song in enumerate(upcoming[:10], 1):
            queue_list.append(f"{i}. {song['title']}")
        embed.add_field(name="Up Next", value="\n".join(queue_list), inline=False)
        
        if len(upcoming) > 10:
            embed.add_field(name="", value=f"... and {len(upcoming) - 10} more songs", inline=False)
    else:
        if not current_song:
            embed.add_field(name="Queue", value="No songs in queue", inline=False)
    
    embed.set_footer(text=f"Total songs: {queue_manager.get_queue_length()}")
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="stop", description="Stop music and clear the queue")
async def slash_stop(interaction: discord.Interaction):
    """Slash command version of stop"""
    player = get_music_player(interaction.guild.id)
    queue_manager = get_queue_manager(interaction.guild.id)
    
    if player.voice_client and player.voice_client.is_playing():
        player.voice_client.stop()
    
    queue_manager.clear()
    embed = create_embed("Stopped", "Music stopped and queue cleared", discord.Color.red())
    await interaction.response.send_message(embed=embed)

if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)
