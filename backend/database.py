import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "inventory.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS inventory (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id TEXT NOT NULL,
    name TEXT NOT NULL,
    description TEXT NOT NULL,
    price REAL NOT NULL,
    quantity INTEGER NOT NULL,
    category TEXT NOT NULL
);
"""

# Siq - Pacific Gems: a small, curated line of certified fine gemstones.
# Low quantities (often 1) is intentional - these are individual stones.
SIQ_ITEMS = [
    ("Ceylon Blue Sapphire 2.10ct", "Oval cut, GIA certified, unheated, Sri Lanka.", 3200.00, 1, "Sapphire"),
    ("Colombian Emerald 1.45ct", "Emerald cut, minor natural inclusions, Colombia.", 2850.00, 1, "Emerald"),
    ("Burmese Ruby 1.02ct", "Round brilliant, vivid red, unheated, Myanmar.", 4100.00, 1, "Ruby"),
    ("Paraiba Tourmaline 0.85ct", "Oval cut, neon blue-green, Mozambique.", 5600.00, 1, "Tourmaline"),
    ("Padparadscha Sapphire 1.30ct", "Cushion cut, pinkish-orange, Sri Lanka.", 6800.00, 1, "Sapphire"),
    ("Tanzanite 3.20ct", "Trillion cut, vivid violet-blue, Tanzania.", 1900.00, 2, "Tanzanite"),
    ("Vivid Pink Spinel 1.15ct", "Oval cut, natural, no heat treatment, Burma.", 1350.00, 3, "Spinel"),
    ("Santa Maria Aquamarine 4.50ct", "Emerald cut, deep sea-blue, Brazil.", 980.00, 2, "Aquamarine"),
    ("Alexandrite 0.62ct", "Round cut, distinct color-change, Brazil.", 3400.00, 1, "Alexandrite"),
    ("Black Opal 2.80ct", "Freeform cabochon, strong play-of-color, Lightning Ridge, Australia.", 2200.00, 1, "Opal"),
]

# Bucks - fast-moving, multi-source stock. Higher quantities, lower prices,
# lots of origins, meant to feel like it turns over quickly.
BUCKS_ITEMS = [
    ("Citrine Cluster Lot (15ct)", "Mixed small citrine pieces, natural color, Brazil.", 45.00, 40, "Citrine"),
    ("Amethyst Point (8ct)", "Natural terminated point, Uruguay.", 22.00, 60, "Amethyst"),
    ("Rainbow Moonstone Cabochon (3.5ct)", "Strong blue flash, India.", 18.00, 35, "Moonstone"),
    ("Garnet Melee 5-Pack (0.20ct ea)", "Small calibrated rounds, mixed origin.", 12.00, 100, "Garnet"),
    ("Peridot 1.8ct", "Round cut, olive-green, Pakistan.", 35.00, 25, "Peridot"),
    ("Smoky Quartz 6ct", "Pear cut, warm brown, Brazil.", 15.00, 50, "Quartz"),
    ("Labradorite Slab (40mm)", "Polished, strong blue schiller, Madagascar.", 28.00, 20, "Labradorite"),
    ("Blue Zircon 1.2ct", "Round cut, high fire, Cambodia.", 60.00, 15, "Zircon"),
    ("Rose Quartz Sphere (30mm)", "Polished, soft pink, Brazil.", 25.00, 30, "Quartz"),
    ("Turquoise Cabochon 4ct", "Natural, robin's-egg blue with light matrix, Nevada USA.", 40.00, 18, "Turquoise"),
]


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(reset: bool = False):
    """Create the inventory table and seed it if empty (or always, if reset=True)."""
    conn = get_connection()
    cur = conn.cursor()
    if reset:
        cur.execute("DROP TABLE IF EXISTS inventory")
    cur.executescript(SCHEMA)

    cur.execute("SELECT COUNT(*) FROM inventory")
    count = cur.fetchone()[0]

    if count == 0:
        for name, desc, price, qty, cat in SIQ_ITEMS:
            cur.execute(
                "INSERT INTO inventory (agent_id, name, description, price, quantity, category) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                ("siq", name, desc, price, qty, cat),
            )
        for name, desc, price, qty, cat in BUCKS_ITEMS:
            cur.execute(
                "INSERT INTO inventory (agent_id, name, description, price, quantity, category) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                ("bucks", name, desc, price, qty, cat),
            )
        conn.commit()

    conn.close()


def search_inventory(agent_id: str, query: str, limit: int = 8):
    conn = get_connection()
    cur = conn.cursor()
    like = f"%{query}%"
    cur.execute(
        """
        SELECT id, name, description, price, quantity, category FROM inventory
        WHERE agent_id = ?
          AND (name LIKE ? OR description LIKE ? OR category LIKE ?)
        LIMIT ?
        """,
        (agent_id, like, like, like, limit),
    )
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def list_inventory(agent_id: str):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, name, description, price, quantity, category FROM inventory WHERE agent_id = ? ORDER BY name",
        (agent_id,),
    )
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def get_item(agent_id: str, item_id: int):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, name, description, price, quantity, category FROM inventory WHERE agent_id = ? AND id = ?",
        (agent_id, item_id),
    )
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None
