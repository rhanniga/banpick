import os
import requests
import dotenv
import re
import time

from concurrent.futures import ThreadPoolExecutor
from fastapi import FastAPI, Form
from fastapi.requests import Request
from fastapi.responses import JSONResponse
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates


dotenv.load_dotenv()

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")

templates = Jinja2Templates(directory="templates")


MAPS = {
    "de_ancient",
    "de_dust2",
    "de_inferno",
    "de_mirage",
    "de_nuke",
    "de_train",
    "de_anubis",
}

API_KEY = os.getenv("FACEIT_API_KEY")

HEADERS = {
    'Authorization': f'Bearer {API_KEY}',
    'Accept': 'application/json'
}


@app.get("/")
def read_root(request: Request):
    return templates.TemplateResponse(request=request, name="index.html.jinja")

@app.get("/form")
def read_root(request: Request):
    return templates.TemplateResponse(request=request, name="form.html.jinja")

@app.post("/match")
def analyze_match(request : Request, match_url : str = Form(...), query_length : str = Form("past_20")):

    pattern = re.compile(r"https://www\.faceit\.com/en/cs2/room/1-([\w-]+)")
    match = pattern.match(match_url)

    if not match:
        return HTMLResponse(content="Invalid match URL", status_code=400)

    match_id = "1-" + match.group(1)
    try: 
        if query_length == "all_time":
            optimal_maps = get_optimal_maps(match_id, num_matches=100)
        else:
            optimal_maps = get_optimal_maps(match_id)
    except:
        return HTMLResponse(content="An error occurred while fetching the data", status_code=500)

    return templates.TemplateResponse(name="maps.html.jinja", context={"request" : request, "optimal_maps": optimal_maps})

def get_optimal_maps(match_id: str, num_matches: int=20):
    response = requests.get(f'https://open.faceit.com/data/v4/matches/{match_id}', headers=HEADERS).json()['teams']
    faction_1, faction_2 = response['faction1'], response['faction2']
    roster_1, roster_2 = faction_1['roster'], faction_2['roster']

    roster_1_winloss, roster_2_winloss = calculate_winloss(roster_1, roster_2, num_matches)

    roster_1_winrates = {map_name: round(wins / (wins + losses), 3) for map_name, (wins, losses) in roster_1_winloss.items()}
    roster_2_winrates = {map_name: round(wins / (wins + losses), 3) for map_name, (wins, losses) in roster_2_winloss.items()}

    sorted_maps_1 = sorted(MAPS, key=lambda map_name: roster_1_winrates[map_name] - roster_2_winrates[map_name], reverse=True)
    sorted_maps_2 = sorted(MAPS, key=lambda map_name: roster_2_winrates[map_name] - roster_1_winrates[map_name], reverse=True)

    sorted_maps_with_diff_1 = [(map_name, round(roster_1_winrates[map_name] - roster_2_winrates[map_name], 2)) for map_name in sorted_maps_1]
    sorted_maps_with_diff_2 = [(map_name, round(roster_2_winrates[map_name] - roster_1_winrates[map_name], 2)) for map_name in sorted_maps_2]

    optimal_maps = {
        "roster_1": {
            "name": faction_1['name'],
            "sorted_maps": sorted_maps_with_diff_1
        },
        "roster_2": {
            "name": faction_2['name'],
            "sorted_maps": sorted_maps_with_diff_2
        }
    }

    return optimal_maps

def fetch_player_stats(player_id, num_matches):
    url = f"https://open.faceit.com/data/v4/players/{player_id}/games/cs2/stats"
    query = {
        "offset": 0,
        "limit": num_matches
    }
    response = requests.get(url, headers=HEADERS, params=query)
    return response.json()["items"]

def calculate_winloss(roster_1, roster_2, num_matches):
    with ThreadPoolExecutor() as executor:
        items_list = list(executor.map(lambda player: fetch_player_stats(player['player_id'], num_matches), roster_1 + roster_2))

    roster_1_size = len(roster_1)

    roster_1_winloss, roster_2_winloss = (
        {map_name: [0, 0] for map_name in MAPS} for _ in range(2)
    )

    for player_index, items in enumerate(items_list):
        for item in items:
            stats = item["stats"]
            map_name = stats["Map"]
            if map_name not in MAPS:
                continue
            if stats["Result"] == "1":
                if player_index < roster_1_size:
                    roster_1_winloss[map_name][0] += 1
                else:
                    roster_2_winloss[map_name][0] += 1
            else:
                if player_index < roster_1_size:
                    roster_1_winloss[map_name][1] += 1
                else:
                    roster_2_winloss[map_name][1] += 1

    print(roster_1_winloss["de_ancient"], roster_2_winloss["de_ancient"])
    return roster_1_winloss, roster_2_winloss

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
