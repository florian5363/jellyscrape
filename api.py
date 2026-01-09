import requests
import json

with open("data.txt", "r") as file:
    BASE_URL = file.readline().strip()
    API_KEY = file.readline().strip()
    USERNAME = file.readline().strip()

HEADERS = {
    "X-Emby-Token": API_KEY,
    "Accept": "application/json"
}


# =====================
# User & Libraries
# =====================

def get_user_id():
    r = requests.get(f"{BASE_URL}/Users", headers=HEADERS, timeout=10)
    r.raise_for_status()
    for user in r.json():
        if user.get("Name") == USERNAME:
            return user["Id"]
    raise RuntimeError("User not found")


def get_libraries(user_id):
    r = requests.get(
        f"{BASE_URL}/Users/{user_id}/Views",
        headers=HEADERS,
        timeout=10
    )
    r.raise_for_status()
    return r.json().get("Items", [])


# =====================
# Items per Library
# =====================

def get_library_items(user_id, library_id):
    items = []
    start_index = 0
    limit = 500

    while True:
        params = {
            "ParentId": library_id,
            "Recursive": "true",
            "StartIndex": start_index,
            "Limit": limit,
            # Request EVERYTHING useful
            "Fields": (
                "Id,Name,Type,Path,ParentId,IndexNumber,"
                "ParentIndexNumber,SeriesId,SeasonId,Container,"
                "MediaType,LocationType"
            )
        }

        r = requests.get(
            f"{BASE_URL}/Users/{user_id}/Items",
            headers=HEADERS,
            params=params,
            timeout=30
        )
        r.raise_for_status()

        data = r.json()
        batch = data.get("Items", [])
        if not batch:
            break

        items.extend(batch)
        start_index += len(batch)

        if start_index >= data.get("TotalRecordCount", 0):
            break

    return items


# =====================
# Main
# =====================

def main():
    user_id = get_user_id()
    print("UserId:", user_id)

    libraries = get_libraries(user_id)
    print(f"Libraries found: {len(libraries)}\n")

    all_data = {}

    for lib in libraries:
        lib_id = lib["Id"]
        lib_name = lib.get("Name", "Unknown")

        print(f"Scraping library: {lib_name}")

        items = get_library_items(user_id, lib_id)

        print(f"  Items found: {len(items)}")

        all_data[lib_name] = {
            "LibraryId": lib_id,
            "CollectionType": lib.get("CollectionType"),
            "Items": items
        }

    # Save everything
    with open("all_items.json", "w", encoding="utf-8") as f:
        json.dump(all_data, f, indent=2, ensure_ascii=False)

    print("\nSaved ALL libraries to all_items.json")


if __name__ == "__main__":
    main()
