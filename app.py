
from flask import Flask, request
from datetime import datetime
import sqlite3
import math

app = Flask(__name__)
DB_NAME = "parking.db"
TOTAL_SLOTS = 5

def connect_db():
    return sqlite3.connect(DB_NAME)

def setup_db():
    with connect_db() as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS parking (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                vehicle_number TEXT NOT NULL,
                vehicle_type TEXT NOT NULL,
                slot INTEGER NOT NULL,
                entry_time TEXT NOT NULL,
                exit_time TEXT,
                charge REAL DEFAULT 0
            )
        """)

def get_parked():
    with connect_db() as con:
        return con.execute("""
            SELECT vehicle_number, vehicle_type, slot, entry_time
            FROM parking
            WHERE exit_time IS NULL
            ORDER BY id
        """).fetchall()

@app.route("/", methods=["GET", "POST"])
def home():
    message = ""

    if request.method == "POST":
        action = request.form.get("action")
        number = request.form.get("number", "").strip().upper()

        if action == "entry":
            vehicle_type = request.form.get("type", "Bike")

            with connect_db() as con:
                existing = con.execute(
                    "SELECT id FROM parking WHERE vehicle_number=? AND exit_time IS NULL",
                    (number,)
                ).fetchone()

                if not number:
                    message = "Enter a vehicle number."
                elif existing:
                    message = "This vehicle is already parked."
                else:
                    occupied = {
                        row[0] for row in con.execute(
                            "SELECT slot FROM parking WHERE exit_time IS NULL"
                        ).fetchall()
                    }

                    free_slots = [
                        s for s in range(1, TOTAL_SLOTS + 1)
                        if s not in occupied
                    ]

                    if not free_slots:
                        message = "Parking is full!"
                    else:
                        con.execute("""
                            INSERT INTO parking
                            (vehicle_number, vehicle_type, slot, entry_time)
                            VALUES (?, ?, ?, ?)
                        """, (
                            number, vehicle_type, free_slots[0],
                            datetime.now().isoformat(timespec="seconds")
                        ))
                        message = f"{number} registered in Slot {free_slots[0]}."

        elif action == "exit":
            with connect_db() as con:
                vehicle = con.execute("""
                    SELECT id, vehicle_type, entry_time, slot
                    FROM parking
                    WHERE vehicle_number=? AND exit_time IS NULL
                    ORDER BY id DESC LIMIT 1
                """, (number,)).fetchone()

                if not vehicle:
                    message = "Vehicle not found."
                else:
                    vehicle_id, vehicle_type, entry_text, slot = vehicle
                    entry_time = datetime.fromisoformat(entry_text)
                    exit_time = datetime.now()
                    hours = max(1, math.ceil(
                        (exit_time - entry_time).total_seconds() / 3600
                    ))
                    rate = 20 if vehicle_type == "Bike" else 50
                    charge = hours * rate

                    con.execute("""
                        UPDATE parking
                        SET exit_time=?, charge=?
                        WHERE id=?
                    """, (
                        exit_time.isoformat(timespec="seconds"),
                        charge, vehicle_id
                    ))

                    message = (
                        f"{number} exited from Slot {slot}. "
                        f"Duration: {hours} hour(s). "
                        f"Charge: Rs. {charge}."
                    )

    parked = get_parked()
    available = TOTAL_SLOTS - len(parked)

    slots_html = ""
    for slot in range(1, TOTAL_SLOTS + 1):
        vehicle = next((v for v in parked if v[2] == slot), None)
        if vehicle:
            slots_html += (
                f'<span class="slot occupied">Slot {slot}<br>'
                f'Occupied<br>{vehicle[0]}</span>'
            )
        else:
            slots_html += (
                f'<span class="slot">Slot {slot}<br>Available</span>'
            )

    records_html = "<p>No vehicles currently parked.</p>"
    if parked:
        records_html = (
            "<table><tr><th>Vehicle</th><th>Type</th>"
            "<th>Entry Time</th><th>Slot</th></tr>"
        )
        for number, vtype, slot, entry in parked:
            records_html += (
                f"<tr><td>{number}</td><td>{vtype}</td>"
                f"<td>{entry.replace('T', ' ')}</td><td>{slot}</td></tr>"
            )
        records_html += "</table>"

    with connect_db() as con:
        total_revenue = con.execute(
            "SELECT COALESCE(SUM(charge), 0) FROM parking WHERE exit_time IS NOT NULL"
        ).fetchone()[0]
        history = con.execute("""
            SELECT vehicle_number, vehicle_type, entry_time, exit_time, charge
            FROM parking WHERE exit_time IS NOT NULL
            ORDER BY id DESC LIMIT 10
        """).fetchall()

    history_html = "<p>No completed parking transactions yet.</p>"
    if history:
        history_html = (
            "<table><tr><th>Vehicle</th><th>Type</th>"
            "<th>Entry</th><th>Exit</th><th>Charge</th></tr>"
        )
        for n, t, entry, exit_time, charge in history:
            history_html += (
                f"<tr><td>{n}</td><td>{t}</td>"
                f"<td>{entry.replace('T', ' ')}</td>"
                f"<td>{exit_time.replace('T', ' ')}</td>"
                f"<td>Rs. {charge:.0f}</td></tr>"
            )
        history_html += "</table>"

    message_html = (
        f'<p class="message">{message}</p>' if message else ""
    )

    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Parking Management System</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            body {{font-family:Arial;background:#eef3f8;margin:0;color:#203047}}
            header {{background:#173b67;color:white;padding:25px;text-align:center}}
            main {{max-width:950px;margin:25px auto;padding:15px}}
            .cards {{display:flex;gap:15px;flex-wrap:wrap}}
            .card,.panel {{background:white;border-radius:10px;padding:20px;margin-bottom:20px;box-shadow:0 2px 8px #0001}}
            .card {{flex:1;min-width:130px;text-align:center}}
            .number {{font-size:30px;font-weight:bold;color:#1768ac}}
            input,select,button {{box-sizing:border-box;width:100%;padding:12px;margin:8px 0;border-radius:6px;border:1px solid #ccd4df}}
            button {{background:#1768ac;color:white;border:0;cursor:pointer}}
            .slot {{display:inline-block;padding:15px;margin:5px;border-radius:7px;background:#e0f5e7;color:#176534}}
            .occupied {{background:#ffe2e2;color:#a52222}}
            .message {{background:#fff4ce;padding:15px;border-radius:7px}}
            table {{width:100%;border-collapse:collapse;display:block;overflow-x:auto;white-space:nowrap}}
            th,td {{padding:10px;border-bottom:1px solid #ddd;text-align:left}}
        </style>
    </head>
    <body>
        <header>
            <h1>Parking Management System</h1>
            <p>Vehicle Entry, Exit and Parking Charges</p>
        </header>
        <main>
            {message_html}
            <div class="cards">
                <div class="card">Total Slots<div class="number">{TOTAL_SLOTS}</div></div>
                <div class="card">Available<div class="number">{available}</div></div>
                <div class="card">Occupied<div class="number">{len(parked)}</div></div>
                <div class="card">Total Revenue<div class="number">Rs. {total_revenue:.0f}</div></div>
            </div>
            <div class="panel">
                <h2>Vehicle Entry</h2>
                <form method="POST">
                    <input type="hidden" name="action" value="entry">
                    <input name="number" placeholder="Vehicle Number e.g. KA09AB1234" required>
                    <select name="type">
                        <option>Bike</option><option>Car</option>
                    </select>
                    <button type="submit">Register Vehicle</button>
                </form>
            </div>
            <div class="panel">
                <h2>Parking Slots</h2>{slots_html}
            </div>
            <div class="panel">
                <h2>Currently Parked Vehicles</h2>{records_html}
                <h2>Vehicle Exit</h2>
                <form method="POST">
                    <input type="hidden" name="action" value="exit">
                    <input name="number" placeholder="Vehicle Number" required>
                    <button type="submit">Calculate Charge and Exit</button>
                </form>
                <p>Bike: Rs. 20/hour | Car: Rs. 50/hour. Partial hours round up.</p>
            </div>
            <div class="panel">
                <h2>Recent Completed Transactions</h2>{history_html}
            </div>
        </main>
    </body>
    </html>
    """

if __name__ == "__main__":
    setup_db()
    app.run(debug=True)
