import sqlite3
from typing import Optional

def view_all_libraries(db_path="library.db"):
    """Display all libraries in the database"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT l.id, l.name, l.collection_type, COUNT(DISTINCT s.id) as item_count
        FROM libraries l
        LEFT JOIN shows s ON l.id = s.library_id
        GROUP BY l.id, l.name, l.collection_type
        ORDER BY l.name
    """)
    
    libraries = cursor.fetchall()
    conn.close()
    
    if not libraries:
        print("No libraries found in database.")
        return
    
    print("\n" + "="*80)
    print("LIBRARIES")
    print("="*80)
    for lib_id, name, coll_type, item_count in libraries:
        print(f"ID: {lib_id} | {name} ({coll_type}) - {item_count} items")
    print("="*80)


def view_library_shows(library_id: Optional[int] = None, db_path="library.db"):
    """Display all shows, optionally filtered by library"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    if library_id:
        cursor.execute("""
            SELECT s.id, s.title, l.name, COUNT(DISTINCT se.id) as season_count,
                   COUNT(e.id) as episode_count
            FROM shows s
            JOIN libraries l ON s.library_id = l.id
            LEFT JOIN seasons se ON s.id = se.show_id
            LEFT JOIN episodes e ON se.id = e.season_id
            WHERE s.library_id = ?
            GROUP BY s.id, s.title, l.name
            ORDER BY s.title
        """, (library_id,))
    else:
        cursor.execute("""
            SELECT s.id, s.title, l.name, COUNT(DISTINCT se.id) as season_count,
                   COUNT(e.id) as episode_count
            FROM shows s
            JOIN libraries l ON s.library_id = l.id
            LEFT JOIN seasons se ON s.id = se.show_id
            LEFT JOIN episodes e ON se.id = e.season_id
            GROUP BY s.id, s.title, l.name
            ORDER BY s.title
        """)
    
    shows = cursor.fetchall()
    conn.close()
    
    if not shows:
        print("No shows found.")
        return
    
    print("\n" + "="*80)
    print("TV SHOWS")
    print("="*80)
    for show_id, title, library_name, season_count, episode_count in shows:
        print(f"ID: {show_id} | {title}")
        print(f"  Library: {library_name} | Seasons: {season_count} | Episodes: {episode_count}")
    print("="*80)


def view_show_details(show_id: int, db_path="library.db"):
    """Display detailed information about a specific show"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT s.title, l.name
        FROM shows s
        JOIN libraries l ON s.library_id = l.id
        WHERE s.id = ?
    """, (show_id,))
    
    show_info = cursor.fetchone()
    if not show_info:
        print(f"Show with ID {show_id} not found.")
        conn.close()
        return
    
    show_title, library_name = show_info
    
    # Get seasons and episodes with file paths
    cursor.execute("""
        SELECT se.season_number, COUNT(e.id) as episode_count,
               COUNT(CASE WHEN e.file_path IS NOT NULL THEN 1 END) as with_paths
        FROM seasons se
        LEFT JOIN episodes e ON se.id = e.season_id
        WHERE se.show_id = ?
        GROUP BY se.id, se.season_number
        ORDER BY se.season_number
    """, (show_id,))
    
    seasons = cursor.fetchall()
    conn.close()
    
    print("\n" + "="*80)
    print(f"SHOW DETAILS: {show_title}")
    print("="*80)
    print(f"Library: {library_name}")
    print(f"Total Seasons: {len(seasons)}")
    print("\nSeasons:")
    
    total_episodes = 0
    total_with_paths = 0
    for season_num, episode_count, with_paths in seasons:
        print(f"  Season {season_num}: {episode_count} episodes ({with_paths} with file paths)")
        total_episodes += episode_count
        total_with_paths += with_paths
    
    print(f"\nTotal Episodes: {total_episodes}")
    print(f"Episodes with file paths: {total_with_paths}/{total_episodes}")
    print("="*80)


def view_season_episodes(show_id: int, season_number: int, db_path="library.db"):
    """Display all episodes in a specific season with file paths"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT s.title, se.id
        FROM shows s
        JOIN seasons se ON s.id = se.show_id
        WHERE s.id = ? AND se.season_number = ?
    """, (show_id, season_number))
    
    result = cursor.fetchone()
    if not result:
        print(f"Season {season_number} not found for show ID {show_id}.")
        conn.close()
        return
    
    show_title, season_id = result
    
    cursor.execute("""
        SELECT episode_number, title, file_path
        FROM episodes
        WHERE season_id = ?
        ORDER BY episode_number
    """, (season_id,))
    
    episodes = cursor.fetchall()
    conn.close()
    
    print("\n" + "="*80)
    print(f"{show_title} - Season {season_number}")
    print("="*80)
    
    if not episodes:
        print("No episodes found.")
    else:
        for ep_num, ep_title, file_path in episodes:
            print(f"  Episode {ep_num}: {ep_title}")
            if file_path:
                print(f"    Path: {file_path}")
            else:
                print(f"    Path: [Not stored]")
    
    print("="*80)


def view_movies(library_id: Optional[int] = None, db_path="library.db"):
    """Display movies"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    if library_id:
        cursor.execute("""
            SELECT m.id, m.title, l.name, m.file_path
            FROM movies m
            JOIN libraries l ON m.library_id = l.id
            WHERE m.library_id = ?
            ORDER BY m.title
        """, (library_id,))
    else:
        cursor.execute("""
            SELECT m.id, m.title, l.name, m.file_path
            FROM movies m
            JOIN libraries l ON m.library_id = l.id
            ORDER BY m.title
        """)
    
    movies = cursor.fetchall()
    conn.close()
    
    if not movies:
        print("No movies found.")
        return
    
    print("\n" + "="*80)
    print("MOVIES")
    print("="*80)
    for movie_id, title, library_name, file_path in movies:
        print(f"ID: {movie_id} | {title}")
        print(f"  Library: {library_name}")
        if file_path:
            print(f"  Path: {file_path}")
    print("="*80)


def view_statistics(db_path="library.db"):
    """Display overall database statistics"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM libraries")
    library_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM shows")
    show_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM seasons")
    season_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM episodes")
    episode_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM episodes WHERE file_path IS NOT NULL")
    episodes_with_path = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM movies")
    movie_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM movies WHERE file_path IS NOT NULL")
    movies_with_path = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM music_albums")
    album_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM music_tracks")
    track_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM book_collections")
    book_collection_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM books")
    book_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM music_video_folders")
    mv_folder_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM music_videos")
    mv_count = cursor.fetchone()[0]
    
    conn.close()
    
    print("\n" + "="*80)
    print("DATABASE STATISTICS")
    print("="*80)
    print(f"Libraries: {library_count}")
    print("\nTV Shows:")
    print(f"  Shows: {show_count}")
    print(f"  Seasons: {season_count}")
    print(f"  Episodes: {episode_count} ({episodes_with_path} with file paths)")
    print("\nMovies:")
    print(f"  Total: {movie_count} ({movies_with_path} with file paths)")
    print("\nMusic:")
    print(f"  Albums: {album_count}")
    print(f"  Tracks: {track_count}")
    print("\nBooks:")
    print(f"  Collections: {book_collection_count}")
    print(f"  Books: {book_count}")
    print("\nMusic Videos:")
    print(f"  Folders: {mv_folder_count}")
    print(f"  Videos: {mv_count}")
    print("="*80)


def interactive_menu(db_path="library.db"):
    """Interactive menu for browsing the database"""
    while True:
        print("\n" + "="*80)
        print("JELLYFIN LIBRARY VIEWER")
        print("="*80)
        print("1. View all libraries")
        print("2. View all TV shows")
        print("3. View show details")
        print("4. View season episodes (with file paths)")
        print("5. View movies")
        print("6. View statistics")
        print("7. Exit")
        print("="*80)
        
        choice = input("\nEnter your choice (1-7): ").strip()
        
        if choice == "1":
            view_all_libraries(db_path)
        
        elif choice == "2":
            view_library_shows(db_path=db_path)
        
        elif choice == "3":
            try:
                show_id = int(input("Enter show ID: ").strip())
                view_show_details(show_id, db_path)
            except ValueError:
                print("Invalid show ID. Please enter a number.")
        
        elif choice == "4":
            try:
                show_id = int(input("Enter show ID: ").strip())
                season_num = int(input("Enter season number: ").strip())
                view_season_episodes(show_id, season_num, db_path)
            except ValueError:
                print("Invalid input. Please enter numbers.")
        
        elif choice == "5":
            view_movies(db_path=db_path)
        
        elif choice == "6":
            view_statistics(db_path)
        
        elif choice == "7":
            print("\nGoodbye!")
            break
        
        else:
            print("Invalid choice. Please enter a number between 1 and 7.")


if __name__ == "__main__":
    import os
    
    db_path = "library.db"
    
    if not os.path.exists(db_path):
        print(f"Error: Database file '{db_path}' not found.")
        print("Please run the import script first to create the database.")
        exit(1)
    
    interactive_menu(db_path)
