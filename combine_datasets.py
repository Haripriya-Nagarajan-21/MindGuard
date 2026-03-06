import pandas as pd

print("🔹 Combining Kaggle datasets for MindGuard")

# ---------------- DATASET 1 ----------------
df1 = pd.read_csv("data/stress_detection_data.csv")
df1 = df1.rename(columns={
    "Sleep_Duration": "sleep_hours",
    "Work_Hours": "work_study_hours",
    "Screen_Time": "screen_time",
    "Physical_Activity": "physical_activity",
    "Stress_Detection": "stress_level"
})
df1 = df1[[
    "sleep_hours",
    "work_study_hours",
    "screen_time",
    "physical_activity",
    "stress_level"
]]

# ---------------- DATASET 2 ----------------
df2 = pd.read_csv("data/student_academic_stress.csv")
df2 = df2.rename(columns={
    "Rate your academic stress index ": "stress_level"
})
df2 = df2[["stress_level"]]

# ---------------- DATASET 3 ----------------
df3 = pd.read_csv("data/mental_health_social_media.csv")
df3 = df3.rename(columns={
    "Daily_Screen_Time(hrs)": "screen_time",
    "Sleep_Quality(1-10)": "sleep_hours",
    "Stress_Level(1-10)": "stress_level",
    "Happiness_Index(1-10)": "mood",
    "Exercise_Frequency(week)": "physical_activity"
})
df3 = df3[[
    "sleep_hours",
    "screen_time",
    "physical_activity",
    "mood",
    "stress_level"
]]

# ---------------- DATASET 4 ----------------
df4 = pd.read_csv("data/student_lifestyle_dataset.csv")
df4 = df4.rename(columns={
    "Sleep_Hours_Per_Day": "sleep_hours",
    "Study_Hours_Per_Day": "work_study_hours",
    "Physical_Activity_Hours_Per_Day": "physical_activity",
    "Stress_Level": "stress_level"
})
df4 = df4[[
    "sleep_hours",
    "work_study_hours",
    "physical_activity",
    "stress_level"
]]

# ---------------- COMBINE ----------------
final_df = pd.concat([df1, df2, df3, df4], ignore_index=True)

# ---------------- HANDLE MISSING VALUES ----------------
final_df = final_df.fillna(final_df.mean(numeric_only=True))

# ---------------- CONVERT STRESS TEXT → NUMBER ----------------
def stress_to_number(value):
    value = str(value).lower()

    if value in ["yes", "high", "high stress"]:
        return 8
    elif value in ["medium", "moderate"]:
        return 5
    elif value in ["no", "low", "low stress"]:
        return 2
    else:
        try:
            return float(value)
        except:
            return 5   # default medium

final_df["stress_level"] = final_df["stress_level"].apply(stress_to_number)

# ---------------- NORMALIZE STRESS LEVEL ----------------
def convert_stress(value):
    if value <= 3:
        return 0   # Low
    elif value <= 6:
        return 1   # Medium
    else:
        return 2   # High

final_df["stress_level"] = final_df["stress_level"].apply(convert_stress)

# ---------------- SAVE ----------------
final_df.to_csv("data/final_stress_dataset.csv", index=False)

print("✅ Final dataset created:", final_df.shape)