import streamlit as st
from datetime import datetime
from zoneinfo import ZoneInfo

st.set_page_config(
    page_title="Streamlit Test",
    page_icon="✅"
)

st.title("✅ Streamlit 연결 테스트")

st.write("이 화면이 보이면 GitHub와 Streamlit이 정상적으로 연결되었습니다.")

st.divider()

st.write("⏰ 현재 시간 (한국 시간):")
st.write(datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d %H:%M:%S"))

st.caption("페이지를 새로고침했을 때 시간이 바뀌면 정상입니다.")

st.success("연결 성공!")
import io
import os
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import streamlit as st

# ── 한글 폰트 (Streamlit CSS) ──────────────────────────────────────────────
st.markdown(
    """
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR&display=swap');
html, body, [class*="css"] {
   font-family: 'Noto Sans KR', 'Malgun Gothic', sans-serif;
}
</style>
""",
    unsafe_allow_html=True,
)

# ── 캐싱된 CSV 읽기 ────────────────────────────────────────────────────────
@st.cache_data
def read_csv(file):
    """utf-8-sig → cp949 순서로 시도, 실패 시 빈 DataFrame 반환."""
    data = file.getvalue()
    for enc in ("utf-8-sig", "cp949"):
        try:
            return pd.read_csv(io.BytesIO(data), encoding=enc)
        except Exception:
            pass
    return pd.DataFrame()


def std_cols(df):
    """열 이름을 표준 이름으로 통일하고 숫자형으로 정리."""
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]

    rename = {}
    for c in df.columns:
        k = c.lower().replace(" ", "")
        if k in ("time", "categories", "시간", "날짜", "datetime", "date"):
            rename[c] = "time"
        elif k in ("temperature", "온도"):
            rename[c] = "temperature"
        elif k in ("humidity", "습도"):
            rename[c] = "humidity"
        elif k == "ph":
            rename[c] = "ph"
        elif k == "ec":
            rename[c] = "ec"
        elif "생중량" in k:
            rename[c] = "생중량"
        elif "잎" in k:
            rename[c] = "잎 수"
        elif "지상부" in k and "길이" in k:
            rename[c] = "지상부 길이"
        elif "지하부" in k and "길이" in k:
            rename[c] = "지하부 길이"
        elif "지상부" in k and ("질량" in k or "무게" in k):
            rename[c] = "지상부 질량"
        elif "지하부" in k and ("질량" in k or "무게" in k):
            rename[c] = "지하부 질량"
        elif "개체" in k:
            rename[c] = "개체번호"
    df = df.rename(columns=rename)

    # 숫자형으로 정리 (글자 열은 계산하지 않음)
    for c in df.columns:
        if c in ("time", "개체번호"):
            continue
        if not pd.api.types.is_numeric_dtype(df[c]):
            m = (
                df[c]
                .astype(str)
                .str.replace(",", "", regex=False)
                .str.extract(r"(-?\d+\.?\d*)", expand=False)
            )
            num = pd.to_numeric(m, errors="coerce")
            if num.notna().mean() >= 0.5:
                df[c] = num

    # 생중량 열이 없고 지상부+지하부 질량이 있으면 계산
    if "생중량" not in df.columns and {"지상부 질량", "지하부 질량"} <= set(df.columns):
        df["생중량"] = df["지상부 질량"] + df["지하부 질량"]

    # time 파싱
    if "time" in df.columns:
        t = df["time"].astype(str).str.strip()
        parsed = pd.to_datetime(t, errors="coerce", format="mixed")
        bad = parsed.isna() & t.str.match(r"^\d{8}_\d{1,2}$")
        if bad.any():
            parts = t[bad].str.split("_", expand=True)
            parsed[bad] = (
                pd.to_datetime(parts[0], format="%Y%m%d")
                + pd.to_timedelta(parts[1].astype(int), unit="h")
            )
        df["time"] = parsed

    return df


# ── Plotly 한글 폰트 헬퍼 ─────────────────────────────────────────────────
def set_kr(fig):
    fig.update_layout(font=dict(family="Malgun Gothic, Apple SD Gothic Neo, sans-serif"))


# ── 사이드바: 파일 업로드 ─────────────────────────────────────────────────
st.sidebar.title("파일 업로드")

env_file = st.sidebar.file_uploader("환경 CSV", type="csv")
growth_file = st.sidebar.file_uploader("생육 결과 CSV", type="csv")

env_df = pd.DataFrame()
growth_df = pd.DataFrame()

env_name = "아직"
growth_name = "아직"

if env_file is not None:
    env_df = read_csv(env_file)
    env_df = std_cols(env_df)
    env_name = os.path.basename(env_file.name).split("_")[0]

if growth_file is not None:
    growth_df = read_csv(growth_file)
    growth_df = std_cols(growth_df)
    growth_name = os.path.basename(growth_file.name).split("_")[0]

st.sidebar.info(
    f"학교명: {env_name} / {growth_name}\n\n"
    "CSV를 업로드하면 자동으로 분석 결과가 표시됩니다."
)

# 생육 측정 항목 선택
meas_cols = []
if growth_file is not None and not growth_df.empty:
    avail = [
        c for c in ["잎 수", "지상부 길이", "지하부 길이"]
        if c in growth_df.columns
    ]
    meas_cols = st.sidebar.multiselect(
        "생육 측정 항목 (그래프에 표시)",
        options=avail,
        default=avail,
    )

# ── wide mode ──────────────────────────────────────────────────────────────
st.set_page_config(page_title="극지식물 생육 대시보드", layout="wide")
st.title("극지식물 개체별 생육 차이 분석")


# ═══════════════════════════════════════════════════════════════════════════
#  탭 1 - 실험 개요
# ═══════════════════════════════════════════════════════════════════════════
tab1, tab2, tab3 = st.tabs(
    ["실험 개요", "환경 데이터", "생육 결과"]
)

with tab1:
    try:
        st.header("연구 배경 및 목적")
        st.markdown(
            """
- **극지식물**은 극한의 환경에서도 살아남는 강인한 식물입니다.
- 같은 조건에서 키워도 **개체마다 생장 속도·크기·잎 수가 크게 차이**날 수 있습니다.
- 이 대시보드는 **우리 학교 극지식물**의 생육 결과를 분석해
  - 평균·표준편차·변동계수(CV)
  - 잎 수·지상부 길이와 생중량의 상관관계
  - 상위 25% vs 하위 25% 개체 비교
  를 통해 개체 차이가 어떻게 나타나는지 살펴봅니다.
"""
        )

        st.header("데이터 요약")
        summary_rows = []

        if growth_file is not None and not growth_df.empty:
            n_ind = len(growth_df)
            if "time" in env_df.columns and not env_df.empty:
                tr = env_df.dropna(subset=["time"])
                if len(tr) > 0:
                    meas_period = f"{tr['time'].min().strftime('%Y-%m-%d')} ~ {tr['time'].max().strftime('%Y-%m-%d')}"
                else:
                    meas_period = "알 수 없음"
            else:
                meas_period = "알 수 없음"

            avail_meas = [m for m in meas_cols if m in growth_df.columns]
            if not avail_meas:
                avail_meas = [
                    m for m in ["잎 수", "지상부 길이", "지하부 길이"]
                    if m in growth_df.columns
                ]
            summary_rows.append({"항목": "총 개체 수", "값": f"{n_ind}개체"})
            summary_rows.append({"항목": "측정 기간 (환경 기준)", "값": meas_period})
            summary_rows.append(
                {"항목": "생육 측정 항목", "값": ", ".join(avail_meas) if avail_meas else "없음"}
            )
        if env_file is not None and not env_df.empty:
            summary_rows.append(
                {"항목": "환경 측정 빈도", "값": f"{len(env_df)}회"}
            )

        if summary_rows:
            st.dataframe(
                pd.DataFrame(summary_rows), width="stretch", hide_index=True
            )
        else:
            st.info("업로드된 데이터가 없습니다. 사이드바에서 CSV를 올려주세요.")

        st.header("주요 지표")
        cols4 = st.columns(4)

        with cols4[0]:
            if growth_file is not None and not growth_df.empty:
                st.metric("총 개체수", f"{len(growth_df)}개체")
            else:
                st.metric("총 개체수", "—")

        with cols4[1]:
            if env_file is not None and not env_df.empty and "temperature" in env_df.columns:
                t = env_df["temperature"].dropna()
                if len(t) >= 1:
                    st.metric("평균 온도", f"{t.mean():.1f} °C")
                else:
                    st.info("온도 데이터가 없습니다.")
            else:
                st.metric("평균 온도", "—")

        with cols4[2]:
            if env_file is not None and not env_df.empty and "humidity" in env_df.columns:
                h = env_df["humidity"].dropna()
                if len(h) >= 1:
                    st.metric("평균 습도", f"{h.mean():.1f} %")
                else:
                    st.info("습도 데이터가 없습니다.")
            else:
                st.metric("평균 습도", "—")

        with cols4[3]:
            if growth_file is not None and not growth_df.empty and "생중량" in growth_df.columns:
                w = growth_df["생중량"].dropna()
                if len(w) >= 1:
                    st.metric("평균 생중량", f"{w.mean():.2f} g")
                else:
                    st.info("생중량 데이터가 없습니다.")
            else:
                st.metric("평균 생중량", "—")

    except Exception as e:
        st.warning(f"⚠️ 이 부분은 데이터 형식 때문에 표시하지 못했어요: {e}")


# ═══════════════════════════════════════════════════════════════════════════
#  탭 2 - 환경 데이터
# ═══════════════════════════════════════════════════════════════════════════
with tab2:
    try:
        if env_file is None or env_df.empty:
            st.info("환경 CSV를 업로드해 주세요. 사이드바에서 파일을 선택하면 데이터가 표시됩니다.")
        else:
            st.header("환경 데이터 요약")

            env_num_cols = [
                c for c in ["temperature", "humidity", "ph", "ec", "water_temp", "co2"]
                if c in env_df.columns
            ]
            if env_num_cols:
                desc = (
                    env_df[env_num_cols]
                    .dropna()
                    .agg(["mean", "min", "max"])
                    .round(2)
                    .T
                    .rename(columns={"mean": "평균", "min": "최소", "max": "최대"})
                )
                display_name = {
                    "temperature": "온도 (°C)",
                    "humidity": "습도 (%)",
                    "ph": "pH",
                    "ec": "EC (mS/cm)",
                    "water_temp": "수온 (°C)",
                    "co2": "CO2 (ppm)",
                }
                desc.index = [display_name.get(i, i) for i in desc.index]
                st.dataframe(desc, width="stretch", hide_index=False)
            else:
                st.info("환경 데이터에 수치 열이 없습니다.")

            st.subheader("일별 환경 변화")
            tdf = env_df.dropna(subset=["time"]).copy()
            if len(tdf) > 0:
                tdf["day"] = tdf["time"].dt.date
                daily = tdf.groupby("day").agg(
                    {"temperature": "mean", "humidity": "mean"}
                ).reset_index()

                fig_temp = go.Figure()
                fig_temp.add_trace(
                    go.Scatter(
                        x=daily["day"],
                        y=daily["temperature"],
                        mode="lines",
                        name="온도",
                        line=dict(color="firebrick", width=2),
                    )
                )
                set_kr(fig_temp)
                fig_temp.update_layout(
                    title="일별 평균 온도 (°C)",
                    xaxis_title="날짜",
                    yaxis_title="온도 (°C)",
                    height=280,
                )
                st.plotly_chart(fig_temp, width="stretch")

                if "humidity" in env_df.columns:
                    daily_h = tdf.groupby("day")["humidity"].mean().reset_index()
                    fig_hum = go.Figure()
                    fig_hum.add_trace(
                        go.Scatter(
                            x=daily_h["day"],
                            y=daily_h["humidity"],
                            mode="lines",
                            name="습도",
                            line=dict(color="royalblue", width=2),
                        )
                    )
                    set_kr(fig_hum)
                    fig_hum.update_layout(
                        title="일별 평균 습도 (%)",
                        xaxis_title="날짜",
                        yaxis_title="습도 (%)",
                        height=280,
                    )
                    st.plotly_chart(fig_hum, width="stretch")

                ph_ec_cols = [c for c in ["ph", "ec"] if c in env_df.columns]
                if ph_ec_cols:
                    daily_ph_ec = (
                        tdf.groupby("day")[ph_ec_cols]
                        .mean()
                        .reset_index()
                    )
                    n_sub = len(ph_ec_cols)
                    fig_pe = make_subplots(
                        rows=1, cols=n_sub, subplot_titles=["pH", "EC"][:n_sub]
                    )
                    colors_pe = {"ph": "teal", "ec": "darkorange"}
                    for idx, col in enumerate(ph_ec_cols, start=1):
                        fig_pe.add_trace(
                            go.Scatter(
                                x=daily_ph_ec["day"],
                                y=daily_ph_ec[col],
                                mode="lines",
                                name=col.upper(),
                                line=dict(color=colors_pe.get(col, "gray"), width=2),
                            ),
                            row=1,
                            col=idx,
                        )
                    set_kr(fig_pe)
                    fig_pe.update_layout(
                        title="일별 pH·EC 변화",
                        height=280,
                        xaxis_title="날짜",
                    )
                    st.plotly_chart(fig_pe, width="stretch")
                else:
                    st.info("pH·EC 열이 없어 해당 그래프는 건너뛰었습니다.")
            else:
                st.info("환경 데이터에 시간 정보가 없습니다.")

            with st.expander("환경 데이터 원본 테이블 보기"):
                st.dataframe(env_df, width="stretch")
                csv_env = env_df.to_csv(index=False).encode("utf-8-sig")
                st.download_button(
                    "환경 CSV 다운로드",
                    data=csv_env,
                    file_name=f"{env_name}_환경데이터.csv",
                    mime="text/csv",
                )
    except Exception as e:
        st.warning(f"⚠️ 이 부분은 데이터 형식 때문에 표시하지 못했어요: {e}")


# ═══════════════════════════════════════════════════════════════════════════
#  탭 3 - 생육 결과
# ═══════════════════════════════════════════════════════════════════════════
with tab3:
    try:
        if growth_file is None or growth_df.empty:
            st.info("생육 결과 CSV를 업로드해 주세요. 사이드바에서 파일을 선택하면 분석 결과가 표시됩니다.")
        else:
            g = growth_df.copy()

            st.header("핵심 결과")
            if "생중량" in g.columns:
                w = g["생중량"].dropna()
                if len(w) >= 2:
                    w_mean = w.mean()
                    w_std = w.std()
                    cv = (w_std / w_mean * 100) if w_mean > 0 else 0
                    idx_max = g["생중량"].idxmax()
                    idx_min = g["생중량"].idxmin()
                    id_max = g.loc[idx_max, "개체번호"]
                    id_min = g.loc[idx_min, "개체번호"]

                    card_cols = st.columns(4)
                    with card_cols[0]:
                        st.metric("평균 생중량", f"{w_mean:.2f} g")
                    with card_cols[1]:
                        st.metric("표준편차", f"{w_std:.2f} g")
                    with card_cols[2]:
                        st.metric("변동계수 (CV)", f"{cv:.1f} %")
                    with card_cols[3]:
                        st.metric("생중량 범위", f"{w.min():.2f} ~ {w.max():.2f} g")

                    st.markdown(
                        f"- **최대 생중량**: 개체 `{id_max}` ({w.max():.2f} g)\n"
                        f"- **최소 생중량**: 개체 `{id_min}` ({w.min():.2f} g)"
                    )
                else:
                    st.info("생중량 데이터가 부족합니다.")
            else:
                st.info("생중량 열이 없어 핵심 결과 카드를 표시할 수 없습니다.")

            st.subheader("개체별 생육 비교")

            meas_for_graph = [m for m in meas_cols if m in g.columns]
            if meas_for_graph:
                fig_bar = make_subplots(
                    rows=len(meas_for_graph),
                    cols=1,
                    subplot_titles=[f"개체별 {m}" for m in meas_for_graph],
                    vertical_spacing=0.12,
                )
                colors_list = ["firebrick", "royalblue", "seagreen", "darkorange"]
                for i, m in enumerate(meas_for_graph):
                    vals = g[m].dropna()
                    if len(vals) < 2:
                        continue
                    x_vals = list(range(len(vals)))
                    fig_bar.add_trace(
                        go.Bar(
                            x=x_vals,
                            y=vals,
                            name=m,
                            marker_color=colors_list[i % len(colors_list)],
                            opacity=0.85,
                        ),
                        row=i + 1,
                        col=1,
                    )
                fig_bar.update_xaxes(title_text="개체 순서", showticklabels=False)
                for i, m in enumerate(meas_for_graph):
                    fig_bar.update_yaxes(
                        title_text=m, row=i + 1, col=1
                    )
                set_kr(fig_bar)
                fig_bar.update_layout(
                    height=180 * len(meas_for_graph) + 60,
                    showlegend=False,
                )
                st.plotly_chart(fig_bar, width="stretch")
            else:
                st.info("표시할 생육 측정 항목이 선택되지 않았습니다. 사이드바에서 선택해 주세요.")

            st.subheader("생중량 분포")
            if "생중량" in g.columns:
                w = g["생중량"].dropna()
                if len(w) >= 3:
                    fig_box = go.Figure()
                    fig_box.add_trace(
                        go.Box(
                            y=w,
                            name="생중량",
                            fillcolor="royalblue",
                            line_color="navy",
                            opacity=0.8,
                            boxpoints="outliers",
                            jitter=0.3,
                            pointpos=-1.8,
                        )
                    )
                    set_kr(fig_box)
                    fig_box.update_layout(
                        title="개체별 생중량 분포 (박스플롯)",
                        yaxis_title="생중량 (g)",
                        height=300,
                    )
                    st.plotly_chart(fig_box, width="stretch")
                else:
                    st.info("생중량 데이터가 부족해 분포 그래프를 표시할 수 없습니다.")
            else:
                st.info("생중량 열이 없어 분포 그래프를 표시할 수 없습니다.")

            st.subheader("상관관계 분석")

            if "생중량" in g.columns:
                corr_cols = [
                    m for m in ["잎 수", "지상부 길이"]
                    if m in g.columns and m != "생중량"
                ]
                for m in corr_cols:
                    df_c = g[[m, "생중량"]].dropna()
                    if len(df_c) < 2:
                        st.info(f"{m}과 생중량의 비교에 사용할 데이터가 부족합니다.")
                        continue

                    x = df_c[m].values
                    y = df_c["생중량"].values
                    r = np.corrcoef(x, y)[0, 1]

                    slope, intercept = np.polyfit(x, y, 1)
                    x_line = np.linspace(x.min(), x.max(), 100)
                    y_line = slope * x_line + intercept

                    fig_sc = go.Figure()
                    fig_sc.add_trace(
                        go.Scatter(
                            x=x,
                            y=y,
                            mode="markers",
                            name=f"{m} vs 생중량",
                            marker=dict(size=8, color="royalblue", opacity=0.7),
                        )
                    )
                    fig_sc.add_trace(
                        go.Scatter(
                            x=x_line,
                            y=y_line,
                            mode="lines",
                            name=f"추세선 (r = {r:.3f})",
                            line=dict(color="firebrick", width=2, dash="dash"),
                        )
                    )
                    set_kr(fig_sc)
                    fig_sc.update_layout(
                        title=f"{m} vs 생중량 (상관계수 r = {r:.3f})",
                        xaxis_title=f"{m}",
                        yaxis_title="생중량 (g)",
                        height=340,
                    )
                    st.plotly_chart(fig_sc, width="stretch")

                    abs_r = abs(r)
                    if abs_r >= 0.7:
                        strength = "매우 강한 상관"
                    elif abs_r >= 0.5:
                        strength = "강한 상관"
                    elif abs_r >= 0.3:
                        strength = "중간 정도 상관"
                    elif abs_r >= 0.1:
                        strength = "약한 상관"
                    else:
                        strength = "거의 상관 없음"
                    direction = "양의 상관" if r > 0 else "음의 상관"
                    st.markdown(
                        f"- **상관계수(r)**: `{r:.3f}` → {strength}, {direction}\n"
                        f"- r이 1에 가까울수록 두 값이 함께 증가하고, -1에 가까울수록 반대로 움직입니다."
                    )
            else:
                st.info("생중량 열이 없어 상관관계 분석을 표시할 수 없습니다.")

            if "생중량" in g.columns:
                w = g["생중량"].dropna()
                if len(w) >= 4:
                    q75 = w.quantile(0.75)
                    q25 = w.quantile(0.25)
                    top = g[g["생중량"] >= q75].copy()
                    bottom = g[g["생중량"] <= q25].copy()

                    st.subheader("생중량 상위 25% vs 하위 25%")

                    top_ids = ", ".join(str(v) for v in top["개체번호"].tolist())
                    bot_ids = ", ".join(str(v) for v in bottom["개체번호"].tolist())
                    st.markdown(
                        f"- **상위 25% (이상 {q75:.2f} g)**: {len(top)}개체 — `{top_ids}`\n"
                        f"- **하위 25% (이하 {q25:.2f} g)**: {len(bottom)}개체 — `{bot_ids}`"
                    )

                    cmp_cols = [
                        c for c in ["잎 수", "지상부 길이", "지하부 길이"]
                        if c in g.columns
                    ]
                    if cmp_cols:
                        cmp_data = []
                        for grp_name, grp_df in [("상위 25%", top), ("하위 25%", bottom)]:
                            row_data = {"그룹": grp_name}
                            for c in cmp_cols:
                                vals = grp_df[c].dropna()
                                if len(vals) >= 1:
                                    row_data[c] = f"{vals.mean():.1f}"
                                else:
                                    row_data[c] = "—"
                            row_data["개체 수"] = len(grp_df)
                            cmp_data.append(row_data)
                        if cmp_data:
                            st.dataframe(
                                pd.DataFrame(cmp_data),
                                width="stretch",
                                hide_index=True,
                            )
                else:
                    st.info("개체 수가 부족해 상위·하위 25% 비교를 할 수 없습니다.")

            with st.expander("생육 데이터 원본 테이블 보기"):
                st.dataframe(g, width="stretch")
                csv_growth = g.to_csv(index=False).encode("utf-8-sig")
                st.download_button(
                    "생육 CSV 다운로드",
                    data=csv_growth,
                    file_name=f"{growth_name}_생육결과데이터.csv",
                    mime="text/csv",
                )
    except Exception as e:
        st.warning(f"⚠️ 이 부분은 데이터 형식 때문에 표시하지 못했어요: {e}")
