"""
3단계: 판정자 간 일치도(Fleiss 카파)를 계산하고, 갈린 영상을 뽑는다.

사용법:
    pip install pandas numpy openpyxl scipy
    python 03_agreement.py A v1               # 세트 A, v1 결과만 분석
    python 03_agreement.py A v1 B v2          # 두 조건 비교 (RQ2)
    python 03_agreement.py A v1 A v2          # 같은 영상 재판정 비교

입력: sheet_<세트>_<가이드>_R1.xlsx ~ R4.xlsx (판정자가 채운 파일)
      videos_<세트>.csv (화질 점수, RQ3용)
출력: report_<...>.md            일치도 표와 해석
      disagreements_<세트>_<가이드>.csv   갈린 영상 + 판정자 메모 (가이드 v2 재료)
"""
import glob
import sys

import numpy as np
import pandas as pd

N_BOOT = 2000
SEED = 2026
TYPES = ["신체 형태", "신체 움직임", "사물·배경", "화질"]


# ---------- 읽기 ----------

def load_condition(set_name: str, guide: str) -> pd.DataFrame:
    """판정자 파일을 읽어 (video_id, rater) 한 줄씩인 긴 표로 만든다."""
    files = sorted(glob.glob(f"sheet_{set_name}_{guide}_R*.xlsx"))
    if len(files) < 2:
        raise SystemExit(f"sheet_{set_name}_{guide}_R*.xlsx 파일이 2개 이상 필요합니다.")
    rows = []
    for f in files:
        rater = f.rsplit("_", 1)[1].replace(".xlsx", "")
        df = pd.read_excel(f, sheet_name="판정", dtype=str).fillna("")
        df["rater"] = rater
        rows.append(df)
    long = pd.concat(rows, ignore_index=True)
    long["왜곡 유무"] = long["왜곡 유무"].str.strip()
    long["심각도"] = long["심각도"].str.strip()
    for t in TYPES:
        long[t] = long[t].str.strip().str.upper().eq("O").astype(int)
    # '없음'인데 유형·심각도가 적혀 있으면 지운다 (입력 실수 정리)
    none = long["왜곡 유무"].eq("없음")
    long.loc[none, TYPES] = 0
    long.loc[none, "심각도"] = ""
    return long


def label_tables(long: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """분석 항목별로 영상 × 판정자 표를 만든다. 빈칸·판단 불가가 있는 영상은 뺀다."""
    valid = long[long["왜곡 유무"].isin(["없음", "있음"])].copy()
    sev = np.where(valid["왜곡 유무"].eq("없음"), "없음", valid["심각도"])
    valid["심각도3"] = sev
    tables = {
        "왜곡 유무": valid.pivot(index="video_id", columns="rater", values="왜곡 유무"),
        "심각도 (없음·경미·심각)": valid.pivot(index="video_id", columns="rater", values="심각도3"),
    }
    for t in TYPES:
        tables[f"유형: {t}"] = valid.pivot(index="video_id", columns="rater", values=t)
    out = {}
    for name, tab in tables.items():
        tab = tab.replace("", np.nan).dropna()  # 모든 판정자가 답한 영상만
        out[name] = tab
    return out


# ---------- 계산 ----------

def fleiss_kappa(table: pd.DataFrame) -> float:
    """table: 영상 × 판정자, 값은 범주. 판정자 수가 모두 같아야 한다."""
    if len(table) == 0:
        return float("nan")
    cats = sorted(pd.unique(table.values.ravel()), key=str)
    counts = np.stack([(table.values == c).sum(axis=1) for c in cats], axis=1).astype(float)
    n = counts.sum(axis=1)[0]
    if n < 2:
        return float("nan")
    p_j = counts.sum(axis=0) / counts.sum()
    p_i = ((counts ** 2).sum(axis=1) - n) / (n * (n - 1))
    p_bar = p_i.mean()
    p_e = (p_j ** 2).sum()
    if np.isclose(p_e, 1.0):
        return float("nan")  # 모두 한 범주만 고른 경우
    return float((p_bar - p_e) / (1 - p_e))


def boot_ci(table: pd.DataFrame, rng: np.random.Generator) -> tuple[float, float]:
    vals = []
    idx = np.arange(len(table))
    for _ in range(N_BOOT):
        k = fleiss_kappa(table.iloc[rng.choice(idx, size=len(idx), replace=True)])
        if not np.isnan(k):
            vals.append(k)
    if not vals:
        return float("nan"), float("nan")
    return float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5))


def boot_diff(t1: pd.DataFrame, t2: pd.DataFrame, rng, paired: bool):
    """조건2 - 조건1 카파 차이의 95% 신뢰구간. 같은 영상이면 paired=True."""
    diffs = []
    if paired:
        common = t1.index.intersection(t2.index)
        t1, t2 = t1.loc[common], t2.loc[common]
        idx = np.arange(len(common))
        for _ in range(N_BOOT):
            s = rng.choice(idx, size=len(idx), replace=True)
            d = fleiss_kappa(t2.iloc[s]) - fleiss_kappa(t1.iloc[s])
            if not np.isnan(d):
                diffs.append(d)
    else:
        i1, i2 = np.arange(len(t1)), np.arange(len(t2))
        for _ in range(N_BOOT):
            d = (fleiss_kappa(t2.iloc[rng.choice(i2, size=len(i2), replace=True)])
                 - fleiss_kappa(t1.iloc[rng.choice(i1, size=len(i1), replace=True)]))
            if not np.isnan(d):
                diffs.append(d)
    if not diffs:
        return float("nan"), float("nan")
    return float(np.percentile(diffs, 2.5)), float(np.percentile(diffs, 97.5))


def interpret(k: float) -> str:
    if np.isnan(k):
        return "계산 불가"
    for limit, word in [(0, "일치 안 됨"), (0.20, "약간"), (0.40, "어느 정도"),
                        (0.60, "보통"), (0.80, "상당히"), (1.01, "거의 완전")]:
        if k <= limit:
            return word
    return "거의 완전"


def disagreements(long: pd.DataFrame, tables) -> pd.DataFrame:
    pres = tables["왜곡 유무"]
    sev = tables["심각도 (없음·경미·심각)"]
    rows = []
    for vid in sorted(set(pres.index) | set(sev.index)):
        reasons = []
        if vid in pres.index and pres.loc[vid].nunique() > 1:
            counts = pres.loc[vid].value_counts().to_dict()
            reasons.append("유무 갈림 " + str(counts))
        elif vid in sev.index and sev.loc[vid].nunique() > 1:
            reasons.append("심각도 갈림 " + str(sev.loc[vid].value_counts().to_dict()))
        if not reasons:
            continue
        sub = long[long["video_id"] == vid].sort_values("rater")
        memos = " | ".join(f"{r.rater}: {r['메모']}" for _, r in sub.iterrows() if r["메모"])
        link = sub["영상 링크"].iloc[0] if "영상 링크" in sub else ""
        rows.append({"video_id": vid, "갈린 내용": "; ".join(reasons),
                     "판정자 메모": memos, "영상 링크": link, "유형(A~): 직접 적기": ""})
    return pd.DataFrame(rows)


def rq3(long: pd.DataFrame, set_name: str) -> str:
    try:
        from scipy.stats import spearmanr
        vq = pd.read_csv(f"videos_{set_name}.csv")[["video_id", "visual_quality"]]
    except Exception as e:  # 파일이 없으면 건너뛴다
        return f"(RQ3 건너뜀: {e})"
    valid = long[long["왜곡 유무"].isin(["없음", "있음"])]
    share = valid.groupby("video_id")["왜곡 유무"].apply(lambda s: (s == "있음").mean())
    m = vq.merge(share.rename("p_distort"), left_on="video_id", right_index=True)
    if len(m) < 5:
        return "(RQ3: 영상이 너무 적음)"
    rho, p = spearmanr(m["visual_quality"], m["p_distort"])
    return (f"화질 점수와 '왜곡 있음' 비율의 스피어만 상관: rho = {rho:.3f} "
            f"(p = {p:.4f}, 영상 {len(m)}개). 음수면 화질이 낮을수록 왜곡 판정이 많다는 뜻.")


# ---------- 보고서 ----------

def summarize(tag: str, tables, rng) -> pd.DataFrame:
    out = []
    for name, tab in tables.items():
        k = fleiss_kappa(tab)
        lo, hi = boot_ci(tab, rng)
        out.append({"항목": name, "영상 수": len(tab), "판정자 수": tab.shape[1],
                    f"카파 ({tag})": round(k, 3), "95% 구간": f"{lo:.3f} ~ {hi:.3f}",
                    "해석": interpret(k)})
    return pd.DataFrame(out)


def to_md(df: pd.DataFrame) -> str:
    cols = list(df.columns)
    lines = ["| " + " | ".join(cols) + " |", "| " + " | ".join("---" for _ in cols) + " |"]
    for _, r in df.iterrows():
        lines.append("| " + " | ".join(str(r[c]) for c in cols) + " |")
    return "\n".join(lines)


def main():
    args = sys.argv[1:]
    if len(args) not in (2, 4):
        print(__doc__)
        sys.exit(1)
    rng = np.random.default_rng(SEED)
    conds = [(args[i].upper(), args[i + 1].lower()) for i in range(0, len(args), 2)]
    parts, all_tables = [], []
    for set_name, guide in conds:
        tag = f"{set_name}·{guide}"
        long = load_condition(set_name, guide)
        tables = label_tables(long)
        all_tables.append(tables)
        summary = summarize(tag, tables, rng)
        dis = disagreements(long, tables)
        dis_file = f"disagreements_{set_name}_{guide}.csv"
        dis.to_csv(dis_file, index=False, encoding="utf-8-sig")
        parts.append(f"## 세트 {set_name} · 가이드 {guide}\n\n{to_md(summary)}\n\n"
                     f"갈린 영상 {len(dis)}개 → `{dis_file}`\n\n{rq3(long, set_name)}\n")

    if len(conds) == 2:
        (s1, g1), (s2, g2) = conds
        paired = s1 == s2
        rows = []
        for name in all_tables[0]:
            t1, t2 = all_tables[0][name], all_tables[1][name]
            k1, k2 = fleiss_kappa(t1), fleiss_kappa(t2)
            lo, hi = boot_diff(t1, t2, rng, paired)
            verdict = "차이 있음 (구간이 0을 포함하지 않음)" if lo > 0 or hi < 0 else "차이 불확실"
            rows.append({"항목": name, f"{s1}·{g1}": round(k1, 3), f"{s2}·{g2}": round(k2, 3),
                         "차이": round(k2 - k1, 3), "차이 95% 구간": f"{lo:.3f} ~ {hi:.3f}",
                         "판단": verdict})
        how = "같은 영상 짝지어 비교" if paired else "서로 다른 영상 세트 비교"
        parts.append(f"## 비교: {s1}·{g1} → {s2}·{g2} ({how})\n\n{to_md(pd.DataFrame(rows))}\n")

    name = "report_" + "_".join(f"{s}{g}" for s, g in conds) + ".md"
    header = (f"# 판정자 간 일치도 보고서\n\nFleiss 카파, 부트스트랩 {N_BOOT}회. "
              "해석 구간은 Landis·Koch(1977).\n\n")
    with open(name, "w", encoding="utf-8") as f:
        f.write(header + "\n".join(parts))
    print(header + "\n".join(parts))
    print(f"저장: {name}")


if __name__ == "__main__":
    main()
