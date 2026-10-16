from __future__ import annotations

import random
import sqlite3
from datetime import datetime
from pathlib import Path

from flask import Flask, jsonify, render_template, request

app = Flask(__name__)

BASE_DIR = Path(__file__).resolve().parent
DATABASE = BASE_DIR / "intelliresq.db"

EMERGENCY_TYPES = {"Road Accident", "Cardiac Emergency", "Breathing Difficulty", "Other"}
SEVERITIES = {"Critical", "High", "Moderate", "Low"}

DEMO_LOCATIONS = {
    "tirupati": (13.6288, 79.4192),
    "tirupati central": (13.6288, 79.4192),
    "tirupati railway station": (13.6350, 79.4500),
    "railway station": (13.6350, 79.4500),
    "tirupati bus stand": (13.6355, 79.4190),
    "bus stand": (13.6355, 79.4190),
    "svims": (13.6400, 79.4030),
    "svims hospital": (13.6400, 79.4030),
    "ruia": (13.6280, 79.4070),
    "ruia government general hospital": (13.6280, 79.4070),
    "apollo": (13.6500, 79.4200),
    "apollo hospital": (13.6500, 79.4200),
    "alipiri": (13.6650, 79.4090),
    "renigunta": (13.6510, 79.5120),
    "kapilatheertham": (13.6750, 79.3500),
}


def get_db_connection():
    conn = sqlite3.connect(DATABASE, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def vehicle_position(ambulance, current_time):
    origin = (ambulance["latitude"], ambulance["longitude"])
    if ambulance["route_started_at"] and ambulance["route_arrival_at"]:
        started_at = datetime.fromisoformat(ambulance["route_started_at"])
        arrival_at = datetime.fromisoformat(ambulance["route_arrival_at"])
        duration = (arrival_at - started_at).total_seconds()
        progress = 1.0 if duration <= 0 else max(
            0.0, min(1.0, (current_time - started_at).total_seconds() / duration)
        )
        return (
            ambulance["route_origin_latitude"]
            + (ambulance["route_destination_latitude"] - ambulance["route_origin_latitude"]) * progress,
            ambulance["route_origin_longitude"]
            + (ambulance["route_destination_longitude"] - ambulance["route_origin_longitude"]) * progress,
        )
    return origin


def find_demo_coordinates(location):
    key = (location or "").strip().lower()
    if key in DEMO_LOCATIONS:
        return DEMO_LOCATIONS[key]

    for keyword in sorted(DEMO_LOCATIONS, key=len, reverse=True):
        if keyword in key:
            return DEMO_LOCATIONS[keyword]

    return DEMO_LOCATIONS["tirupati"]


def generate_demo_vitals(severity):
    values = {
        "Critical": (132, 89, 38.2),
        "High": (112, 94, 37.8),
        "Moderate": (96, 97, 37.1),
        "Low": (82, 98, 36.8),
    }
    return values.get(severity, values["Moderate"])


def make_bp(severity):
    mapping = {
        "Critical": (160, 95),
        "High": (145, 88),
        "Moderate": (125, 82),
        "Low": (118, 78),
    }
    systolic, diastolic = mapping.get(severity, mapping["Moderate"])
    return f"{random.randint(systolic - 8, systolic + 8)}/{random.randint(diastolic - 4, diastolic + 4)}"


def assess_vitals(heart_rate, spo2, temperature, blood_pressure, respiratory_rate):
    """Apply demonstration screening thresholds; this is not a clinical diagnosis."""
    warnings = []
    critical = []

    if heart_rate < 40 or heart_rate > 150:
        critical.append("heart rate")
    elif heart_rate < 60 or heart_rate > 100:
        warnings.append("heart rate")

    if spo2 < 90:
        critical.append("oxygen saturation")
    elif spo2 < 95:
        warnings.append("oxygen saturation")

    if temperature < 35 or temperature >= 40:
        critical.append("temperature")
    elif temperature < 36 or temperature >= 38.5:
        warnings.append("temperature")

    if respiratory_rate is not None:
        if respiratory_rate < 8 or respiratory_rate > 30:
            critical.append("respiratory rate")
        elif respiratory_rate < 12 or respiratory_rate > 20:
            warnings.append("respiratory rate")

    if blood_pressure:
        systolic, diastolic = (int(value) for value in blood_pressure.split("/"))
        if systolic < 80 or systolic >= 180 or diastolic < 50 or diastolic >= 120:
            critical.append("blood pressure")
        elif systolic < 90 or systolic >= 140 or diastolic < 60 or diastolic >= 90:
            warnings.append("blood pressure")

    if critical or len(warnings) >= 2:
        status = "Critical"
        findings = critical + warnings
        message = f"Critical screening flag: review {' and '.join(findings)}."
    elif warnings:
        status = "Needs Attention"
        message = f"Screening flag: review {' and '.join(warnings)}."
    else:
        status = "Normal"
        message = "Entered vital readings are within the demonstration thresholds."

    return status, message, warnings, critical


def initialize_database():
    conn = get_db_connection()

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS emergencies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_name TEXT NOT NULL,
            age INTEGER,
            location TEXT NOT NULL,
            emergency_type TEXT NOT NULL,
            severity TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'Pending',
            ambulance_id INTEGER,
            ambulance_name TEXT,
            hospital_id INTEGER,
            hospital_name TEXT,
            latitude REAL,
            longitude REAL,
            heart_rate INTEGER,
            spo2 INTEGER,
            temperature REAL,
            blood_pressure TEXT,
            respiratory_rate INTEGER,
            vitals_source TEXT NOT NULL DEFAULT 'Demo sample',
            vitals_updated_at TEXT,
            vitals_recorded_by TEXT,
            fall_detected INTEGER DEFAULT 0,
            condition_status TEXT DEFAULT 'Stable',
            condition_notes TEXT,
            alert_level TEXT,
            alert_message TEXT,
            last_update TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            pickup_time TEXT,
            transport_start TEXT,
            hospital_eta TEXT
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS ambulances (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ambulance_name TEXT NOT NULL UNIQUE,
            driver_name TEXT,
            status TEXT NOT NULL DEFAULT 'Available',
            current_location TEXT,
            latitude REAL,
            longitude REAL,
            assigned_emergency_id INTEGER,
            route_origin_latitude REAL,
            route_origin_longitude REAL,
            route_destination_latitude REAL,
            route_destination_longitude REAL,
            route_started_at TEXT,
            route_arrival_at TEXT,
            route_emergency_id INTEGER
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS hospitals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            hospital_name TEXT NOT NULL UNIQUE,
            location TEXT NOT NULL,
            latitude REAL NOT NULL,
            longitude REAL NOT NULL,
            available_beds INTEGER NOT NULL DEFAULT 10,
            icu_beds INTEGER NOT NULL DEFAULT 3,
            emergency_beds INTEGER NOT NULL DEFAULT 4,
            doctors_available INTEGER NOT NULL DEFAULT 12,
            facilities TEXT NOT NULL,
            diversion_status TEXT NOT NULL DEFAULT 'Normal',
            readiness_status TEXT NOT NULL DEFAULT 'Ready'
        )
        """
    )

    for table_name, columns in {
        "emergencies": [
            ("age", "INTEGER"),
            ("blood_pressure", "TEXT"),
            ("respiratory_rate", "INTEGER"),
            ("vitals_source", "TEXT NOT NULL DEFAULT 'Demo sample'"),
            ("vitals_updated_at", "TEXT"),
            ("vitals_recorded_by", "TEXT"),
            ("fall_detected", "INTEGER DEFAULT 0"),
            ("condition_status", "TEXT DEFAULT 'Stable'"),
            ("condition_notes", "TEXT"),
            ("alert_level", "TEXT"),
            ("alert_message", "TEXT"),
            ("last_update", "TEXT"),
            ("created_at", "TEXT"),
            ("pickup_time", "TEXT"),
            ("transport_start", "TEXT"),
            ("hospital_eta", "TEXT"),
        ],
        "ambulances": [
            ("driver_name", "TEXT"),
            ("current_location", "TEXT"),
            ("assigned_emergency_id", "INTEGER"),
            ("route_origin_latitude", "REAL"),
            ("route_origin_longitude", "REAL"),
            ("route_destination_latitude", "REAL"),
            ("route_destination_longitude", "REAL"),
            ("route_started_at", "TEXT"),
            ("route_arrival_at", "TEXT"),
            ("route_emergency_id", "INTEGER"),
        ],
        "hospitals": [
            ("icu_beds", "INTEGER NOT NULL DEFAULT 3"),
            ("emergency_beds", "INTEGER NOT NULL DEFAULT 4"),
            ("doctors_available", "INTEGER NOT NULL DEFAULT 12"),
            ("diversion_status", "TEXT NOT NULL DEFAULT 'Normal'"),
            ("readiness_status", "TEXT NOT NULL DEFAULT 'Ready'"),
        ],
    }.items():
        existing = {
            row["name"] for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()
        }
        for column_name, definition in columns:
            if column_name not in existing:
                conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}")

    conn.executemany(
        """
        INSERT OR IGNORE INTO ambulances (ambulance_name, driver_name, status, current_location, latitude, longitude)
        VALUES (?, ?, 'Available', ?, ?, ?)
        """,
        [
            ("AMB-101", "Ravi Kumar", "Tirupati Central", 13.6288, 79.4192),
            ("AMB-102", "Suresh Reddy", "Tirupati Railway Station", 13.6350, 79.4500),
            ("AMB-103", "Kiran Das", "Tirupati Bus Stand", 13.6355, 79.4190),
        ],
    )
    conn.execute(
        """
        UPDATE ambulances
        SET driver_name = CASE ambulance_name
                WHEN 'AMB-101' THEN 'Ravi Kumar'
                WHEN 'AMB-102' THEN 'Suresh Reddy'
                WHEN 'AMB-103' THEN 'Kiran Das'
                ELSE driver_name
            END,
            current_location = CASE ambulance_name
                WHEN 'AMB-101' THEN 'Tirupati Central'
                WHEN 'AMB-102' THEN 'Tirupati Railway Station'
                WHEN 'AMB-103' THEN 'Tirupati Bus Stand'
                ELSE current_location
            END
        WHERE driver_name IS NULL OR current_location IS NULL
        """
    )

    conn.executemany(
        """
        INSERT OR IGNORE INTO hospitals
            (hospital_name, location, latitude, longitude, available_beds, icu_beds, emergency_beds, doctors_available, facilities, diversion_status, readiness_status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            ("SVIMS Hospital", "Tirupati", 13.6400, 79.4030, 20, 8, 6, 14, "Emergency, ICU, Cardiology", "Normal", "Ready"),
            ("Ruia Government General Hospital", "Tirupati", 13.6280, 79.4070, 15, 5, 5, 9, "Emergency, Trauma Care, Surgery", "Normal", "Ready"),
            ("Apollo Hospital", "Tirupati", 13.6500, 79.4200, 12, 6, 4, 11, "Emergency, ICU, Cardiology, Surgery", "Normal", "Ready"),
        ],
    )
    conn.execute(
        """
        UPDATE hospitals
        SET doctors_available = CASE hospital_name
                WHEN 'SVIMS Hospital' THEN 14
                WHEN 'Ruia Government General Hospital' THEN 9
                WHEN 'Apollo Hospital' THEN 11
                ELSE doctors_available
            END,
            icu_beds = CASE hospital_name
                WHEN 'SVIMS Hospital' THEN 8
                WHEN 'Ruia Government General Hospital' THEN 5
                WHEN 'Apollo Hospital' THEN 6
                ELSE icu_beds
            END,
            emergency_beds = CASE hospital_name
                WHEN 'SVIMS Hospital' THEN 6
                WHEN 'Ruia Government General Hospital' THEN 5
                WHEN 'Apollo Hospital' THEN 4
                ELSE emergency_beds
            END
        WHERE hospital_name IN ('SVIMS Hospital', 'Ruia Government General Hospital', 'Apollo Hospital')
            AND doctors_available = 12 AND icu_beds = 3 AND emergency_beds = 4
        """
    )

    if conn.execute("SELECT COUNT(*) FROM emergencies").fetchone()[0] == 0:
        seeds = [
            ("Asha Reddy", 42, "Tirupati Railway Station", "Road Accident", "High", "Pending", 13.6350, 79.4500, 112, 94, 37.8, "132/90", 18, 0, "Needs Attention", "Driver notified, trauma support requested.", "High", "Awaiting ambulance assignment"),
            ("K. Narayana", 58, "SVIMS Hospital", "Cardiac Emergency", "Critical", "Ambulance Assigned", 13.6400, 79.4030, 132, 89, 38.2, "150/96", 24, 0, "Critical", "Cardiac symptoms observed before transport.", "Critical", "Prepared for emergency transfer"),
        ]
        for patient_name, age, location, emergency_type, severity, status, latitude, longitude, heart_rate, spo2, temperature, blood_pressure, respiratory_rate, fall_detected, condition_status, condition_notes, alert_level, alert_message in seeds:
            lat, lon = find_demo_coordinates(location)
            conn.execute(
                """
                INSERT INTO emergencies (
                    patient_name, age, location, emergency_type, severity, status,
                    latitude, longitude, heart_rate, spo2, temperature,
                    blood_pressure, respiratory_rate, fall_detected,
                    condition_status, condition_notes, alert_level, alert_message
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    patient_name, age, location, emergency_type, severity, status,
                    lat, lon, heart_rate, spo2, temperature,
                    blood_pressure, respiratory_rate, fall_detected,
                    condition_status, condition_notes, alert_level, alert_message,
                ),
            )

    conn.execute(
        """
        UPDATE emergencies
        SET created_at = COALESCE(created_at, last_update, datetime('now')),
            last_update = COALESCE(last_update, created_at, datetime('now'))
        WHERE created_at IS NULL OR last_update IS NULL
        """
    )
    conn.execute(
        """
        UPDATE emergencies
        SET condition_status = 'Awaiting nurse entry'
        WHERE heart_rate IS NULL OR spo2 IS NULL OR temperature IS NULL
        """
    )
    for emergency in conn.execute(
        """
        SELECT id, heart_rate, spo2, temperature, blood_pressure, respiratory_rate
        FROM emergencies
        WHERE heart_rate IS NOT NULL AND spo2 IS NOT NULL AND temperature IS NOT NULL
        """
    ).fetchall():
        condition_status, _, _, _ = assess_vitals(
            emergency["heart_rate"],
            emergency["spo2"],
            emergency["temperature"],
            emergency["blood_pressure"],
            emergency["respiratory_rate"],
        )
        conn.execute(
            "UPDATE emergencies SET condition_status = ? WHERE id = ?",
            (condition_status, emergency["id"]),
        )
    conn.commit()
    conn.close()


@app.get("/")
def home():
    return render_template("index.html")


@app.get("/api/dashboard")
def dashboard_data():
    conn = get_db_connection()
    emergencies = conn.execute(
        """
        SELECT * FROM emergencies
        ORDER BY
            CASE
                WHEN status = 'Pending' THEN 0
                WHEN status = 'Ambulance Assigned' THEN 1
                WHEN status = 'En Route' THEN 2
                WHEN status = 'At Patient' THEN 3
                WHEN status = 'Transporting' THEN 4
                ELSE 5
            END,
            CASE severity
                WHEN 'Critical' THEN 0
                WHEN 'High' THEN 1
                WHEN 'Moderate' THEN 2
                ELSE 3
            END,
            id DESC
        """
    ).fetchall()
    ambulances = conn.execute("SELECT * FROM ambulances ORDER BY id").fetchall()
    hospitals = conn.execute("SELECT * FROM hospitals ORDER BY id").fetchall()

    stats = {
        "total": conn.execute("SELECT COUNT(*) FROM emergencies").fetchone()[0],
        "pending": conn.execute("SELECT COUNT(*) FROM emergencies WHERE status = 'Pending'").fetchone()[0],
        "assigned": conn.execute("SELECT COUNT(*) FROM emergencies WHERE status IN ('Ambulance Assigned', 'En Route', 'At Patient', 'Transporting')").fetchone()[0],
        "available_ambulances": conn.execute("SELECT COUNT(*) FROM ambulances WHERE status = 'Available'").fetchone()[0],
        "critical_patients": conn.execute(
            "SELECT COUNT(*) FROM emergencies WHERE condition_status = 'Critical' AND status != 'Completed'"
        ).fetchone()[0],
    }

    response = {
        "emergencies": [dict(row) for row in emergencies],
        "ambulances": [dict(row) for row in ambulances],
        "hospitals": [dict(row) for row in hospitals],
        "stats": stats,
        "server_time": datetime.now().astimezone().isoformat(timespec="seconds"),
    }
    conn.close()
    return jsonify(response)


@app.post("/register_emergency")
def register_emergency():
    patient_name = (request.form.get("patient_name") or "").strip()
    location = (request.form.get("location") or "").strip()
    emergency_type = request.form.get("emergency_type")
    severity = request.form.get("severity")
    age = request.form.get("age")

    if not patient_name or not location:
        return jsonify({"success": False, "message": "Patient name and location are required."}), 400
    if emergency_type not in EMERGENCY_TYPES:
        return jsonify({"success": False, "message": "Select a valid emergency type."}), 400
    if severity not in SEVERITIES:
        return jsonify({"success": False, "message": "Select a valid severity."}), 400

    latitude, longitude = find_demo_coordinates(location)

    conn = get_db_connection()
    conn.execute(
        """
        INSERT INTO emergencies (
            patient_name, age, location, emergency_type, severity, status,
            latitude, longitude, heart_rate, spo2, temperature,
            blood_pressure, respiratory_rate, fall_detected,
            condition_status, alert_level, alert_message, last_update, created_at, vitals_updated_at
        ) VALUES (?, ?, ?, ?, ?, 'Pending', ?, ?, NULL, NULL, NULL, NULL, NULL, 0, 'Awaiting nurse entry', 'Awaiting nurse entry', ?, datetime('now'), datetime('now'), NULL)
        """,
        (
            patient_name,
            int(age) if age and age.isdigit() else None,
            location,
            emergency_type,
            severity,
            latitude,
            longitude,
            "Patient registered; nurse readings are pending.",
        ),
    )
    conn.commit()
    conn.close()
    return jsonify({"success": True, "message": "Emergency recorded successfully."})


@app.post("/allocate_ambulance/<int:emergency_id>")
def allocate_ambulance(emergency_id):
    conn = get_db_connection()
    emergency = conn.execute("SELECT * FROM emergencies WHERE id = ?", (emergency_id,)).fetchone()
    if emergency is None:
        conn.close()
        return jsonify({"success": False, "message": "Emergency not found."}), 404
    if emergency["status"] != "Pending":
        conn.close()
        return jsonify({"success": False, "message": "Only pending emergencies can be assigned."}), 400

    ambulance = conn.execute("SELECT * FROM ambulances WHERE status = 'Available' ORDER BY id LIMIT 1").fetchone()
    if ambulance is None:
        conn.close()
        return jsonify({"success": False, "message": "No available ambulances remain."}), 400

    conn.execute("UPDATE ambulances SET status = 'Assigned', assigned_emergency_id = ? WHERE id = ?", (emergency_id, ambulance["id"]))
    conn.execute("UPDATE emergencies SET status = 'Ambulance Assigned', ambulance_id = ?, ambulance_name = ?, last_update = datetime('now') WHERE id = ?", (ambulance["id"], ambulance["ambulance_name"], emergency_id))
    conn.commit()
    conn.close()
    return jsonify({"success": True, "message": f"{ambulance['ambulance_name']} assigned to emergency #{emergency_id}."})


@app.post("/select_hospital/<int:emergency_id>")
def select_hospital(emergency_id):
    hospital_id = request.form.get("hospital_id", type=int)
    if hospital_id is None:
        return jsonify({"success": False, "message": "Please choose a hospital."}), 400

    conn = get_db_connection()
    hospital = conn.execute("SELECT * FROM hospitals WHERE id = ?", (hospital_id,)).fetchone()
    emergency = conn.execute("SELECT * FROM emergencies WHERE id = ?", (emergency_id,)).fetchone()
    if hospital is None or emergency is None:
        conn.close()
        return jsonify({"success": False, "message": "Hospital or emergency not found."}), 404

    if (
        emergency["hospital_id"] != hospital["id"]
        and emergency["status"] in {"At Patient", "Transporting"}
        and emergency["ambulance_id"] is not None
    ):
        ambulance = conn.execute(
            "SELECT * FROM ambulances WHERE id = ?", (emergency["ambulance_id"],)
        ).fetchone()
        if ambulance:
            position = vehicle_position(ambulance, datetime.now().astimezone())
            conn.execute(
                """
                UPDATE ambulances
                SET status = 'At Patient Location', latitude = ?, longitude = ?, route_origin_latitude = NULL,
                    route_origin_longitude = NULL, route_destination_latitude = NULL,
                    route_destination_longitude = NULL, route_started_at = NULL,
                    route_arrival_at = NULL, route_emergency_id = NULL
                WHERE id = ?
                """,
                (position[0], position[1], emergency["ambulance_id"]),
            )

    conn.execute("UPDATE emergencies SET hospital_id = ?, hospital_name = ?, last_update = datetime('now') WHERE id = ?", (hospital["id"], hospital["hospital_name"], emergency_id))
    if (
        emergency["hospital_id"] != hospital["id"]
        and emergency["status"] in {"At Patient", "Transporting"}
    ):
        conn.execute("UPDATE emergencies SET hospital_eta = NULL WHERE id = ?", (emergency_id,))
    conn.commit()
    conn.close()
    return jsonify({"success": True, "message": f"{hospital['hospital_name']} selected for patient {emergency['patient_name']}."})


@app.post("/set_vehicle_arrival/<int:emergency_id>")
def set_vehicle_arrival(emergency_id):
    arrival_input = (request.form.get("arrival_time") or "").strip()
    try:
        arrival_at = datetime.fromisoformat(arrival_input)
    except ValueError:
        return jsonify({"success": False, "message": "Enter a valid arrival date and time."}), 400

    now = datetime.now().astimezone()
    if arrival_at.tzinfo is None:
        arrival_at = arrival_at.replace(tzinfo=now.tzinfo)
    else:
        arrival_at = arrival_at.astimezone(now.tzinfo)
    if arrival_at <= now:
        return jsonify({"success": False, "message": "Arrival time must be in the future."}), 400

    conn = get_db_connection()
    emergency = conn.execute(
        "SELECT * FROM emergencies WHERE id = ?", (emergency_id,)
    ).fetchone()
    if emergency is None:
        conn.close()
        return jsonify({"success": False, "message": "Emergency not found."}), 404
    if emergency["status"] in {"Pending", "Completed", "Arrived at Hospital"}:
        conn.close()
        return jsonify({"success": False, "message": "An active assigned trip is required to set an arrival time."}), 400

    ambulance = conn.execute(
        "SELECT * FROM ambulances WHERE id = ? AND assigned_emergency_id = ?",
        (emergency["ambulance_id"], emergency_id),
    ).fetchone()
    if ambulance is None or ambulance["latitude"] is None or ambulance["longitude"] is None:
        conn.close()
        return jsonify({"success": False, "message": "The assigned ambulance has no known starting position."}), 400

    if emergency["status"] in {"Ambulance Assigned", "En Route"}:
        destination = (emergency["latitude"], emergency["longitude"])
        destination_label = emergency["location"]
    else:
        hospital = conn.execute(
            "SELECT * FROM hospitals WHERE id = ?", (emergency["hospital_id"],)
        ).fetchone()
        if hospital is None:
            conn.close()
            return jsonify({"success": False, "message": "Choose a receiving hospital before setting the arrival time."}), 400
        destination = (hospital["latitude"], hospital["longitude"])
        destination_label = hospital["hospital_name"]

    origin = vehicle_position(ambulance, now)
    if origin[0] is None or origin[1] is None:
        conn.close()
        return jsonify({"success": False, "message": "The assigned ambulance has no known starting position."}), 400

    conn.execute(
        """
        UPDATE ambulances
        SET latitude = ?, longitude = ?,
            route_origin_latitude = ?, route_origin_longitude = ?,
            route_destination_latitude = ?, route_destination_longitude = ?,
            route_started_at = ?, route_arrival_at = ?, route_emergency_id = ?
        WHERE id = ?
        """,
        (
            origin[0], origin[1], origin[0], origin[1], destination[0], destination[1],
            now.isoformat(timespec="seconds"), arrival_at.isoformat(timespec="seconds"),
            emergency_id, ambulance["id"],
        ),
    )
    conn.execute(
        "UPDATE emergencies SET hospital_eta = ?, last_update = datetime('now') WHERE id = ?",
        (arrival_at.isoformat(timespec="seconds"), emergency_id),
    )
    conn.commit()
    conn.close()
    return jsonify({
        "success": True,
        "message": f"Simulated arrival set for {destination_label} at {arrival_at.strftime('%Y-%m-%d %H:%M %Z')}.",
        "arrival_at": arrival_at.isoformat(timespec="seconds"),
    })


@app.post("/update_status/<int:emergency_id>")
def update_status(emergency_id):
    requested_status = request.form.get("status")

    conn = get_db_connection()
    emergency = conn.execute("SELECT * FROM emergencies WHERE id = ?", (emergency_id,)).fetchone()
    if emergency is None:
        conn.close()
        return jsonify({"success": False, "message": "Emergency not found."}), 404

    next_status = {
        "Ambulance Assigned": "En Route",
        "En Route": "At Patient",
        "At Patient": "Transporting",
        "Transporting": "Arrived at Hospital",
        "Arrived at Hospital": "Completed",
    }
    if next_status.get(emergency["status"]) != requested_status:
        conn.close()
        return jsonify({"success": False, "message": "Trip status must follow the next available dispatch step."}), 400
    if requested_status in {"Transporting", "Arrived at Hospital"} and emergency["hospital_id"] is None:
        conn.close()
        return jsonify({"success": False, "message": "Choose a receiving hospital before patient transport."}), 400

    if requested_status == "Completed":
        ambulance = conn.execute(
            "SELECT * FROM ambulances WHERE id = ?", (emergency["ambulance_id"],)
        ).fetchone()
        if ambulance:
            position = vehicle_position(ambulance, datetime.now().astimezone())
            conn.execute(
                """
                UPDATE ambulances
                SET status = 'Available', assigned_emergency_id = NULL,
                    latitude = ?, longitude = ?, route_origin_latitude = NULL,
                    route_origin_longitude = NULL, route_destination_latitude = NULL,
                    route_destination_longitude = NULL, route_started_at = NULL,
                    route_arrival_at = NULL, route_emergency_id = NULL
                WHERE id = ?
                """,
                (position[0], position[1], emergency["ambulance_id"]),
            )
    elif requested_status == "At Patient":
        conn.execute(
            """
            UPDATE ambulances
            SET status = 'At Patient Location', latitude = ?, longitude = ?, route_origin_latitude = NULL,
                route_origin_longitude = NULL, route_destination_latitude = NULL,
                route_destination_longitude = NULL, route_started_at = NULL,
                route_arrival_at = NULL, route_emergency_id = NULL
            WHERE id = ?
            """,
            (emergency["latitude"], emergency["longitude"], emergency["ambulance_id"]),
        )
    elif requested_status == "Arrived at Hospital":
        hospital = conn.execute(
            "SELECT latitude, longitude FROM hospitals WHERE id = ?", (emergency["hospital_id"],)
        ).fetchone()
        if hospital:
            conn.execute(
                """
                UPDATE ambulances
                SET status = 'At Hospital', latitude = ?, longitude = ?, route_origin_latitude = NULL,
                    route_origin_longitude = NULL, route_destination_latitude = NULL,
                    route_destination_longitude = NULL, route_started_at = NULL,
                    route_arrival_at = NULL, route_emergency_id = NULL
                WHERE id = ?
                """,
                (hospital["latitude"], hospital["longitude"], emergency["ambulance_id"]),
            )
    elif requested_status == "En Route":
        conn.execute("UPDATE ambulances SET status = 'En Route to Patient' WHERE id = ?", (emergency["ambulance_id"],))
    elif requested_status == "Transporting":
        conn.execute("UPDATE ambulances SET status = 'Transporting Patient' WHERE id = ?", (emergency["ambulance_id"],))

    if requested_status == "Transporting":
        conn.execute(
            "UPDATE emergencies SET status = ?, pickup_time = datetime('now'), transport_start = datetime('now'), last_update = datetime('now') WHERE id = ?",
            (requested_status, emergency_id),
        )
    else:
        conn.execute("UPDATE emergencies SET status = ?, last_update = datetime('now') WHERE id = ?", (requested_status, emergency_id))
        if requested_status == "At Patient":
            conn.execute("UPDATE emergencies SET hospital_eta = NULL WHERE id = ?", (emergency_id,))
    conn.commit()
    conn.close()
    return jsonify({"success": True, "message": f"Emergency #{emergency_id} status updated to {requested_status}."})


@app.post("/update_vitals/<int:emergency_id>")
def update_vitals(emergency_id):
    recorded_by = (request.form.get("recorded_by") or "").strip()
    heart_rate = request.form.get("heart_rate", type=int)
    spo2 = request.form.get("spo2", type=int)
    temperature = request.form.get("temperature", type=float)
    blood_pressure = (request.form.get("blood_pressure") or "").strip()
    respiratory_rate_value = (request.form.get("respiratory_rate") or "").strip()
    respiratory_rate = None

    if not recorded_by:
        return jsonify({"success": False, "message": "Enter the nurse or staff member's name."}), 400
    if len(recorded_by) > 100:
        return jsonify({"success": False, "message": "Staff name must be 100 characters or fewer."}), 400
    if heart_rate is None or not 20 <= heart_rate <= 250:
        return jsonify({"success": False, "message": "Heart rate must be between 20 and 250 bpm."}), 400
    if spo2 is None or not 0 <= spo2 <= 100:
        return jsonify({"success": False, "message": "Oxygen saturation must be between 0 and 100%."}), 400
    if temperature is None or not 25 <= temperature <= 45:
        return jsonify({"success": False, "message": "Temperature must be between 25 and 45 °C."}), 400
    if blood_pressure:
        parts = blood_pressure.split("/")
        if (
            len(parts) != 2
            or not all(part.isdigit() for part in parts)
            or not 30 <= int(parts[0]) <= 300
            or not 20 <= int(parts[1]) <= 200
        ):
            return jsonify({"success": False, "message": "Blood pressure must use systolic/diastolic format, such as 120/80."}), 400
    if respiratory_rate_value:
        if not respiratory_rate_value.isdigit() or not 1 <= int(respiratory_rate_value) <= 100:
            return jsonify({"success": False, "message": "Respiratory rate must be between 1 and 100 breaths per minute."}), 400
        respiratory_rate = int(respiratory_rate_value)

    condition_status, alert_message, warnings, critical = assess_vitals(
        heart_rate, spo2, temperature, blood_pressure, respiratory_rate
    )
    alert_level = "Critical" if condition_status == "Critical" else (
        "High" if condition_status == "Needs Attention" else "Normal"
    )

    conn = get_db_connection()
    emergency = conn.execute("SELECT id FROM emergencies WHERE id = ?", (emergency_id,)).fetchone()
    if emergency is None:
        conn.close()
        return jsonify({"success": False, "message": "Emergency not found."}), 404

    conn.execute(
        """
        UPDATE emergencies
        SET heart_rate = ?, spo2 = ?, temperature = ?, blood_pressure = ?, respiratory_rate = ?,
            vitals_source = 'Manual entry', vitals_recorded_by = ?, vitals_updated_at = datetime('now'),
            condition_status = ?, alert_level = ?, alert_message = ?, last_update = datetime('now')
        WHERE id = ?
        """,
        (
            heart_rate, spo2, temperature, blood_pressure or None, respiratory_rate, recorded_by,
            condition_status, alert_level, alert_message, emergency_id,
        ),
    )
    conn.commit()
    conn.close()
    return jsonify({
        "success": True,
        "message": "Manually entered readings saved to the patient record and hospital dashboard.",
        "recorded_by": recorded_by,
        "condition_status": condition_status,
        "alert_message": alert_message,
        "warning_signals": warnings,
        "critical_signals": critical,
        "last_values": {
            "heart_rate": heart_rate,
            "spo2": spo2,
            "temperature": temperature,
            "blood_pressure": blood_pressure or None,
            "respiratory_rate": respiratory_rate,
        },
    })


@app.post("/raise_alert/<int:emergency_id>")
def raise_alert(emergency_id):
    conn = get_db_connection()
    emergency = conn.execute("SELECT * FROM emergencies WHERE id = ?", (emergency_id,)).fetchone()
    if emergency is None:
        conn.close()
        return jsonify({"success": False, "message": "Emergency not found."}), 404

    alert_level = "Critical" if emergency["severity"] == "Critical" else "High"
    message = request.form.get("message") or "Emergency alert recorded by monitoring team."

    conn.execute("UPDATE emergencies SET alert_level = ?, alert_message = ?, condition_status = 'Needs Attention', last_update = datetime('now') WHERE id = ?", (alert_level, message, emergency_id))
    conn.commit()
    conn.close()
    return jsonify({"success": True, "message": "Alert recorded and shared with the hospital team."})


@app.get("/api/health")
def health():
    return jsonify({"ok": True, "message": "RapidResQ demo API is running"})


if __name__ == "__main__":
    initialize_database()
    app.run(debug=True)
