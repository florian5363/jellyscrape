import os
import threading
import requests

with open("data.txt", "r") as file:
    BASE_URL = file.readline().strip()
    API_KEY = file.readline().strip()
    USERNAME = file.readline().strip()

HEADERS = {
    "X-Emby-Token": API_KEY,
    "Accept": "application/json"
}

DOWNLOAD_ROOT = "downloads"


# =========================
# Public API (called by Flask)
# =========================

def download_show_background(show_id, shows, seasons_by_show, episodes_by_season):
    threading.Thread(
        target=_download_show_worker,
        args=(show_id, shows, seasons_by_show, episodes_by_season),
        daemon=True
    ).start()


def download_season_background(season_id, shows, seasons_by_show, episodes_by_season):
    threading.Thread(
        target=_download_season_worker,
        args=(season_id, shows, seasons_by_show, episodes_by_season),
        daemon=True
    ).start()


def download_episode_background(episode):
    threading.Thread(
        target=_download_episode_worker,
        args=(episode, None),
        daemon=True
    ).start()



# =========================
# Workers
# =========================

def _download_show_worker(show_id, shows, seasons_by_show, episodes_by_season):
    show = shows.get(show_id)
    if not show:
        print("Show not found:", show_id)
        return

    show_name = safe(show["Name"])
    print(f"Starting show download: {show_name}")

    for season in seasons_by_show.get(show_id, []):
        _download_season(season, show_name, episodes_by_season)
    

def _download_season_worker(season_id, shows, seasons_by_show, episodes_by_season):
    for show_id, seasons in seasons_by_show.items():
        for season in seasons:
            if season["Id"] == season_id:
                show_name = safe(shows[show_id]["Name"])
                _download_season(season, show_name, episodes_by_season)
                return

    print("Season not found:", season_id)


def _download_season(season, show_name, episodes_by_season):
    season_name = safe(season.get("Name", f"Season {season.get('IndexNumber', '')}"))
    season_dir = os.path.join(DOWNLOAD_ROOT, show_name, season_name)
    os.makedirs(season_dir, exist_ok=True)

    episodes = episodes_by_season.get(season["Id"], [])
    print(f"Downloading {len(episodes)} episodes for {season_name}")

    for ep in episodes:
        _download_episode_worker(ep, season_dir)


def _download_episode_worker(ep, season_dir):
    item_id = ep["Id"]
    container_raw = ep.get("Container", "mkv")
    container = container_raw.split(",")[0].strip()  # Fix extension by picking the first

    ep_num = ep.get("IndexNumber")
    season_num = ep.get("ParentIndexNumber")

    filename = safe(ep.get("Name", item_id))
    if season_num and ep_num:
        filename = f"S{season_num:02d}E{ep_num:02d} - {filename}"

    filename = f"{filename}.{container}"

    if season_dir is None:
        season_dir = DOWNLOAD_ROOT

    path = os.path.join(season_dir, filename)

    if os.path.exists(path):
        print("Already exists, skipping:", filename)
        return

    url = f"{BASE_URL}/Items/{item_id}/Download"
    print("Downloading:", filename)

    try:
        with requests.get(url, headers=HEADERS, stream=True, timeout=60) as r:
            r.raise_for_status()
            with open(path, "wb") as f:
                for chunk in r.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        f.write(chunk)

        print("Finished:", filename)

    except Exception as e:
        print("Download failed:", filename, e)

# =========================
# Helpers
# =========================

def safe(name: str) -> str:
    return "".join(c for c in name if c not in r'\/:*?"<>|').strip()
