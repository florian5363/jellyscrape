from flask import Flask, render_template, abort, url_for, request, redirect, Response, stream_with_context, send_file, after_this_request
import requests
import json
import sqlite3
from math import ceil
from collections import defaultdict
import mimetypes
from download import (
    download_show_background,
    download_season_background,
    download_episode_background
)

app = Flask(__name__)

DB_FILE = "library.db"
ITEMS_PER_PAGE = 100

with open("data.txt", "r") as file:
    BASE_URL = file.readline().strip()
    API_KEY = file.readline().strip()

# Debug: verify credentials loaded
print(f"Loaded BASE_URL: {BASE_URL}")
print(f"Loaded API_KEY: {API_KEY[:10]}..." if API_KEY else "API_KEY is empty!")


# =====================
# Database Helpers
# =====================

def get_db():
    """Get database connection"""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def get_all_libraries():
    """Get all libraries from database"""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT id, name, jellyfin_id, collection_type
        FROM libraries
        ORDER BY name
    """)
    
    libraries = []
    for row in cursor.fetchall():
        libraries.append({
            'id': row['id'],
            'name': row['name'],
            'jellyfin_id': row['jellyfin_id'],
            'collection_type': row['collection_type']
        })
    
    conn.close()
    return libraries


# =====================
# TV Shows Helpers
# =====================

def get_library_shows(library_id, page=1, items_per_page=100):
    """Get shows for a specific library with pagination"""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT COUNT(*) as total
        FROM shows
        WHERE library_id = ?
    """, (library_id,))
    total = cursor.fetchone()['total']
    
    offset = (page - 1) * items_per_page
    cursor.execute("""
        SELECT s.id, s.show_id, s.title,
               COUNT(DISTINCT se.id) as season_count,
               COUNT(e.id) as episode_count
        FROM shows s
        LEFT JOIN seasons se ON s.id = se.show_id
        LEFT JOIN episodes e ON se.id = e.season_id
        WHERE s.library_id = ?
        GROUP BY s.id, s.show_id, s.title
        ORDER BY s.title
        LIMIT ? OFFSET ?
    """, (library_id, items_per_page, offset))
    
    shows = []
    for row in cursor.fetchall():
        image_url = f"{BASE_URL}/Items/{row['show_id']}/Images/Primary?quality=90&api_key={API_KEY}"
        
        show = {
            'Id': row['show_id'],
            'Name': row['title'],
            'db_id': row['id'],
            'season_count': row['season_count'],
            'episode_count': row['episode_count'],
            'ImageUrl': image_url
        }
        shows.append(show)
    
    conn.close()
    total_pages = ceil(total / items_per_page) if total > 0 else 1
    return shows, total_pages


def get_show_details(show_jellyfin_id):
    """Get show details including seasons"""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT s.id, s.show_id, s.title, l.name as library_name, l.id as library_id
        FROM shows s
        JOIN libraries l ON s.library_id = l.id
        WHERE s.show_id = ?
    """, (show_jellyfin_id,))
    
    show_row = cursor.fetchone()
    if not show_row:
        conn.close()
        return None, None, None
    
    show = {
        'Id': show_row['show_id'],
        'Name': show_row['title'],
        'db_id': show_row['id'],
        'library_name': show_row['library_name'],
        'library_id': show_row['library_id']
    }
    
    cursor.execute("""
        SELECT se.id, se.season_id, se.season_number,
               COUNT(e.id) as episode_count
        FROM seasons se
        LEFT JOIN episodes e ON se.id = e.season_id
        WHERE se.show_id = ?
        GROUP BY se.id, se.season_id, se.season_number
        ORDER BY se.season_number
    """, (show_row['id'],))
    
    seasons = []
    for row in cursor.fetchall():
        image_url = f"{BASE_URL}/Items/{row['season_id']}/Images/Primary?quality=90&api_key={API_KEY}"
        
        season = {
            'Id': row['season_id'],
            'db_id': row['id'],
            'IndexNumber': row['season_number'],
            'Name': f"Season {row['season_number']}",
            'episode_count': row['episode_count'],
            'ImageUrl': image_url
        }
        seasons.append(season)
    
    conn.close()
    return show, seasons, show_row['library_name']


def get_season_details(season_jellyfin_id):
    """Get season details including episodes"""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT se.id, se.season_id, se.season_number,
               s.show_id, s.title as show_title, s.id as show_db_id,
               l.name as library_name
        FROM seasons se
        JOIN shows s ON se.show_id = s.id
        JOIN libraries l ON s.library_id = l.id
        WHERE se.season_id = ?
    """, (season_jellyfin_id,))
    
    season_row = cursor.fetchone()
    if not season_row:
        conn.close()
        return None, None, None, None
    
    season = {
        'Id': season_row['season_id'],
        'db_id': season_row['id'],
        'IndexNumber': season_row['season_number'],
        'Name': f"Season {season_row['season_number']}",
        'show_id': season_row['show_id'],
        'show_title': season_row['show_title']
    }
    
    cursor.execute("""
        SELECT episode_id, episode_number, title
        FROM episodes
        WHERE season_id = ?
        ORDER BY episode_number
    """, (season_row['id'],))
    
    episodes = []
    for row in cursor.fetchall():
        image_url = f"{BASE_URL}/Items/{row['episode_id']}/Images/Primary?quality=90&api_key={API_KEY}"
        
        episode = {
            'Id': row['episode_id'],
            'IndexNumber': row['episode_number'],
            'Name': row['title'],
            'ImageUrl': image_url
        }
        episodes.append(episode)
    
    conn.close()
    return season, episodes, season_row['library_name'], season_row['show_id']


# =====================
# Movies Helpers
# =====================

def get_library_movies(library_id, page=1, items_per_page=100):
    """Get movies for a specific library with pagination"""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT COUNT(*) as total
        FROM movies
        WHERE library_id = ?
    """, (library_id,))
    total = cursor.fetchone()['total']
    
    offset = (page - 1) * items_per_page
    cursor.execute("""
        SELECT movie_id, title
        FROM movies
        WHERE library_id = ?
        ORDER BY title
        LIMIT ? OFFSET ?
    """, (library_id, items_per_page, offset))
    
    movies = []
    for row in cursor.fetchall():
        image_url = f"{BASE_URL}/Items/{row['movie_id']}/Images/Primary?quality=90&api_key={API_KEY}"
        
        movie = {
            'Id': row['movie_id'],
            'Name': row['title'],
            'ImageUrl': image_url
        }
        movies.append(movie)
    
    conn.close()
    total_pages = ceil(total / items_per_page) if total > 0 else 1
    return movies, total_pages


# =====================
# Music Helpers
# =====================

def get_library_albums(library_id, page=1, items_per_page=100):
    """Get music albums for a specific library with pagination"""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT COUNT(*) as total
        FROM music_albums
        WHERE library_id = ?
    """, (library_id,))
    total = cursor.fetchone()['total']
    
    offset = (page - 1) * items_per_page
    cursor.execute("""
        SELECT album_id, title
        FROM music_albums
        WHERE library_id = ?
        ORDER BY title
        LIMIT ? OFFSET ?
    """, (library_id, items_per_page, offset))
    
    albums = []
    for row in cursor.fetchall():
        image_url = f"{BASE_URL}/Items/{row['album_id']}/Images/Primary?quality=90&api_key={API_KEY}"
        
        album = {
            'Id': row['album_id'],
            'Name': row['title'],
            'ImageUrl': image_url
        }
        albums.append(album)
    
    conn.close()
    total_pages = ceil(total / items_per_page) if total > 0 else 1
    return albums, total_pages


def get_album_tracks(album_jellyfin_id):
    """Get tracks for a specific album"""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT ma.album_id, ma.title, l.name as library_name
        FROM music_albums ma
        JOIN libraries l ON ma.library_id = l.id
        WHERE ma.album_id = ?
    """, (album_jellyfin_id,))
    
    album_row = cursor.fetchone()
    if not album_row:
        conn.close()
        return None, None, None
    
    album = {
        'Id': album_row['album_id'],
        'Name': album_row['title']
    }
    
    cursor.execute("""
        SELECT mt.track_id, mt.title, mt.track_number
        FROM music_tracks mt
        JOIN music_albums ma ON mt.album_id = ma.id
        WHERE ma.album_id = ?
        ORDER BY mt.track_number
    """, (album_jellyfin_id,))
    
    tracks = []
    for row in cursor.fetchall():
        track = {
            'Id': row['track_id'],
            'Name': row['title'],
            'IndexNumber': row['track_number']
        }
        tracks.append(track)
    
    conn.close()
    return album, tracks, album_row['library_name']


# =====================
# Books Helpers
# =====================

def get_library_book_collections(library_id, page=1, items_per_page=100):
    """Get book collections for a specific library with pagination"""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT COUNT(*) as total
        FROM book_collections
        WHERE library_id = ?
    """, (library_id,))
    total = cursor.fetchone()['total']
    
    offset = (page - 1) * items_per_page
    cursor.execute("""
        SELECT collection_id, title
        FROM book_collections
        WHERE library_id = ?
        ORDER BY title
        LIMIT ? OFFSET ?
    """, (library_id, items_per_page, offset))
    
    collections = []
    for row in cursor.fetchall():
        image_url = f"{BASE_URL}/Items/{row['collection_id']}/Images/Primary?quality=90&api_key={API_KEY}"
        
        collection = {
            'Id': row['collection_id'],
            'Name': row['title'],
            'ImageUrl': image_url
        }
        collections.append(collection)
    
    conn.close()
    total_pages = ceil(total / items_per_page) if total > 0 else 1
    return collections, total_pages


def get_collection_books(collection_jellyfin_id):
    """Get books for a specific collection"""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT bc.collection_id, bc.title, l.name as library_name
        FROM book_collections bc
        JOIN libraries l ON bc.library_id = l.id
        WHERE bc.collection_id = ?
    """, (collection_jellyfin_id,))
    
    collection_row = cursor.fetchone()
    if not collection_row:
        conn.close()
        return None, None, None
    
    collection = {
        'Id': collection_row['collection_id'],
        'Name': collection_row['title']
    }
    
    cursor.execute("""
        SELECT b.book_id, b.title
        FROM books b
        JOIN book_collections bc ON b.collection_id = bc.id
        WHERE bc.collection_id = ?
        ORDER BY b.title
    """, (collection_jellyfin_id,))
    
    books = []
    for row in cursor.fetchall():
        image_url = f"{BASE_URL}/Items/{row['book_id']}/Images/Primary?quality=90&api_key={API_KEY}"
        
        book = {
            'Id': row['book_id'],
            'Name': row['title'],
            'ImageUrl': image_url
        }
        books.append(book)
    
    conn.close()
    return collection, books, collection_row['library_name']


# =====================
# Music Videos Helpers
# =====================

def get_library_music_video_folders(library_id, page=1, items_per_page=100):
    """Get music video folders for a specific library with pagination"""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT COUNT(*) as total
        FROM music_video_folders
        WHERE library_id = ?
    """, (library_id,))
    total = cursor.fetchone()['total']
    
    offset = (page - 1) * items_per_page
    cursor.execute("""
        SELECT folder_id, title
        FROM music_video_folders
        WHERE library_id = ?
        ORDER BY title
        LIMIT ? OFFSET ?
    """, (library_id, items_per_page, offset))
    
    folders = []
    for row in cursor.fetchall():
        image_url = f"{BASE_URL}/Items/{row['folder_id']}/Images/Primary?quality=90&api_key={API_KEY}"
        
        folder = {
            'Id': row['folder_id'],
            'Name': row['title'],
            'ImageUrl': image_url
        }
        folders.append(folder)
    
    conn.close()
    total_pages = ceil(total / items_per_page) if total > 0 else 1
    return folders, total_pages


def get_folder_music_videos(folder_jellyfin_id, page=1, items_per_page=100):
    """Get music videos for a specific folder with pagination"""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT mvf.folder_id, mvf.title, l.name as library_name
        FROM music_video_folders mvf
        JOIN libraries l ON mvf.library_id = l.id
        WHERE mvf.folder_id = ?
    """, (folder_jellyfin_id,))
    
    folder_row = cursor.fetchone()
    if not folder_row:
        conn.close()
        return None, None, None, 1
    
    folder = {
        'Id': folder_row['folder_id'],
        'Name': folder_row['title']
    }
    
    # Get total count
    cursor.execute("""
        SELECT COUNT(*) as total
        FROM music_videos mv
        JOIN music_video_folders mvf ON mv.folder_id = mvf.id
        WHERE mvf.folder_id = ?
    """, (folder_jellyfin_id,))
    total = cursor.fetchone()['total']
    
    offset = (page - 1) * items_per_page
    cursor.execute("""
        SELECT mv.video_id, mv.title
        FROM music_videos mv
        JOIN music_video_folders mvf ON mv.folder_id = mvf.id
        WHERE mvf.folder_id = ?
        ORDER BY mv.title
        LIMIT ? OFFSET ?
    """, (folder_jellyfin_id, items_per_page, offset))
    
    videos = []
    for row in cursor.fetchall():
        image_url = f"{BASE_URL}/Items/{row['video_id']}/Images/Primary?quality=90&api_key={API_KEY}"
        
        video = {
            'Id': row['video_id'],
            'Name': row['title'],
            'ImageUrl': image_url
        }
        videos.append(video)
    
    conn.close()
    total_pages = ceil(total / items_per_page) if total > 0 else 1
    return folder, videos, folder_row['library_name'], total_pages


# =====================
# Routes
# =====================

@app.route("/")
def libraries():
    """List all libraries"""
    libraries_list = get_all_libraries()
    
    formatted_libraries = {}
    for lib in libraries_list:
        formatted_libraries[lib['name']] = {
            'Id': lib['jellyfin_id'],
            'Name': lib['name'],
            'CollectionType': lib['collection_type'],
            'db_id': lib['id']
        }
    
    return render_template(
        "libraries.html",
        libraries=formatted_libraries
    )


@app.route("/library/<library_name>")
def library(library_name):
    """Show library contents"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, jellyfin_id, collection_type FROM libraries WHERE name = ?", (library_name,))
    lib_row = cursor.fetchone()
    conn.close()
    
    if not lib_row:
        abort(404)
    
    library_id = lib_row['id']
    collection_type = lib_row['collection_type']
    page = request.args.get('page', 1, type=int)
    
    if collection_type == "tvshows":
        shows, total_pages = get_library_shows(library_id, page, ITEMS_PER_PAGE)
        return render_template(
            "show.html",
            library_name=library_name,
            shows=shows,
            page=page,
            total_pages=total_pages
        )
    
    elif collection_type == "movies":
        movies, total_pages = get_library_movies(library_id, page, ITEMS_PER_PAGE)
        return render_template(
            "movies.html",
            library_name=library_name,
            movies=movies,
            page=page,
            total_pages=total_pages
        )
    
    elif collection_type == "music":
        albums, total_pages = get_library_albums(library_id, page, ITEMS_PER_PAGE)
        return render_template(
            "music_albums.html",
            library_name=library_name,
            albums=albums,
            page=page,
            total_pages=total_pages
        )
    
    elif collection_type == "books":
        collections, total_pages = get_library_book_collections(library_id, page, ITEMS_PER_PAGE)
        return render_template(
            "book_collections.html",
            library_name=library_name,
            collections=collections,
            page=page,
            total_pages=total_pages
        )
    
    elif collection_type == "musicvideos":
        folders, total_pages = get_library_music_video_folders(library_id, page, ITEMS_PER_PAGE)
        return render_template(
            "music_video_folders.html",
            library_name=library_name,
            folders=folders,
            page=page,
            total_pages=total_pages
        )
    
    else:
        abort(404)


# =====================
# TV Shows Routes
# =====================

@app.route("/show/<library_name>/<show_id>")
def show(library_name, show_id):
    """Show details of a TV show"""
    show_obj, seasons, lib_name = get_show_details(show_id)
    
    if not show_obj:
        abort(404)
    
    seasons_with_episodes = [s for s in seasons if s['episode_count'] > 0]
    
    if not seasons_with_episodes:
        abort(404)
    
    return render_template(
        "show.html",
        library_name=library_name,
        show=show_obj,
        seasons=seasons_with_episodes
    )


@app.route("/season/<library_name>/<season_id>")
def season(library_name, season_id):
    """Show episodes in a season"""
    season_obj, episodes, lib_name, show_id = get_season_details(season_id)
    
    if not season_obj or not episodes:
        abort(404)
    
    return render_template(
        "episodes.html",
        library_name=library_name,
        season=season_obj,
        episodes=episodes
    )


# =====================
# Music Routes
# =====================

@app.route("/album/<library_name>/<album_id>")
def album(library_name, album_id):
    """Show album tracks"""
    album_obj, tracks, lib_name = get_album_tracks(album_id)
    
    if not album_obj:
        abort(404)
    
    return render_template(
        "album.html",
        library_name=library_name,
        album=album_obj,
        songs=tracks
    )


# =====================
# Books Routes
# =====================

@app.route("/books/<library_name>/<collection_id>")
def book_collection(library_name, collection_id):
    """Show books in a collection"""
    collection_obj, books, lib_name = get_collection_books(collection_id)
    
    if not collection_obj:
        abort(404)
    
    return render_template(
        "books.html",
        library_name=library_name,
        collection=collection_obj,
        collection_name=collection_obj['Name'],
        books=books
    )


# =====================
# Music Videos Routes
# =====================

@app.route("/music-videos/<library_name>/<folder_id>")
def music_video_folder(library_name, folder_id):
    """Show music videos in a folder"""
    page = request.args.get('page', 1, type=int)
    folder_obj, videos, lib_name, total_pages = get_folder_music_videos(folder_id, page, ITEMS_PER_PAGE)
    
    if not folder_obj:
        abort(404)
    
    return render_template(
        "music_videos.html",
        library_name=library_name,
        folder=folder_obj,
        videos=videos,
        page=page,
        total_pages=total_pages
    )


# =====================
# Download Routes
# =====================

@app.route("/download/show/<library_name>/<show_id>")
def download_show(library_name, show_id):
    """Download entire show"""
    conn = get_db()
    cursor = conn.cursor()
    
    # Get show info
    cursor.execute("""
        SELECT s.id, s.show_id, s.title
        FROM shows s
        WHERE s.show_id = ?
    """, (show_id,))
    
    show_row = cursor.fetchone()
    if not show_row:
        conn.close()
        abort(404)
    
    show_name = show_row['title']
    
    # Get seasons with episodes
    cursor.execute("""
        SELECT se.id, se.season_id, se.season_number
        FROM seasons se
        WHERE se.show_id = ?
        ORDER BY se.season_number
    """, (show_row['id'],))
    
    seasons = cursor.fetchall()
    
    # Build data structures for download_show_background
    shows = {show_id: {'Id': show_id, 'Name': show_name}}
    seasons_by_show = {show_id: []}
    episodes_by_season = {}
    
    for season_row in seasons:
        season_obj = {
            'Id': season_row['season_id'],
            'IndexNumber': season_row['season_number'],
            'ParentId': show_id
        }
        seasons_by_show[show_id].append(season_obj)
        
        # Get episodes for this season
        cursor.execute("""
            SELECT episode_id, episode_number, title
            FROM episodes
            WHERE season_id = ?
            ORDER BY episode_number
        """, (season_row['id'],))
        
        episodes = cursor.fetchall()
        episodes_by_season[season_row['season_id']] = []
        
        for ep_row in episodes:
            episode_obj = {
                'Id': ep_row['episode_id'],
                'IndexNumber': ep_row['episode_number'],
                'Name': ep_row['title'],
                'LocationType': 'FileSystem'
            }
            episodes_by_season[season_row['season_id']].append(episode_obj)
    
    conn.close()
    
    # Call the background download function
    download_show_background(show_id, shows, seasons_by_show, episodes_by_season)
    
    return render_template(
        "download_started.html",
        type="show",
        name=show_name,
        back_url=url_for("library", library_name=library_name)
    )


@app.route("/download/season/<library_name>/<season_id>")
def download_season(library_name, season_id):
    """Download entire season"""
    conn = get_db()
    cursor = conn.cursor()
    
    # Get season and show info
    cursor.execute("""
        SELECT se.id, se.season_id, se.season_number,
               s.show_id, s.title as show_title, s.id as show_db_id
        FROM seasons se
        JOIN shows s ON se.show_id = s.id
        WHERE se.season_id = ?
    """, (season_id,))
    
    season_row = cursor.fetchone()
    if not season_row:
        conn.close()
        abort(404)
    
    show_id = season_row['show_id']
    show_name = season_row['show_title']
    season_number = season_row['season_number']
    
    # Build data structures for download_season_background
    shows = {show_id: {'Id': show_id, 'Name': show_name}}
    
    season_obj = {
        'Id': season_row['season_id'],
        'IndexNumber': season_number,
        'ParentId': show_id
    }
    seasons_by_show = {show_id: [season_obj]}
    episodes_by_season = {season_id: []}
    
    # Get episodes for this season
    cursor.execute("""
        SELECT episode_id, episode_number, title
        FROM episodes
        WHERE season_id = ?
        ORDER BY episode_number
    """, (season_row['id'],))
    
    episodes = cursor.fetchall()
    
    for ep_row in episodes:
        episode_obj = {
            'Id': ep_row['episode_id'],
            'IndexNumber': ep_row['episode_number'],
            'Name': ep_row['title'],
            'LocationType': 'FileSystem'
        }
        episodes_by_season[season_id].append(episode_obj)
    
    conn.close()
    
    # Call the background download function
    download_season_background(season_id, shows, seasons_by_show, episodes_by_season)
    
    name = f"{show_name} – Season {season_number}"
    
    return render_template(
        "download_started.html",
        type="season",
        name=name,
        back_url=url_for("show", library_name=library_name, show_id=show_id)
    )


@app.route("/download/single/<library_name>/<single_id>")
def download_single(library_name, single_id):
    """Download single item (episode, movie, song, book, music video)"""
    return redirect(f"{BASE_URL}/Items/{single_id}/Download?api_key={API_KEY}")


@app.route('/download_zip/<library_name>/<mul_id>')
def download_zip(library_name, mul_id):
    """Download item as ZIP file - creates from disk"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT collection_type FROM libraries WHERE name = ?", (library_name,))
    lib_row = cursor.fetchone()
    
    if not lib_row:
        conn.close()
        abort(404)
    
    collection_type = lib_row['collection_type']
    
    if collection_type == "tvshows":
        # Check if it's a show or season
        cursor.execute("SELECT show_id FROM shows WHERE show_id = ?", (mul_id,))
        show_row = cursor.fetchone()
        
        if show_row:
            conn.close()
            return create_show_zip_from_disk(mul_id)
        else:
            cursor.execute("SELECT season_id FROM seasons WHERE season_id = ?", (mul_id,))
            season_row = cursor.fetchone()
            
            if season_row:
                conn.close()
                return create_season_zip_from_disk(mul_id)
            else:
                conn.close()
                abort(404)
    
    conn.close()
    abort(404)


def create_show_zip_from_disk(show_id):
    """Create ZIP from disk files and send it"""
    import tempfile
    import zipfile
    import os
    
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT s.id, s.show_id, s.title
        FROM shows s
        WHERE s.show_id = ?
    """, (show_id,))
    
    show_row = cursor.fetchone()
    if not show_row:
        conn.close()
        abort(404)
    
    show_name = show_row['title']
    
    # Get episodes with file paths
    cursor.execute("""
        SELECT se.season_number, e.episode_id, e.episode_number, 
               e.title as episode_title, e.file_path
        FROM seasons se
        JOIN episodes e ON se.id = e.season_id
        WHERE se.show_id = ?
        ORDER BY se.season_number, e.episode_number
    """, (show_row['id'],))
    
    episodes = cursor.fetchall()
    conn.close()
    
    if not episodes:
        abort(404)
    
    # Create temp ZIP file
    temp_zip = tempfile.NamedTemporaryFile(delete=False, suffix='.zip')
    temp_zip_path = temp_zip.name
    temp_zip.close()
    
    print(f"Creating ZIP for: {show_name}")
    
    try:
        with zipfile.ZipFile(temp_zip_path, 'w', zipfile.ZIP_STORED) as zipf:
            for ep_row in episodes:
                season_num = ep_row['season_number']
                episode_num = ep_row['episode_number']
                episode_title = ep_row['episode_title']
                file_path = ep_row['file_path']
                
                if not file_path or not os.path.exists(file_path):
                    print(f"Skipping S{season_num}E{episode_num} - file not found: {file_path}")
                    continue
                
                season_folder = f"Season {season_num}"
                original_filename = os.path.basename(file_path)
                zip_internal_path = f"{season_folder}/{original_filename}"
                
                try:
                    print(f"Adding S{season_num}E{episode_num}: {original_filename}")
                    zipf.write(file_path, zip_internal_path)
                except Exception as e:
                    print(f"Error adding S{season_num}E{episode_num}: {e}")
                    continue
        
        print(f"ZIP created successfully")
        
        # Send the file and delete it after
        @after_this_request
        def remove_file(response):
            try:
                os.unlink(temp_zip_path)
                print(f"Cleaned up temp ZIP")
            except Exception as e:
                print(f"Error removing temp file: {e}")
            return response
        
        return send_file(
            temp_zip_path,
            as_attachment=True,
            download_name=f"{show_name}.zip",
            mimetype='application/zip'
        )
        
    except Exception as e:
        print(f"Error creating ZIP: {e}")
        if os.path.exists(temp_zip_path):
            os.unlink(temp_zip_path)
        abort(500)


def create_season_zip_from_disk(season_id):
    """Create season ZIP from disk files and send it"""
    import tempfile
    import zipfile
    import os
    
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT se.season_number, s.title as show_title, se.id as season_db_id
        FROM seasons se
        JOIN shows s ON se.show_id = s.id
        WHERE se.season_id = ?
    """, (season_id,))
    
    season_row = cursor.fetchone()
    if not season_row:
        conn.close()
        abort(404)
    
    show_name = season_row['show_title']
    season_num = season_row['season_number']
    
    # Get episodes with file paths
    cursor.execute("""
        SELECT e.episode_number, e.title as episode_title, e.file_path
        FROM episodes e
        WHERE e.season_id = ?
        ORDER BY e.episode_number
    """, (season_row['season_db_id'],))
    
    episodes = cursor.fetchall()
    conn.close()
    
    if not episodes:
        abort(404)
    
    temp_zip = tempfile.NamedTemporaryFile(delete=False, suffix='.zip')
    temp_zip_path = temp_zip.name
    temp_zip.close()
    
    zip_name = f"{show_name} - Season {season_num}"
    print(f"Creating ZIP for: {zip_name}")
    
    try:
        with zipfile.ZipFile(temp_zip_path, 'w', zipfile.ZIP_STORED) as zipf:
            for ep_row in episodes:
                episode_num = ep_row['episode_number']
                episode_title = ep_row['episode_title']
                file_path = ep_row['file_path']
                
                if not file_path or not os.path.exists(file_path):
                    print(f"Skipping E{episode_num} - file not found: {file_path}")
                    continue
                
                original_filename = os.path.basename(file_path)
                
                try:
                    print(f"Adding E{episode_num}: {original_filename}")
                    zipf.write(file_path, original_filename)
                except Exception as e:
                    print(f"Error adding E{episode_num}: {e}")
                    continue
        
        print(f"ZIP created successfully")
        
        @after_this_request
        def remove_file(response):
            try:
                os.unlink(temp_zip_path)
                print(f"Cleaned up temp ZIP")
            except Exception as e:
                print(f"Error removing temp file: {e}")
            return response
        
        return send_file(
            temp_zip_path,
            as_attachment=True,
            download_name=f"{zip_name}.zip",
            mimetype='application/zip'
        )
        
    except Exception as e:
        print(f"Error creating ZIP: {e}")
        if os.path.exists(temp_zip_path):
            os.unlink(temp_zip_path)
        abort(500)


def download_show_zip(show_id, z, cursor, conn):
    """Download entire show as ZIP"""
    print(f"[DEBUG] download_show_zip called with show_id: {show_id}")
    
    cursor.execute("""
        SELECT s.id, s.show_id, s.title
        FROM shows s
        WHERE s.show_id = ?
    """, (show_id,))
    
    show_row = cursor.fetchone()
    if not show_row:
        print(f"[DEBUG] No show found with ID: {show_id}")
        conn.close()
        abort(404)
    
    show_name = show_row['title']
    print(f"[DEBUG] Found show: {show_name} (db_id: {show_row['id']})")
    
    cursor.execute("""
        SELECT se.id, se.season_id, se.season_number
        FROM seasons se
        WHERE se.show_id = ?
        ORDER BY se.season_number
    """, (show_row['id'],))
    
    seasons = cursor.fetchall()
    print(f"[DEBUG] Found {len(seasons)} seasons")
    
    total_episodes = 0
    for season_row in seasons:
        season_folder = f"Season {season_row['season_number']}"
        print(f"[DEBUG] Processing {season_folder} (season_id: {season_row['season_id']})")
        
        cursor.execute("""
            SELECT episode_id, episode_number, title
            FROM episodes
            WHERE season_id = ?
            ORDER BY episode_number
        """, (season_row['id'],))
        
        episodes = cursor.fetchall()
        print(f"[DEBUG] Found {len(episodes)} episodes in {season_folder}")
        
        for episode in episodes:
            episode_id = episode['episode_id']
            print(f"[DEBUG] Downloading episode {episode['episode_number']}: {episode['title']} (ID: {episode_id})")
            
            url = f"{BASE_URL}/Items/{episode_id}/Download"
            headers = {"X-Emby-Token": API_KEY}
            print(f"[DEBUG] URL: {url}")
            
            try:
                resp = requests.get(url, headers=headers, stream=True, timeout=30)
                print(f"[DEBUG] Response status: {resp.status_code}")
                
                if resp.status_code != 200:
                    print(f"[DEBUG] Error response: {resp.text[:200]}")
                    print(f"[DEBUG] Skipping episode due to non-200 status")
                    continue
            except Exception as e:
                print(f"[DEBUG] Exception downloading episode: {e}")
                continue
            try:
                cd = resp.headers.get('Content-Disposition')
                filename = get_filename_from_cd(cd)
                
                if not filename:
                    content_type = resp.headers.get('Content-Type', '')
                    ext = mimetypes.guess_extension(content_type.split(';')[0].strip())
                    ext = ext if ext else ''
                    filename = f"{episode_id}{ext}"
                
                print(f"[DEBUG] Adding to ZIP: {season_folder}/{filename}")
                zip_path = f"{season_folder}/{filename}"
                z.write_iter(zip_path, resp.iter_content(chunk_size=8192))
                total_episodes += 1
                print(f"[DEBUG] Finished adding episode {episode['episode_number']}")
            except Exception as e:
                print(f"[DEBUG] Error while streaming episode to ZIP: {e}")
                print(f"[DEBUG] Continuing with next episode...")
                continue
    
    print(f"[DEBUG] Total episodes added to ZIP: {total_episodes}")
    conn.close()
    
    return Response(
        stream_with_context(z),
        mimetype='application/zip',
        headers={'Content-Disposition': f'attachment; filename={show_name}.zip'}
    )


def download_season_zip(season_id, z, cursor, conn):
    """Download single season as ZIP"""
    print(f"[DEBUG] download_season_zip called with season_id: {season_id}")
    
    cursor.execute("""
        SELECT se.id, se.season_id, se.season_number,
               s.show_id, s.title as show_title
        FROM seasons se
        JOIN shows s ON se.show_id = s.id
        WHERE se.season_id = ?
    """, (season_id,))
    
    season_row = cursor.fetchone()
    if not season_row:
        print(f"[DEBUG] No season found with ID: {season_id}")
        conn.close()
        abort(404)
    
    show_name = season_row['show_title']
    season_number = season_row['season_number']
    zip_name = f"{show_name} - Season {season_number}"
    print(f"[DEBUG] Found season: {zip_name} (db_id: {season_row['id']})")
    
    cursor.execute("""
        SELECT episode_id, episode_number, title
        FROM episodes
        WHERE season_id = ?
        ORDER BY episode_number
    """, (season_row['id'],))
    
    episodes = cursor.fetchall()
    print(f"[DEBUG] Found {len(episodes)} episodes")
    
    for episode in episodes:
        episode_id = episode['episode_id']
        print(f"[DEBUG] Downloading episode {episode['episode_number']}: {episode['title']} (ID: {episode_id})")
        
        url = f"{BASE_URL}/Items/{episode_id}/Download"
        headers = {"X-Emby-Token": API_KEY}
        print(f"[DEBUG] URL: {url}")
        
        try:
            resp = requests.get(url, headers=headers, stream=True, timeout=30)
            print(f"[DEBUG] Response status: {resp.status_code}")
            
            if resp.status_code != 200:
                print(f"[DEBUG] Error response: {resp.text[:200]}")
                print(f"[DEBUG] Skipping episode due to non-200 status")
                continue
        except Exception as e:
            print(f"[DEBUG] Exception downloading episode: {e}")
            continue
        try:
            cd = resp.headers.get('Content-Disposition')
            filename = get_filename_from_cd(cd)
            
            if not filename:
                content_type = resp.headers.get('Content-Type', '')
                ext = mimetypes.guess_extension(content_type.split(';')[0].strip())
                ext = ext if ext else ''
                filename = f"{episode_id}{ext}"
            
            print(f"[DEBUG] Adding to ZIP: {filename}")
            # No subfolder for single season download
            z.write_iter(filename, resp.iter_content(chunk_size=8192))
            print(f"[DEBUG] Finished adding episode {episode['episode_number']}")
        except Exception as e:
            print(f"[DEBUG] Error while streaming episode to ZIP: {e}")
            print(f"[DEBUG] Continuing with next episode...")
            continue
    
    conn.close()
    
    return Response(
        stream_with_context(z),
        mimetype='application/zip',
        headers={'Content-Disposition': f'attachment; filename={zip_name}.zip'}
    )


def download_album_zip(album_id, z, cursor, conn, library_name):
    """Download album as ZIP"""
    cursor.execute("""
        SELECT ma.album_id, ma.title
        FROM music_albums ma
        WHERE ma.album_id = ?
    """, (album_id,))
    
    album_row = cursor.fetchone()
    if not album_row:
        conn.close()
        abort(404)
    
    album_name = album_row['title']
    
    cursor.execute("""
        SELECT mt.track_id
        FROM music_tracks mt
        JOIN music_albums ma ON mt.album_id = ma.id
        WHERE ma.album_id = ?
        ORDER BY mt.track_number
    """, (album_id,))
    
    tracks = cursor.fetchall()
    
    for track in tracks:
        track_id = track['track_id']
        
        url = f"{BASE_URL}/Items/{track_id}/Download"
        headers = {"X-Emby-Token": API_KEY}
        resp = requests.get(url, headers=headers, stream=True)
        if resp.status_code != 200:
            continue
        
        cd = resp.headers.get('Content-Disposition')
        filename = get_filename_from_cd(cd)
        
        if not filename:
            content_type = resp.headers.get('Content-Type', '')
            ext = mimetypes.guess_extension(content_type.split(';')[0].strip())
            ext = ext if ext else ''
            filename = f"{track_id}{ext}"
        
        z.write_iter(filename, resp.iter_content(chunk_size=8192))
    
    conn.close()
    
    return Response(
        stream_with_context(z),
        mimetype='application/zip',
        headers={'Content-Disposition': f'attachment; filename={album_name}.zip'}
    )


def download_book_collection_zip(collection_id, z, cursor, conn, library_name):
    """Download book collection as ZIP"""
    cursor.execute("""
        SELECT bc.collection_id, bc.title
        FROM book_collections bc
        WHERE bc.collection_id = ?
    """, (collection_id,))
    
    collection_row = cursor.fetchone()
    if not collection_row:
        conn.close()
        abort(404)
    
    collection_name = collection_row['title']
    
    cursor.execute("""
        SELECT b.book_id
        FROM books b
        JOIN book_collections bc ON b.collection_id = bc.id
        WHERE bc.collection_id = ?
    """, (collection_id,))
    
    books = cursor.fetchall()
    
    for book in books:
        book_id = book['book_id']
        
        url = f"{BASE_URL}/Items/{book_id}/Download"
        headers = {"X-Emby-Token": API_KEY}
        resp = requests.get(url, headers=headers, stream=True)
        if resp.status_code != 200:
            continue
        
        cd = resp.headers.get('Content-Disposition')
        filename = get_filename_from_cd(cd)
        
        if not filename:
            content_type = resp.headers.get('Content-Type', '')
            ext = mimetypes.guess_extension(content_type.split(';')[0].strip())
            ext = ext if ext else ''
            filename = f"{book_id}{ext}"
        
        z.write_iter(filename, resp.iter_content(chunk_size=8192))
    
    conn.close()
    
    return Response(
        stream_with_context(z),
        mimetype='application/zip',
        headers={'Content-Disposition': f'attachment; filename={collection_name}.zip'}
    )


def download_music_video_folder_zip(folder_id, z, cursor, conn, library_name):
    """Download music video folder as ZIP"""
    cursor.execute("""
        SELECT mvf.folder_id, mvf.title
        FROM music_video_folders mvf
        WHERE mvf.folder_id = ?
    """, (folder_id,))
    
    folder_row = cursor.fetchone()
    if not folder_row:
        conn.close()
        abort(404)
    
    folder_name = folder_row['title']
    
    cursor.execute("""
        SELECT mv.video_id
        FROM music_videos mv
        JOIN music_video_folders mvf ON mv.folder_id = mvf.id
        WHERE mvf.folder_id = ?
    """, (folder_id,))
    
    videos = cursor.fetchall()
    
    for video in videos:
        video_id = video['video_id']
        
        url = f"{BASE_URL}/Items/{video_id}/Download"
        headers = {"X-Emby-Token": API_KEY}
        resp = requests.get(url, headers=headers, stream=True)
        if resp.status_code != 200:
            continue
        
        cd = resp.headers.get('Content-Disposition')
        filename = get_filename_from_cd(cd)
        
        if not filename:
            content_type = resp.headers.get('Content-Type', '')
            ext = mimetypes.guess_extension(content_type.split(';')[0].strip())
            ext = ext if ext else ''
            filename = f"{video_id}{ext}"
        
        z.write_iter(filename, resp.iter_content(chunk_size=8192))
    
    conn.close()
    
    return Response(
        stream_with_context(z),
        mimetype='application/zip',
        headers={'Content-Disposition': f'attachment; filename={folder_name}.zip'}
    )


def download_show_zip_sequential(show_id):
    """Download entire show as ZIP - sequential processing to avoid timeouts"""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT s.id, s.show_id, s.title
        FROM shows s
        WHERE s.show_id = ?
    """, (show_id,))
    
    show_row = cursor.fetchone()
    if not show_row:
        conn.close()
        abort(404)
    
    show_name = show_row['title']
    
    # Get all episodes organized by season
    cursor.execute("""
        SELECT se.season_number, e.episode_id, e.episode_number, e.title as episode_title
        FROM seasons se
        JOIN episodes e ON se.id = e.season_id
        WHERE se.show_id = ?
        ORDER BY se.season_number, e.episode_number
    """, (show_row['id'],))
    
    episodes = cursor.fetchall()
    conn.close()
    
    def generate_zip():
        """Generator that yields ZIP data chunk by chunk"""
        z = zipstream.ZipFile(mode='w', compression=zipstream.ZIP_STORED, allowZip64=True)
        headers = {"X-Emby-Token": API_KEY}
        
        for ep_row in episodes:
            season_num = ep_row['season_number']
            episode_id = ep_row['episode_id']
            episode_num = ep_row['episode_number']
            episode_title = ep_row['episode_title']
            
            season_folder = f"Season {season_num}"
            
            try:
                url = f"{BASE_URL}/Items/{episode_id}/Download"
                
                # Download the file completely first with a longer timeout
                print(f"Downloading S{season_num}E{episode_num}: {episode_title}")
                resp = requests.get(url, headers=headers, stream=True, timeout=120)
                
                if resp.status_code != 200:
                    print(f"Skipped S{season_num}E{episode_num} - Status {resp.status_code}")
                    continue
                
                # Get filename
                cd = resp.headers.get('Content-Disposition')
                filename = get_filename_from_cd(cd)
                if not filename:
                    content_type = resp.headers.get('Content-Type', '')
                    ext = mimetypes.guess_extension(content_type.split(';')[0].strip()) or ''
                    filename = f"{episode_id}{ext}"
                
                zip_path = f"{season_folder}/{filename}"
                
                # Add to ZIP with streaming
                z.write_iter(zip_path, resp.iter_content(chunk_size=65536))
                print(f"Added S{season_num}E{episode_num}")
                
            except Exception as e:
                print(f"Error with S{season_num}E{episode_num}: {e}")
                continue
        
        # Yield the ZIP content
        for chunk in z:
            yield chunk
    
    return Response(
        generate_zip(),
        mimetype='application/zip',
        headers={
            'Content-Disposition': f'attachment; filename="{show_name}.zip"',
            'X-Accel-Buffering': 'no'  # Disable nginx buffering if behind nginx
        }
    )


def download_season_zip_sequential(season_id):
    """Download single season as ZIP - sequential processing"""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT se.season_number, s.title as show_title, s.id as show_db_id
        FROM seasons se
        JOIN shows s ON se.show_id = s.id
        WHERE se.season_id = ?
    """, (season_id,))
    
    season_row = cursor.fetchone()
    if not season_row:
        conn.close()
        abort(404)
    
    show_name = season_row['show_title']
    season_num = season_row['season_number']
    
    # Get all episodes in this season
    cursor.execute("""
        SELECT e.episode_id, e.episode_number, e.title as episode_title
        FROM episodes e
        JOIN seasons se ON e.season_id = se.id
        WHERE se.season_id = ?
        ORDER BY e.episode_number
    """, (season_id,))
    
    episodes = cursor.fetchall()
    conn.close()
    
    def generate_zip():
        """Generator that yields ZIP data chunk by chunk"""
        z = zipstream.ZipFile(mode='w', compression=zipstream.ZIP_STORED, allowZip64=True)
        headers = {"X-Emby-Token": API_KEY}
        
        for ep_row in episodes:
            episode_id = ep_row['episode_id']
            episode_num = ep_row['episode_number']
            episode_title = ep_row['episode_title']
            
            try:
                url = f"{BASE_URL}/Items/{episode_id}/Download"
                
                print(f"Downloading E{episode_num}: {episode_title}")
                resp = requests.get(url, headers=headers, stream=True, timeout=120)
                
                if resp.status_code != 200:
                    print(f"Skipped E{episode_num} - Status {resp.status_code}")
                    continue
                
                # Get filename
                cd = resp.headers.get('Content-Disposition')
                filename = get_filename_from_cd(cd)
                if not filename:
                    content_type = resp.headers.get('Content-Type', '')
                    ext = mimetypes.guess_extension(content_type.split(';')[0].strip()) or ''
                    filename = f"{episode_id}{ext}"
                
                # Add to ZIP with streaming
                z.write_iter(filename, resp.iter_content(chunk_size=65536))
                print(f"Added E{episode_num}")
                
            except Exception as e:
                print(f"Error with E{episode_num}: {e}")
                continue
        
        # Yield the ZIP content
        for chunk in z:
            yield chunk
    
    zip_name = f"{show_name} - Season {season_num}"
    return Response(
        generate_zip(),
        mimetype='application/zip',
        headers={
            'Content-Disposition': f'attachment; filename="{zip_name}.zip"',
            'X-Accel-Buffering': 'no'
        }
    )


def get_filename_from_cd(cd):
    """Parse Content-Disposition header to get filename"""
    if not cd:
        return None
    fname = None
    parts = cd.split(';')
    for part in parts:
        part = part.strip()
        if part.startswith('filename='):
            fname = part.split('=', 1)[1].strip('"')
    return fname


if __name__ == "__main__":
    app.run(debug=True)
