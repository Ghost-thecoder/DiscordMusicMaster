import discord
import yt_dlp
import asyncio
import logging

# Test audio streaming with a minimal working implementation
logger = logging.getLogger(__name__)

class WorkingAudioSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get('title')
        self.url = data.get('url')

    @classmethod
    async def from_url(cls, url, *, loop=None, stream=False):
        loop = loop or asyncio.get_event_loop()
        
        ytdl_format_options = {
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

        ffmpeg_options = {
            'before_options': '-nostdin',
            'options': '-vn'
        }

        ytdl = yt_dlp.YoutubeDL(ytdl_format_options)

        try:
            data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=not stream))
        except Exception as e:
            logger.error(f"Error extracting info: {e}")
            raise

        if 'entries' in data:
            # take first item from a playlist
            data = data['entries'][0]

        filename = data['url'] if stream else ytdl.prepare_filename(data)
        return cls(discord.FFmpegPCMAudio(filename, **ffmpeg_options), data=data)

# Test function
async def test_audio_creation(url):
    try:
        player = await WorkingAudioSource.from_url(url, stream=True)
        print(f"Successfully created audio source for: {player.title}")
        return player
    except Exception as e:
        print(f"Failed to create audio source: {e}")
        return None

if __name__ == "__main__":
    # Test with a simple URL
    test_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    asyncio.run(test_audio_creation(test_url))