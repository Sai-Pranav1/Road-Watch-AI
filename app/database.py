"""
Unified Database & Storage Layer
Seamlessly supports Supabase PostgreSQL + Supabase Storage,
with an automatic embedded SQLite + Local Media fallback for offline hackathon demos.
"""

import os
import json
import sqlite3
import uuid
import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
import requests

from app.config import settings, UPLOAD_DIR, DB_PATH


class DatabaseService:
    def __init__(self):
        self.supabase_url = settings.SUPABASE_URL.rstrip("/")
        self.supabase_key = settings.SUPABASE_SERVICE_ROLE_KEY or settings.SUPABASE_KEY
        self.bucket_name = settings.SUPABASE_STORAGE_BUCKET
        self.is_supabase_configured = bool(self.supabase_url and self.supabase_key)

        if self.is_supabase_configured:
            print(f"[Database] Active backend: Supabase Cloud ({self.supabase_url})")
        else:
            print("[Database] Supabase credentials not found in env. Initializing embedded local SQLite fallback.")
            self._init_sqlite()

    def _init_sqlite(self):
        """Initializes local SQLite tables matching the Supabase PostgreSQL schema."""
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        # Jurisdictions table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS jurisdictions (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                code TEXT UNIQUE NOT NULL,
                contact_email TEXT,
                boundary_geojson TEXT,
                active_crew_count INTEGER DEFAULT 3,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)

        # Reports table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS reports (
                id TEXT PRIMARY KEY,
                image_url TEXT NOT NULL,
                latitude REAL NOT NULL,
                longitude REAL NOT NULL,
                damage_type TEXT NOT NULL,
                severity TEXT NOT NULL,
                confidence REAL NOT NULL,
                priority_score INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'Reported',
                road_class TEXT NOT NULL DEFAULT 'Local Street',
                bbox TEXT DEFAULT '[]',
                assigned_crew TEXT,
                jurisdiction_id TEXT,
                notes TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now'))
            )
        """)

        # Status Updates table (Audit Log)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS status_updates (
                id TEXT PRIMARY KEY,
                report_id TEXT NOT NULL,
                previous_status TEXT,
                new_status TEXT NOT NULL,
                changed_by TEXT NOT NULL DEFAULT 'Municipal Operator',
                notes TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (report_id) REFERENCES reports (id) ON DELETE CASCADE
            )
        """)

        # Create indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_reports_priority ON reports (priority_score DESC)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_reports_coords ON reports (latitude, longitude)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_reports_status ON reports (status)")

        # Seed default jurisdictions if empty
        cursor.execute("SELECT COUNT(*) FROM jurisdictions")
        if cursor.fetchone()[0] == 0:
            default_jurisdictions = [
                (str(uuid.uuid4()), "Metro Central District", "METRO-C", "central.dispatch@cityworks.gov", 5),
                (str(uuid.uuid4()), "North Highway Division", "HIGHWAY-N", "north.maintenance@cityworks.gov", 4),
                (str(uuid.uuid4()), "South Suburban Precinct", "SUBURB-S", "south.roads@cityworks.gov", 3),
                (str(uuid.uuid4()), "East Industrial Sector", "IND-E", "east.works@cityworks.gov", 2),
            ]
            cursor.executemany(
                "INSERT INTO jurisdictions (id, name, code, contact_email, active_crew_count) VALUES (?, ?, ?, ?, ?)",
                default_jurisdictions
            )

        conn.commit()
        conn.close()

    # -------------------------------------------------------------------------
    # Storage Uploads
    # -------------------------------------------------------------------------
    def upload_image(self, file_bytes: bytes, filename: str, content_type: str = "image/jpeg") -> str:
        """
        Uploads image to Supabase Storage Bucket, or saves to local static uploads folder.
        Returns the publicly accessible URL.
        """
        # Save local copy first
        safe_name = f"{uuid.uuid4().hex[:12]}_{filename}"
        local_path = UPLOAD_DIR / safe_name
        with open(local_path, "wb") as f:
            f.write(file_bytes)

        local_url = f"/static/uploads/{safe_name}"

        # If Supabase is configured, upload to Supabase Storage
        if self.is_supabase_configured:
            try:
                storage_url = f"{self.supabase_url}/storage/v1/object/{self.bucket_name}/{safe_name}"
                headers = {
                    "apikey": self.supabase_key,
                    "Authorization": f"Bearer {self.supabase_key}",
                    "Content-Type": content_type,
                    "x-upsert": "true"
                }
                res = requests.post(storage_url, headers=headers, data=file_bytes, timeout=8)
                if res.status_code in (200, 201):
                    public_url = f"{self.supabase_url}/storage/v1/object/public/{self.bucket_name}/{safe_name}"
                    return public_url
                else:
                    print(f"[Supabase Storage] Upload returned status {res.status_code}: {res.text}. Using local fallback.")
            except Exception as e:
                print(f"[Supabase Storage] Error uploading: {e}. Falling back to local URL.")

        return local_url

    # -------------------------------------------------------------------------
    # Reports Persistence
    # -------------------------------------------------------------------------
    def insert_report(self, report_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Inserts report into Supabase PostgreSQL reports table, or local SQLite.
        """
        report_id = report_data.get("id") or str(uuid.uuid4())
        report_data["id"] = report_id
        if "created_at" not in report_data:
            report_data["created_at"] = datetime.datetime.utcnow().isoformat() + "Z"
        if "updated_at" not in report_data:
            report_data["updated_at"] = report_data["created_at"]

        # Ensure bbox is serialized
        bbox_json = json.dumps(report_data.get("bbox", []))

        if self.is_supabase_configured:
            try:
                endpoint = f"{self.supabase_url}/rest/v1/reports"
                headers = {
                    "apikey": self.supabase_key,
                    "Authorization": f"Bearer {self.supabase_key}",
                    "Content-Type": "application/json",
                    "Prefer": "return=representation"
                }
                payload = {
                    "id": report_id,
                    "image_url": report_data["image_url"],
                    "latitude": float(report_data["latitude"]),
                    "longitude": float(report_data["longitude"]),
                    "damage_type": report_data["damage_type"],
                    "severity": report_data["severity"],
                    "confidence": float(report_data["confidence"]),
                    "priority_score": int(report_data["priority_score"]),
                    "status": report_data.get("status", "Reported"),
                    "road_class": report_data.get("road_class", "Local Street"),
                    "bbox": report_data.get("bbox", []),
                    "notes": report_data.get("notes", ""),
                    "created_at": report_data["created_at"],
                    "updated_at": report_data["updated_at"]
                }
                res = requests.post(endpoint, headers=headers, json=payload, timeout=8)
                if res.status_code in (200, 201):
                    inserted = res.json()
                    return inserted[0] if isinstance(inserted, list) and inserted else payload
                else:
                    print(f"[Supabase DB] Insert error {res.status_code}: {res.text}. Falling back to SQLite.")
            except Exception as e:
                print(f"[Supabase DB] Error inserting to Supabase: {e}. Falling back to SQLite.")

        # Local SQLite fallback
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO reports (
                id, image_url, latitude, longitude, damage_type, severity, 
                confidence, priority_score, status, road_class, bbox, assigned_crew, notes, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            report_id,
            report_data["image_url"],
            float(report_data["latitude"]),
            float(report_data["longitude"]),
            report_data["damage_type"],
            report_data["severity"],
            float(report_data["confidence"]),
            int(report_data["priority_score"]),
            report_data.get("status", "Reported"),
            report_data.get("road_class", "Local Street"),
            bbox_json,
            report_data.get("assigned_crew", None),
            report_data.get("notes", ""),
            report_data["created_at"],
            report_data["updated_at"]
        ))
        conn.commit()
        conn.close()

        return report_data

    def get_reports(
        self,
        status: Optional[str] = None,
        severity: Optional[str] = None,
        min_priority: Optional[int] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Retrieves damage reports sorted by priority_score DESC.
        """
        if self.is_supabase_configured:
            try:
                query_params = ["order=priority_score.desc"]
                if status and status.lower() != "all":
                    query_params.append(f"status=eq.{status}")
                if severity and severity.lower() != "all":
                    query_params.append(f"severity=eq.{severity}")
                if min_priority is not None:
                    query_params.append(f"priority_score=gte.{min_priority}")
                query_params.append(f"limit={limit}")

                url = f"{self.supabase_url}/rest/v1/reports?{'&'.join(query_params)}"
                headers = {
                    "apikey": self.supabase_key,
                    "Authorization": f"Bearer {self.supabase_key}"
                }
                res = requests.get(url, headers=headers, timeout=8)
                if res.status_code == 200:
                    return res.json()
            except Exception as e:
                print(f"[Supabase DB] Error querying reports: {e}. Reading from local SQLite.")

        # Local SQLite
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        query = "SELECT * FROM reports WHERE 1=1"
        params = []
        if status and status.lower() != "all":
            query += " AND status = ?"
            params.append(status)
        if severity and severity.lower() != "all":
            query += " AND severity = ?"
            params.append(severity)
        if min_priority is not None:
            query += " AND priority_score >= ?"
            params.append(min_priority)

        query += " ORDER BY priority_score DESC, created_at DESC LIMIT ?"
        params.append(limit)

        cursor.execute(query, params)
        rows = cursor.fetchall()
        results = []
        for r in rows:
            d = dict(r)
            if isinstance(d.get("bbox"), str):
                try:
                    d["bbox"] = json.loads(d["bbox"])
                except Exception:
                    d["bbox"] = []
            results.append(d)
        conn.close()
        return results

    def get_report_by_id(self, report_id: str) -> Optional[Dict[str, Any]]:
        if self.is_supabase_configured:
            try:
                url = f"{self.supabase_url}/rest/v1/reports?id=eq.{report_id}"
                headers = {
                    "apikey": self.supabase_key,
                    "Authorization": f"Bearer {self.supabase_key}"
                }
                res = requests.get(url, headers=headers, timeout=8)
                if res.status_code == 200:
                    data = res.json()
                    if data:
                        return data[0]
            except Exception as e:
                print(f"[Supabase DB] Error getting report by ID: {e}")

        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM reports WHERE id = ?", (report_id,))
        row = cursor.fetchone()
        conn.close()
        if row:
            d = dict(row)
            if isinstance(d.get("bbox"), str):
                try:
                    d["bbox"] = json.loads(d["bbox"])
                except Exception:
                    d["bbox"] = []
            return d
        return None

    def update_report_status(
        self,
        report_id: str,
        new_status: str,
        assigned_crew: Optional[str] = None,
        notes: Optional[str] = None,
        changed_by: str = "Municipal Operator"
    ) -> Optional[Dict[str, Any]]:
        """
        Updates status ('Reported', 'Assigned', 'In Progress', 'Resolved')
        and writes to status_updates audit table.
        """
        current = self.get_report_by_id(report_id)
        if not current:
            return None

        previous_status = current.get("status")
        now_iso = datetime.datetime.utcnow().isoformat() + "Z"

        if self.is_supabase_configured:
            try:
                # Update report
                url = f"{self.supabase_url}/rest/v1/reports?id=eq.{report_id}"
                headers = {
                    "apikey": self.supabase_key,
                    "Authorization": f"Bearer {self.supabase_key}",
                    "Content-Type": "application/json",
                    "Prefer": "return=representation"
                }
                body = {
                    "status": new_status,
                    "updated_at": now_iso
                }
                if assigned_crew is not None:
                    body["assigned_crew"] = assigned_crew
                if notes is not None:
                    body["notes"] = notes

                res = requests.patch(url, headers=headers, json=body, timeout=8)
                
                # Insert status update audit log
                audit_url = f"{self.supabase_url}/rest/v1/status_updates"
                audit_body = {
                    "report_id": report_id,
                    "previous_status": previous_status,
                    "new_status": new_status,
                    "changed_by": changed_by,
                    "notes": notes or f"Status shifted to {new_status}"
                }
                requests.post(audit_url, headers=headers, json=audit_body, timeout=8)

                if res.status_code == 200:
                    data = res.json()
                    return data[0] if data else body
            except Exception as e:
                print(f"[Supabase DB] Error updating status in Supabase: {e}")

        # Local SQLite update
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        crew_val = assigned_crew if assigned_crew is not None else current.get("assigned_crew")
        notes_val = notes if notes is not None else current.get("notes")

        cursor.execute("""
            UPDATE reports
            SET status = ?, assigned_crew = ?, notes = ?, updated_at = ?
            WHERE id = ?
        """, (new_status, crew_val, notes_val, now_iso, report_id))

        # Insert audit log
        cursor.execute("""
            INSERT INTO status_updates (id, report_id, previous_status, new_status, changed_by, notes, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            str(uuid.uuid4()),
            report_id,
            previous_status,
            new_status,
            changed_by,
            notes or f"Status transitioned from {previous_status} to {new_status}",
            now_iso
        ))
        conn.commit()
        conn.close()

        return self.get_report_by_id(report_id)

    def get_stats(self) -> Dict[str, Any]:
        """Calculates live KPI metrics for dashboard."""
        reports = self.get_reports(limit=500)
        total = len(reports)
        if total == 0:
            return {
                "total_reports": 0,
                "pending_triage": 0,
                "assigned": 0,
                "in_progress": 0,
                "resolved": 0,
                "critical_count": 0,
                "high_priority_count": 0,
                "avg_priority_score": 0,
                "active_crews": 4
            }

        pending = sum(1 for r in reports if r.get("status") == "Reported")
        assigned = sum(1 for r in reports if r.get("status") == "Assigned")
        in_prog = sum(1 for r in reports if r.get("status") == "In Progress")
        resolved = sum(1 for r in reports if r.get("status") == "Resolved")
        critical = sum(1 for r in reports if r.get("severity") == "Critical")
        high_prio = sum(1 for r in reports if (r.get("priority_score") or 0) >= 75)
        avg_score = round(sum((r.get("priority_score") or 0) for r in reports) / total, 1)

        return {
            "total_reports": total,
            "pending_triage": pending,
            "assigned": assigned,
            "in_progress": in_prog,
            "resolved": resolved,
            "critical_count": critical,
            "high_priority_count": high_prio,
            "avg_priority_score": avg_score,
            "active_crews": 4
        }


db_service = DatabaseService()
