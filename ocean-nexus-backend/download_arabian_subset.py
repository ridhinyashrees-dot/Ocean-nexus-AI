import os
import time
import requests
import pandas as pd

BASE_URL = "https://osmc.noaa.gov/erddap/tabledap/ArgoFloats.csv"

OUTPUT_DIR = "data/arabian_sea"
OUTPUT_FILE = os.path.join(
    OUTPUT_DIR,
    "arabian_sea_argo_subset.csv"
)

# Arabian Sea
MIN_LAT = 8
MAX_LAT = 25
MIN_LON = 60
MAX_LON = 77

# Real multi-year window
START_DATE = "2015-01-01T00:00:00Z"
END_DATE = "2025-12-31T23:59:59Z"

TARGET_PROFILES = 80


def get_profile_list():

    variables = ",".join([
        "platform_number",
        "cycle_number",
        "time",
        "latitude",
        "longitude",
        "data_mode",
        "profile_temp_qc",
        "profile_psal_qc",
        "profile_pres_qc"
    ])

    query = (
        f"{variables}"
        f"&latitude>={MIN_LAT}"
        f"&latitude<={MAX_LAT}"
        f"&longitude>={MIN_LON}"
        f"&longitude<={MAX_LON}"
        f"&time>={START_DATE}"
        f"&time<={END_DATE}"
        '&data_mode="D"'
        '&orderByLimit("platform_number,cycle_number,1")'
    )

    url = BASE_URL + "?" + query

    print("Fetching Arabian Sea delayed-mode profiles...")
    print(url)

    response = requests.get(
        url,
        timeout=300,
        headers={
            "User-Agent": "Ocean-Nexus-AI-Hackathon/1.0"
        }
    )

    response.raise_for_status()

    df = pd.read_csv(
        pd.io.common.BytesIO(
            response.content
        )
    )

    return df


def get_profile_measurements(
    platform_number,
    cycle_number
):

    variables = ",".join([
        "platform_number",
        "cycle_number",
        "time",
        "latitude",
        "longitude",
        "data_mode",
        "pres_adjusted",
        "pres_adjusted_qc",
        "pres_adjusted_error",
        "temp_adjusted",
        "temp_adjusted_qc",
        "psal_adjusted",
        "psal_adjusted_qc"
    ])

    query = (
        f"{variables}"
        f'&platform_number="{platform_number}"'
        f"&cycle_number={int(cycle_number)}"
    )

    url = BASE_URL + "?" + query

    response = requests.get(
        url,
        timeout=120,
        headers={
            "User-Agent": "Ocean-Nexus-AI-Hackathon/1.0"
        }
    )

    response.raise_for_status()

    return pd.read_csv(
        pd.io.common.BytesIO(
            response.content
        )
    )


def main():

    os.makedirs(
        OUTPUT_DIR,
        exist_ok=True
    )

    profiles = get_profile_list()

    print(
        "Profiles found:",
        len(profiles)
    )

    if profiles.empty:

        raise RuntimeError(
            "No delayed-mode Arabian Sea profiles found."
        )




    profiles["platform_number"] = (
    profiles["platform_number"]
    .astype(str)
    .str.replace(r"\.0$", "", regex=True)
    .str.strip()
    )

    # Sort chronologically
    profiles["time"] = pd.to_datetime(
        profiles["time"],
        errors="coerce"
    )

    profiles = profiles.sort_values(
        "time"
    )

    # Evenly sample profiles across the period
    if len(profiles) > TARGET_PROFILES:

        indices = (
            pd.Series(
                range(len(profiles))
            )
            .sample(
                n=TARGET_PROFILES,
                random_state=42
            )
            .sort_values()
        )

        profiles = profiles.iloc[
            indices
        ]

    print(
        "Profiles selected:",
        len(profiles)
    )

    all_data = []

    for index, row in profiles.iterrows():

        platform = row[
            "platform_number"
        ]

        cycle = row[
            "cycle_number"
        ]

        try:

            print(
                f"[{index}] "
                f"Float={platform}, "
                f"Cycle={cycle}"
            )

            measurements = (
                get_profile_measurements(
                    platform,
                    cycle
                )
            )

            if not measurements.empty:

                all_data.append(
                    measurements
                )

            time.sleep(0.15)

        except Exception as error:

            print(
                "FAILED:",
                platform,
                cycle,
                error
            )

    if not all_data:

        raise RuntimeError(
            "No measurement data downloaded."
        )

    final_df = pd.concat(
        all_data,
        ignore_index=True
    )


     # Convert geographic columns to numeric
    final_df["latitude"] = pd.to_numeric(
    final_df["latitude"],
    errors="coerce"
)

    final_df["longitude"] = pd.to_numeric(
    final_df["longitude"],
    errors="coerce"
)

# Remove invalid coordinates
    final_df = final_df.dropna(
    subset=["latitude", "longitude"]
)

    # Keep only valid geographic area
    final_df = final_df[
        (final_df["latitude"] >= MIN_LAT)
        &
        (final_df["latitude"] <= MAX_LAT)
        &
        (final_df["longitude"] >= MIN_LON)
        &
        (final_df["longitude"] <= MAX_LON)
    ]

    # Remove rows without adjusted pressure
    final_df = final_df.dropna(
        subset=["pres_adjusted"]
    )

    final_df.to_csv(
        OUTPUT_FILE,
        index=False
    )

    print("\n====================================")
    print("ARABIAN SEA ARGO SUBSET READY")
    print("====================================")
    print(
        "Profiles:",
        final_df[
            ["platform_number", "cycle_number"]
        ].drop_duplicates().shape[0]
    )

    print(
        "Measurements:",
        len(final_df)
    )

    print(
        "Output:",
        os.path.abspath(OUTPUT_FILE)
    )

    print(
        "Time:",
        final_df["time"].min(),
        "→",
        final_df["time"].max()
    )


if __name__ == "__main__":
    main()