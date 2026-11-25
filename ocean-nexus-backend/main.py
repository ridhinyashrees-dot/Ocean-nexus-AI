import os
import json
import re

from sqlalchemy.orm import Session
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional, List, Dict
from db import get_db
from dotenv import load_dotenv
import google.generativeai as genai
from ai_sql_service import generate_sql_from_query
from argo_service import fetch_real_argo_data
from sqlalchemy import text

load_dotenv()

app = FastAPI(
    title="Ocean Nexus AI Engine",
    version="13.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =========================================================
# REQUEST MODEL
# =========================================================

class ChatQueryRequest(BaseModel):
    query: str
    history: Optional[List[Dict[str, str]]] = Field(
        default_factory=list
    )


# =========================================================
# GOOGLE GEMINI SETUP (Replaced Azure OpenAI)
# =========================================================

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

gemini_client = None

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    # Using Gemini 1.5 Flash for fast chat processing
    gemini_client = genai.GenerativeModel("gemini-3.5-flash")


# =========================================================
# ROOT ENDPOINT
# =========================================================

@app.get("/")
def root():
    return {
        "status": "Ocean Nexus AI Engine Ready",
        "version": "13.0.0"
    }


# =========================================================
# ARGO DATA ENDPOINT
# =========================================================

@app.get("/api/argo")
def get_argo_data(limit: int = 100):

    try:
        argo_data = fetch_real_argo_data()

        trajectory = argo_data.get("trajectory", [])

        # Send only limited points to frontend
        response_trajectory = trajectory[:limit]

        metrics = calculate_argo_metrics(trajectory)

        return {
            "success": True,
            "source": "ARGO GDAC",

            "float_id": argo_data.get(
                "float_id",
                "ARGO-GLOBAL"
            ),

            "latitude": argo_data.get(
                "latitude",
                15.0
            ),

            "longitude": argo_data.get(
                "longitude",
                80.0
            ),

             "trajectory": response_trajectory,

            "metrics": metrics,

            "source_file": argo_data.get(
                "source_file",
                ""
            )
        }


    except Exception as error:

        print("ARGO ERROR:", error)

        raise HTTPException(
            status_code=500,
            detail=f"Unable to fetch ARGO data: {str(error)}"
        )


def calculate_argo_metrics(trajectory):
    """
    Calculates ocean metrics dynamically from real ARGO data.
    """
    if not trajectory:
        return {
            "surface_temp": None,
            "deep_temp": None,
            "average_temp": None,
            "average_salinity": None,
            "max_depth": None,
            "depth_range": "Unknown",
            "measurement_count": 0
        }

    temperature_points = []

    for point in trajectory:
        depth = point.get("pressure")
        temp = point.get("temperature")

        if depth is None or temp is None:
            continue

        try:
            temperature_points.append({
                "depth": float(depth),
                "temp": float(temp)
            })
        except (ValueError, TypeError):
            continue

    salinity_values = []

    for point in trajectory:
        salinity = point.get("salinity")

        if salinity is None:
            continue

        try:
            salinity_values.append(float(salinity))
        except (ValueError, TypeError):
            continue

    depth_values = []

    for point in trajectory:
        depth = point.get("pressure")

        if depth is None:
            continue

        try:
            depth_values.append(float(depth))
        except (ValueError, TypeError):
            continue

    surface_temp = None
    deep_temp = None

    if temperature_points:
        shallowest_point = min(
            temperature_points,
            key=lambda point: point["depth"]
        )

        deepest_point = max(
            temperature_points,
            key=lambda point: point["depth"]
        )

        surface_temp = shallowest_point["temp"]
        deep_temp = deepest_point["temp"]

    average_temp = None

    if temperature_points:
        average_temp = (
            sum(point["temp"] for point in temperature_points)
            / len(temperature_points)
        )

    average_salinity = None

    if salinity_values:
        average_salinity = (
            sum(salinity_values)
            / len(salinity_values)
        )

    max_depth = None

    if depth_values:
        max_depth = max(depth_values)

    depth_range = "Unknown"

    if max_depth is not None:
        depth_range = f"0–{max_depth:.0f}m"

    return {
        "surface_temp": (
            round(surface_temp, 2)
            if surface_temp is not None
            else None
        ),

        "deep_temp": (
            round(deep_temp, 2)
            if deep_temp is not None
            else None
        ),

        "average_temp": (
            round(average_temp, 2)
            if average_temp is not None
            else None
        ),

        "average_salinity": (
            round(average_salinity, 2)
            if average_salinity is not None
            else None
        ),

        "max_depth": (
            round(max_depth, 2)
            if max_depth is not None
            else None
        ),

        "depth_range": depth_range,

        "measurement_count": len(trajectory)
    }


def dynamic_ocean_ai_processor(user_query: str):

    text = user_query.lower().strip()

    greeting_words = [
        "hi", "hello", "hey", "how are you", "who are you", "how are u", "sup", "greetings"
    ]

    ocean_keywords = [
        "temp", "temperature", "ocean", "argo", "sea", "bay", "salinity", "depth", "heatwave", "marine", "float", "thermocline"
    ]

    is_greeting = any(
        re.search(rf"\b{re.escape(word)}\b", text)
        for word in greeting_words
    )

    is_ocean_query = any(
        keyword in text
        for keyword in ocean_keywords
    )

    if is_greeting and not is_ocean_query:
        return {
            "text_response": (
                "Hello! I am Ocean Nexus AI. "
                "I can analyze ARGO float oceanography, "
                "thermocline layers, salinity, temperature "
                "and marine heatwaves. "
                "How can I assist your marine research today?"
            ),
            "is_casual": True,
            "is_text_only": True,
            "visualization_params": None
        }

    reasoning_keywords = [
        "why", "reason", "explain", "how come", "what causes", "cause", "due to", "meaning"
    ]

    is_reasoning_query = any(
        word in text
        for word in reasoning_keywords
    )

    # -----------------------------------------------------
    # Google Gemini Processing (Replaced Azure OpenAI Call)
    # -----------------------------------------------------

    if gemini_client:
        try:
            system_prompt = """
You are Ocean Nexus AI, an expert oceanographer.
Analyze the user's ocean-related query.
Return valid JSON only (no markdown code blocks, just raw JSON).

{
  "is_text_only": boolean,
  "text_response": string,
  "title": string,
  "region": string,
  "start_year": string,
  "end_year": string,
  "float_id": string or null,
  "start_date": string or null,
  "end_date": string or null,
  "has_heatwave": boolean
}

Rules:
- If the user asks why, explain, reason or cause, set is_text_only to true.
- If the user asks for map, chart, profile, temperature, salinity or ARGO analysis, set is_text_only to false.

- Do not invent exact real-time ARGO measurements.
- Do not invent float IDs or dates.
- Mention scientific explanations clearly.

- If the user specifies an ARGO float ID, extract it exactly and return it in float_id.
- If the user does not specify an ARGO float ID, return null for float_id.

- If the user specifies a specific date or date range, return start_date and end_date in YYYY-MM-DD format.
- If the user specifies a month and year, convert it to the complete date range.
  Example:
  December 2024:
  start_date = "2024-12-01"
  end_date = "2024-12-31"

- If the user specifies only a year:
  Example:
  2024:
  start_date = "2024-01-01"
  end_date = "2024-12-31"

- If no specific date or date range is mentioned, return null for start_date and end_date.
"""

            full_prompt = f"{system_prompt}\n\nUser Query: {user_query}"
            response = gemini_client.generate_content(full_prompt)
            content = response.text.strip()

            # Clean up markdown code blocks if Gemini returns them
            if content.startswith("```json"):
                content = content[7:]
            if content.startswith("```"):
                content = content[3:]
            if content.endswith("```"):
                content = content[:-3]

            ai_data = json.loads(content.strip())

            region = ai_data.get(
                "region",
                "Arabian Sea" if "arabian" in text else "Bay of Bengal"
            )

            if "arabian" in region.lower():
                bbox = [60.0, 8.0, 77.0, 25.0]
            else:
                bbox = [80.0, 5.0, 95.0, 22.0]

            return {
                "text_response": ai_data.get(
                    "text_response",
                    f"Analyzing ARGO data for {region}."
                ),
                "is_casual": False,
                "is_text_only": ai_data.get("is_text_only", is_reasoning_query),
                "title": ai_data.get("title", f"{region} 4D Telemetry Analysis"),
               "visualization_params": {
    "region": region,
    "bbox": bbox,
    "start_year": ai_data.get("start_year", "2023"),
    "end_year": ai_data.get("end_year", "2024"),
    "float_id": ai_data.get("float_id"),
    "start_date": ai_data.get("start_date"),
    "end_date": ai_data.get("end_date"),
    "has_heatwave": ai_data.get(
        "has_heatwave",
        False
    )
}
            }

        except Exception as error:
            print(f"Gemini API Error: {error}")

    # Fallback response
    is_arabian = "arabian" in text
    region_name = "Arabian Sea" if is_arabian else "Bay of Bengal"

    if is_arabian:
        bbox = [60.0, 8.0, 77.0, 25.0]
        text_response = (
            "Analyzing ARGO telemetry for the Arabian Sea. "
            "The region is influenced by strong evaporation, "
            "high salinity and seasonal monsoon circulation."
        )
    else:
        bbox = [80.0, 5.0, 95.0, 22.0]
        text_response = (
            "Analyzing ARGO telemetry for the Bay of Bengal. "
            "River runoff, rainfall and monsoon circulation "
            "strongly influence surface salinity and temperature."
        )

    return {
        "text_response": text_response,
        "is_casual": False,
        "is_text_only": is_reasoning_query,
        "title": f"{region_name} 4D Telemetry Analysis",
        "visualization_params": {
            "region": region_name,
            "bbox": bbox,
            "start_year": "2023",
            "end_year": "2024",
            "has_heatwave": False
        }
    }


# =========================================================
# CHAT ENDPOINT
# =========================================================

@app.post("/api/v1/chat")
def handle_chat_post(req: ChatQueryRequest):
    return process_chat_query(req.query)


@app.get("/api/v1/chat")
def handle_chat_get(q: Optional[str] = None):
    user_text = q or "Bay of Bengal temperature"
    return process_chat_query(user_text)


# =========================================================
# FRONTEND DEDICATED ARGO FLOATS ENDPOINT
# =========================================================

@app.get("/api/v1/argo-floats")
def get_frontend_argo_floats():
    try:
        argo_result = fetch_real_argo_data(
    float_id=ai_output.get("float_id"),
    start_date=ai_output.get("start_date"),
    end_date=ai_output.get("end_date")
)
        trajectory_4d = argo_result.get("trajectory", [])
        
        if not trajectory_4d:
            raise ValueError("Empty trajectory from GDAC")

        float_id = argo_result.get("float_id", "ARGO-GLOBAL")
        lat = argo_result.get("latitude", 15.0)
        lng = argo_result.get("longitude", 80.0)
        source_file = argo_result.get("source_file", "")
        region = argo_result.get("region", "Bay of Bengal")

    except Exception as error:
        print(f"Using fallback ARGO data due to: {error}")
        float_id = "ARGO-FALLBACK-5906495"
        region = "Bay of Bengal"
        lat = 13.08
        lng = 80.27
        source_file = "fallback_mock_data.nc"
        trajectory_4d = [
            {"lat": 13.0, "lng": 80.0, "depth": 10, "temp": 29.2, "salinity": 34.5, "time": "2026-03-01T00:00:00Z"},
            {"lat": 13.5, "lng": 80.5, "depth": 50, "temp": 26.8, "salinity": 35.0, "time": "2026-03-02T00:00:00Z"},
            {"lat": 14.0, "lng": 81.0, "depth": 100, "temp": 23.5, "salinity": 35.2, "time": "2026-03-03T00:00:00Z"},
            {"lat": 14.5, "lng": 81.5, "depth": 200, "temp": 19.1, "salinity": 34.9, "time": "2026-03-04T00:00:00Z"}
        ]

    metrics = calculate_argo_metrics(trajectory_4d)

    dashboard_payload = [
        {
            "float_id": float_id,
            "title": f"{region} 4D Telemetry Analysis",
            "region": region,
            "surface_temp": metrics["surface_temp"],
            "deep_temp": metrics["deep_temp"],
            "average_temp": metrics["average_temp"],
            "average_salinity": metrics["average_salinity"],
            "depth_range": metrics["depth_range"],
            "max_depth": metrics["max_depth"],
            "measurement_count": metrics["measurement_count"],
            "lat": lat,
            "lng": lng,
            "has_heatwave": False,
            "trajectory_4d": trajectory_4d,
            "source_file": source_file
        }
    ]

    return {
        "success": True,
        "dashboard_payload": dashboard_payload
    }


def process_chat_query(user_text: str):

    ai_output = dynamic_ocean_ai_processor(user_text)

    if ai_output["is_casual"] or ai_output.get("is_text_only", False):
        return {
            "success": True,
            "query": user_text,
            "chat_response": ai_output["text_response"],
            "generated_sql": "",
            "dashboard_payload": None,
            "visualization_ready": False
        }

    # Get dynamic parameters extracted by Gemini
    vis = ai_output.get("visualization_params", {})

    float_id_filter = vis.get("float_id")
    start_date = vis.get("start_date")
    end_date = vis.get("end_date")

    try:

        argo_result = fetch_real_argo_data(
            float_id=float_id_filter,
            start_date=start_date,
            end_date=end_date
        )

        trajectory_4d = argo_result.get("trajectory", [])

        float_id = argo_result.get(
            "float_id",
            "ARGO-GLOBAL"
        )

        lat = argo_result.get(
            "latitude",
            15.0
        )

        lng = argo_result.get(
            "longitude",
            80.0
        )

        source_file = argo_result.get(
            "source_file",
            ""
        )

    except Exception as error:

        print(
            f"Live ARGO fetch error: {error}"
        )

        trajectory_4d = []
        float_id = "ARGO-FALLBACK"
        lat = 13.08
        lng = 80.27
        source_file = ""

    metrics = calculate_argo_metrics(
        trajectory_4d
    )

    bbox = vis.get(
        "bbox",
        [80.0, 5.0, 95.0, 22.0]
    )

    region = vis.get(
        "region",
        "Bay of Bengal"
    )

    start_year = vis.get(
        "start_year",
        "2023"
    )

    end_year = vis.get(
        "end_year",
        "2024"
    )

    has_heatwave = vis.get(
        "has_heatwave",
        False
    )

    # Dynamic SQL shown in response
    generated_sql = (
        "SELECT "
        "p.float_id, "
        "p.location, "
        "p.time, "
        "m.depth_m, "
        "m.temperature_c, "
        "m.salinity_psu "
        "FROM argo_profiles p "
        "JOIN argo_measurements m "
        "ON p.profile_id = m.profile_id "
        f"WHERE ST_Within("
        f"p.location, "
        f"ST_MakeEnvelope("
        f"{bbox[0]}, "
        f"{bbox[1]}, "
        f"{bbox[2]}, "
        f"{bbox[3]}, "
        f"4326"
        f")) "
        f"AND p.time BETWEEN "
        f"'{start_year}-01-01' "
        f"AND "
        f"'{end_year}-12-31' "
        "ORDER BY p.time ASC "
        "LIMIT 100;"
    )

    dashboard_payload = [
        {
            "float_id": float_id,

            "title": ai_output.get(
                "title",
                f"{region} 4D Telemetry Analysis"
            ),

            "region": region,

            "surface_temp":
                metrics["surface_temp"],

            "deep_temp":
                metrics["deep_temp"],

            "average_temp":
                metrics["average_temp"],

            "average_salinity":
                metrics["average_salinity"],

            "depth_range":
                metrics["depth_range"],

            "max_depth":
                metrics["max_depth"],

            "measurement_count":
                metrics["measurement_count"],

            "lat": lat,
            "lng": lng,

            "has_heatwave":
                has_heatwave,

            "trajectory_4d":
                trajectory_4d,

            "source_file":
                source_file
        }
    ]

    print("======================================")
    print("DYNAMIC DASHBOARD DEBUG")
    print("Query:", user_text)
    print("Float:", float_id)
    print("Region:", region)
    print("Points:", len(trajectory_4d))
    print("Surface Temp:", metrics["surface_temp"])
    print("Deep Temp:", metrics["deep_temp"])
    print("Average Temp:", metrics["average_temp"])
    print("Average Salinity:", metrics["average_salinity"])
    print("Max Depth:", metrics["max_depth"])
    print("First Point:", trajectory_4d[0] if trajectory_4d else None)
    print("Last Point:", trajectory_4d[-1] if trajectory_4d else None)
    print("======================================")
    return {
        "success": True,
        "query": user_text,

        "chat_response":
            ai_output["text_response"],

        "generated_sql":
            generated_sql,

        "dashboard_payload":
            dashboard_payload,

        "visualization_ready":
            True
    }

@app.post("/api/text-to-sql-query")
def run_text_to_sql(payload: dict, db: Session = Depends(get_db)):
    user_query = payload.get("query")
    if not user_query:
        raise HTTPException(status_code=400, detail="Query cannot be empty")
    
    try:
        generated_sql = generate_sql_from_query(user_query)
        result = db.execute(text(generated_sql))
        rows = [dict(row._mapping) for row in result]
        
        return {
            "user_query": user_query,
            "generated_sql": generated_sql,
            "data": rows
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))