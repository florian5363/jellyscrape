from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
import requests
import sqlite3
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

# Store the last sync timestamp per library
last_sync_times = {}

def init_scheduler(app, jellyfin_url, api_key, db_path="library.db"):
    """
    Initialize the background scheduler for Jellyfin syncing
    
    Args:
        app: Flask app instance
        jellyfin_url: Your Jellyfin server URL
        api_key: Your Jellyfin API key
        db_path: Path to SQLite database
    """
    scheduler = BackgroundScheduler()
    
    # Add the sync job to run every 5 minutes
    scheduler.add_job(
        func=sync_jellyfin_library,
        trigger=IntervalTrigger(minutes=5),
        id='jellyfin_sync',
        name='Sync Jellyfin Library',
        replace_existing=True,
        args=[jellyfin_url, api_key, db_path]
    )
    
    scheduler.start()
    logger.info("Jellyfin sync scheduler started - will check every 5 minutes")
    
    # Shut down the scheduler when the app terminates
    if not app.debug or os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
        import atexit
        atexit.register(lambda: scheduler.shutdown())


def sync_jellyfin_library(jellyfin_url, api_key, db_path="library.db", include_specials=False):
    """
    Sync Jellyfin library and update database with new items
    
    Args:
        jellyfin_url: Your Jellyfin server URL
        api_key: Your Jellyfin API key
        db_path: Path to SQLite database
        include_specials: If True, include Season 0 (specials)
    """
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("PRAGMA foreign_keys = ON;")
        
        headers = {"X-Emby-Token": api_key}
        
        # Get all libraries
        libraries_url = f"{jellyfin_url}/Library/VirtualFolders"
        response = requests.get(libraries_url, headers=headers, timeout=10)
        response.raise_for_status()
        libraries = response.json()
        
        sync_timestamp = datetime.now()
        
        for library in libraries:
            collection_type = library.get("CollectionType", "unknown")
            library_name = library.get("Name")
            library_jellyfin_id = library.get("ItemId")
            
            # Get or create library in DB
            cursor.execute(
                "INSERT OR IGNORE INTO libraries (name, jellyfin_id, collection_type) VALUES (?, ?, ?)",
                (library_name, library_jellyfin_id, collection_type)
            )
            conn.commit()
            
            cursor.execute("SELECT id FROM libraries WHERE name = ?", (library_name,))
            library_db_id = cursor.fetchone()[0]
            
            # Sync based on collection type
            if collection_type == "tvshows":
                sync_tv_shows(jellyfin_url, headers, library_jellyfin_id, library_db_id, cursor, conn, include_specials)
            
            elif collection_type == "movies":
                sync_movies(jellyfin_url, headers, library_jellyfin_id, library_db_id, cursor, conn)
            
            elif collection_type == "music":
                sync_music(jellyfin_url, headers, library_jellyfin_id, library_db_id, cursor, conn)
            
            elif collection_type == "books":
                sync_books(jellyfin_url, headers, library_jellyfin_id, library_db_id, cursor, conn)
            
            elif collection_type == "musicvideos":
                sync_music_videos(jellyfin_url, headers, library_jellyfin_id, library_db_id, cursor, conn)
        
        conn.close()
        logger.info(f"✓ Jellyfin library synced successfully at {sync_timestamp}")
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Error syncing Jellyfin library: {e}")
    except Exception as e:
        logger.error(f"Unexpected error during sync: {e}")
        import traceback
        traceback.print_exc()


def sync_tv_shows(jellyfin_url, headers, library_jellyfin_id, library_db_id, cursor, conn, include_specials):
    """Sync TV shows, seasons, and episodes - only adds new items"""
    items_url = f"{jellyfin_url}/Items"
    params = {
        "IncludeItemTypes": "Series",
        "Recursive": "true",
        "ParentId": library_jellyfin_id,
        "Fields": "Path"
    }
    
    response = requests.get(items_url, headers=headers, params=params, timeout=10)
    response.raise_for_status()
    shows_data = response.json()
    
    new_shows = 0
    new_episodes = 0
    
    for show in shows_data.get("Items", []):
        show_id = show.get("Id")
        show_title = show.get("Name")
        
        # Check if show already exists
        cursor.execute("SELECT id FROM shows WHERE show_id = ?", (show_id,))
        show_result = cursor.fetchone()
        
        if show_result is None:
            cursor.execute(
                "INSERT INTO shows (show_id, title, library_id) VALUES (?, ?, ?)",
                (show_id, show_title, library_db_id)
            )
            new_shows += 1
            show_db_id = cursor.lastrowid
        else:
            show_db_id = show_result[0]
        
        # Get seasons
        seasons_url = f"{jellyfin_url}/Shows/{show_id}/Seasons"
        response = requests.get(seasons_url, headers=headers, timeout=10)
        response.raise_for_status()
        seasons_data = response.json()
        
        for season in seasons_data.get("Items", []):
            season_id = season.get("Id")
            season_number = season.get("IndexNumber")
            
            if season_number is None or (season_number == 0 and not include_specials):
                continue
            
            cursor.execute(
                "INSERT OR IGNORE INTO seasons (season_id, season_number, show_id) VALUES (?, ?, ?)",
                (season_id, season_number, show_db_id)
            )
            
            cursor.execute("SELECT id FROM seasons WHERE season_id = ?", (season_id,))
            season_result = cursor.fetchone()
            if season_result is None:
                continue
            season_db_id = season_result[0]
            
            # Get episodes
            episodes_url = f"{jellyfin_url}/Shows/{show_id}/Episodes"
            params = {"SeasonId": season_id, "Fields": "Path"}
            response = requests.get(episodes_url, headers=headers, params=params, timeout=10)
            response.raise_for_status()
            episodes_data = response.json()
            
            for episode in episodes_data.get("Items", []):
                episode_id = episode.get("Id")
                episode_number = episode.get("IndexNumber")
                episode_title = episode.get("Name", "Unknown Episode")
                file_path = episode.get("Path")
                
                if episode_number is None or episode_number == 0:
                    continue
                
                # Check if episode already exists
                cursor.execute("SELECT id FROM episodes WHERE episode_id = ?", (episode_id,))
                if cursor.fetchone() is None:
                    cursor.execute(
                        "INSERT OR IGNORE INTO episodes (episode_id, episode_number, title, file_path, season_id) VALUES (?, ?, ?, ?, ?)",
                        (episode_id, episode_number, episode_title, file_path, season_db_id)
                    )
                    new_episodes += 1
        
        conn.commit()
    
    if new_shows > 0 or new_episodes > 0:
        logger.info(f"TV Shows: Added {new_shows} new shows, {new_episodes} new episodes")


def sync_movies(jellyfin_url, headers, library_jellyfin_id, library_db_id, cursor, conn):
    """Sync movies - only adds new items"""
    items_url = f"{jellyfin_url}/Items"
    params = {
        "IncludeItemTypes": "Movie",
        "Recursive": "true",
        "ParentId": library_jellyfin_id,
        "Fields": "Path"
    }
    
    response = requests.get(items_url, headers=headers, params=params, timeout=10)
    response.raise_for_status()
    movies_data = response.json()
    
    new_movies = 0
    
    for movie in movies_data.get("Items", []):
        movie_id = movie.get("Id")
        movie_title = movie.get("Name")
        file_path = movie.get("Path")
        
        if not file_path:
            continue
        
        # Check if movie already exists
        cursor.execute("SELECT id FROM movies WHERE movie_id = ?", (movie_id,))
        if cursor.fetchone() is None:
            cursor.execute(
                "INSERT INTO movies (movie_id, title, file_path, library_id) VALUES (?, ?, ?, ?)",
                (movie_id, movie_title, file_path, library_db_id)
            )
            new_movies += 1
    
    conn.commit()
    
    if new_movies > 0:
        logger.info(f"Movies: Added {new_movies} new movies")


def sync_music(jellyfin_url, headers, library_jellyfin_id, library_db_id, cursor, conn):
    """Sync music albums and tracks - only adds new items"""
    items_url = f"{jellyfin_url}/Items"
    params = {
        "IncludeItemTypes": "MusicAlbum",
        "Recursive": "true",
        "ParentId": library_jellyfin_id
    }
    
    response = requests.get(items_url, headers=headers, params=params, timeout=10)
    response.raise_for_status()
    albums_data = response.json()
    
    new_albums = 0
    new_tracks = 0
    
    for album in albums_data.get("Items", []):
        album_id = album.get("Id")
        album_title = album.get("Name")
        
        # Check if album already exists
        cursor.execute("SELECT id FROM music_albums WHERE album_id = ?", (album_id,))
        album_result = cursor.fetchone()
        
        if album_result is None:
            cursor.execute(
                "INSERT INTO music_albums (album_id, title, library_id) VALUES (?, ?, ?)",
                (album_id, album_title, library_db_id)
            )
            new_albums += 1
            album_db_id = cursor.lastrowid
        else:
            album_db_id = album_result[0]
        
        # Get tracks
        tracks_url = f"{jellyfin_url}/Items"
        params = {
            "IncludeItemTypes": "Audio",
            "ParentId": album_id,
            "SortBy": "SortName"
        }
        response = requests.get(tracks_url, headers=headers, params=params, timeout=10)
        response.raise_for_status()
        tracks_data = response.json()
        
        for track in tracks_data.get("Items", []):
            track_id = track.get("Id")
            track_title = track.get("Name")
            track_number = track.get("IndexNumber")
            
            # Check if track already exists
            cursor.execute("SELECT id FROM music_tracks WHERE track_id = ?", (track_id,))
            if cursor.fetchone() is None:
                cursor.execute(
                    "INSERT INTO music_tracks (track_id, title, track_number, album_id) VALUES (?, ?, ?, ?)",
                    (track_id, track_title, track_number, album_db_id)
                )
                new_tracks += 1
        
        conn.commit()
    
    if new_albums > 0 or new_tracks > 0:
        logger.info(f"Music: Added {new_albums} new albums, {new_tracks} new tracks")


def sync_books(jellyfin_url, headers, library_jellyfin_id, library_db_id, cursor, conn):
    """Sync book collections and books - only adds new items"""
    items_url = f"{jellyfin_url}/Items"
    params = {
        "IncludeItemTypes": "Folder",
        "Recursive": "false",
        "ParentId": library_jellyfin_id
    }
    
    response = requests.get(items_url, headers=headers, params=params, timeout=10)
    response.raise_for_status()
    collections_data = response.json()
    
    new_collections = 0
    new_books = 0
    
    for collection in collections_data.get("Items", []):
        collection_id = collection.get("Id")
        collection_title = collection.get("Name")
        
        # Check if collection already exists
        cursor.execute("SELECT id FROM book_collections WHERE collection_id = ?", (collection_id,))
        collection_result = cursor.fetchone()
        
        if collection_result is None:
            cursor.execute(
                "INSERT INTO book_collections (collection_id, title, library_id) VALUES (?, ?, ?)",
                (collection_id, collection_title, library_db_id)
            )
            new_collections += 1
            collection_db_id = cursor.lastrowid
        else:
            collection_db_id = collection_result[0]
        
        # Get books in this collection
        books_url = f"{jellyfin_url}/Items"
        params = {
            "IncludeItemTypes": "Book",
            "ParentId": collection_id
        }
        response = requests.get(books_url, headers=headers, params=params, timeout=10)
        response.raise_for_status()
        books_data = response.json()
        
        for book in books_data.get("Items", []):
            book_id = book.get("Id")
            book_title = book.get("Name")
            
            # Check if book already exists
            cursor.execute("SELECT id FROM books WHERE book_id = ?", (book_id,))
            if cursor.fetchone() is None:
                cursor.execute(
                    "INSERT INTO books (book_id, title, collection_id) VALUES (?, ?, ?)",
                    (book_id, book_title, collection_db_id)
                )
                new_books += 1
        
        conn.commit()
    
    if new_collections > 0 or new_books > 0:
        logger.info(f"Books: Added {new_collections} new collections, {new_books} new books")


def sync_music_videos(jellyfin_url, headers, library_jellyfin_id, library_db_id, cursor, conn):
    """Sync music video folders and videos - only adds new items"""
    items_url = f"{jellyfin_url}/Items"
    params = {
        "IncludeItemTypes": "Folder",
        "Recursive": "false",
        "ParentId": library_jellyfin_id
    }
    
    response = requests.get(items_url, headers=headers, params=params, timeout=10)
    response.raise_for_status()
    folders_data = response.json()
    
    new_folders = 0
    new_videos = 0
    
    for folder in folders_data.get("Items", []):
        folder_id = folder.get("Id")
        folder_title = folder.get("Name")
        
        # Check if folder already exists
        cursor.execute("SELECT id FROM music_video_folders WHERE folder_id = ?", (folder_id,))
        folder_result = cursor.fetchone()
        
        if folder_result is None:
            cursor.execute(
                "INSERT INTO music_video_folders (folder_id, title, library_id) VALUES (?, ?, ?)",
                (folder_id, folder_title, library_db_id)
            )
            new_folders += 1
            folder_db_id = cursor.lastrowid
        else:
            folder_db_id = folder_result[0]
        
        # Get videos in this folder
        videos_url = f"{jellyfin_url}/Items"
        params = {
            "IncludeItemTypes": "MusicVideo",
            "ParentId": folder_id
        }
        response = requests.get(videos_url, headers=headers, params=params, timeout=10)
        response.raise_for_status()
        videos_data = response.json()
        
        for video in videos_data.get("Items", []):
            video_id = video.get("Id")
            video_title = video.get("Name")
            
            # Check if video already exists
            cursor.execute("SELECT id FROM music_videos WHERE video_id = ?", (video_id,))
            if cursor.fetchone() is None:
                cursor.execute(
                    "INSERT INTO music_videos (video_id, title, folder_id) VALUES (?, ?, ?)",
                    (video_id, video_title, folder_db_id)
                )
                new_videos += 1
        
        conn.commit()
    
    if new_folders > 0 or new_videos > 0:
        logger.info(f"Music Videos: Added {new_folders} new folders, {new_videos} new videos")