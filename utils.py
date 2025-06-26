import discord
import re
from urllib.parse import urlparse, parse_qs

def create_embed(title, description, color=discord.Color.blue()):
    """Create a formatted Discord embed"""
    embed = discord.Embed(
        title=title,
        description=description,
        color=color
    )
    return embed

def is_url(string):
    """Check if a string is a valid URL"""
    try:
        result = urlparse(string)
        return all([result.scheme, result.netloc])
    except:
        return False

def is_youtube_url(url):
    """Check if URL is a YouTube URL"""
    youtube_domains = ['youtube.com', 'youtu.be', 'www.youtube.com', 'www.youtu.be']
    try:
        parsed = urlparse(url)
        return parsed.netloc.lower() in youtube_domains
    except:
        return False

def is_spotify_url(url):
    """Check if URL is a Spotify URL"""
    return 'spotify.com' in url or url.startswith('spotify:')

def extract_video_id(url):
    """Extract YouTube video ID from URL"""
    if not is_youtube_url(url):
        return None
    
    # Handle different YouTube URL formats
    patterns = [
        r'(?:youtube\.com\/watch\?v=|youtu\.be\/)([a-zA-Z0-9_-]{11})',
        r'youtube\.com\/embed\/([a-zA-Z0-9_-]{11})',
        r'youtube\.com\/v\/([a-zA-Z0-9_-]{11})'
    ]
    
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    
    return None

def format_duration(seconds):
    """Format duration from seconds to HH:MM:SS or MM:SS"""
    if not seconds or seconds <= 0:
        return "Unknown"
    
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    seconds = seconds % 60
    
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    else:
        return f"{minutes:02d}:{seconds:02d}"

def truncate_string(text, max_length=100):
    """Truncate a string to a maximum length"""
    if len(text) <= max_length:
        return text
    return text[:max_length-3] + "..."

def validate_file_extension(filename, allowed_extensions):
    """Validate if file has allowed extension"""
    if not filename:
        return False
    
    extension = filename.lower().split('.')[-1]
    return extension in allowed_extensions

def clean_filename(filename):
    """Clean filename by removing invalid characters"""
    # Remove invalid characters for file systems
    invalid_chars = '<>:"/\\|?*'
    for char in invalid_chars:
        filename = filename.replace(char, '_')
    
    # Limit length
    if len(filename) > 255:
        name, ext = filename.rsplit('.', 1) if '.' in filename else (filename, '')
        max_name_length = 255 - len(ext) - 1
        filename = name[:max_name_length] + ('.' + ext if ext else '')
    
    return filename

def parse_time_string(time_str):
    """Parse time string (e.g., '1:30', '90s', '1m30s') to seconds"""
    if not time_str:
        return 0
    
    time_str = time_str.lower().strip()
    
    # Handle MM:SS or HH:MM:SS format
    if ':' in time_str:
        parts = time_str.split(':')
        if len(parts) == 2:  # MM:SS
            try:
                minutes, seconds = map(int, parts)
                return minutes * 60 + seconds
            except ValueError:
                return 0
        elif len(parts) == 3:  # HH:MM:SS
            try:
                hours, minutes, seconds = map(int, parts)
                return hours * 3600 + minutes * 60 + seconds
            except ValueError:
                return 0
    
    # Handle formats like '90s', '1m30s', '1h30m'
    total_seconds = 0
    
    # Extract hours
    if 'h' in time_str:
        try:
            hours = int(time_str.split('h')[0])
            total_seconds += hours * 3600
            time_str = time_str.split('h', 1)[1]
        except (ValueError, IndexError):
            pass
    
    # Extract minutes
    if 'm' in time_str:
        try:
            minutes = int(time_str.split('m')[0])
            total_seconds += minutes * 60
            time_str = time_str.split('m', 1)[1]
        except (ValueError, IndexError):
            pass
    
    # Extract seconds
    if 's' in time_str:
        try:
            seconds = int(time_str.split('s')[0])
            total_seconds += seconds
        except (ValueError, IndexError):
            pass
    elif time_str.isdigit():
        # If just a number, assume seconds
        total_seconds += int(time_str)
    
    return total_seconds

def create_progress_bar(current, total, length=20):
    """Create a text progress bar"""
    if total <= 0:
        return "█" * length
    
    progress = min(current / total, 1.0)
    filled_length = int(length * progress)
    
    bar = "█" * filled_length + "░" * (length - filled_length)
    percentage = int(progress * 100)
    
    return f"{bar} {percentage}%"

def format_file_size(size_bytes):
    """Format file size in human readable format"""
    if size_bytes == 0:
        return "0 B"
    
    size_names = ["B", "KB", "MB", "GB"]
    i = 0
    while size_bytes >= 1024 and i < len(size_names) - 1:
        size_bytes /= 1024.0
        i += 1
    
    return f"{size_bytes:.1f} {size_names[i]}"
