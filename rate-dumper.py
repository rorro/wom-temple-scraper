#!/usr/bin/env python
import argparse
import json
from bs4 import BeautifulSoup
import re
from dataclasses import dataclass, field
from typing import List
import requests
from itertools import tee, zip_longest
from collections import defaultdict
import os
from inspect import signature
from pprint import pprint

EHP_PAGES = {
    "main": "https://templeosrs.com/efficiency/skilling.php",
    "ironman": "https://templeosrs.com/efficiency/skilling.php?ehp=im",
    "uim": "https://templeosrs.com/efficiency/skilling.php?ehp=uim",
    "f2p": "https://templeosrs.com/efficiency/skilling.php?ehp=f2p",
    "lvl3": "https://templeosrs.com/efficiency/skilling.php?ehp=lvl3",
    "f2p_ironman": "https://templeosrs.com/efficiency/skilling.php?ehp=f2pim",
    "f2p_lvl3": "https://templeosrs.com/efficiency/skilling.php?ehp=f2plvl3"
}

EHB_PAGES = {
    "main": "https://templeosrs.com/efficiency/pvm.php",
    "ironman": "https://templeosrs.com/efficiency/pvm.php?ehb=im",
}

MISC_PAGES = {"main": "https://templeosrs.com/efficiency/misc.php"}


class WomFormatDumper:
    """
    This is stupid, but we can't just simply dump this to json
    because it's some weird ts format
    This outputs a rough outline that we have prettier handle later on
    """

    @staticmethod
    def dumps(data, depth=0, indent=2, move=True):
        if not move:
            depth = 0
        if data is None:
            return "null"
        elif isinstance(data, list):
            if not data:
                return "[]"
            return (
                "[\n"
                + ",\n".join([WomFormatDumper.dumps(d, depth + indent)
                             for d in data])
                + " " * depth
                + "\n]"
            )
        elif isinstance(data, dict):
            return (
                " " * depth
                + "{\n"
                + " " * (depth + indent)
                + f",\n{' '*(depth+indent)}".join(
                    key + ": " + WomFormatDumper.dumps(val, depth + indent)
                    for key, val in data.items()
                )
                + "\n"
                + " " * depth
                + "}"
            )
        elif isinstance(data, bool):
            return "true" if data else "false"
        elif isinstance(data, int):
            return f"{data:_}"
        elif isinstance(data, float):
            return f"{data:g}"
        elif isinstance(data, str):
            if (data.startswith("Skill.")):
                return data
            return "'" + data.replace("'", "\\'") + "'"


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
            level, xp, rate, description, bxp = data
            method = TempleEhpMethod(
                to_int(xp.getText()), to_int(
                    rate.getText()), description.getText()
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


def boss_sort_key(entry):
    return entry.name.split('Boss.')[1]


def save_to(path, info, move=True):
    dump = WomFormatDumper.dumps(info, move=move)
    if not move:
        # The lack of newlines makes prettier format this into a
        # more compact format
        dump = dump.replace("\n", "")

    dumping_ehp = "ehp" in path
    with open(path, "w") as file:
        file.write(
            "import { " + ("Skill" if dumping_ehp else "Boss") + " } from '../../../../../utils';\n\n")
        file.write("export default ")
        file.write(dump.replace("'", "").replace(
            "\\", "") if not dumping_ehp else dump)
        file.write(";")


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
        choices=["ehp", "ehb", "misc"],
    )
    parser.add_argument("path", action="store",
                        help="the path to the output folder")

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
    summary = parse_summary_table(tables[0])

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
    return summary, entries


def parse_summary_table(t):
    summ = {}
    # skip the table header, we know what is in the table
    for row in t.findAll("tr")[1:]:
        img, xp_left, amount_bxp, hours = row.findAll("td")
        skill = extract_skill_from_icon_path(img.find("img").get("src"))
        xp_left = to_int(xp_left.getText())
        amount_bxp = to_int(amount_bxp.getText())
        hours = float(hours.getText().replace(",", ""))
        summ[skill] = {"xpLeft": xp_left,
                       "amountBxp": amount_bxp, "hours": hours}
    return summ


def extract_skill_from_icon_path(path):
    n = path.split("_")[-1].split(".")[0].lower()
    return n if n != "runecraft" else "runecrafting"


def parse_ehb_page(raw):
    soup = BeautifulSoup(raw, "html.parser")
    table = soup.find(id="comp-table")
    entries = []
    for row in table.findAll("tr"):
        data = row.findAll("td")
        if not data:
            continue
        boss, killph, pet_rate, avg_pet_ehb, avg_gp_kill = data
        name = boss.find("img").get("title").lower().replace(" ", "_")
        name = convert_boss_name(name)
        rate = float(killph.getText())
        entries.append(TempleEhbEntry(name, rate))
    return entries


def convert_boss_name(name):
    return "Boss." + convert_to_wom_name(name).upper().replace('-', '_')


def convert_to_wom_name(name):
    if name == "the_nightmare":
        return "nightmare"
    if name == "theatre_of_blood_challenge_mode":
        return "theatre_of_blood_hard_mode"
    if name == "chambers_of_xeric_challenge_mode":
        return "chambers_of_xeric_cm"
    return name


def parse_misc_page(raw):
    return parse_ehb_page(raw)


def capitalize_first_letter(s):
    if s:
        return s[0].upper() + s[1:]
    return s


def convert_skill_name(name):
    return "Skill." + (name.upper() if name != "runecraft" else "RUNECRAFTING")


def convert_ehp_to_wom_format(entry, entries):
    # Wom uses runecrafting :/
    name = convert_skill_name(entry.name)
    d = {"skill": name, "methods": [], "bonuses": []}
    sieve = defaultdict(list)
    saved_start = None

    for method, next_method in pairwise(entry.methods):
        d["methods"].append(
            {
                "startExp": method.start_xp,
                "rate": method.rate,
                "description": capitalize_first_letter(method.description),
            }
        )

        # Adjacent bonuses need to be cleaned up
        ugly_bonuses = [
            {
                "originSkill": convert_skill_name(entry.name),
                "bonusSkill": convert_skill_name(bonus.skill),
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
    return {"boss": entry.name, "rate": entry.rate}


def account_for_not_updated_iron_ehb(main_entries, iron_entries):
    modified_iron_entries = []
    for entry in iron_entries:
        mainrate = [e.rate for e in main_entries if e.name == entry.name]
        if not mainrate:
            modified_iron_entries.append(entry)
            continue
        mainrate = mainrate[0]

        # Iron rate is always lower or equal to main rate since it's not really updated as well
        modified_iron_entries.append(
            TempleEhbEntry(entry.name, min(entry.rate, mainrate))
        )
    return modified_iron_entries


def convert_misc_to_wom_format(entry):
    return {"metric": entry.name.replace("-", "_"), "rate": entry.rate}


def convert_format(converter, entries):
    sig = signature(converter)

    if len(sig.parameters) == 2:
        return [converter(entry, entries) for entry in entries]
    return [converter(entry) for entry in entries]


def dump_ehb(path):
    # Grab rates for main and iron simultaneously since wee need to compare them
    # Only main rates are updated
    mainraw = fetch_page(EHB_PAGES["main"])
    main_entries = sorted(parse_ehb_page(mainraw), key=boss_sort_key)
    wom_formatted_main = convert_format(
        convert_ehb_to_wom_format, main_entries)
    save_to(os.path.join(path, f"main.ehb.ts"), wom_formatted_main, move=False)

    ironraw = fetch_page(EHB_PAGES["ironman"])
    iron_entries = parse_ehb_page(ironraw)

    # Correct outdated rates because they are not actively used
    modified_iron_entries = sorted(account_for_not_updated_iron_ehb(
        main_entries, iron_entries), key=boss_sort_key)

    wom_formatted_iron = convert_format(
        convert_ehb_to_wom_format, modified_iron_entries)

    save_to(os.path.join(path, f"ironman.ehb.ts"),
            wom_formatted_iron, move=False)
    save_to(os.path.join(path, f"uim.ehb.ts"), wom_formatted_iron, move=False)

    # Zero out any rates for f2p or lvl3
    lvl3_and_f2p_entries = [TempleEhbEntry(e.name, 0) for e in main_entries]
    wom_formatted_lvl3_and_f2p = convert_format(
        convert_ehb_to_wom_format, lvl3_and_f2p_entries
    )
    for name in ["lvl3", "f2p"]:
        save_to(
            os.path.join(path, f"{name}.ehb.ts"), wom_formatted_lvl3_and_f2p, move=False
        )


def dump_ehp(path):
    for name, url in EHP_PAGES.items():
        print(f"Dumping {name} EHP...")
        raw = fetch_page(url)
        summary, entries = parse_ehp_page(raw)
        wom_formatted = convert_format(convert_ehp_to_wom_format, entries)
        # add the maxBonus thing to the last bonus entry
        for skill in wom_formatted:
            if skill["bonuses"]:
                last_bonus = skill["bonuses"][-1]
                bskill = last_bonus["bonusSkill"]
                max_bonus = summary[bskill.split('.')[1].lower()]["amountBxp"]
                if max_bonus != 200_000_000 and bskill in ["fishing", "firemaking", "cooking", "smithing", "thieving"]:
                    last_bonus["maxBonus"] = max_bonus
        save_to(os.path.join(path, f"{name}.ehp.ts"), wom_formatted)


def dump_misc(path):
    main_raw = fetch_page(MISC_PAGES["main"])
    main_entries = parse_misc_page(main_raw)
    wom_formatted = convert_format(convert_misc_to_wom_format, main_entries)
    for name in EHP_PAGES.keys():
        save_to(os.path.join(path, f"{name}.ehp.ts"),
                wom_formatted, move=False)


def main():
    args = get_args()
    path = args["path"]
    if args["category"] == "ehp":
        print("Dumping ehp...")
        dump_ehp(path)
    elif args["category"] == "ehb":
        print("Dumping ehb...")
        dump_ehb(path)
    elif args["category"] == "misc":
        print("Dumping misc...")
        dump_misc(path)
    else:
        print("Invalid category")


if __name__ == "__main__":
    main()
