from flask import Flask, render_template, abort, url_for, request
import json
from math import ceil
from collections import defaultdict
from download import (
    download_show_background,
    download_season_background,
    download_episode_background
)

app = Flask(__name__)

DATA_FILE = "all_items.json"
ITEMS_PER_PAGE = 100

with open("data.txt", "r") as file:
    BASE_URL = file.readline().strip()
    API_KEY = file.readline().strip()


# =====================
# Load libraries
# =====================

with open(DATA_FILE, "r", encoding="utf-8") as f:
    LIBRARIES = json.load(f)


# =====================
# Helpers
# =====================

def is_real_media(item):
    """Filters out phantom / virtual items"""
    return (
        item.get("Path")
        #and item.get("Container")
        and item.get("LocationType") != "Virtual"
    )


def organize_items(items):
    shows = {}
    seasons_by_show = defaultdict(list)
    episodes_by_season = defaultdict(list)

    for item in items:
        if item.get("Type") == "Series":
            shows[item["Id"]] = item

    for item in items:
            if item.get("Type") == "Series":
                shows[item["Id"]] = item

    for item in items:
        if item.get("Type") == "Season":
            #if item.get("IndexNumber", 0) == 0:
            #    continue
            parent_id = item.get("ParentId")
            if parent_id and parent_id in shows:
                seasons_by_show[parent_id].append(item)

    for item in items:
        if item.get("Type") == "Episode":
            season_id = item.get("ParentId") or item.get("SeasonId")

            if not season_id:
                series_id = item.get("SeriesId")
                if series_id:
                    pseudo_season_id = f"unknown_season_{series_id}"
                    if not any(s["Id"] == pseudo_season_id for s in seasons_by_show[series_id]):
                        pseudo_season = {
                            "Id": pseudo_season_id,
                            "Name": "Season Unknown",
                            "IndexNumber": 0,
                            "ParentId": series_id,
                            "ImageUrl": None
                        }
                        seasons_by_show[series_id].append(pseudo_season)
                    episodes_by_season[pseudo_season_id].append(item)
                else:
                    continue
            else:
                episodes_by_season[season_id].append(item)

    for seasons in seasons_by_show.values():
        seasons.sort(key=lambda s: s.get("IndexNumber") or 0)

    for eps in episodes_by_season.values():
        eps.sort(key=lambda e: (e.get("ParentIndexNumber") or 0, e.get("IndexNumber") or 0))

    return shows, seasons_by_show, episodes_by_season


# =====================
# Routes
# =====================

@app.route("/")
def libraries():
    filtered_libraries = {
        name: lib for name, lib in LIBRARIES.items()
        if lib.get("CollectionType") != "playlists"
    }
    return render_template(
        "libraries.html",
        libraries=filtered_libraries
    )


@app.route("/library/<library_name>")
def library(library_name):
    library = LIBRARIES.get(library_name)
    if not library:
        abort(404)

    items = library["Items"]
    collection_type = library.get("CollectionType")

    if collection_type == "movies":
        movies = [
            i for i in items
            if i.get("Type") == "Movie" and is_real_media(i)
        ]
        movies_with_images = []
        for movie in movies:
            movie_id = movie["Id"]
            image_url = f"{BASE_URL}/Items/{movie_id}/Images/Primary?quality=90&api_key={API_KEY}"
            movie_copy = dict(movie)
            movie_copy["ImageUrl"] = image_url
            movies_with_images.append(movie_copy)

        return render_template(
            "movies.html",
            library_name=library_name,
            movies=movies_with_images
        )


    elif collection_type == "tvshows":
        shows, seasons_by_show, episodes_by_season = organize_items(items)

        shows_with_images = []
        for show_id, show in shows.items():
            image_url = f"{BASE_URL}/Items/{show_id}/Images/Primary?quality=90&api_key={API_KEY}"
            show_copy = dict(show)
            show_copy["ImageUrl"] = image_url
            shows_with_images.append(show_copy)

        # Pagination
        page = request.args.get('page', 1, type=int)
        total_shows = len(shows_with_images)
        total_pages = ceil(total_shows / ITEMS_PER_PAGE)

        start = (page - 1) * ITEMS_PER_PAGE
        end = start + ITEMS_PER_PAGE
        shows_page = shows_with_images[start:end]

        return render_template(
            "show.html",
            library_name=library_name,
            shows=shows_page,
            page=page,
            total_pages=total_pages
        )

    elif collection_type == "books":
        # Show folders (book collections)
        collections = [i for i in items if i.get("Type") == "Folder"]

        collections_with_images = []
        for collection in collections:
            coll_copy = dict(collection)

            # Try to get image from collection's ImageTags (if any)
            image_url = None
            image_tag = collection.get("ImageTags", {}).get("Primary")
            if image_tag:
                image_url = f"{BASE_URL}/Items/{collection['Id']}/Images/Primary?tag={image_tag}&api_key={API_KEY}"
            else:
                # fallback: try to get first book's image inside this folder
                first_book = next((b for b in items if b.get("Type") == "Book" and b.get("ParentId") == collection["Id"]), None)
                if first_book:
                    book_image_tag = first_book.get("ImageTags", {}).get("Primary")
                    if book_image_tag:
                        image_url = f"{BASE_URL}/Items/{first_book['Id']}/Images/Primary?tag={book_image_tag}&api_key={API_KEY}"

            coll_copy["ImageUrl"] = image_url
            collections_with_images.append(coll_copy)

        # Pagination
        page = request.args.get('page', 1, type=int)
        total_collections = len(collections_with_images)
        total_pages = ceil(total_collections / ITEMS_PER_PAGE)

        start = (page - 1) * ITEMS_PER_PAGE
        end = start + ITEMS_PER_PAGE
        collections_page = collections_with_images[start:end]

        return render_template(
            "book_collections.html",
            library_name=library_name,
            collections=collections_page,
            page=page,
            total_pages=total_pages
        )

    elif collection_type == "music":
        # Show music albums or artists
        albums = [i for i in items if i.get("Type") == "MusicAlbum"]
        albums_with_images = []
        for album in albums:
            album_copy = dict(album)
            image_tag = album.get("ImageTags", {}).get("Primary")
            if image_tag:
                image_url = f"{BASE_URL}/Items/{album['Id']}/Images/Primary?tag={image_tag}&api_key={API_KEY}"
            else:
                image_url = None  # explicitly set to None if no image
            album_copy["ImageUrl"] = image_url
            albums_with_images.append(album_copy)

        return render_template(
            "music_albums.html",
            library_name=library_name,
            albums=albums_with_images
        )

    elif collection_type == "musicvideos":
        page = int(request.args.get("page", 1))
        per_page = 100

        folders = [i for i in items if i.get("Type") == "Folder"]

        total = len(folders)
        total_pages = (total + per_page - 1) // per_page

        start = (page - 1) * per_page
        end = start + per_page
        folders_page = folders[start:end]

        folders_with_images = []
        for folder in folders_page:
            folder_copy = dict(folder)

            image_tag = folder.get("ImageTags", {}).get("Primary")
            if image_tag:
                folder_copy["ImageUrl"] = (
                    f"{BASE_URL}/Items/{folder['Id']}/Images/Primary"
                    f"?tag={image_tag}&api_key={API_KEY}"
                )
            else:
                folder_copy["ImageUrl"] = None

            folders_with_images.append(folder_copy)

        return render_template(
            "music_video_folders.html",
            library_name=library_name,
            folders=folders_with_images,
            page=page,
            total_pages=total_pages
        )




    else:
        abort(404)

@app.route("/album/<library_name>/<album_id>")
def album(library_name, album_id):
    library = LIBRARIES.get(library_name)
    if not library:
        abort(404)

    items = library["Items"]
    album = next((a for a in items if a.get("Id") == album_id and a.get("Type") == "MusicAlbum"), None)
    if not album:
        abort(404)

    # You could list songs inside the album here if you want
    songs = [i for i in items if i.get("Type") == "Audio" and i.get("ParentId") == album_id]

    return render_template(
        "album.html",
        library_name=library_name,
        album=album,
        songs=songs
    )


@app.route("/books/<library_name>/<collection_id>")
def book_collection(library_name, collection_id):
    library = LIBRARIES.get(library_name)
    if not library:
        abort(404)

    items = library["Items"]

    # Get all books inside the collection folder
    books = []
    for item in items:
        if item.get("Type") == "Book" and item.get("ParentId") == collection_id:
            book_copy = dict(item)
            image_tag = item.get("ImageTags", {}).get("Primary")
            if image_tag:
                book_copy["ImageUrl"] = f"{BASE_URL}/Items/{item['Id']}/Images/Primary?tag={image_tag}&api_key={API_KEY}"
            else:
                book_copy["ImageUrl"] = None
            books.append(book_copy)

    if not books:
        abort(404)

    # Optionally get collection folder name for title
    collection = next((c for c in items if c.get("Id") == collection_id), None)
    if not collection:
        abort(404)

    return render_template(
        "books.html",
        library_name=library_name,
        collection=collection,
        books=books
    )



@app.route("/music-videos/<library_name>/<folder_id>")
def music_video_folder(library_name, folder_id):
    library = LIBRARIES.get(library_name)
    if not library:
        abort(404)

    items = library["Items"]

    folder = next(
        (i for i in items if i.get("Id") == folder_id and i.get("Type") == "Folder"),
        None
    )
    if not folder:
        abort(404)

    videos = [
        i for i in items
        if i.get("Type") in ("MusicVideo", "Video")
        and i.get("ParentId") == folder_id
    ]

    # Pagination setup
    page = int(request.args.get("page", 1))
    per_page = 100
    total = len(videos)
    total_pages = (total + per_page - 1) // per_page

    start = (page - 1) * per_page
    end = start + per_page
    videos_page = videos[start:end]

    videos_with_images = []
    for video in videos_page:
        video_copy = dict(video)
        tag = video.get("ImageTags", {}).get("Primary")
        if tag:
            video_copy["ImageUrl"] = (
                f"{BASE_URL}/Items/{video['Id']}/Images/Primary"
                f"?tag={tag}&api_key={API_KEY}"
            )
        else:
            video_copy["ImageUrl"] = None
        videos_with_images.append(video_copy)

    return render_template(
        "music_videos.html",
        library_name=library_name,
        folder=folder,
        videos=videos_with_images,
        page=page,
        total_pages=total_pages
    )



@app.route("/music-video/<library_name>/<video_id>")
def music_video(library_name, video_id):
    library = LIBRARIES.get(library_name)
    if not library:
        abort(404)

    items = library["Items"]
    video = next(
        (v for v in items if v.get("Id") == video_id and v.get("Type") == "MusicVideo"),
        None
    )
    if not video:
        abort(404)

    return render_template(
        "music_video.html",
        library_name=library_name,
        video=video
    )



@app.route("/show/<library_name>/<show_id>")
def show(library_name, show_id):
    library = LIBRARIES.get(library_name)
    if not library:
        abort(404)

    items = library["Items"]
    shows, seasons_by_show, episodes_by_season = organize_items(items)

    show_obj = shows.get(show_id)
    if not show_obj:
        abort(404)

    seasons = seasons_by_show.get(show_id)
    if not seasons:
        abort(404)

    seasons_with_images = []
    for season in seasons:
        season_id = season.get("Id")
        episodes = episodes_by_season.get(season_id, [])
        episodes_with_container = [ep for ep in episodes if ep.get("Container")]
        if not episodes_with_container:
            continue

        image_tag = season.get("ImageTags", {}).get("Primary")
        image_url = None
        if image_tag:
            image_url = f"{BASE_URL}/Items/{season['Id']}/Images/Primary?tag={image_tag}&api_key={API_KEY}"

        season_copy = dict(season)
        season_copy["ImageUrl"] = image_url
        seasons_with_images.append(season_copy)

    if not seasons_with_images:
        abort(404)

    return render_template(
        "show.html",
        library_name=library_name,
        show=show_obj,
        seasons=seasons_with_images
    )

@app.route("/download/music-video/<library_name>/<video_id>")
def download_music_video(library_name, video_id):
    library = LIBRARIES.get(library_name)
    if not library:
        abort(404)

    video = next(
        (v for v in library["Items"] if v.get("Id") == video_id),
        None
    )
    if not video:
        abort(404)

    download_episode_background(video)  # or your generic download function

    return render_template(
        "download_started.html",
        type="music video",
        name=video["Name"],
        back_url=url_for("library", library_name=library_name)
    )



@app.route("/download/album/<library_name>/<album_id>")
def download_album(library_name, album_id):
    # Your download logic here
    # ...
    return render_template("download_started.html", ...)

@app.route("/download/song/<library_name>/<song_id>")
def download_song(library_name, song_id):
    # Find the song item in the library by song_id and library_name
    library = LIBRARIES.get(library_name)
    if not library:
        abort(404)

    # Find the song in the items
    song = next((item for item in library["Items"] if item.get("Id") == song_id and item.get("Type") == "Audio"), None)
    if not song:
        abort(404)

    # Call your download logic here
    # For example: download_song_file(song)

    return render_template(
        "download_started.html",
        type="song",
        name=song.get("Name", "Unknown"),
        back_url=url_for("album", library_name=library_name, album_id=song.get("AlbumId"))
    )



@app.route("/download/book_collection/<library_name>/<collection_id>")
def download_book_collection(library_name, collection_id):
    # Your logic to handle downloading the book collection background/images/files
    # ...
    return render_template("download_started.html", ...)


@app.route("/season/<library_name>/<season_id>")
def season(library_name, season_id):
    library = LIBRARIES.get(library_name)
    if not library:
        abort(404)

    items = library["Items"]
    shows, seasons_by_show, episodes_by_season = organize_items(items)

    season_info = None
    for seasons in seasons_by_show.values():
        for s in seasons:
            if s["Id"] == season_id:
                season_info = s
                break

    if not season_info:
        abort(404)

    episodes = episodes_by_season.get(season_id)
    if not episodes:
        abort(404)

    episodes_with_images = []
    for ep in episodes:
        image_tag = ep.get("ImageTags", {}).get("Primary")
        image_url = None
        if image_tag:
            image_url = f"{BASE_URL}/Items/{ep['Id']}/Images/Primary?tag={image_tag}&api_key={API_KEY}"

        ep_copy = dict(ep)
        ep_copy["ImageUrl"] = image_url
        episodes_with_images.append(ep_copy)

    return render_template(
        "episodes.html",
        library_name=library_name,
        season=season_info,
        episodes=episodes_with_images
    )

@app.route("/download/show/<library_name>/<show_id>")
def download_show(library_name, show_id):
    library = LIBRARIES.get(library_name)
    if not library:
        abort(404)

    items = library["Items"]
    shows, seasons_by_show, episodes_by_season = organize_items(items)

    if show_id not in shows:
        abort(404)

    download_show_background(show_id, shows, seasons_by_show, episodes_by_season)

    return render_template(
        "download_started.html",
        type="show",
        name=shows[show_id]["Name"],
        back_url=url_for("library", library_name=library_name)
    )


@app.route("/download/season/<library_name>/<season_id>")
def download_season(library_name, season_id):
    library = LIBRARIES.get(library_name)
    if not library:
        abort(404)

    items = library["Items"]
    shows, seasons_by_show, episodes_by_season = organize_items(items)

    season_info = None
    show_id = None
    for sid, seasons in seasons_by_show.items():
        for s in seasons:
            if s["Id"] == season_id:
                season_info = s
                show_id = sid
                break

    if not season_info:
        abort(404)

    download_season_background(season_id, shows, seasons_by_show, episodes_by_season)

    name = f"{shows[show_id]['Name']} – Season {season_info.get('IndexNumber', '?')}"

    return render_template(
        "download_started.html",
        type="season",
        name=name,
        back_url=url_for("show", library_name=library_name, show_id=show_id)
    )


@app.route("/download/episode/<library_name>/<episode_id>")
def download_episode(library_name, episode_id):
    library = LIBRARIES.get(library_name)
    if not library:
        abort(404)

    items = library["Items"]
    shows, seasons_by_show, episodes_by_season = organize_items(items)

    episode = None
    season_id = None
    show_id = None

    for sid, seasons in seasons_by_show.items():
        for s in seasons:
            eps = episodes_by_season.get(s["Id"], [])
            for ep in eps:
                if ep["Id"] == episode_id:
                    episode = ep
                    season_id = s["Id"]
                    show_id = sid
                    break

    if not episode:
        abort(404)

    download_episode_background(episode)

    ep_name = (
        f"{shows[show_id]['Name']} – "
        f"S{episode.get('ParentIndexNumber', '?')}E{episode.get('IndexNumber', '?')} "
        f"{episode['Name']}"
    )

    return render_template(
        "download_started.html",
        type="episode",
        name=ep_name,
        back_url=url_for("season", library_name=library_name, season_id=season_id)
    )

@app.route("/download/movie/<library_name>/<movie_id>")
def download_movie(library_name, movie_id):
    # You need to implement this function for downloading movies
    # Example:
    library = LIBRARIES.get(library_name)
    if not library:
        abort(404)
    
    items = library["Items"]
    movie = next((i for i in items if i.get("Id") == movie_id and i.get("Type") == "Movie"), None)
    if not movie:
        abort(404)

    # Call your download function here (you need to implement)
    # download_movie_background(movie)  # for example

    return render_template(
        "download_started.html",
        type="movie",
        name=movie["Name"],
        back_url=url_for("library", library_name=library_name)
    )


if __name__ == "__main__":
    app.run(debug=True)
