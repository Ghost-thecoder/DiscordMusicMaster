import discord
import yt_dlp
import asyncio
import os
import logging
from urllib.parse import urlparse, parse_qs

logger = logging.getLogger(__name__)

class MusicPlayer:
    def __init__(self, bot):
        self.bot = bot
        self.voice_client = None
        self.current_song = None
        
        # Simplified yt-dlp configuration for better compatibility
        self.ytdl_format_options = {
            'format': 'bestaudio/best',
            'restrictfilenames': True,
            'noplaylist': True,
            'nocheckcertificate': True,
            'ignoreerrors': False,
            'logtostderr': False,
            'quiet': True,
            'no_warnings': True,
            'default_search': 'ytsearch',
            'source_address': '0.0.0.0'
        }
        
        # Discord-compatible FFmpeg options
        self.ffmpeg_options = {
            'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 -nostdin',
            'options': '-vn -filter:a "volume=0.5"'
        }
        
        self.ytdl = yt_dlp.YoutubeDL(self.ytdl_format_options)

    async def connect(self, channel):
        """Connect to a voice channel"""
        if self.voice_client and self.voice_client.is_connected():
            await self.voice_client.move_to(channel)
        else:
            self.voice_client = await channel.connect()

    async def disconnect(self):
        """Disconnect from voice channel"""
        if self.voice_client:
            await self.voice_client.disconnect()
            self.voice_client = None
        
        # Clean up temporary files
        await self.cleanup_temp_files()

    def is_playing(self):
        """Check if music is currently playing"""
        return self.voice_client and self.voice_client.is_playing()

    async def get_youtube_info(self, query):
        """Get YouTube video information"""
        try:
            loop = asyncio.get_event_loop()
            data = await loop.run_in_executor(None, lambda: self.ytdl.extract_info(query, download=False))
            
            if not data:
                return None
                
            if 'entries' in data and data['entries']:
                # Search result
                video = data['entries'][0]
            else:
                # Direct URL
                video = data

            if not video:
                return None

            song_info = {
                'title': video.get('title', 'Unknown'),
                'url': video.get('url'),
                'webpage_url': video.get('webpage_url'),
                'duration': self.format_duration(video.get('duration')),
                'source': 'youtube',
                'temp_file': False
            }
            
            return song_info
            
        except Exception as e:
            logger.error(f"Error extracting YouTube info: {e}")
            return None

    async def get_playlist_info(self, playlist_url):
        """Get YouTube playlist information"""
        try:
            # Modify options for playlist extraction
            playlist_options = self.ytdl_format_options.copy()
            playlist_options['extract_flat'] = True
            playlist_ytdl = yt_dlp.YoutubeDL(playlist_options)
            
            loop = asyncio.get_event_loop()
            data = await loop.run_in_executor(None, lambda: playlist_ytdl.extract_info(playlist_url, download=False))
            
            songs = []
            if 'entries' in data:
                for entry in data['entries'][:50]:  # Limit to 50 songs
                    if entry:
                        song_info = {
                            'title': entry.get('title', 'Unknown'),
                            'url': f"https://www.youtube.com/watch?v={entry['id']}",
                            'webpage_url': f"https://www.youtube.com/watch?v={entry['id']}",
                            'duration': self.format_duration(entry.get('duration')),
                            'source': 'youtube',
                            'temp_file': False
                        }
                        songs.append(song_info)
            
            return songs
            
        except Exception as e:
            logger.error(f"Error extracting playlist info: {e}")
            return []

    async def create_audio_source(self, song_info):
        """Create audio source for Discord using proven method"""
        try:
            if song_info.get('temp_file'):
                # Direct file playback
                logger.info(f"Creating source for uploaded file: {song_info['url']}")
                source = discord.FFmpegPCMAudio(song_info['url'], **self.ffmpeg_options)
                return discord.PCMVolumeTransformer(source, volume=0.5)
            else:
                # YouTube streaming using working approach
                webpage_url = song_info.get('webpage_url')
                if not webpage_url:
                    raise Exception("No webpage URL available for streaming")
                
                logger.info(f"Creating audio source from: {webpage_url}")
                
                # Use proven yt-dlp configuration
                ytdl_opts = {
                    'format': 'bestaudio/best',
                    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
                    'restrictfilenames': True,
                    'noplaylist': True,
                    'nocheckcertificate': True,
                    'ignoreerrors': False,
                    'logtostderr': False,
                    'quiet': True,
                    'no_warnings': True,
                    'default_search': 'auto',
                    'source_address': '0.0.0.0'
                }

                # Simple FFmpeg options that work with Discord
                ffmpeg_opts = {
                    'before_options': '-nostdin',
                    'options': '-vn'
                }
                
                ytdl = yt_dlp.YoutubeDL(ytdl_opts)
                loop = asyncio.get_event_loop()
                
                try:
                    data = await loop.run_in_executor(None, lambda: ytdl.extract_info(webpage_url, download=False))
                except Exception as e:
                    logger.error(f"Error extracting info: {e}")
                    raise

                if 'entries' in data:
                    data = data['entries'][0]

                stream_url = data['url']
                logger.info(f"Stream URL extracted successfully")
                
                # Create PCM audio source with volume control
                source = discord.FFmpegPCMAudio(stream_url, **ffmpeg_opts)
                return discord.PCMVolumeTransformer(source, volume=0.5)
                    
        except Exception as e:
            logger.error(f"Error creating audio source: {e}")
            raise

    async def play_song(self, song_info, after_callback=None):
        """Play a song"""
        if not self.voice_client:
            raise Exception("Not connected to a voice channel")

        self.current_song = song_info
        logger.info(f"Starting playback: {song_info['title']}")

        try:
            source = await self.create_audio_source(song_info)
            logger.info(f"Audio source created: {type(source)}")
            
            def after_playing(error):
                if error:
                    logger.error(f'Playback error: {error}')
                    logger.error(f'Error type: {type(error).__name__}')
                    import traceback
                    logger.error(f'Full error: {traceback.format_exc()}')
                else:
                    logger.info(f"Finished playing: {song_info['title']}")
                
                # Clean up temp files
                if song_info.get('temp_file') and song_info.get('url'):
                    try:
                        if os.path.exists(song_info['url']):
                            os.remove(song_info['url'])
                    except Exception as e:
                        logger.error(f"Error removing temp file: {e}")
                
                if after_callback:
                    try:
                        asyncio.run_coroutine_threadsafe(after_callback, self.bot.loop)
                    except Exception as e:
                        logger.error(f"Error in after callback: {e}")

            logger.info(f"Voice client connected: {self.voice_client.is_connected()}")
            self.voice_client.play(source, after=after_playing)
            logger.info(f"Play command sent to Discord")
            
            # Check if playback actually started
            await asyncio.sleep(0.5)
            if self.voice_client.is_playing():
                logger.info("Audio playback confirmed")
            else:
                logger.error("Audio not playing - possible format issue")
            
        except Exception as e:
            logger.error(f"Failed to play song '{song_info['title']}': {e}")
            logger.error(f"Exception details: {type(e).__name__}: {str(e)}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            if song_info.get('temp_file') and song_info.get('url'):
                try:
                    if os.path.exists(song_info['url']):
                        os.remove(song_info['url'])
                except:
                    pass
            raise

    def format_duration(self, seconds):
        """Format duration from seconds to MM:SS"""
        if not seconds:
            return "Unknown"
        
        minutes = seconds // 60
        seconds = seconds % 60
        return f"{minutes:02d}:{seconds:02d}"

    async def cleanup_temp_files(self):
        """Clean up any temporary files"""
        try:
            # Remove any temp files that might exist
            for file in os.listdir('.'):
                if file.startswith('temp_') and file.endswith('.mp3'):
                    try:
                        os.remove(file)
                    except Exception as e:
                        logger.error(f"Error removing temp file {file}: {e}")
        except:
            pass

    async def cleanup(self):
        """Full cleanup of the player"""
        if self.voice_client:
            await self.voice_client.disconnect()
        await self.cleanup_temp_files()
