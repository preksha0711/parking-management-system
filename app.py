
from flask import Flask, request
from datetime import datetime
import sqlite3
import math
import html
import re

app = Flask(__name__)

# Separate test database: does not use your live database.
DB_NAME = "parking.db"

SLOTS_PER_BASEMENT = 5
BASEMENTS = ["Basement 1", "Basement 2"]
TOTAL_SLOTS = SLOTS_PER_BASEMENT * len(BASEMENTS)


def connect_db():
    con = sqlite3.connect(DB_NAME)
    con.row_factory = sqlite3.Row
    return con


def setup_db():
    with connect_db() as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS parking (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                vehicle_number TEXT NOT NULL,
                vehicle_type TEXT NOT NULL,
                slot INTEGER NOT NULL,
                basement TEXT NOT NULL DEFAULT 'Basement 1',
                entry_time TEXT NOT NULL,
                exit_time TEXT,
                charge REAL DEFAULT 0
            )
        """)

        # Safely add the basement column if an older test database exists.
        columns = {
            row["name"]
            for row in con.execute("PRAGMA table_info(parking)").fetchall()
        }

        if "basement" not in columns:
            con.execute("""
                ALTER TABLE parking
                ADD COLUMN basement TEXT NOT NULL DEFAULT 'Basement 1'
            """)


def get_parked():
    with connect_db() as con:
        return con.execute("""
            SELECT vehicle_number, vehicle_type, slot, entry_time, basement
            FROM parking
            WHERE exit_time IS NULL
            ORDER BY
                CASE basement
                    WHEN 'Basement 1' THEN 1
                    ELSE 2
                END,
                slot
        """).fetchall()


@app.route("/", methods=["GET", "POST"])
def home():
    message = ""
    message_type = "info"

    if request.method == "POST":
        action = request.form.get("action", "")
        number = request.form.get("number", "").strip().upper()

        if not number:
            message = "Please enter a vehicle number."
            message_type = "error"

        elif len(number) > 20 or not re.fullmatch(
            r"[A-Z0-9 -]+", number
        ):
            message = "Enter a valid vehicle number using letters and numbers."
            message_type = "error"

        elif action == "entry":
            vehicle_type = request.form.get("type", "")

            if vehicle_type not in ("Bike", "Car"):
                message = "Please select Bike or Car."
                message_type = "error"

            else:
                with connect_db() as con:
                    existing = con.execute("""
                        SELECT id FROM parking
                        WHERE vehicle_number = ?
                        AND exit_time IS NULL
                    """, (number,)).fetchone()

                    if existing:
                        message = "This vehicle is already parked."
                        message_type = "error"

                    else:
                        occupied = {
                            (row["basement"], row["slot"])
                            for row in con.execute("""
                                SELECT basement, slot
                                FROM parking
                                WHERE exit_time IS NULL
                            """).fetchall()
                        }

                        free_slot = None

                        # Fill Basement 1 first, then Basement 2.
                        for basement in BASEMENTS:
                            for slot in range(1, SLOTS_PER_BASEMENT + 1):
                                if (basement, slot) not in occupied:
                                    free_slot = (basement, slot)
                                    break

                            if free_slot is not None:
                                break

                        if free_slot is None:
                            message = "Parking is full! All 10 slots are occupied."
                            message_type = "error"

                        else:
                            basement, slot = free_slot

                            con.execute("""
                                INSERT INTO parking
                                (vehicle_number, vehicle_type, slot,
                                 basement, entry_time)
                                VALUES (?, ?, ?, ?, ?)
                            """, (
                                number,
                                vehicle_type,
                                slot,
                                basement,
                                datetime.now().isoformat(timespec="seconds")
                            ))

                            message = (
                                f"{number} registered successfully in "
                                f"{basement}, Slot {slot}."
                            )
                            message_type = "success"

        elif action == "exit":
            with connect_db() as con:
                vehicle = con.execute("""
                    SELECT id, vehicle_type, entry_time, slot, basement
                    FROM parking
                    WHERE vehicle_number = ?
                    AND exit_time IS NULL
                    ORDER BY id DESC
                    LIMIT 1
                """, (number,)).fetchone()

                if vehicle is None:
                    message = "Vehicle not found in the parking area."
                    message_type = "error"

                else:
                    vehicle_id = vehicle["id"]
                    vehicle_type = vehicle["vehicle_type"]
                    entry_text = vehicle["entry_time"]
                    slot = vehicle["slot"]
                    basement = vehicle["basement"]

                    entry_time = datetime.fromisoformat(entry_text)
                    exit_time = datetime.now()

                    hours = max(1, math.ceil(
                        (exit_time - entry_time).total_seconds() / 3600
                    ))

                    rate = 20 if vehicle_type == "Bike" else 50
                    charge = hours * rate

                    con.execute("""
                        UPDATE parking
                        SET exit_time = ?, charge = ?
                        WHERE id = ?
                    """, (
                        exit_time.isoformat(timespec="seconds"),
                        charge,
                        vehicle_id
                    ))

                    message = (
                        f"{number} exited from {basement}, Slot {slot}. "
                        f"Duration: {hours} hour(s). "
                        f"Charge: Rs. {charge:.0f}."
                    )
                    message_type = "success"

        else:
            message = "Invalid request. Please try again."
            message_type = "error"

    parked = get_parked()
    occupied_count = len(parked)
    available_count = TOTAL_SLOTS - occupied_count

    # Display five slots for each basement.
    slots_html = ""

    for basement in BASEMENTS:
        slots_html += (
            f'<section class="basement">'
            f'<h3>{basement}</h3><div class="slot-grid">'
        )

        for slot in range(1, SLOTS_PER_BASEMENT + 1):
            vehicle = next(
                (
                    v for v in parked
                    if v["basement"] == basement and v["slot"] == slot
                ),
                None
            )

            slot_name = f"B{BASEMENTS.index(basement) + 1}-{slot:02d}"

            if vehicle:
                vehicle_number = html.escape(vehicle["vehicle_number"])
                slots_html += (
                    f'<div class="slot occupied">'
                    f'<strong>{slot_name}</strong>'
                    f'<span>Occupied</span>'
                    f'<small>{vehicle_number}</small>'
                    f'</div>'
                )
            else:
                slots_html += (
                    f'<div class="slot available">'
                    f'<strong>{slot_name}</strong>'
                    f'<span>Available</span>'
                    f'</div>'
                )

        slots_html += "</div></section>"

    # Currently parked vehicles.
    records_html = (
        '<p class="empty">No vehicles are currently parked.</p>'
    )

    if parked:
        records_html = """
            <div class="table-wrap">
            <table>
                <tr>
                    <th>Vehicle</th>
                    <th>Type</th>
                    <th>Basement</th>
                    <th>Slot</th>
                    <th>Entry Time</th>
                </tr>
        """

        for vehicle in parked:
            records_html += (
                "<tr>"
                f"<td>{html.escape(vehicle['vehicle_number'])}</td>"
                f"<td>{html.escape(vehicle['vehicle_type'])}</td>"
                f"<td>{html.escape(vehicle['basement'])}</td>"
                f"<td>{vehicle['slot']}</td>"
                f"<td>{html.escape(vehicle['entry_time'].replace('T', ' '))}</td>"
                "</tr>"
            )

        records_html += "</table></div>"

    with connect_db() as con:
        total_revenue = con.execute("""
            SELECT COALESCE(SUM(charge), 0)
            FROM parking
            WHERE exit_time IS NOT NULL
        """).fetchone()[0]

        history = con.execute("""
            SELECT vehicle_number, vehicle_type, basement, slot,
                   entry_time, exit_time, charge
            FROM parking
            WHERE exit_time IS NOT NULL
            ORDER BY id DESC
            LIMIT 10
        """).fetchall()

    history_html = (
        '<p class="empty">No completed parking transactions yet.</p>'
    )

    if history:
        history_html = """
            <div class="table-wrap">
            <table>
                <tr>
                    <th>Vehicle</th>
                    <th>Type</th>
                    <th>Basement</th>
                    <th>Slot</th>
                    <th>Entry</th>
                    <th>Exit</th>
                    <th>Charge</th>
                </tr>
        """

        for record in history:
            history_html += (
                "<tr>"
                f"<td>{html.escape(record['vehicle_number'])}</td>"
                f"<td>{html.escape(record['vehicle_type'])}</td>"
                f"<td>{html.escape(record['basement'])}</td>"
                f"<td>{record['slot']}</td>"
                f"<td>{html.escape(record['entry_time'].replace('T', ' '))}</td>"
                f"<td>{html.escape(record['exit_time'].replace('T', ' '))}</td>"
                f"<td>Rs. {record['charge']:.0f}</td>"
                "</tr>"
            )

        history_html += "</table></div>"

    message_html = ""

    if message:
        message_html = (
            f'<div class="message {message_type}">'
            f'{html.escape(message)}</div>'
        )

    return f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>Parking Management System</title>

        <style>
            * {{ box-sizing: border-box; }}

            body {{
                font-family: Arial, sans-serif;
                background: #f1f5f9;
                margin: 0;
                color: #1e293b;
            }}

            header {{
                background: linear-gradient(135deg, #12345a, #1768ac);
                color: white;
                padding: 28px 16px;
                text-align: center;
            }}

            header h1 {{ margin: 0 0 8px; }}
            header p {{ margin: 0; color: #e0ecff; }}

            main {{
                max-width: 1100px;
                margin: 24px auto;
                padding: 0 16px;
            }}

            .cards {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
                gap: 16px;
                margin-bottom: 22px;
            }}

            .card, .panel {{
                background: white;
                border-radius: 12px;
                padding: 20px;
                box-shadow: 0 4px 14px #0f172a0d;
                margin-bottom: 20px;
            }}

            .card {{ border-top: 4px solid #1768ac; }}
            .card-label {{ color: #64748b; font-size: 14px; }}
            .number {{
                font-size: 30px;
                font-weight: bold;
                margin-top: 8px;
                color: #1768ac;
            }}

            h2 {{ margin-top: 0; font-size: 21px; }}
            h3 {{ margin: 8px 0 14px; }}

            input, select, button {{
                width: 100%;
                padding: 12px;
                margin: 8px 0;
                border-radius: 7px;
                border: 1px solid #cbd5e1;
                font-size: 15px;
            }}

            button {{
                background: #1768ac;
                color: white;
                border: 0;
                font-weight: bold;
                cursor: pointer;
            }}

            button:hover {{ background: #124f85; }}

            .message {{
                padding: 14px;
                margin-bottom: 20px;
                border-radius: 8px;
            }}

            .success {{ background: #dcfce7; color: #166534; }}
            .error {{ background: #fee2e2; color: #991b1b; }}
            .info {{ background: #dbeafe; color: #1e40af; }}

            .basement {{
                border: 1px solid #e2e8f0;
                border-radius: 10px;
                padding: 14px;
                margin: 14px 0;
            }}

            .slot-grid {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(115px, 1fr));
                gap: 10px;
            }}

            .slot {{
                min-height: 88px;
                padding: 12px 8px;
                border-radius: 8px;
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: center;
                gap: 7px;
                text-align: center;
            }}

            .available {{ background: #dcfce7; color: #166534; }}
            .occupied {{ background: #fee2e2; color: #991b1b; }}
            .slot small {{ overflow-wrap: anywhere; }}

            .table-wrap {{ overflow-x: auto; }}

            table {{
                width: 100%;
                border-collapse: collapse;
                white-space: nowrap;
            }}

            th, td {{
                padding: 12px;
                border-bottom: 1px solid #e2e8f0;
                text-align: left;
            }}

            th {{ background: #f8fafc; }}
            .empty {{ color: #64748b; }}

            .rates {{
                color: #64748b;
                font-size: 14px;
                line-height: 1.6;
            }}

            footer {{
                text-align: center;
                color: #64748b;
                padding: 20px;
                font-size: 13px;
            }}
        </style>
    </head>

    <body>
        <header>
            <h1>Parking Management System</h1>
            <p>Two-Level Parking • Vehicle Entry and Exit • Charge Management</p>
        </header>

        <main>
            {message_html}

            <div class="cards">
                <div class="card">
                    <div class="card-label">Total Capacity</div>
                    <div class="number">{TOTAL_SLOTS}</div>
                </div>
                <div class="card">
                    <div class="card-label">Available Slots</div>
                    <div class="number">{available_count}</div>
                </div>
                <div class="card">
                    <div class="card-label">Occupied Slots</div>
                    <div class="number">{occupied_count}</div>
                </div>
                <div class="card">
                    <div class="card-label">Total Revenue</div>
                    <div class="number">Rs. {total_revenue:.0f}</div>
                </div>
            </div>

            <section class="panel">
                <h2>Register Vehicle Entry</h2>
                <form method="POST">
                    <input type="hidden" name="action" value="entry">
                    <input
                        name="number"
                        placeholder="Vehicle Number e.g. KA09AB1234"
                        maxlength="20"
                        required
                    >
                    <select name="type" required>
                        <option value="Bike">Bike</option>
                        <option value="Car">Car</option>
                    </select>
                    <button type="submit">Register Vehicle</button>
                </form>
            </section>

            <section class="panel">
                <h2>Parking Layout</h2>
                <p class="rates">
                    Basement 1 is filled first. Basement 2 is used
                    when all five Basement 1 slots are occupied.
                </p>
                {slots_html}
            </section>

            <section class="panel">
                <h2>Currently Parked Vehicles</h2>
                {records_html}
            </section>

            <section class="panel">
                <h2>Vehicle Exit</h2>
                <form method="POST">
                    <input type="hidden" name="action" value="exit">
                    <input
                        name="number"
                        placeholder="Enter vehicle number"
                        maxlength="20"
                        required
                    >
                    <button type="submit">Calculate Charge and Exit</button>
                </form>
                <p class="rates">
                    Bike: Rs. 20/hour | Car: Rs. 50/hour.<br>
                    Partial hours are rounded up. Minimum charge is one hour.
                </p>
            </section>

            <section class="panel">
                <h2>Recent Completed Transactions</h2>
                {history_html}
            </section>
        </main>

        <footer>Parking Management System — Local Test Version</footer>
    </body>
    </html>
    """


setup_db()

if __name__ == "__main__":
    app.run(debug=True)
