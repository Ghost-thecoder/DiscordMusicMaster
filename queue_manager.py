from collections import deque
import logging

logger = logging.getLogger(__name__)

class QueueManager:
    def __init__(self):
        self.queue = deque()
        self.current_song = None
        self.history = deque(maxlen=10)  # Keep last 10 played songs

    def add_song(self, song_info):
        """Add a song to the queue"""
        self.queue.append(song_info)
        logger.info(f"Added song to queue: {song_info['title']}")

    def get_next_song(self):
        """Get the next song from the queue"""
        if self.queue:
            if self.current_song:
                self.history.appendleft(self.current_song)
            
            self.current_song = self.queue.popleft()
            logger.info(f"Playing next song: {self.current_song['title']}")
            return self.current_song
        
        return None

    def get_current_song(self):
        """Get the currently playing song"""
        return self.current_song

    def get_queue_list(self):
        """Get a list of upcoming songs"""
        return list(self.queue)

    def is_empty(self):
        """Check if the queue is empty"""
        return len(self.queue) == 0

    def clear(self):
        """Clear the entire queue"""
        self.queue.clear()
        self.current_song = None
        logger.info("Queue cleared")

    def remove_song(self, index):
        """Remove a song at specific index"""
        if 0 <= index < len(self.queue):
            removed_song = self.queue[index]
            del self.queue[index]
            logger.info(f"Removed song: {removed_song['title']}")
            return removed_song
        return None

    def get_queue_length(self):
        """Get the number of songs in queue"""
        return len(self.queue)

    def get_history(self):
        """Get the history of played songs"""
        return list(self.history)

    def shuffle(self):
        """Shuffle the queue"""
        import random
        queue_list = list(self.queue)
        random.shuffle(queue_list)
        self.queue = deque(queue_list)
        logger.info("Queue shuffled")

    def move_song(self, from_index, to_index):
        """Move a song from one position to another"""
        if 0 <= from_index < len(self.queue) and 0 <= to_index < len(self.queue):
            queue_list = list(self.queue)
            song = queue_list.pop(from_index)
            queue_list.insert(to_index, song)
            self.queue = deque(queue_list)
            logger.info(f"Moved song from position {from_index} to {to_index}")
            return True
        return False
