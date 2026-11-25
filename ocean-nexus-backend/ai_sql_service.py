import os
import google.generativeai as genai

# Configure Google Gemini API key
gemini_api_key = os.getenv("GEMINI_API_KEY", "")
if gemini_api_key:
    genai.configure(api_key=gemini_api_key)

# Using Gemini 1.5 Flash for fast and accurate Text-to-SQL generation
sql_model = genai.GenerativeModel("gemini-1.5-flash")

def generate_sql_from_query(user_query: str) -> str:
    """
    User query-a eduthu PostGIS SQL query-ah convert panra function (Google Gemini version)
    """
    system_prompt = """
    You are an expert PostGIS SQL generator for an oceanographic database.
    The database schema has two tables:
    1. argo_profiles (profile_id SERIAL PRIMARY KEY, float_id VARCHAR(50), location GEOMETRY(Point, 4326), time TIMESTAMP WITH TIME ZONE)
    2. argo_measurements (measurement_id SERIAL PRIMARY KEY, profile_id INT REFERENCES argo_profiles(profile_id), depth_m FLOAT, temperature_c FLOAT, salinity_psu FLOAT)

    Rules:
    - Convert the user's natural language question into a valid PostgreSQL query using PostGIS functions.
    - If a region or location is mentioned, use ST_MakeEnvelope and ST_Within for spatial filtering (SRID 4326).
    - Return ONLY the raw SQL query. Do not include markdown formatting like ```sql or any extra explanation.
    """

    full_prompt = f"{system_prompt}\n\nUser Query: {user_query}"

    response = sql_model.generate_content(
        full_prompt,
        generation_config=genai.types.GenerationConfig(
            temperature=0.0
        )
    )
    
    sql_query = response.text.strip()
    
    # Clean up markdown code blocks if Gemini returns them
    if sql_query.startswith("```sql"):
        sql_query = sql_query[6:]
    elif sql_query.startswith("```"):
        sql_query = sql_query[3:]
    if sql_query.endswith("```"):
        sql_query = sql_query[:-3]
        
    return sql_query.strip()