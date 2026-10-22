
from flask import Flask, request
from datetime import datetime
import sqlite3
import math
import html
import re

app = Flask(__name__)

DB_NAME = "parking_test.db"
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


def get_parked():
    with connect_db() as con:
        return con.execute("""
            SELECT vehicle_number, vehicle_type, slot,
                   basement, entry_time
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
            message = "Enter a valid vehicle number."
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
                        for basement in BASEMENTS:
                            for slot in range(1, SLOTS_PER_BASEMENT + 1):
                                if (basement, slot) not in occupied:
                                    free_slot = (basement, slot)
                                    break
                            if free_slot:
                                break

                        if free_slot is None:
                            message = "Parking is full!"
                            message_type = "error"
                        else:
                            basement, slot = free_slot
                            con.execute("""
                                INSERT INTO parking
                                (vehicle_number, vehicle_type, slot,
                                 basement, entry_time)
                                VALUES (?, ?, ?, ?, ?)
                            """, (
                                number, vehicle_type, slot, basement,
                                datetime.now().isoformat(timespec="seconds")
                            ))
                            message = (
                                f"{number} registered in {basement}, "
                                f"Slot {slot}."
                            )
                            message_type = "success"

        elif action == "exit":
            with connect_db() as con:
                vehicle = con.execute("""
                    SELECT id, vehicle_type, slot, basement, entry_time
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
                    entry_time = datetime.fromisoformat(
                        vehicle["entry_time"]
                    )
                    exit_time = datetime.now()
                    hours = max(1, math.ceil(
                        (exit_time - entry_time).total_seconds() / 3600
                    ))
                    rate = 20 if vehicle["vehicle_type"] == "Bike" else 50
                    charge = hours * rate

                    con.execute("""
                        UPDATE parking
                        SET exit_time = ?, charge = ?
                        WHERE id = ?
                    """, (
                        exit_time.isoformat(timespec="seconds"),
                        charge, vehicle["id"]
                    ))

                    message = (
                        f"{number} exited from {vehicle['basement']}, "
                        f"Slot {vehicle['slot']}. Duration: {hours} hour(s). "
                        f"Charge: Rs. {charge}."
                    )
                    message_type = "success"
        else:
            message = "Invalid request."
            message_type = "error"

    parked = get_parked()
    occupied_count = len(parked)
    available_count = TOTAL_SLOTS - occupied_count

    occupied = {
        (v["basement"], v["slot"]): v for v in parked
    }

    slots_html = ""
    for basement in BASEMENTS:
        slots_html += (
            f'<section class="panel"><h2>{basement}</h2>'
            '<div class="slots">'
        )
        for slot in range(1, SLOTS_PER_BASEMENT + 1):
            vehicle = occupied.get((basement, slot))
            name = f"B{BASEMENTS.index(basement) + 1}-{slot:02d}"
            if vehicle:
                plate = html.escape(vehicle["vehicle_number"])
                slots_html += (
                    f'<div class="slot occupied"><b>{name}</b>'
                    f'<span>Occupied</span><small>{plate}</small></div>'
                )
            else:
                slots_html += (
                    f'<div class="slot available"><b>{name}</b>'
                    '<span>Available</span></div>'
                )
        slots_html += "</div></section>"

    with connect_db() as con:
        total_revenue = con.execute("""
            SELECT COALESCE(SUM(charge), 0)
            FROM parking WHERE exit_time IS NOT NULL
        """).fetchone()[0]

        history = con.execute("""
            SELECT vehicle_number, vehicle_type, basement, slot,
                   entry_time, exit_time, charge
            FROM parking
            WHERE exit_time IS NOT NULL
            ORDER BY id DESC LIMIT 10
        """).fetchall()

    def table_html(rows, headers, render_row):
        if not rows:
            return '<p class="empty">No records yet.</p>'
        result = '<div class="table-wrap"><table><tr>'
        result += "".join(f"<th>{h}</th>" for h in headers)
        result += "</tr>"
        for row in rows:
            result += render_row(row)
        return result + "</table></div>"

    parked_html = table_html(
        parked,
        ["Vehicle", "Type", "Basement", "Slot", "Entry Time"],
        lambda v: (
            "<tr>"
            f"<td>{html.escape(v['vehicle_number'])}</td>"
            f"<td>{html.escape(v['vehicle_type'])}</td>"
            f"<td>{html.escape(v['basement'])}</td>"
            f"<td>{v['slot']}</td>"
            f"<td>{html.escape(v['entry_time'].replace('T', ' '))}</td>"
            "</tr>"
        )
    )

    history_html = table_html(
        history,
        ["Vehicle", "Type", "Basement", "Slot", "Entry", "Exit", "Charge"],
        lambda v: (
            "<tr>"
            f"<td>{html.escape(v['vehicle_number'])}</td>"
            f"<td>{html.escape(v['vehicle_type'])}</td>"
            f"<td>{html.escape(v['basement'])}</td>"
            f"<td>{v['slot']}</td>"
            f"<td>{html.escape(v['entry_time'].replace('T', ' '))}</td>"
            f"<td>{html.escape(v['exit_time'].replace('T', ' '))}</td>"
            f"<td>Rs. {v['charge']:.0f}</td>"
            "</tr>"
        )
    )

    notice = ""
    if message:
        notice = (
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
            body {{ font-family: Arial, sans-serif; background: #f1f5f9;
                    color: #1e293b; margin: 0; }}
            header {{ background: #12345a; color: white; padding: 25px;
                      text-align: center; }}
            main {{ max-width: 1100px; margin: 24px auto; padding: 0 16px; }}
            .cards {{ display: grid; grid-template-columns:
                      repeat(auto-fit, minmax(160px, 1fr)); gap: 14px; }}
            .card, .panel {{ background: white; border-radius: 10px;
                             padding: 18px; margin-bottom: 18px; }}
            .number {{ font-size: 28px; font-weight: bold; color: #1768ac; }}
            input, select, button {{ width: 100%; padding: 12px; margin: 7px 0;
                                    border: 1px solid #cbd5e1; border-radius: 6px; }}
            button {{ background: #1768ac; color: white; border: 0;
                      cursor: pointer; font-weight: bold; }}
            .slots {{ display: grid; grid-template-columns:
                      repeat(auto-fit, minmax(110px, 1fr)); gap: 10px; }}
            .slot {{ padding: 14px 8px; border-radius: 8px; display: flex;
                     flex-direction: column; align-items: center; gap: 7px;
                     overflow-wrap: anywhere; }}
            .available {{ background: #dcfce7; color: #166534; }}
            .occupied {{ background: #fee2e2; color: #991b1b; }}
            .message {{ padding: 14px; border-radius: 8px; margin-bottom: 18px; }}
            .success {{ background: #dcfce7; color: #166534; }}
            .error {{ background: #fee2e2; color: #991b1b; }}
            .info {{ background: #dbeafe; color: #1e40af; }}
            .table-wrap {{ overflow-x: auto; }}
            table {{ width: 100%; border-collapse: collapse; white-space: nowrap; }}
            th, td {{ text-align: left; padding: 10px; border-bottom: 1px solid #e2e8f0; }}
            th {{ background: #f8fafc; }}
            .empty {{ color: #64748b; }}
        </style>
    </head>
    <body>
        <header>
            <h1>Parking Management System</h1>
            <p>Two Basements • Vehicle Entry, Exit and Parking Charges</p>
        </header>
        <main>
            {notice}
            <div class="cards">
                <div class="card">Total Slots<div class="number">{TOTAL_SLOTS}</div></div>
                <div class="card">Available<div class="number">{available_count}</div></div>
                <div class="card">Occupied<div class="number">{occupied_count}</div></div>
                <div class="card">Total Revenue<div class="number">Rs. {total_revenue:.0f}</div></div>
            </div>

            <section class="panel">
                <h2>Register Vehicle Entry</h2>
                <form method="POST">
                    <input type="hidden" name="action" value="entry">
                    <input name="number" placeholder="Vehicle Number e.g. KA09AB1234"
                           maxlength="20" required>
                    <select name="type" required>
                        <option value="Bike">Bike</option>
                        <option value="Car">Car</option>
                    </select>
                    <button type="submit">Register Vehicle</button>
                </form>
            </section>

            <h2>Parking Layout</h2>
            <p>Basement 1 fills first. Basement 2 is used when all five slots in Basement 1 are occupied.</p>
            {slots_html}

            <section class="panel">
                <h2>Currently Parked Vehicles</h2>
                {parked_html}
            </section>

            <section class="panel">
                <h2>Vehicle Exit</h2>
                <form method="POST">
                    <input type="hidden" name="action" value="exit">
                    <input name="number" placeholder="Vehicle Number"
                           maxlength="20" required>
                    <button type="submit">Calculate Charge and Exit</button>
                </form>
                <p>Bike: Rs. 20/hour | Car: Rs. 50/hour. Partial hours round up; minimum one hour.</p>
            </section>

            <section class="panel">
                <h2>Recent Completed Transactions</h2>
                {history_html}
            </section>
        </main>
    </body>
    </html>
    """


setup_db()

if __name__ == "__main__":
    app.run(debug=True)

