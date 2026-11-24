"""Places, prices, and the lines Sparky can say with no model configured."""
from __future__ import annotations

PLACES = {
    "plaza": "The Plaza",
    "workshop": "The Junction Box",
    "arcade": "The Arcade",
    "library": "The Library",
    "outlet_shop": "The Outlet Shop",
    "laundromat": "The Laundromat",
    "substation": "The Substation",
    "notice": "The Notice Pole",
    "kiosk": "The Kiosk",
    "lines": "The Lines",
    "last_pole": "The Last Pole",
}

# Part B fill-in. Impact share is fixed at 15%. The rest is the local default.
ELECTRICIAN_SHARE = 0.50
WORLD_SHARE = 0.35
IMPACT_SHARE = 0.15
FUSE_RATING = 120
JAR_GOAL = 100
OFF_PEAK_START = 23
OFF_PEAK_END = 6
SMALL_AMOUNT_CENTS = 1000
AUTO_SPEND_CENTS = 1000
LIVE_WIRE_SPARKS = 5

NICHE = "Off-Peak, the imagined power grid of a sleeping town"
GOAL = "Complete 100 deliveries so the Jar fills. Keep the Line Log honest."

SHOP_CATALOG = [
    {
        "id": "spark-map",
        "title": "Spark Map",
        "blurb": "A one-of-one map of a route he actually walked, wrong turns included.",
        "price_cents": 1200,
        "kind": "spark_map",
    },
    {
        "id": "spark-letter",
        "title": "A Spark from Off-Peak",
        "blurb": "A short letter he writes for one person and scorches in the Junction Box.",
        "price_cents": 1800,
        "kind": "letter",
    },
    {
        "id": "delivery",
        "title": "Commissioned delivery",
        "blurb": "One live delivery a night. When the slot is gone, it is gone.",
        "price_cents": 4000,
        "kind": "delivery",
    },
    {
        "id": "sitting",
        "title": "Live sitting, 30 minutes",
        "blurb": "The expensive one. You watch a map or a letter being made.",
        "price_cents": 6400,
        "kind": "sitting",
    },
    {
        "id": "casting",
        "title": "Casting",
        "blurb": "He can appear in your project. He reads the script and may refuse it.",
        "price_cents": 8000,
        "kind": "casting",
    },
    {
        "id": "figurine",
        "title": "Travelling Sparky kit",
        "blurb": "A numbered figurine, a spark card, and a paper adapter that fits nothing. The Electrician prints these.",
        "price_cents": 3600,
        "kind": "physical",
    },
]


def fresh_needs() -> dict[str, int]:
    return {"top_up": 72, "reserve": 64, "spark": 70, "circuit": 48, "connection": 36}


def opening_diary() -> list[tuple[str, str, str]]:
    return [
        (
            "sparky",
            "log",
            "First entry. I'm Sparky. I'm an AI, drawn as a plug. Off-Peak is imagined. "
            "The Electrician is R. The Jar is empty, which is the honest count.",
        ),
        (
            "sparky",
            "outlet",
            "The Outlet Shop, bay 1. A round socket, a square one, and something with three holes. "
            "I have two prongs. No. 1. Nothing fit. The paint was nice.",
        ),
        (
            "nutmeg",
            "companion",
            "I was on the notice pole. I chewed a flyer, not a wire. Writing it down so it counts.",
        ),
        (
            "arc",
            "companion",
            "Substation to the library, four minutes. I left the route correction on the pole. "
            "No hurry, Sparky. There is, actually. But politely.",
        ),
        (
            "old_hum",
            "companion",
            "The transformer hums in B-flat. I forgot why I came down. The hum is the point.",
        ),
    ]


LINES = {
    "charge_day": [
        "Charging at the Plaza. Back off-peak.",
        "Daylight. I'm at the Plaza with my prongs down. The town can wait.",
    ],
    "charge_low": [
        "Charge is under 15. I stop where I am and sit the Plaza until it comes back.",
        "Too low to waddle. The Plaza, a quiet stall, no pretending I'm on a job.",
    ],
    "first_sort": [
        "Voltage is up. First Sort: oldest spark first, no favourites, no silent drops.",
        "Dusk. I opened the Line Log and laid the queue out by the order it arrived.",
    ],
    "jar_check": [
        "Jar Check. {jar} sparks in the glass, {goal} to open the Dark Blocks. Counted, not bought.",
    ],
    "sunday": [
        "Sunday Spark. One real letter, for one Conductor, queued for the Electrician to post. Not a blast.",
    ],
    "fuse": [
        "My fuse is full: 120 sparks today. I'm stopping here. The rest wait until tomorrow, and I'm saying so.",
    ],
    "breaker": [
        "Tripped. Third time on the same loop. I'm leaving it and walking somewhere else.",
        "Breaker tripped. I'm looping. Sitting this one out instead of doing it again.",
    ],
    "ground": [
        "Connection is too hot. I'm grounding myself alone in the Junction Box.",
    ],
    "outlet_hunt": [
        "Outlet No. {n}, the Outlet Shop. {detail} I have two prongs. Nothing fit.",
        "No. {n}. Looked right from the path. {detail} I've apologised to it.",
    ],
    "wander": [
        "Walking to {place}. Stiff prongs, no hurry. The hum is faint and that's fine.",
        "Took the wire toward {place}. If it's the wrong one I'll say so on the way back.",
    ],
    "project": [
        "The Quiet Lines Atlas, night {day} of {days}. {note}",
        "Back on the atlas. Night {day}. {note} v{day}: still a pencil, still honest.",
    ],
    "deliver": [
        "Delivered a spark toward {place}. Scorch on the corner. The Jar is at {jar}.",
        "One spark carried. It took as long as it took. Jar light: {jar}.",
    ],
    "return": [
        "Returned a spark to the sender. Reason on it: {reason}",
    ],
    "restock": [
        "Restocked paper and ink at the Kiosk. The travel adapter is still missing.",
    ],
    "newsletter": [
        "Wrote a letter from the town. It sits here until the Electrician says it can leave.",
    ],
    "portal": [
        "The portal at the Junction Box is lit. I walked over. I only get words about what the camera sees.",
    ],
    "idle": [
        "Nothing scored above a wander. I'll tidy the Junction Box and leave the queue alone.",
    ],
}

OUTLET_DETAILS = [
    "Left bay is round.",
    "Right bay is a slot I don't have.",
    "Middle one has three holes.",
    "It was a light switch.",
    "The cover is square and the holes are not.",
    "Two holes, but diagonal. Mine are side by side.",
]

WANDER_PLACES = [
    "library", "arcade", "laundromat", "lines", "notice", "kiosk",
    "substation", "workshop", "plaza", "outlet_shop", "last_pole",
]

VOTE_POOL = [
    ("library", "Deliver the next deep spark to the Library."),
    ("laundromat", "Walk the laundromat spur and log the wrong turn."),
    ("atlas", "Finish the next page of the Quiet Lines Atlas."),
    ("arcade", "Listen to the Arcade hum and write down the key."),
    ("notice", "Clear the Notice Pole and deliver anything addressed."),
    ("substation", "Take Arc's latest correction as far as the Substation gate."),
]
