#!/usr/bin/env python3
import argparse
import json

from bs4 import BeautifulSoup
import re
from datetime import datetime
from pprint import pprint
from pathlib import Path


import requests

PAGES = {
    "main": "https://templeosrs.com/efficiency/skilling.php",
    "iron": "https://templeosrs.com/efficiency/skilling.php?ehp=im",
    "f2p": "https://templeosrs.com/efficiency/skilling.php?ehp=f2p",
    "lvl3": "https://templeosrs.com/efficiency/skilling.php?ehp=lvl3",
    "misc": "https://templeosrs.com/efficiency/misc.php",
    "ehb": "https://templeosrs.com/efficiency/pvm.php",
}

# Is the bonus xp start or end xp,m determined by the method
END_BXP = {
    "main": {
        "slayer": False,
        "mining": True,
        "firemaking": True,
        "woodcutting": True,
        "fishing": False,
    },
    "iron": {"slayer": False, "fishing": False},
    "f2p": {"firemaking": True, "mining": False},
    "lvl3": {"woodcutting": True, "firemaking": True, "mining": True},
}


def main():
    parser = argparse.ArgumentParser(description="dump temple rates")
    parser.add_argument(
        "type",
        action="store",
        help="the ehp type to dump",
        choices=list(PAGES.keys()) + ["all"],
    )

    args = vars(parser.parse_args())

    ts = datetime.now().date().isoformat()

    Path("current").mkdir(parents=True, exist_ok=True)
    Path("history").mkdir(parents=True, exist_ok=True)

    if args["type"] == "all":
        for rate in PAGES.keys():
            if not rate in {"ehb", "misc"}:
                Path(f"current/{rate}").mkdir(parents=True, exist_ok=True)
                Path(f"history/{ts}/{rate}").mkdir(parents=True, exist_ok=True)
            if rate in {"ehb", "misc"}:
                dump_ehb_page(rate, ts)
            else:
                dump_ehp_page(rate, ts)
    elif args["type"] in {"ehb", "misc"}:
        dump_ehb_page(args["type"], ts)
    else:
        Path(f"current/{rate}").mkdir(parents=True, exist_ok=True)
        Path(f"history/{ts}/{rate}").mkdir(parents=True, exist_ok=True)
        dump_ehp_page(args["type"], ts)


def dump_ehp_page(ehp_type, timestamp):
    response = requests.get(PAGES[ehp_type])

    if response.status_code != 200:
        response.raise_for_status()

    soup = BeautifulSoup(response.content, "html.parser")

    rates = soup.findAll(id="comp-table")
    nameTags = soup.findAll("p", {"class": "records-small-title"})
    names = [name.getText().lower() for name in nameTags]

    start_rates = {
        name: tag.next_sibling
        if "small-red-text-ehp" in tag.next_sibling.get("class", [])
        else None
        for name, tag in zip(names, nameTags)
    }

    start_rates = {
        name: int(re.sub("\D", "", r.getText()))
        for name, r in start_rates.items()
        if r is not None
    }
    # filter out the stupid f2p descriptions
    skillrates = [
        rate
        for rate in rates[1:]
        if not rate.find("div", {"class": "news-post-container"})
    ]

    info = {"type": ehp_type, "date": timestamp, "skills": []}

    for name, skill in zip(names, skillrates):
        methods = []
        for row in skill.findAll("tr"):
            cols = row.findAll("td")
            if not cols:
                continue
            xp, rate, method, bxp = cols

            invalid = "strike" in rate.get("class", [])
            xprate = int(rate.getText().replace(",", ""))
            xpstart = int(xp.getText().replace(",", ""))
            description = method.getText()
            bxpentry = []

            if bxp.getText() not in {"-", ""}:
                bxpskills = [tag.get("title").lower() for tag in bxp.findAll("img")]
                bxprates = [float(tag.getText()) for tag in bxp.findAll("p")]
                bxpentry = [
                    {"skill": bskill, "ratio": ratio, "end": END_BXP[ehp_type][name]}
                    for bskill, ratio in zip(bxpskills, bxprates)
                ]

            method = {
                "startExp": xpstart,
                "rate": xprate,
                "description": description,
                "bonuses": bxpentry,
            }
            methods.append(method)
        # we want rc to be weird
        name = name if not name == "runecraft" else "runecrafting"

        info["skills"].append({"skill": name, "methods": methods})

    save_to(f"current/{ehp_type}/ehp.ts", info)
    save_to(f"history/{timestamp}/{ehp_type}/ehp.ts", info)


def dump_ehb_page(page_type, timestamp):
    response = requests.get(PAGES[page_type])

    if response.status_code != 200:
        response.raise_for_status()

    soup = BeautifulSoup(response.content, "html.parser")
    rates = soup.find(id="comp-table")

    info = {"type": page_type, "date": timestamp, "bosses": []}

    for row in rates.findAll("tr")[1:]:  # skip the th

        cols = row.findAll("td")
        if not cols:
            continue
        boss, killph, pet_rate, avg_pet_ehb = cols
        boss_name = boss.find("img").get("title").lower().replace(" ", "_")
        killph = float(killph.getText())
        info["bosses"].append({"boss": boss_name, "rate": killph})

    # Since we have no originality
    for account in list(PAGES.keys())[:4]:
        save_to(f"current/{account}/{page_type}.ts", info)
        save_to(f"history/{timestamp}/{account}/{page_type}.ts", info)


def save_to(path, info):
    with open(path, "w") as file:
        file.write("export default\n")
        json.dump(info, file, indent=2)


if __name__ == "__main__":
    main()
