"""
API Router: POST /api/v1/analyze
Implements the core Hackathon Person 1 ➔ Person 2 pipeline contract.
Receives citizen image + GPS coordinates, executes YOLOv8 object detection,
computes Severity, Confidence, and Priority Score, persists to Supabase,
and returns structured inference JSON.
"""

import uuid
import datetime
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from typing import Optional

from app.ai_engine import detector
from app.database import db_service

router = APIRouter(prefix="/api/v1", tags=["Inference & Analysis"])


@router.post("/analyze")
async def analyze_road_damage(
    image: UploadFile = File(...),
    lat: float = Form(...),
    lng: float = Form(...),
    road_class: Optional[str] = Form("Local Street"),
    notes: Optional[str] = Form("")
):
    """
    Unified Endpoint:
    1. Receives image upload & GPS metadata from Citizen Web UI
    2. Runs YOLOv8 object detection (damage type: pothole, crack, surface wear, edge break)
    3. Calculates defect size ratio and severity (Low, Medium, High, Critical)
    4. Evaluates Priority Engine composite score: f(Severity, Confidence, Road Class)
    5. Persists media asset to Supabase Storage Bucket ('road-damage-media')
    6. Writes structured record to Supabase PostgreSQL table 'reports'
    7. Returns the strict Section 3.1 Inference JSON payload contract
    """
    if not image.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Uploaded file must be a valid image format.")

    try:
        image_bytes = await image.read()
        if len(image_bytes) == 0:
            raise HTTPException(status_code=400, detail="Empty image file received.")

        # 1. Execute YOLOv8 & Computer Vision Inference
        inference_result = detector.analyze_image_bytes(
            image_bytes=image_bytes,
            road_class=road_class
        )

        damage_type = inference_result["damage_type"]
        severity = inference_result["severity"]
        confidence = inference_result["confidence"]
        priority_score = inference_result["priority_score"]
        bboxes = inference_result["bboxes"]
        annotated_bytes = inference_result["annotated_bytes"]

        # 2. Upload annotated image to Supabase Storage (or local storage fallback)
        report_id = str(uuid.uuid4())
        filename = f"{report_id}_{image.filename or 'damage.jpg'}"
        image_url = db_service.upload_image(
            file_bytes=annotated_bytes,
            filename=filename,
            content_type="image/jpeg"
        )

        now_timestamp = datetime.datetime.utcnow().isoformat() + "Z"

        # 3. Persist record to Supabase PostgreSQL reports table
        record = {
            "id": report_id,
            "image_url": image_url,
            "latitude": lat,
            "longitude": lng,
            "damage_type": damage_type,
            "severity": severity,
            "confidence": confidence,
            "priority_score": priority_score,
            "status": "Reported",
            "road_class": road_class,
            "bbox": bboxes,
            "notes": notes,
            "created_at": now_timestamp,
            "updated_at": now_timestamp
        }
        db_service.insert_report(record)

        # 4. Return Output Contract (matches Section 3.1 specification)
        return {
            "report_id": report_id,
            "image_url": image_url,
            "location": {
                "lat": lat,
                "lng": lng
            },
            "detection": {
                "type": damage_type,
                "severity": severity,
                "confidence": confidence,
                "priority_score": priority_score
            },
            "timestamp": now_timestamp,
            "road_class": road_class,
            "status": "Reported",
            "bbox": bboxes
        }

    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Inference and persistence failed: {str(e)}")
