import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
import logging
import re

logger = logging.getLogger(__name__)

class SpotifyHandler:
    def __init__(self, client_id, client_secret):
        self.client_id = client_id
        self.client_secret = client_secret
        self.spotify = None
        
        if client_id and client_secret and client_id != 'your_spotify_client_id':
            try:
                client_credentials_manager = SpotifyClientCredentials(
                    client_id=client_id,
                    client_secret=client_secret
                )
                self.spotify = spotipy.Spotify(client_credentials_manager=client_credentials_manager)
                logger.info("Spotify client initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize Spotify client: {e}")
                self.spotify = None

    async def get_track_info(self, spotify_url):
        """Extract track information from Spotify URL"""
        if not self.spotify:
            raise Exception("Spotify client not initialized. Please check your credentials.")

        try:
            # Extract Spotify URI from URL
            track_id = self.extract_spotify_id(spotify_url)
            if not track_id:
                raise Exception("Invalid Spotify URL")

            # Determine if it's a track or playlist
            if '/track/' in spotify_url:
                return await self.get_single_track(track_id)
            elif '/playlist/' in spotify_url:
                return await self.get_playlist_tracks(track_id)
            elif '/album/' in spotify_url:
                return await self.get_album_tracks(track_id)
            else:
                raise Exception("Unsupported Spotify URL type")

        except Exception as e:
            logger.error(f"Error processing Spotify URL: {e}")
            raise

    def extract_spotify_id(self, url):
        """Extract Spotify ID from URL"""
        patterns = [
            r'https://open\.spotify\.com/(track|playlist|album)/([a-zA-Z0-9]+)',
            r'spotify:(track|playlist|album):([a-zA-Z0-9]+)'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(2)
        
        return None

    async def get_single_track(self, track_id):
        """Get information for a single track"""
        try:
            track = self.spotify.track(track_id)
            
            return {
                'type': 'track',
                'name': track['name'],
                'artist': ', '.join([artist['name'] for artist in track['artists']]),
                'album': track['album']['name'],
                'duration': track['duration_ms'] // 1000,
                'external_url': track['external_urls']['spotify']
            }
        except Exception as e:
            logger.error(f"Error fetching track {track_id}: {e}")
            raise

    async def get_playlist_tracks(self, playlist_id):
        """Get all tracks from a playlist"""
        try:
            playlist = self.spotify.playlist(playlist_id)
            tracks = []
            
            # Get playlist info
            playlist_info = {
                'type': 'playlist',
                'name': playlist['name'],
                'description': playlist.get('description', ''),
                'total_tracks': playlist['tracks']['total'],
                'tracks': []
            }
            
            # Get all tracks (handle pagination)
            results = playlist['tracks']
            while results:
                for item in results['items']:
                    if item['track'] and item['track']['type'] == 'track':
                        track = item['track']
                        track_info = {
                            'name': track['name'],
                            'artist': ', '.join([artist['name'] for artist in track['artists']]),
                            'album': track['album']['name'],
                            'duration': track['duration_ms'] // 1000,
                            'external_url': track['external_urls']['spotify']
                        }
                        playlist_info['tracks'].append(track_info)
                
                # Get next page
                results = self.spotify.next(results) if results['next'] else None
                
                # Limit to 100 tracks to avoid excessive processing
                if len(playlist_info['tracks']) >= 100:
                    break
            
            return playlist_info
            
        except Exception as e:
            logger.error(f"Error fetching playlist {playlist_id}: {e}")
            raise

    async def get_album_tracks(self, album_id):
        """Get all tracks from an album"""
        try:
            album = self.spotify.album(album_id)
            
            album_info = {
                'type': 'playlist',  # Treat album as playlist
                'name': album['name'],
                'description': f"Album by {', '.join([artist['name'] for artist in album['artists']])}",
                'total_tracks': album['total_tracks'],
                'tracks': []
            }
            
            # Get all tracks from album
            results = album['tracks']
            while results:
                for track in results['items']:
                    track_info = {
                        'name': track['name'],
                        'artist': ', '.join([artist['name'] for artist in track['artists']]),
                        'album': album['name'],
                        'duration': track['duration_ms'] // 1000,
                        'external_url': track['external_urls']['spotify']
                    }
                    album_info['tracks'].append(track_info)
                
                # Get next page
                results = self.spotify.next(results) if results['next'] else None
            
            return album_info
            
        except Exception as e:
            logger.error(f"Error fetching album {album_id}: {e}")
            raise

    def search_track(self, query, limit=1):
        """Search for tracks on Spotify"""
        if not self.spotify:
            return None
        
        try:
            results = self.spotify.search(q=query, type='track', limit=limit)
            tracks = []
            
            for track in results['tracks']['items']:
                track_info = {
                    'name': track['name'],
                    'artist': ', '.join([artist['name'] for artist in track['artists']]),
                    'album': track['album']['name'],
                    'duration': track['duration_ms'] // 1000,
                    'external_url': track['external_urls']['spotify']
                }
                tracks.append(track_info)
            
            return tracks
            
        except Exception as e:
            logger.error(f"Error searching for track: {e}")
            return None
