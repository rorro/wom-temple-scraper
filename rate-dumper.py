#!/usr/bin/env python
import argparse
import json
from bs4 import BeautifulSoup
import re
from dataclasses import dataclass, field
from typing import List
import requests
from pprint import pprint
from itertools import tee, zip_longest
from collections import defaultdict

EHP_PAGES = {
    "main": "https://templeosrs.com/efficiency/skilling.php",
    "ironman": "https://templeosrs.com/efficiency/skilling.php?ehp=im",
    "f2p": "https://templeosrs.com/efficiency/skilling.php?ehp=f2p",
    "lvl3": "https://templeosrs.com/efficiency/skilling.php?ehp=lvl3",
}

EHB_PAGES = {
    "main": "https://templeosrs.com/efficiency/pvm.php",
    "ironman": "https://templeosrs.com/efficiency/pvm.php?ehb=im",
}

MISC_PAGES = {"main": "https://templeosrs.com/efficiency/misc.php"}

PAGES = {"ehp": EHP_PAGES, "ehb": EHB_PAGES, "misc": MISC_PAGES}


@dataclass
class TempleEhpMethodBonus:
    skill: str
    ratio: float


@dataclass
class TempleEhpMethod:
    start_xp: int
    rate: float
    description: str
    bonuses: List[TempleEhpMethodBonus] = field(default_factory=list)

    def parse_bxp(self, bxp):
        if bxp.getText() in {"-", ""}:
            return
        skills = [tag.get("title").lower() for tag in bxp.findAll("img")]
        ratios = [float(tag.getText()) for tag in bxp.findAll("p")]

        for skill, ratio in zip(skills, ratios):
            self.bonuses.append(TempleEhpMethodBonus(skill, ratio))


@dataclass
class TempleEhpEntry:
    name: str
    # If starting xp is 0, then any bonus xp awarded to this skill is endXp
    start_xp: int
    methods: List[TempleEhpMethod] = field(default_factory=list)

    def parse_table(self, table):
        for row in table.findAll("tr"):
            data = row.findAll("td")
            if not data:
                continue
            xp, rate, description, bxp = data
            method = TempleEhpMethod(
                to_int(xp.getText()), to_int(rate.getText()), description.getText()
            )
            method.parse_bxp(bxp)
            self.methods.append(method)


@dataclass
class TempleEhbEntry:
    name: str
    rate: float


def to_int(text):
    subbed = re.sub("\D", "", text)
    return int(subbed) if subbed else 0


def pairwise(iterable):
    "s -> (s0,s1), (s1,s2), (s2, s3), (s3, None)"
    a, b = tee(iterable)
    next(b, None)
    return zip_longest(a, b)


def save_to(path, info):
    with open(path, "w") as file:
        file.write("export default\n")
        json.dump(info, file, indent=2)


def dir_path(string):
    if os.path.isdir(string):
        return string
    else:
        raise NotADirectoryError(string)


def get_args():
    parser = argparse.ArgumentParser(description="dump temple rates")
    parser.add_argument(
        "category",
        action="store",
        help="the rate category to dump",
        choices=list(PAGES.keys()) + ["all"],
    )
    parser.add_argument("path", action="store", help="the path to the output folder")

    args = vars(parser.parse_args())
    return args


def fetch_page(url):
    response = requests.get(url)
    if response.status_code != 200:
        response.raise_for_status()

    return response.content


def parse_ehp_page(raw):
    soup = BeautifulSoup(raw, "html.parser")
    tables = soup.findAll(id="comp-table")
    entries = []

    # First table is the summary table
    for table in tables[1:]:

        if table.find("div", {"class": "news-post-container"}):
            # These are the More info+ description boxes
            continue
        maybe_name = table.find_previous_sibling("p")

        if "small-red-text-ehp" not in maybe_name.get("class", []):
            name = maybe_name.getText().lower()
            start_xp = 0
        else:
            # The skill has start_xp so the name is the next sibling
            name = maybe_name.find_previous_sibling("p").getText().lower()
            start_xp = to_int(maybe_name.getText())

        entry = TempleEhpEntry(name, start_xp)
        entry.parse_table(table)
        entries.append(entry)
    return entries


def parse_ehb_page(raw):
    soup = BeautifulSoup(raw, "html.parser")
    table = soup.find(id="comp-table")
    entries = []
    for row in table.findAll("tr"):
        data = row.findAll("td")
        if not data:
            continue
        boss, killph, pet_rate, avg_pet_ehb = data
        name = boss.find("img").get("title").lower().replace(" ", "_")
        rate = float(killph.getText())
        entries.append(TempleEhbEntry(name, rate))
        print(name, rate)
    return entries


def parse_misc_page(raw):
    return parse_ehb_page(raw)


def convert_ehp_to_wom_format(entry, entries):
    d = {"skill": entry.name, "methods": [], "bonuses": []}
    sieve = defaultdict(list)
    saved_start = None

    for method, next_method in pairwise(entry.methods):
        d["methods"].append(
            {
                "startExp": method.start_xp,
                "rate": method.rate,
                "description": method.description,
            }
        )

        # Adjacent bonuses need to be cleaned up
        ugly_bonuses = [
            {
                "originSkill": entry.name,
                "bonusSkill": bonus.skill,
                "startExp": method.start_xp,
                "endExp": next_method.start_xp
                if next_method is not None
                else 200_000_000,
                "end": any(e.name == bonus.skill and e.start_xp == 0 for e in entries),
                "ratio": bonus.ratio,
            }
            for bonus in method.bonuses
        ]
        for bonus in ugly_bonuses:
            sieve[bonus["bonusSkill"]].append(bonus)

    for v in sieve.values():
        for b1, b2 in pairwise(v):
            if b2 is None or b1["ratio"] != b2["ratio"]:
                bonus = b1
            else:
                if saved_start is None:
                    saved_start = b1["startExp"]
                continue

            if saved_start is not None:
                bonus["startExp"] = saved_start
                saved_start = None
            d["bonuses"].append(bonus)
    return d


def convert_ehb_to_wom_format(entry):
    pass


def main():
    args = get_args()
    if args["category"] == "ehp":
        for name, url in EHP_PAGES.items():
            raw = fetch_page(url)
            entries = parse_ehp_page(raw)
            wom_formatted = [
                convert_ehp_to_wom_format(entry, entries) for entry in entries
            ]
            save_to(f"{name}.ehp.ts", wom_formatted)

    elif args[category] == "ehb":
        pass

    elif args[category] == "misc":
        pass

    elif args["all"]:
        pass
    else:
        print("Invalid category")


if __name__ == "__main__":
    main()
