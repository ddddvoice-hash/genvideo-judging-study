"""
1단계: VideoFeedback에서 '사람이 나오는' 영상 240개를 뽑아 세트 A/B로 나눈다.

사용법 (본인 컴퓨터에서):
    pip install datasets pandas
    python 01_sample_videos.py

결과:
    videos_A.csv, videos_B.csv  (각 120개, 화질 점수 1~4 층마다 같은 수)
    videos_all_candidates.csv   (사람 키워드에 걸린 전체 후보, 검토용)

화질 점수(visual quality)는 판정자에게 보여주지 않는다. 분석(RQ3)에만 쓴다.
"""
import re
import sys

import pandas as pd

SEED = 2026
PER_LEVEL = 60          # 화질 점수 1~4 각 60개 → 총 240개
LEVELS = [1, 2, 3, 4]

# 프롬프트(영어)에 사람이 등장하는지 판단하는 단어. 필요하면 더하거나 빼세요.
PERSON_WORDS = [
    "person", "people", "man", "men", "woman", "women", "girl", "boy", "child",
    "children", "kid", "baby", "lady", "guy", "dancer", "player", "worker",
    "chef", "student", "teacher", "doctor", "athlete", "couple", "family",
    "hand", "hands", "face", "someone", "crowd", "singer", "actor", "runner",
]
PATTERN = re.compile(r"\b(?:" + "|".join(PERSON_WORDS) + r")\b", re.IGNORECASE)


def load_videofeedback() -> pd.DataFrame:
    from datasets import load_dataset  # 본인 컴퓨터에 설치 필요

    parts = []
    for split in ["train", "test"]:
        ds = load_dataset("TIGER-Lab/VideoFeedback", name="annotated", split=split)
        df = ds.remove_columns(["conversations"]).to_pandas()
        df["split"] = split
        parts.append(df)
    return pd.concat(parts, ignore_index=True)


def select(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    df = df.rename(columns={
        "text prompt": "prompt",
        "video link": "video_link",
        "visual quality": "visual_quality",
    })
    df = df[df["video_link"].astype(str).str.len() > 0]
    df = df[df["prompt"].astype(str).str.contains(PATTERN)]
    df = df.drop_duplicates(subset="video_link")
    candidates = df[["id", "prompt", "video_link", "visual_quality", "split"]].copy()

    picked = []
    for level in LEVELS:
        pool = candidates[candidates["visual_quality"] == level]
        n = min(PER_LEVEL, len(pool))
        if n < PER_LEVEL:
            print(f"[주의] 화질 {level}점 후보가 {len(pool)}개뿐입니다. {n}개만 뽑습니다.",
                  file=sys.stderr)
        n -= n % 2  # A/B 반씩 나누려고 짝수로
        picked.append(pool.sample(n=n, random_state=SEED + level))
    sample = pd.concat(picked, ignore_index=True)

    # 화질 층마다 반씩 A/B로 나눈다
    set_a, set_b = [], []
    for level, grp in sample.groupby("visual_quality"):
        grp = grp.sample(frac=1, random_state=SEED).reset_index(drop=True)
        half = len(grp) // 2
        set_a.append(grp.iloc[:half])
        set_b.append(grp.iloc[half:])
    a = pd.concat(set_a, ignore_index=True)
    b = pd.concat(set_b, ignore_index=True)
    a.insert(0, "video_id", [f"A{i + 1:03d}" for i in range(len(a))])
    b.insert(0, "video_id", [f"B{i + 1:03d}" for i in range(len(b))])
    return candidates, a, b


def main():
    df = load_videofeedback()
    candidates, a, b = select(df)
    candidates.to_csv("videos_all_candidates.csv", index=False, encoding="utf-8-sig")
    a.to_csv("videos_A.csv", index=False, encoding="utf-8-sig")
    b.to_csv("videos_B.csv", index=False, encoding="utf-8-sig")
    print(f"후보 {len(candidates)}개 중 세트 A {len(a)}개, 세트 B {len(b)}개를 뽑았습니다.")
    print("화질 점수별 개수 (A):", a["visual_quality"].value_counts().sort_index().to_dict())
    print("화질 점수별 개수 (B):", b["visual_quality"].value_counts().sort_index().to_dict())
    print("다음: 링크 몇 개를 직접 열어 사람이 실제로 나오는지 확인하세요.")


if __name__ == "__main__":
    main()
