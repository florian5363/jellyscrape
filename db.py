import sqlite3
import requests
import os

def init_db(db_path="library.db", force_recreate=False):
    """
    Initialize the database schema for all media types
    
    Args:
        db_path: Path to SQLite database
        force_recreate: If True, delete existing database and create fresh
    """
    if force_recreate and os.path.exists(db_path):
        os.remove(db_path)
        print(f"Removed existing database: {db_path}")
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Enable foreign key support
    cursor.execute("PRAGMA foreign_keys = ON;")
    
    # Libraries table with collection type
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS libraries (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        jellyfin_id TEXT UNIQUE,
        collection_type TEXT NOT NULL
    );
    """)
    
    # TV Shows tables
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS shows (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        show_id TEXT NOT NULL UNIQUE,
        title TEXT NOT NULL,
        library_id INTEGER NOT NULL,
        FOREIGN KEY (library_id)
            REFERENCES libraries(id)
            ON DELETE CASCADE
    );
    """)
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS seasons (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        season_id TEXT NOT NULL UNIQUE,
        season_number INTEGER NOT NULL,
        show_id INTEGER NOT NULL,
        UNIQUE(show_id, season_number),
        FOREIGN KEY (show_id)
            REFERENCES shows(id)
            ON DELETE CASCADE
    );
    """)
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS episodes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        episode_id TEXT NOT NULL UNIQUE,
        episode_number INTEGER NOT NULL,
        title TEXT NOT NULL,
        file_path TEXT,
        season_id INTEGER NOT NULL,
        UNIQUE(season_id, episode_number),
        FOREIGN KEY (season_id)
            REFERENCES seasons(id)
            ON DELETE CASCADE
    );
    """)
    
    # Movies table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS movies (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        movie_id TEXT NOT NULL UNIQUE,
        title TEXT NOT NULL,
        file_path TEXT,
        library_id INTEGER NOT NULL,
        FOREIGN KEY (library_id)
            REFERENCES libraries(id)
            ON DELETE CASCADE
    );
    """)
    
    # Music tables
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS music_albums (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        album_id TEXT NOT NULL UNIQUE,
        title TEXT NOT NULL,
        library_id INTEGER NOT NULL,
        FOREIGN KEY (library_id)
            REFERENCES libraries(id)
            ON DELETE CASCADE
    );
    """)
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS music_tracks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        track_id TEXT NOT NULL UNIQUE,
        title TEXT NOT NULL,
        track_number INTEGER,
        album_id INTEGER NOT NULL,
        FOREIGN KEY (album_id)
            REFERENCES music_albums(id)
            ON DELETE CASCADE
    );
    """)
    
    # Books tables
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS book_collections (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        collection_id TEXT NOT NULL UNIQUE,
        title TEXT NOT NULL,
        library_id INTEGER NOT NULL,
        FOREIGN KEY (library_id)
            REFERENCES libraries(id)
            ON DELETE CASCADE
    );
    """)
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS books (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        book_id TEXT NOT NULL UNIQUE,
        title TEXT NOT NULL,
        collection_id INTEGER NOT NULL,
        FOREIGN KEY (collection_id)
            REFERENCES book_collections(id)
            ON DELETE CASCADE
    );
    """)
    
    # Music Videos tables
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS music_video_folders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        folder_id TEXT NOT NULL UNIQUE,
        title TEXT NOT NULL,
        library_id INTEGER NOT NULL,
        FOREIGN KEY (library_id)
            REFERENCES libraries(id)
            ON DELETE CASCADE
    );
    """)
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS music_videos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        video_id TEXT NOT NULL UNIQUE,
        title TEXT NOT NULL,
        folder_id INTEGER NOT NULL,
        FOREIGN KEY (folder_id)
            REFERENCES music_video_folders(id)
            ON DELETE CASCADE
    );
    """)
    
    # Create indexes for common queries
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_shows_library ON shows(library_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_seasons_show ON seasons(show_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_episodes_season ON episodes(season_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_movies_library ON movies(library_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_music_albums_library ON music_albums(library_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_music_tracks_album ON music_tracks(album_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_book_collections_library ON book_collections(library_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_books_collection ON books(collection_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_music_video_folders_library ON music_video_folders(library_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_music_videos_folder ON music_videos(folder_id);")
    
    conn.commit()
    conn.close()
    
    print("Database initialized successfully")

def fetch_jellyfin_data(jellyfin_url, api_key, db_path="library.db", include_specials=False):
    """
    Fetch data from Jellyfin API and populate the database
    
    Args:
        jellyfin_url: Your Jellyfin server URL (e.g., "http://localhost:8096")
        api_key: Your Jellyfin API key
        db_path: Path to SQLite database
        include_specials: If True, include Season 0 (specials). Default False.
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("PRAGMA foreign_keys = ON;")
    
    headers = {
        "X-Emby-Token": api_key
    }
    
    try:
        # Get all libraries
        print("Fetching libraries...")
        libraries_url = f"{jellyfin_url}/Library/VirtualFolders"
        response = requests.get(libraries_url, headers=headers)
        response.raise_for_status()
        libraries = response.json()
        
        for library in libraries:
            collection_type = library.get("CollectionType", "unknown")
            library_name = library.get("Name")
            library_jellyfin_id = library.get("ItemId")
            
            print(f"\nProcessing library: {library_name} (Type: {collection_type})")
            
            # Insert library with collection type
            cursor.execute(
                "INSERT OR IGNORE INTO libraries (name, jellyfin_id, collection_type) VALUES (?, ?, ?)",
                (library_name, library_jellyfin_id, collection_type)
            )
            conn.commit()
            
            # Get library_db_id
            cursor.execute("SELECT id FROM libraries WHERE name = ?", (library_name,))
            library_db_id = cursor.fetchone()[0]
            
            # Process based on collection type
            if collection_type == "tvshows":
                fetch_tv_shows(jellyfin_url, headers, library_jellyfin_id, library_db_id, cursor, conn, include_specials)
            
            elif collection_type == "movies":
                fetch_movies(jellyfin_url, headers, library_jellyfin_id, library_db_id, cursor, conn)
            
            elif collection_type == "music":
                fetch_music(jellyfin_url, headers, library_jellyfin_id, library_db_id, cursor, conn)
            
            elif collection_type == "books":
                fetch_books(jellyfin_url, headers, library_jellyfin_id, library_db_id, cursor, conn)
            
            elif collection_type == "musicvideos":
                fetch_music_videos(jellyfin_url, headers, library_jellyfin_id, library_db_id, cursor, conn)
            
            else:
                print(f"  Skipping unsupported collection type: {collection_type}")
        
        print("\n✓ Data import completed successfully!")
        
    except requests.exceptions.RequestException as e:
        print(f"Error fetching data from Jellyfin: {e}")
        conn.rollback()
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        conn.rollback()
    finally:
        conn.close()


def fetch_tv_shows(jellyfin_url, headers, library_jellyfin_id, library_db_id, cursor, conn, include_specials):
    """Fetch TV shows, seasons, and episodes"""
    items_url = f"{jellyfin_url}/Items"
    params = {
        "IncludeItemTypes": "Series",
        "Recursive": "true",
        "ParentId": library_jellyfin_id,
        "Fields": "Path"
    }
    
    response = requests.get(items_url, headers=headers, params=params)
    response.raise_for_status()
    shows_data = response.json()
    
    print(f"  Found {len(shows_data.get('Items', []))} shows")
    
    for show in shows_data.get("Items", []):
        show_id = show.get("Id")
        show_title = show.get("Name")
        
        print(f"  Processing show: {show_title}")
        
        cursor.execute(
            "INSERT OR IGNORE INTO shows (show_id, title, library_id) VALUES (?, ?, ?)",
            (show_id, show_title, library_db_id)
        )
        conn.commit()
        
        cursor.execute("SELECT id FROM shows WHERE show_id = ?", (show_id,))
        result = cursor.fetchone()
        if result is None:
            continue
        show_db_id = result[0]
        
        # Get seasons
        seasons_url = f"{jellyfin_url}/Shows/{show_id}/Seasons"
        response = requests.get(seasons_url, headers=headers)
        response.raise_for_status()
        seasons_data = response.json()
        
        for season in seasons_data.get("Items", []):
            season_id = season.get("Id")
            season_number = season.get("IndexNumber")
            
            if season_number is None:
                continue
            
            if season_number == 0 and not include_specials:
                continue
            
            cursor.execute(
                "INSERT OR IGNORE INTO seasons (season_id, season_number, show_id) VALUES (?, ?, ?)",
                (season_id, season_number, show_db_id)
            )
            conn.commit()
            
            cursor.execute("SELECT id FROM seasons WHERE season_id = ?", (season_id,))
            result = cursor.fetchone()
            if result is None:
                continue
            season_db_id = result[0]
            
            # Get episodes
            episodes_url = f"{jellyfin_url}/Shows/{show_id}/Episodes"
            params = {"SeasonId": season_id, "Fields": "Path"}
            response = requests.get(episodes_url, headers=headers, params=params)
            response.raise_for_status()
            episodes_data = response.json()
            
            for episode in episodes_data.get("Items", []):
                episode_id = episode.get("Id")
                episode_number = episode.get("IndexNumber")
                episode_title = episode.get("Name", "Unknown Episode")
                file_path = episode.get("Path")  # Get the file path
                
                if episode_number is None or episode_number == 0:
                    continue
                
                cursor.execute(
                    "INSERT OR IGNORE INTO episodes (episode_id, episode_number, title, file_path, season_id) VALUES (?, ?, ?, ?, ?)",
                    (episode_id, episode_number, episode_title, file_path, season_db_id)
                )
            
            conn.commit()


def fetch_movies(jellyfin_url, headers, library_jellyfin_id, library_db_id, cursor, conn):
    """Fetch movies"""
    items_url = f"{jellyfin_url}/Items"
    params = {
        "IncludeItemTypes": "Movie",
        "Recursive": "true",
        "ParentId": library_jellyfin_id,
        "Fields": "Path"
    }
    
    response = requests.get(items_url, headers=headers, params=params)
    response.raise_for_status()
    movies_data = response.json()
    
    print(f"  Found {len(movies_data.get('Items', []))} movies")
    
    for movie in movies_data.get("Items", []):
        movie_id = movie.get("Id")
        movie_title = movie.get("Name")
        file_path = movie.get("Path")
        
        # Skip if no Path (virtual item)
        if not file_path:
            continue
        
        cursor.execute(
            "INSERT OR IGNORE INTO movies (movie_id, title, file_path, library_id) VALUES (?, ?, ?, ?)",
            (movie_id, movie_title, file_path, library_db_id)
        )
    
    conn.commit()


def fetch_music(jellyfin_url, headers, library_jellyfin_id, library_db_id, cursor, conn):
    """Fetch music albums and tracks"""
    items_url = f"{jellyfin_url}/Items"
    params = {
        "IncludeItemTypes": "MusicAlbum",
        "Recursive": "true",
        "ParentId": library_jellyfin_id
    }
    
    response = requests.get(items_url, headers=headers, params=params)
    response.raise_for_status()
    albums_data = response.json()
    
    print(f"  Found {len(albums_data.get('Items', []))} albums")
    
    for album in albums_data.get("Items", []):
        album_id = album.get("Id")
        album_title = album.get("Name")
        
        cursor.execute(
            "INSERT OR IGNORE INTO music_albums (album_id, title, library_id) VALUES (?, ?, ?)",
            (album_id, album_title, library_db_id)
        )
        conn.commit()
        
        cursor.execute("SELECT id FROM music_albums WHERE album_id = ?", (album_id,))
        result = cursor.fetchone()
        if result is None:
            continue
        album_db_id = result[0]
        
        # Get tracks
        tracks_url = f"{jellyfin_url}/Items"
        params = {
            "IncludeItemTypes": "Audio",
            "ParentId": album_id,
            "SortBy": "SortName"
        }
        response = requests.get(tracks_url, headers=headers, params=params)
        response.raise_for_status()
        tracks_data = response.json()
        
        for track in tracks_data.get("Items", []):
            track_id = track.get("Id")
            track_title = track.get("Name")
            track_number = track.get("IndexNumber")
            
            cursor.execute(
                "INSERT OR IGNORE INTO music_tracks (track_id, title, track_number, album_id) VALUES (?, ?, ?, ?)",
                (track_id, track_title, track_number, album_db_id)
            )
        
        conn.commit()


def fetch_books(jellyfin_url, headers, library_jellyfin_id, library_db_id, cursor, conn):
    """Fetch book collections and books"""
    items_url = f"{jellyfin_url}/Items"
    params = {
        "IncludeItemTypes": "Folder",
        "Recursive": "false",
        "ParentId": library_jellyfin_id
    }
    
    response = requests.get(items_url, headers=headers, params=params)
    response.raise_for_status()
    collections_data = response.json()
    
    print(f"  Found {len(collections_data.get('Items', []))} book collections")
    
    for collection in collections_data.get("Items", []):
        collection_id = collection.get("Id")
        collection_title = collection.get("Name")
        
        cursor.execute(
            "INSERT OR IGNORE INTO book_collections (collection_id, title, library_id) VALUES (?, ?, ?)",
            (collection_id, collection_title, library_db_id)
        )
        conn.commit()
        
        cursor.execute("SELECT id FROM book_collections WHERE collection_id = ?", (collection_id,))
        result = cursor.fetchone()
        if result is None:
            continue
        collection_db_id = result[0]
        
        # Get books in this collection
        books_url = f"{jellyfin_url}/Items"
        params = {
            "IncludeItemTypes": "Book",
            "ParentId": collection_id
        }
        response = requests.get(books_url, headers=headers, params=params)
        response.raise_for_status()
        books_data = response.json()
        
        for book in books_data.get("Items", []):
            book_id = book.get("Id")
            book_title = book.get("Name")
            
            cursor.execute(
                "INSERT OR IGNORE INTO books (book_id, title, collection_id) VALUES (?, ?, ?)",
                (book_id, book_title, collection_db_id)
            )
        
        conn.commit()


def fetch_music_videos(jellyfin_url, headers, library_jellyfin_id, library_db_id, cursor, conn):
    """Fetch music video folders and videos"""
    items_url = f"{jellyfin_url}/Items"
    params = {
        "IncludeItemTypes": "Folder",
        "Recursive": "false",
        "ParentId": library_jellyfin_id
    }
    
    response = requests.get(items_url, headers=headers, params=params)
    response.raise_for_status()
    folders_data = response.json()
    
    print(f"  Found {len(folders_data.get('Items', []))} music video folders")
    
    for folder in folders_data.get("Items", []):
        folder_id = folder.get("Id")
        folder_title = folder.get("Name")
        
        cursor.execute(
            "INSERT OR IGNORE INTO music_video_folders (folder_id, title, library_id) VALUES (?, ?, ?)",
            (folder_id, folder_title, library_db_id)
        )
        conn.commit()
        
        cursor.execute("SELECT id FROM music_video_folders WHERE folder_id = ?", (folder_id,))
        result = cursor.fetchone()
        if result is None:
            continue
        folder_db_id = result[0]
        
        # Get videos in this folder
        videos_url = f"{jellyfin_url}/Items"
        params = {
            "IncludeItemTypes": "MusicVideo",
            "ParentId": folder_id
        }
        response = requests.get(videos_url, headers=headers, params=params)
        response.raise_for_status()
        videos_data = response.json()
        
        for video in videos_data.get("Items", []):
            video_id = video.get("Id")
            video_title = video.get("Name")
            
            cursor.execute(
                "INSERT OR IGNORE INTO music_videos (video_id, title, folder_id) VALUES (?, ?, ?)",
                (video_id, video_title, folder_db_id)
            )
        
        conn.commit()


if __name__ == "__main__":
    # Initialize the database (set force_recreate=True to start fresh)
    init_db(force_recreate=True)
    
    # Configure your Jellyfin connection
    JELLYFIN_URL = ""  # Change to your Jellyfin server URL
    API_KEY = ""  # Change to your API key
    
    # Fetch and populate data
    # Set include_specials=True if you want to include Season 0 (specials)
    fetch_jellyfin_data(JELLYFIN_URL, API_KEY, include_specials=False)
