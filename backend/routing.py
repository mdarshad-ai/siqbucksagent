"""
Pick which partner should answer an opening question from the homepage.

Deliberately simple and free (no AI call): count which partner's inventory
matches the question, nudged by budget and "fine stone" words. If the pick is
wrong, the partner can hand the customer over with refer_to_partner.
"""

import re

import database

BUDGET_WORDS = {
    "cheap", "cheapest", "budget", "affordable", "bargain", "deal", "deals",
    "gift", "gifts", "crystal", "crystals", "specimen", "specimens", "bulk",
    "lot", "sphere", "slab", "point", "cluster", "beads", "healing",
}
FINE_WORDS = {
    "certified", "certificate", "gia", "grs", "rare", "fine", "investment",
    "engagement", "unheated", "untreated", "heirloom", "provenance", "padparadscha",
    "paraiba", "alexandrite", "luxury",
}
_PRICE = re.compile(r"\$\s?([\d,]+(?:\.\d+)?)\s*(k)?", re.I)

# Which partner leans which way, by id. Unknown partners get no nudge.
LEANS = {"bucks": "budget", "siq": "fine"}
DEFAULT_AGENT = "siq"


def _mentioned_budget(text):
    amounts = []
    for number, thousand in _PRICE.findall(text):
        value = float(number.replace(",", ""))
        amounts.append(value * 1000 if thousand else value)
    return max(amounts) if amounts else None


def pick_agent(message: str) -> str:
    agents = [a["id"] for a in database.list_agents()]
    if not agents:
        return DEFAULT_AGENT
    words = set(re.findall(r"[a-z]+", message.lower()))
    budget = _mentioned_budget(message)

    scores = {}
    for agent_id in agents:
        matches = [i for i in database.search_items(agent_id, message) if i["status"] != "sold"]
        score = min(len(matches), 5)
        lean = LEANS.get(agent_id)
        if lean == "budget":
            score += 2 * len(words & BUDGET_WORDS)
            if budget is not None and budget <= 200:
                score += 3
        elif lean == "fine":
            score += 2 * len(words & FINE_WORDS)
            if budget is not None and budget >= 500:
                score += 3
        scores[agent_id] = score

    best = max(scores.values())
    winners = [a for a in agents if scores[a] == best]
    return DEFAULT_AGENT if DEFAULT_AGENT in winners else winners[0]
