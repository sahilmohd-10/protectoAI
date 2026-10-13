"""
One-time database migration script to import historical ppe_log.csv
data into SQLite and seed default users, cameras, and system settings.
"""

import os
import sys
from datetime import datetime
from pathlib import Path
import pandas as pd

# Ensure the root directory is on the Python path
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from app import create_app
from app.extensions import db
from app.models.user import User
from app.models.violation import Violation
from app.models.daily_stat import DailyStat
from app.models.camera import Camera
from app.models.setting import Setting


def import_csv_and_seed():
    app = create_app()

    with app.app_context():
        print("[*] Initializing database tables...")
        db.create_all()

        # 1. Seed Default Users
        if not User.query.filter_by(username="admin").first():
            admin = User(
                username="admin",
                email="admin@protecto.ai",
                role="admin",
            )
            admin.set_password("admin123")
            db.session.add(admin)
            print("[+] Created admin account: admin / admin123")

        if not User.query.filter_by(username="viewer").first():
            viewer = User(
                username="viewer",
                email="viewer@protecto.ai",
                role="viewer",
            )
            viewer.set_password("viewer123")
            db.session.add(viewer)
            print("[+] Created viewer account: viewer / viewer123")

        # 2. Seed Default Cameras
        if Camera.query.count() == 0:
            cam1 = Camera(
                name="Main Gate - Primary Webcam",
                source_type="webcam",
                source_path="0",
                is_active=True,
            )
            cam2 = Camera(
                name="Zone 1 - Demo Video Stream",
                source_type="file",
                source_path="pp2.mp4",
                is_active=False,
            )
            db.session.add_all([cam1, cam2])
            print("[+] Created default cameras: Webcam (0) and Demo Video (pp2.mp4)")

        # 3. Seed Default System Settings
        default_settings = [
            ("confidence_threshold", "0.25", "YOLOv8 minimum detection confidence"),
            ("alert_cooldown_seconds", "30", "Cooldown between duplicate alerts per track ID"),
        ]
        for key, val, desc in default_settings:
            if not Setting.query.filter_by(key=key).first():
                db.session.add(Setting(key=key, value=val, description=desc))
        print("[+] Initialized default system settings.")

        # 4. Import ppe_log.csv
        csv_path = ROOT_DIR / "ppe_log.csv"
        if csv_path.exists():
            print(f"[*] Found CSV file at {csv_path}. Reading data...")
            df = pd.read_csv(csv_path)

            # Strip column whitespace
            df.columns = [c.strip() for c in df.columns]

            # Group by date to aggregate total non-compliance occurrences
            # Columns in CSV: date, hardhat_not, vest_not, mask_not, gloves_not
            grouped = df.groupby("date").agg({
                "hardhat_not": "sum",
                "vest_not": "sum",
                "mask_not": "sum",
                "gloves_not": "sum"
            }).reset_index()

            imported_stats_count = 0
            imported_violations_count = 0

            for _, row in grouped.iterrows():
                date_str = str(row["date"]).strip()
                h_not = int(row["hardhat_not"])
                v_not = int(row["vest_not"])
                m_not = int(row["mask_not"])
                g_not = int(row["gloves_not"])
                tot_viols = h_not + v_not + m_not + g_not

                # Estimate baseline compliant workers for compliance calculation
                estimated_workers = max(tot_viols + 15, 20)
                compliance_rate = round(max(0.0, 100.0 - (tot_viols / (estimated_workers * 3)) * 100.0), 1)

                existing_stat = DailyStat.query.filter_by(date=date_str).first()
                if not existing_stat:
                    stat = DailyStat(
                        date=date_str,
                        hardhat_not=h_not,
                        vest_not=v_not,
                        mask_not=m_not,
                        gloves_not=g_not,
                        total_workers=estimated_workers,
                        compliance_rate=compliance_rate,
                    )
                    db.session.add(stat)
                    imported_stats_count += 1

            # Seed sample individual violation rows for realistic historical analytics
            # if violations table is empty
            if Violation.query.count() == 0:
                for _, row in df.iterrows():
                    d_str = str(row["date"]).strip()
                    try:
                        base_dt = datetime.strptime(d_str, "%Y-%m-%d")
                    except Exception:
                        base_dt = datetime.utcnow()

                    if int(row.get("hardhat_not", 0)) > 0:
                        db.session.add(Violation(
                            timestamp=base_dt,
                            track_id=1,
                            violation_type="Hardhat",
                            camera="Camera 1",
                            confidence=0.88,
                            acknowledged=True
                        ))
                        imported_violations_count += 1
                    if int(row.get("vest_not", 0)) > 0:
                        db.session.add(Violation(
                            timestamp=base_dt,
                            track_id=2,
                            violation_type="Safety Vest",
                            camera="Camera 1",
                            confidence=0.91,
                            acknowledged=True
                        ))
                        imported_violations_count += 1
                    if int(row.get("mask_not", 0)) > 0:
                        db.session.add(Violation(
                            timestamp=base_dt,
                            track_id=3,
                            violation_type="Mask",
                            camera="Camera 1",
                            confidence=0.85,
                            acknowledged=True
                        ))
                        imported_violations_count += 1

            db.session.commit()
            print(f"[+] Successfully imported {imported_stats_count} daily stat records and {imported_violations_count} sample violation logs.")
        else:
            print("[!] ppe_log.csv not found; skipped CSV import.")

        print("[OK] Database setup & migration complete!")


if __name__ == "__main__":
    import_csv_and_seed()
