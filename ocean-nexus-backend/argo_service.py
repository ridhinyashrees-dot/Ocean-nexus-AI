import gzip
import csv
import io
import re
import requests
import numpy as np
import xarray as xr
import psycopg2

from datetime import datetime, timedelta


# =========================================================
# POSTGRESQL CONFIGURATION
# =========================================================

POSTGRES_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "database": "ocean_nexus_argo",
    "user": "postgres",
    "password": "Ridhinya@2008"
}


def get_postgres_connection():

    return psycopg2.connect(
        host=POSTGRES_CONFIG["host"],
        port=POSTGRES_CONFIG["port"],
        dbname=POSTGRES_CONFIG["database"],
        user=POSTGRES_CONFIG["user"],
        password=POSTGRES_CONFIG["password"]
    )

# =========================================================
# FETCH ARGO DATA FROM POSTGRESQL
# =========================================================

def fetch_argo_from_postgres(
    float_id=None,
    start_date=None,
    end_date=None,
    max_points=500
):

    print("======================================")
    print("FETCHING ARGO DATA FROM POSTGRESQL")
    print("======================================")

    conn = None
    cursor = None

    try:

        conn = get_postgres_connection()
        cursor = conn.cursor()

        query = """
            SELECT
                platform_number,
                cycle_number,
                time,
                latitude,
                longitude,
                pres_adjusted,
                temp_adjusted,
                psal_adjusted,
                pres_adjusted_error
            FROM argo_measurements
            WHERE data_mode = 'D'
              AND pres_adjusted_qc = 1
              AND temp_adjusted_qc = 1
              AND psal_adjusted_qc = 1
              AND pres_adjusted_error < 20
              AND temp_adjusted IS NOT NULL
              AND psal_adjusted IS NOT NULL
        """

        params = []

        if float_id:
            query += " AND platform_number = %s"
            params.append(int(float_id))

        if start_date:
            query += " AND time >= %s"
            params.append(start_date)

        if end_date:
            query += " AND time <= %s"
            params.append(end_date)

        query += """
            ORDER BY time ASC, pres_adjusted ASC
        """

        cursor.execute(query, params)

        rows = cursor.fetchall()

        print("PostgreSQL rows:", len(rows))

        if not rows:
            raise Exception(
                "No valid ARGO data found in PostgreSQL"
            )

        MAX_TRAJECTORY_POINTS = max_points

        if len(rows) > MAX_TRAJECTORY_POINTS:
            step = len(rows) // MAX_TRAJECTORY_POINTS
            rows = rows[::step][:MAX_TRAJECTORY_POINTS]

        print(
            "Rows selected for dashboard:",
            len(rows)
        )

        trajectory = []

        for row in rows:

            (
                platform_number,
                cycle_number,
                time,
                latitude,
                longitude,
                pressure,
                temperature,
                salinity,
                pressure_error
            ) = row

            trajectory.append({
                "float_id": str(int(platform_number)),
                "cycle_number": int(cycle_number),
                "time": time.isoformat() if time else None,
                "latitude": float(latitude),
                "longitude": float(longitude),
                "pressure": float(pressure),
                "temperature": float(temperature),
                "salinity": float(salinity),
                "pressure_error": float(pressure_error),
                "qc_pass": True
            })

        latest = trajectory[-1]

        print("Latest Float ID:", latest["float_id"])
        print("Latest Latitude:", latest["latitude"])
        print("Latest Longitude:", latest["longitude"])
        print("Trajectory points:", len(trajectory))

        return {
            "float_id": latest["float_id"],
            "latitude": latest["latitude"],
            "longitude": latest["longitude"],
            "trajectory": trajectory,
            "source_file": "PostgreSQL: argo_measurements",
            "qc_summary": {
                "total_points": len(trajectory),
                "valid_points": len(trajectory),
                "rejected_points": 0
            }
        }

    except Exception as error:

        print("POSTGRES ERROR:", error)

        raise

    finally:

        if cursor:
            cursor.close()

        if conn:
            conn.close()
# =========================================================
# ARGO GDAC CONFIGURATION
# =========================================================

ARGO_BASE_URL = "https://data-argo.ifremer.fr/"

ARGO_PROFILE_INDEX_URL = (
    ARGO_BASE_URL + "ar_index_global_prof.txt.gz"
)

MAX_PROFILES = 10


# =========================================================
# DOWNLOAD ARGO GLOBAL PROFILE INDEX
# =========================================================

def download_argo_index():

    print("======================================")
    print("DOWNLOADING ARGO PROFILE INDEX")
    print("======================================")

    response = requests.get(
        ARGO_PROFILE_INDEX_URL,
        timeout=180,
        headers={
            "User-Agent": "Ocean-Nexus-AI/1.0"
        }
    )

    response.raise_for_status()

    print("ARGO response status:", response.status_code)
    print("ARGO content type:", response.headers.get("content-type"))
    print("ARGO compressed size:", len(response.content))

    data = gzip.decompress(response.content)

    print("ARGO decompressed size:", len(data))

    text = data.decode(
        "utf-8",
        errors="replace"
    )

    return text


# =========================================================
# FIND PROFILE FILES
# =========================================================

def find_argo_profile_files():

    text = download_argo_index()

    lines = text.splitlines()

    print("ARGO index lines:", len(lines))

    header_index = None

    for i, line in enumerate(lines):

        cleaned = line.strip()

        if cleaned.startswith(
            "file,date,latitude,longitude"
        ):

            header_index = i

            print(
                "ARGO CSV header found at line:",
                i
            )

            print(
                "HEADER:",
                cleaned
            )

            break

    if header_index is None:

        raise Exception(
            "ARGO profile index CSV header not found"
        )

    headers = [
        h.strip()
        for h in lines[header_index].split(",")
    ]

    print("ARGO headers:", headers)

    file_index = headers.index("file")
    date_index = headers.index("date")

    records = []

    for line in lines[header_index + 1:]:

        if not line.strip():
            continue

        try:

            values = next(
                csv.reader([line])
            )

            if len(values) <= max(
                file_index,
                date_index
            ):
                continue

            file_path = values[file_index].strip()
            date_value = values[date_index].strip()

            if not file_path.endswith(".nc"):
                continue

            # Correct ARGO profile filename extraction
            match = re.search(
                r"([RD])(\d{7})_(\d+)\.nc$",
                file_path
            )

            if not match:
                continue

            float_id = match.group(2)

            records.append(
                {
                    "file": file_path,
                    "date": date_value,
                    "float_id": float_id
                }
            )

        except Exception:
            continue

    if not records:

        raise Exception(
            "No ARGO profile records found"
        )

    print(
        "Total ARGO profile records:",
        len(records)
    )

    # Latest record
    latest_record = records[-1]

    float_id = latest_record["float_id"]

    print(
        "Latest float ID:",
        float_id
    )

    # Keep profiles from same float
    same_float = [
        record
        for record in records
        if record["float_id"] == float_id
    ]

    print(
        "Profiles found for float",
        float_id,
        ":",
        len(same_float)
    )

    same_float.sort(
        key=lambda x: x["date"]
    )

    selected = same_float[-MAX_PROFILES:]

    print("Selected profiles:")

    for record in selected:

        print(
            record["date"],
            record["file"]
        )

    return selected


# =========================================================
# SAFE FLOAT
# =========================================================

def safe_float(value):

    try:

        value = float(value)

        if not np.isfinite(value):
            return None

        return value

    except Exception:

        return None


# =========================================================
# BUILD ARGO FILE URL
# =========================================================

def build_argo_file_url(file_path):

    file_path = file_path.strip()

    if file_path.startswith("http"):
        return file_path

    if file_path.startswith("dac/"):
        return ARGO_BASE_URL + file_path

    return ARGO_BASE_URL + "dac/" + file_path


# =========================================================
# JULD → ISO TIME
# =========================================================

def convert_juld_to_time(juld_value):

    try:

        value = float(juld_value)

        if not np.isfinite(value):
            return None

        base_date = datetime(
            1950,
            1,
            1
        )

        result = (
            base_date
            + timedelta(days=value)
        )

        return result.isoformat()

    except Exception:

        return None


# =========================================================
# ARGO NETCDF READER
# =========================================================

def read_argo_netcdf(file_url):

    print(
        "Downloading ARGO profile:"
    )

    print(file_url)

    response = requests.get(
        file_url,
        timeout=120,
        headers={
            "User-Agent": "Ocean-Nexus-AI/1.0"
        }
    )

    response.raise_for_status()

    dataset = xr.open_dataset(
        io.BytesIO(response.content),
        engine="netcdf4"
    )

    try:

        required_variables = [
            "LATITUDE",
            "LONGITUDE",
            "PRES",
            "TEMP"
        ]

        for variable in required_variables:

            if variable not in dataset:

                raise Exception(
                    f"{variable} variable missing"
                )

        # -------------------------------------------------
        # LOCATION
        # -------------------------------------------------

        latitude = np.asarray(
            dataset["LATITUDE"].values
        ).flatten()

        longitude = np.asarray(
            dataset["LONGITUDE"].values
        ).flatten()

        profile_latitude = safe_float(
            latitude[0]
        )

        profile_longitude = safe_float(
            longitude[0]
        )

        # -------------------------------------------------
        # FLOAT ID
        # -------------------------------------------------

        float_id = "Unknown"

        if "PLATFORM_NUMBER" in dataset:

            platform = np.asarray(
                dataset[
                    "PLATFORM_NUMBER"
                ].values
            ).flatten()

            if len(platform) > 0:

                try:

                    float_id = str(
                        platform[0]
                    ).strip()

                    float_id = (
                        float_id
                        .replace("b'", "")
                        .replace("'", "")
                    )

                except Exception:

                    float_id = "Unknown"

        # -------------------------------------------------
        # PRESSURE
        # -------------------------------------------------

        pressure = np.asarray(
            dataset["PRES"].values
        )

        # -------------------------------------------------
        # TEMPERATURE
        # -------------------------------------------------

        temperature = np.asarray(
            dataset["TEMP"].values
        )

        # -------------------------------------------------
        # SALINITY
        # -------------------------------------------------

        if "PSAL" in dataset:

            salinity = np.asarray(
                dataset["PSAL"].values
            )

        else:

            salinity = None

        # -------------------------------------------------
        # ADJUSTED VARIABLES
        # -------------------------------------------------

        adjusted_pressure = None
        adjusted_temperature = None
        adjusted_salinity = None

        if "PRES_ADJUSTED" in dataset:
            adjusted_pressure = np.asarray(
                dataset["PRES_ADJUSTED"].values
            )

        if "TEMP_ADJUSTED" in dataset:
            adjusted_temperature = np.asarray(
                dataset["TEMP_ADJUSTED"].values
            )

        if "PSAL_ADJUSTED" in dataset:
            adjusted_salinity = np.asarray(
                dataset["PSAL_ADJUSTED"].values
            )

        # -------------------------------------------------
        # QC VARIABLES
        # -------------------------------------------------

        pressure_qc = None
        temperature_qc = None
        salinity_qc = None

        if "PRES_ADJUSTED_QC" in dataset:
            pressure_qc = np.asarray(
                dataset[
                    "PRES_ADJUSTED_QC"
                ].values
            )

        if "TEMP_ADJUSTED_QC" in dataset:
            temperature_qc = np.asarray(
                dataset[
                    "TEMP_ADJUSTED_QC"
                ].values
            )

        if "PSAL_ADJUSTED_QC" in dataset:
            salinity_qc = np.asarray(
                dataset[
                    "PSAL_ADJUSTED_QC"
                ].values
            )

        # -------------------------------------------------
        # PRESSURE ERROR
        # -------------------------------------------------

        pressure_error = None

        if "PRES_ADJUSTED_ERROR" in dataset:

            pressure_error = np.asarray(
                dataset[
                    "PRES_ADJUSTED_ERROR"
                ].values
            )

        # -------------------------------------------------
        # DATA MODE
        # -------------------------------------------------

        data_mode = None

        if "DATA_MODE" in dataset:

            data_mode = np.asarray(
                dataset["DATA_MODE"].values
            ).flatten()

        # -------------------------------------------------
        # TIME
        # -------------------------------------------------

        profile_times = []

        if "JULD" in dataset:

            juld_values = np.asarray(
                dataset["JULD"].values
            ).flatten()

            for value in juld_values:

                profile_times.append(
                    convert_juld_to_time(value)
                )

        # -------------------------------------------------
        # PROFILE DIMENSIONS
        # -------------------------------------------------

        if pressure.ndim == 1:

            pressure_profiles = [
                pressure
            ]

        else:

            pressure_profiles = [
                pressure[i]
                for i in range(
                    pressure.shape[0]
                )
            ]

        if temperature.ndim == 1:

            temperature_profiles = [
                temperature
            ]

        else:

            temperature_profiles = [
                temperature[i]
                for i in range(
                    temperature.shape[0]
                )
            ]

        if salinity is None:

            salinity_profiles = [
                None
            ] * len(
                pressure_profiles
            )

        elif salinity.ndim == 1:

            salinity_profiles = [
                salinity
            ]

        else:

            salinity_profiles = [
                salinity[i]
                for i in range(
                    salinity.shape[0]
                )
            ]

        # -------------------------------------------------
        # BUILD TRAJECTORY
        # -------------------------------------------------

        trajectory = []

        number_of_profiles = min(
            len(pressure_profiles),
            len(temperature_profiles)
        )

        for profile_index in range(
            number_of_profiles
        ):

            profile_pressure = np.asarray(
                pressure_profiles[
                    profile_index
                ]
            ).flatten()

            profile_temperature = np.asarray(
                temperature_profiles[
                    profile_index
                ]
            ).flatten()

            profile_salinity = (
                salinity_profiles[
                    profile_index
                ]
                if profile_index
                < len(salinity_profiles)
                else None
            )

            if profile_salinity is not None:

                profile_salinity = np.asarray(
                    profile_salinity
                ).flatten()

            # Profile time

            if (
                profile_index
                < len(profile_times)
                and profile_times[
                    profile_index
                ] is not None
            ):

                profile_time = profile_times[
                    profile_index
                ]

            else:

                profile_time = None

            # -------------------------------------------------
            # DEPTH LEVELS
            # -------------------------------------------------

            for level_index in range(
                len(profile_pressure)
            ):

                raw_depth = safe_float(
                    profile_pressure[
                        level_index
                    ]
                )

                if raw_depth is None:
                    continue

                # ---------------------------------------------
                # Prefer adjusted values when available
                # ---------------------------------------------

                depth = raw_depth

                if (
                    adjusted_pressure is not None
                    and adjusted_pressure.ndim >= 1
                ):

                    try:

                        if adjusted_pressure.ndim == 1:

                            adjusted_depth = safe_float(
                                adjusted_pressure[
                                    level_index
                                ]
                            )

                        else:

                            adjusted_depth = safe_float(
                                adjusted_pressure[
                                    profile_index,
                                    level_index
                                ]
                            )

                        if adjusted_depth is not None:

                            depth = adjusted_depth

                    except Exception:
                        pass

                # ---------------------------------------------
                # Temperature
                # ---------------------------------------------

                temp = None

                if (
                    level_index
                    < len(profile_temperature)
                ):

                    temp = safe_float(
                        profile_temperature[
                            level_index
                        ]
                    )

                # Prefer adjusted temperature

                if adjusted_temperature is not None:

                    try:

                        if adjusted_temperature.ndim == 1:

                            adjusted_temp = safe_float(
                                adjusted_temperature[
                                    level_index
                                ]
                            )

                        else:

                            adjusted_temp = safe_float(
                                adjusted_temperature[
                                    profile_index,
                                    level_index
                                ]
                            )

                        if adjusted_temp is not None:
                            temp = adjusted_temp

                    except Exception:
                        pass

                # ---------------------------------------------
                # Salinity
                # ---------------------------------------------

                salt = None

                if (
                    profile_salinity is not None
                    and level_index
                    < len(profile_salinity)
                ):

                    salt = safe_float(
                        profile_salinity[
                            level_index
                        ]
                    )

                # Prefer adjusted salinity

                if adjusted_salinity is not None:

                    try:

                        if adjusted_salinity.ndim == 1:

                            adjusted_salt = safe_float(
                                adjusted_salinity[
                                    level_index
                                ]
                            )

                        else:

                            adjusted_salt = safe_float(
                                adjusted_salinity[
                                    profile_index,
                                    level_index
                                ]
                            )

                        if adjusted_salt is not None:
                            salt = adjusted_salt

                    except Exception:
                        pass

                # ---------------------------------------------
                # QC
                # ---------------------------------------------

                qc_values = []

                for qc_array in [
                    pressure_qc,
                    temperature_qc,
                    salinity_qc
                ]:

                    if qc_array is None:
                        continue

                    try:

                        if qc_array.ndim == 1:

                            qc_value = qc_array[
                                level_index
                            ]

                        else:

                            qc_value = qc_array[
                                profile_index,
                                level_index
                            ]

                        qc_values.append(
                            str(qc_value)
                        )

                    except Exception:
                        pass

                # ---------------------------------------------
                # Pressure error
                # ---------------------------------------------

                pressure_error_value = None

                if pressure_error is not None:

                    try:

                        if pressure_error.ndim == 1:

                            pressure_error_value = safe_float(
                                pressure_error[
                                    level_index
                                ]
                            )

                        else:

                            pressure_error_value = safe_float(
                                pressure_error[
                                    profile_index,
                                    level_index
                                ]
                            )

                    except Exception:
                        pass

                # ---------------------------------------------
                # QC eligibility
                # ---------------------------------------------

                qc_pass = True

                if qc_values:

                    qc_pass = all(
                        q == "1"
                        for q in qc_values
                        if q not in [
                            "nan",
                            "None",
                            ""
                        ]
                    )

                if (
                    pressure_error_value is not None
                    and pressure_error_value >= 20
                ):

                    qc_pass = False

                trajectory.append(
                    {
                        "time": profile_time,
                        "lat": profile_latitude,
                        "lng": profile_longitude,
                        "depth": depth,
                        "temp": temp,
                        "salinity": salt,
                        "qc_pass": qc_pass,
                        "pressure_error": pressure_error_value
                    }
                )

        return {
            "float_id": float_id,
            "latitude": profile_latitude,
            "longitude": profile_longitude,
            "trajectory": trajectory,
            "source_file": file_url
        }

    finally:

        dataset.close()


# =========================================================
# FETCH REAL ARGO DATA
# =========================================================

def fetch_real_argo_data(
    float_id=None,
    start_date=None,
    end_date=None
):

    print("======================================")
    print("FETCHING REAL ARGO DATA")
    print("======================================")

    return fetch_argo_from_postgres(
        float_id=float_id,
        start_date=start_date,
        end_date=end_date,
        max_points=500
    )
    all_trajectory = []

    float_id = "Unknown"

    latest_latitude = None
    latest_longitude = None

    source_file = None

    # -----------------------------------------------------
    # READ PROFILES
    # -----------------------------------------------------

    for record in selected_profiles:

        try:

            file_path = record["file"]

            file_url = build_argo_file_url(
                file_path
            )

            profile_data = read_argo_netcdf(
                file_url
            )

            float_id = profile_data[
                "float_id"
            ]

            latest_latitude = profile_data[
                "latitude"
            ]

            latest_longitude = profile_data[
                "longitude"
            ]

            source_file = profile_data[
                "source_file"
            ]

            all_trajectory.extend(
                profile_data[
                    "trajectory"
                ]
            )

        except Exception as error:

            print(
                "FAILED PROFILE:",
                record["file"]
            )

            print(
                "ERROR:",
                error
            )

            continue

    if not all_trajectory:

        raise Exception(
            "Could not read any ARGO profile data"
        )

    # -----------------------------------------------------
    # SORT
    # -----------------------------------------------------

    all_trajectory.sort(
        key=lambda point:
        point.get("time") or ""
    )

    # -----------------------------------------------------
    # QC SUMMARY
    # -----------------------------------------------------

    total_points = len(
        all_trajectory
    )

    valid_points = sum(
        1
        for point in all_trajectory
        if point.get("qc_pass", True)
    )

    rejected_points = (
        total_points
        - valid_points
    )

    print("======================================")
    print("ARGO DATA SUCCESS")
    print("======================================")

    print(
        "Float ID:",
        float_id
    )

    print(
        "Latitude:",
        latest_latitude
    )

    print(
        "Longitude:",
        latest_longitude
    )

    print(
        "Total points:",
        total_points
    )

    print(
        "QC valid points:",
        valid_points
    )

    print(
        "QC rejected points:",
        rejected_points
    )

    print("======================================")

    return {
        "float_id": float_id,
        "latitude": latest_latitude,
        "longitude": latest_longitude,
        "trajectory": all_trajectory,
        "source_file": source_file,
        "qc_summary": {
            "total_points": total_points,
            "valid_points": valid_points,
            "rejected_points": rejected_points
        }
    }