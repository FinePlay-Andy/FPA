import sys
import re
import pandas as pd
import ctypes
import os
from PyQt5 import uic, QtGui, QtCore, QtWidgets
from PyQt5.QtWidgets import (
    QApplication, QDialog, QFileDialog, QMessageBox,
    QGraphicsScene, QGraphicsPixmapItem, QLineEdit, QButtonGroup)
from PyQt5.QtCore import QTime, QRectF
import numpy as np

# DPI 인식 + 고해상도 아이콘 사용
if hasattr(QtCore.Qt, 'AA_EnableHighDpiScaling'):
    QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_EnableHighDpiScaling, True)
if hasattr(QtCore.Qt, 'AA_UseHighDpiPixmaps'):
    QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_UseHighDpiPixmaps, True)

def resource_path(relative_path):
    """ PyInstaller 실행 또는 개발 환경에서 리소스 경로 찾기 """
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)


def analyze_pass_data(df):
    """
    경기 이벤트 데이터프레임을 분석하여 보정 좌표, 패스 거리, 패스 방향을 추가합니다.

    Args:
        df (pd.DataFrame): 'StartX', 'StartY', 'EndX', 'EndY', 'Direction' 등의
                           컬럼을 포함하는 데이터프레임.

    Returns:
        pd.DataFrame: 분석 결과(보정 좌표, 거리, 방향 등)가 추가된 데이터프레임.
    """
    # --- 0. 사전 준비 ---
    # 필드 규격 설정
    FIELD_W = 105  # 필드 가로 길이
    FIELD_H = 68  # 필드 세로 너비

    # 좌표 데이터가 숫자가 아닐 경우를 대비해 숫자형으로 변환
    coord_cols = ['StartX', 'StartY', 'EndX', 'EndY']
    for col in coord_cols:
        df[col] = pd.to_numeric(df[col], errors='coerce')

    # 분석에 필요한 컬럼이 없는 경우 원본 데이터프레임 반환
    if not all(col in df.columns for col in coord_cols + ['Direction']):
        print("분석에 필요한 컬럼이 부족합니다.")
        return df

    # --- 1. 보정 좌표 산출 ---
    # Direction이 'left'일 경우, 모든 좌표를 180도 회전시켜 'right' 기준으로 통일
    is_left_direction = df['Direction'].str.lower() == 'left'

    df['StartX_adj'] = np.where(is_left_direction, FIELD_W - df['StartX'], df['StartX'])
    df['StartY_adj'] = np.where(is_left_direction, FIELD_H - df['StartY'], df['StartY'])
    df['EndX_adj'] = np.where(is_left_direction, FIELD_W - df['EndX'], df['EndX'])
    df['EndY_adj'] = np.where(is_left_direction, FIELD_H - df['EndY'], df['EndY'])

    # --- 2. 패스 거리 분류 ---
    # 보정된 좌표를 기준으로 두 점 사이의 거리(유클리드 거리) 계산
    distance = np.sqrt(
        (df['EndX_adj'] - df['StartX_adj']) ** 2 + (df['EndY_adj'] - df['StartY_adj']) ** 2
    )
    df['Distance'] = distance

    # 거리(distance) 값에 따라 구간 나누기
    conditions_dist = [
        distance < 20,
        (distance >= 20) & (distance < 40),
        distance >= 40
    ]
    choices_dist = ['short', 'middle', 'long']
    df['Pass_Distance'] = np.select(conditions_dist, choices_dist, default=None)

    # --- 3. 패스 방향 분류 ---
    # 보정된 좌표를 기준으로 각도 계산 (atan2 사용)
    dx = df['EndX_adj'] - df['StartX_adj']
    dy = df['EndY_adj'] - df['StartY_adj']
    angle = np.degrees(np.arctan2(dy, dx))

    # 각도를 0~360 범위로 변환
    df['Angle'] = (angle + 360) % 360

    # 각도(angle) 값에 따라 방향 분류
    conditions_dir = [
        (df['Angle'] >= 315) | (df['Angle'] < 45),  # 전진 (forward)
        (df['Angle'] >= 45) & (df['Angle'] < 135),  # 좌측 (left)
        (df['Angle'] >= 135) & (df['Angle'] < 225),  # 후진 (backward)
        (df['Angle'] >= 225) & (df['Angle'] < 315)  # 우측 (right)
    ]
    choices_dir = ['forward', 'left', 'backward', 'right']
    df['Pass_Direction'] = np.select(conditions_dir, choices_dir, default=None)

    return df


# 1. create_player_summary 수정
def create_player_summary(df_analyzed):
    all_players = df_analyzed['Player'].unique()  # 전체 선수 명단 확보
    pass_actions = ['Pass', 'Cross']
    if 'Tags' not in df_analyzed.columns: df_analyzed['Tags'] = ''
    df_pass = df_analyzed[df_analyzed['Action'].isin(pass_actions)].copy()
    if df_pass.empty: return pd.DataFrame(index=all_players).fillna(0)

    summary = df_pass.groupby('Player').agg(
        Total_Pass=('Action', 'count'),
        Success_Pass=('Tags', lambda x: x.str.contains('Success').sum()),
        Key_Pass=('Tags', lambda x: x.str.contains('Key').sum()),
        Assist=('Tags', lambda x: x.str.contains('Assist').sum())
    )
    # ▼▼▼ (추가) 전체 선수 명단을 기준으로 결과표를 재구성하고 없는 선수는 0으로 채움 ▼▼▼
    summary = summary.reindex(all_players).fillna(0)

    summary['Fail_Pass'] = summary['Total_Pass'] - summary['Success_Pass']
    summary['Pass_Success_Rate'] = (summary['Success_Pass'] / summary['Total_Pass'] * 100).fillna(0).round(2)
    # ... (이하 기존과 동일) ...
    pivot_direction = pd.pivot_table(df_pass, values='Action', index='Player', columns='Pass_Direction',
                                     aggfunc='count').reindex(all_players).fillna(0)
    pivot_distance = pd.pivot_table(df_pass, values='Action', index='Player', columns='Pass_Distance',
                                    aggfunc='count').reindex(all_players).fillna(0)
    summary = summary.join(pivot_direction, how='left').join(pivot_distance, how='left').fillna(0)
    ALL_DIRECTIONS = ['forward', 'left', 'right', 'backward'];
    ALL_DISTANCES = ['short', 'middle', 'long']
    for col in ALL_DIRECTIONS:
        if col not in summary.columns: summary[col] = 0
    for col in ALL_DISTANCES:
        if col not in summary.columns: summary[col] = 0
    int_cols = ['Total_Pass', 'Success_Pass', 'Fail_Pass', 'Key_Pass', 'Assist'] + ALL_DIRECTIONS + ALL_DISTANCES
    for col in int_cols:
        if col in summary.columns: summary[col] = summary[col].astype(int)
    final_columns_order = ['Total_Pass', 'Success_Pass', 'Fail_Pass', 'Pass_Success_Rate', 'Key_Pass', 'Assist',
                           'forward', 'backward', 'left', 'right', 'short', 'middle', 'long']
    ordered_cols = [col for col in final_columns_order if col in summary.columns]
    summary = summary[ordered_cols]
    return summary.sort_values(by='Total_Pass', ascending=False)


# 2. create_shooter_summary 수정
def create_shooter_summary(df_with_xg):
    all_players = df_with_xg['Player'].unique()
    shot_actions = ['Goal', 'Shot On Target', 'Shot', 'Blocked Shot']
    df_shots = df_with_xg[df_with_xg['Action'].isin(shot_actions)].copy()
    if df_shots.empty: return pd.DataFrame(index=all_players).fillna(0)
    if 'Tags' not in df_shots.columns: df_shots['Tags'] = ''
    df_shots['Tags'] = df_shots['Tags'].fillna('')

    summary = df_shots.groupby('Player').agg(
        Total_Shots=('Action', 'count'),
        Shots_On_Target=('Action', lambda x: x.isin(['Shot On Target', 'Goal']).sum()),
        Goals=('Action', lambda x: (x == 'Goal').sum()),
        Total_xG=('xG', 'sum')
    ).reindex(all_players).fillna(0)  # reindex 및 fillna(0) 추가

    headed_goals = \
    df_shots[(df_shots['Action'] == 'Goal') & (df_shots['Tags'].str.contains('Header'))].groupby('Player')[
        'Action'].count()
    outbox_goals = \
    df_shots[(df_shots['Action'] == 'Goal') & (df_shots['Tags'].str.contains('Out-box'))].groupby('Player')[
        'Action'].count()
    summary = summary.join(headed_goals.rename('Headed_Goals'))
    summary = summary.join(outbox_goals.rename('Outbox_Goals'))
    summary[['Headed_Goals', 'Outbox_Goals']] = summary[['Headed_Goals', 'Outbox_Goals']].fillna(0).astype(int)
    return summary.sort_values(by='Goals', ascending=False)


# 3. create_cross_summary 수정
def create_cross_summary(df_analyzed):
    all_players = df_analyzed['Player'].unique()
    if 'Tags' not in df_analyzed.columns: df_analyzed['Tags'] = ''
    df_cross = df_analyzed[df_analyzed['Action'] == 'Cross'].copy()
    if df_cross.empty: return pd.DataFrame(index=all_players).fillna(0)

    summary = df_cross.groupby('Player').agg(
        Total_Crosses=('Action', 'count'),
        Successful_Crosses=('Tags', lambda x: x.str.contains('Success').sum())
    ).reindex(all_players).fillna(0)  # reindex 및 fillna(0) 추가
    summary['Cross_Accuracy'] = (summary['Successful_Crosses'] / summary['Total_Crosses'] * 100).fillna(0).round(2)
    return summary


# 4. create_tackle_summary 수정
def create_tackle_summary(df_analyzed):
    all_players = df_analyzed['Player'].unique()
    if 'Tags' not in df_analyzed.columns: df_analyzed['Tags'] = ''
    df_tackle = df_analyzed[df_analyzed['Action'] == 'Tackle'].copy()
    if df_tackle.empty: return pd.DataFrame(index=all_players).fillna(0)

    summary = df_tackle.groupby('Player').agg(
        Total_Tackles=('Action', 'count'),
        Successful_Tackles=('Tags', lambda x: x.str.contains('Success').sum())
    ).reindex(all_players).fillna(0)  # reindex 및 fillna(0) 추가
    summary['Tackle_Success_Rate'] = (summary['Successful_Tackles'] / summary['Total_Tackles'] * 100).fillna(0).round(2)
    return summary


# 5. create_heading_summary 수정
def create_heading_summary(df_analyzed):
    all_players = df_analyzed['Player'].unique()
    if 'Tags' not in df_analyzed.columns: df_analyzed['Tags'] = ''

    df_aerial = df_analyzed[(df_analyzed['Action'] == 'Duel') & (df_analyzed['Tags'].str.contains('Aerial'))].copy()
    if not df_aerial.empty:
        aerial_summary = df_aerial.groupby('Player').agg(
            Total_Aerial_Duels=('Action', 'count'),
            Aerial_Duels_Won=('Tags', lambda x: x.str.contains('Success').sum())
        )
        aerial_summary['Aerial_Duel_Success_Rate'] = (
                    aerial_summary['Aerial_Duels_Won'] / aerial_summary['Total_Aerial_Duels'] * 100).round(2)
    else:
        aerial_summary = pd.DataFrame()

    shot_actions = ['Shot', 'Shot On Target', 'Goal']
    df_headed_shots = df_analyzed[
        (df_analyzed['Action'].isin(shot_actions)) & (df_analyzed['Tags'].str.contains('Header'))].copy()
    if not df_headed_shots.empty:
        headed_shot_summary = df_headed_shots.groupby('Player').agg(
            Total_Headed_Shots=('Action', 'count'),
            Headed_Shots_On_Target=('Action', lambda x: x.isin(['Shot On Target', 'Goal']).sum())
        )
        headed_shot_summary['Headed_SOT_Rate'] = (headed_shot_summary['Headed_Shots_On_Target'] / headed_shot_summary[
            'Total_Headed_Shots'] * 100).round(2)
    else:
        headed_shot_summary = pd.DataFrame()

    if aerial_summary.empty and headed_shot_summary.empty:
        summary = pd.DataFrame(index=all_players)
    elif aerial_summary.empty:
        summary = headed_shot_summary
    elif headed_shot_summary.empty:
        summary = aerial_summary
    else:
        summary = pd.merge(aerial_summary, headed_shot_summary, on='Player', how='outer')

    return summary.reindex(all_players).fillna(0)  # reindex 및 fillna(0) 추가


# 6. calculate_heading_score 수정 (0으로 나누기 방지)
def calculate_heading_score(df_heading_summary):
    summary = df_heading_summary.copy()
    if summary.empty: return summary
    required_cols = ['Aerial_Duel_Success_Rate', 'Headed_SOT_Rate', 'Aerial_Duels_Won']
    for col in required_cols:
        if col not in summary.columns: summary[col] = 0
    aerial_score = summary['Aerial_Duel_Success_Rate'] * 0.5
    shot_score = summary['Headed_SOT_Rate'] * 0.3
    volume_bonus = np.log1p(summary['Aerial_Duels_Won']) * 2
    summary['Raw_Heading_Score'] = aerial_score + shot_score + volume_bonus
    mid_point = 45;
    steepness = 0.1
    raw_scores = summary['Raw_Heading_Score']
    heading_scores = 100 / (1 + np.exp(-steepness * (raw_scores - mid_point)))
    summary['Heading_Score'] = heading_scores.round(0).astype(int)
    return summary

def calculate_pass_score(df_summary):
    """
    선수별 요약 통계로부터 패스 점수를 계산합니다. (절대평가 버전)
    """
    if df_summary.empty:
        return df_summary

    # 1. 항목별 점수 계산
    df_summary['Accuracy_Score'] = df_summary['Pass_Success_Rate'] * 0.5
    df_summary['Influence_Score'] = (df_summary['forward'] / df_summary['Total_Pass']).fillna(0) * 30
    df_summary['Creativity_Score'] = (df_summary['Key_Pass'] * 2) + (df_summary['Assist'] * 5)
    df_summary['Volume_Bonus'] = np.log1p(df_summary['Success_Pass']) * 3

    # 2. Raw 점수 합산
    df_summary['Raw_Score'] = (df_summary['Accuracy_Score'] +
                               df_summary['Influence_Score'] +
                               df_summary['Creativity_Score'] +
                               df_summary['Volume_Bonus'])

    # ▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼
    # 3. (수정) Sigmoid 함수를 이용해 1~100점 절대 점수로 변환

    # --- 여기서 기준점을 설정할 수 있습니다 ---
    mid_point = 50  # Raw_Score가 50점일 때 Pass_Score 50점이 되는 기준점
    steepness = 0.1  # 곡선의 기울기 (숫자가 클수록 가파름)

    # 시그모이드 함수 계산
    raw_scores = df_summary['Raw_Score']
    pass_scores = 100 / (1 + np.exp(-steepness * (raw_scores - mid_point)))

    df_summary['Pass_Score'] = pass_scores.round(0).astype(int)
    # ▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲

    return df_summary


def add_xg_to_data(df):
    """
    전체 데이터프레임에서 슛 이벤트에 대한 기대 득점(xG) 값을 계산하여 추가합니다.
    """
    # 슛과 관련된 Action만 필터링
    shot_actions = ['Goal', 'Shot On Target', 'Shot', 'Blocked Shot']
    # df.loc를 사용하여 SettingWithCopyWarning 방지
    df_shots = df[df['Action'].isin(shot_actions)].copy()

    if df_shots.empty:
        df['xG'] = np.nan  # 슛 데이터가 없으면 xG 컬럼만 추가
        return df

    # 골대의 위치는 (105, 34)로 고정 (필드 오른쪽 끝 중앙)
    goal_x, goal_y = 105, 34

    # 보정된 좌표(_adj)를 사용하여 골문과의 거리를 계산
    distance = np.sqrt(
        (goal_x - df_shots['StartX_adj']) ** 2 + (goal_y - df_shots['StartY_adj']) ** 2
    )

    # 거리를 기반으로 xG 값을 계산하는 간단한 모델
    # (거리가 멀수록 xG는 급격히 감소)
    xg_values = 1 / (1 + np.exp(0.14 * distance - 2.5))

    # 원본 df_shots에 xG 값을 할당
    df_shots['xG'] = xg_values

    # 원본 데이터프레임(df)에 xG 값을 합치기 (슛이 아닌 이벤트는 NaN)
    # df.merge를 사용하여 안전하게 병합
    df = pd.merge(df, df_shots[['No', 'xG']], on='No', how='left')

    return df

def calculate_shooting_score(df_shooter_summary):
    """
    선수별 슈팅 요약 통계로부터 슈팅 점수를 계산합니다. (태그 보너스 추가)
    """
    summary = df_shooter_summary.copy()
    if summary.empty:
        return summary

    # 1. 기본 점수 계산
    finishing_score = (summary['Goals'] - summary['Total_xG']) * 15
    threat_score = summary['Total_xG'] * 20

    # ▼▼▼▼▼ (추가된 부분) 태그 기반 보너스 점수 계산 ▼▼▼▼▼
    # 헤더 골은 1골당 3점, 박스 밖 골은 1골당 5점의 보너스
    headed_bonus = summary.get('Headed_Goals', 0) * 3
    outbox_bonus = summary.get('Outbox_Gals', 0) * 5  # Outbox_Goals

    summary['Specialty_Bonus'] = headed_bonus + outbox_bonus
    # ▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲

    summary['Raw_Shooting_Score'] = finishing_score + threat_score + summary['Specialty_Bonus']

    # 2. Sigmoid 함수로 1~100점 변환
    mid_point = 10
    steepness = 0.15
    raw_scores = summary['Raw_Shooting_Score']
    shooting_scores = 100 / (1 + np.exp(-steepness * (raw_scores - mid_point)))

    summary['Shooting_Score'] = shooting_scores.round(0).astype(int)
    return summary

def calculate_cross_score(df_cross_summary):
    """
    선수별 크로스 요약 통계로부터 CRO 스탯 점수를 계산합니다.
    """
    summary = df_cross_summary.copy()
    if summary.empty:
        return summary

    # Raw Score 계산: (정확도 * 70%) + (성공 횟수 보너스)
    accuracy_score = summary['Cross_Accuracy'] * 0.7
    volume_bonus = np.log1p(summary['Successful_Crosses']) * 3
    summary['Raw_Cross_Score'] = accuracy_score + volume_bonus

    # Sigmoid 함수로 1~100점 변환
    mid_point = 40  # Raw Score 40점을 평균(50점)으로 설정
    steepness = 0.1
    raw_scores = summary['Raw_Cross_Score']
    cross_scores = 100 / (1 + np.exp(-steepness * (raw_scores - mid_point)))

    summary['Cross_Score'] = cross_scores.round(0).astype(int)
    return summary

def calculate_tackle_score(df_tackle_summary):
    """
    선수별 태클 요약 통계로부터 TAC 스탯 점수를 계산합니다.
    """
    summary = df_tackle_summary.copy()
    if summary.empty:
        return summary

    # Raw Score 계산: (성공률 * 60%) + (성공 횟수 보너스)
    accuracy_score = summary['Tackle_Success_Rate'] * 0.6
    volume_bonus = np.log1p(summary['Successful_Tackles']) * 4
    summary['Raw_Tackle_Score'] = accuracy_score + volume_bonus

    # Sigmoid 함수로 1~100점 변환
    mid_point = 50  # Raw Score 50점을 평균(50점)으로 설정
    steepness = 0.1
    raw_scores = summary['Raw_Tackle_Score']
    tackle_scores = 100 / (1 + np.exp(-steepness * (raw_scores - mid_point)))

    summary['Tackle_Score'] = tackle_scores.round(0).astype(int)
    return summary


def calculate_heading_score(df_heading_summary):
    """
    선수별 헤딩 요약 통계로부터 HED 스탯 점수를 계산합니다.
    """
    summary = df_heading_summary.copy()
    if summary.empty:
        return summary

    # 필요한 컬럼이 없을 경우 0으로 채우기
    required_cols = ['Aerial_Duel_Success_Rate', 'Headed_SOT_Rate', 'Aerial_Duels_Won']
    for col in required_cols:
        if col not in summary.columns:
            summary[col] = 0

    # Raw Score 계산: (공중볼 성공률 * 50%) + (헤딩 유효슛 비율 * 30%) + (공중볼 성공 횟수 보너스)
    aerial_score = summary['Aerial_Duel_Success_Rate'] * 0.5
    shot_score = summary['Headed_SOT_Rate'] * 0.3
    volume_bonus = np.log1p(summary['Aerial_Duels_Won']) * 2
    summary['Raw_Heading_Score'] = aerial_score + shot_score + volume_bonus

    # Sigmoid 함수로 1~100점 변환
    mid_point = 45
    steepness = 0.1
    raw_scores = summary['Raw_Heading_Score']
    heading_scores = 100 / (1 + np.exp(-steepness * (raw_scores - mid_point)))

    summary['Heading_Score'] = heading_scores.round(0).astype(int)
    return summary

class DataLogUI(QDialog):
    def __init__(self):
        super().__init__()
        uic.loadUi(resource_path("UI/fpa_data_coll_exe.ui"), self)

        # ▼▼▼ 최소화, 최대화, 닫기 버튼을 모두 활성화하는 코드 ▼▼▼
        self.setWindowFlags(
            QtCore.Qt.Window |
            QtCore.Qt.WindowMinimizeButtonHint |
            QtCore.Qt.WindowMaximizeButtonHint |
            QtCore.Qt.WindowCloseButtonHint
        )
        # ▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲

        # ⚽ 경기장 설정
        self.FIELD_WIDTH = 105
        self.FIELD_HEIGHT = 68
        self.PIXEL_WIDTH = 600
        self.PIXEL_HEIGHT = 383
        self.scene = QGraphicsScene(self)
        self.footballfield.setScene(self.scene)
        self.footballfield.setSceneRect(0, 0, self.PIXEL_WIDTH, self.PIXEL_HEIGHT)
        self.footballfield.mousePressEvent = self.on_field_click
        self.dot_items = []

        # ⚽ 필드 이미지 삽입
        self.field_pixmap = QtGui.QPixmap(resource_path("assets/football_field.png"))
        self.field_item = QGraphicsPixmapItem(self.field_pixmap)
        self.scene.addItem(self.field_item)

        # 📃 리스트 위젯 설정 (Drag & Drop 지원)
        self.listWidget.setDragDropMode(self.listWidget.InternalMove)

        # 🖼️ 로고 이미지 삽입
        self.logo_scene = QGraphicsScene(self)
        self.logo.setScene(self.logo_scene)
        self.logo_pixmap = QtGui.QPixmap(resource_path("assets/logo.png"))
        self.logo_item = QGraphicsPixmapItem(self.logo_pixmap)
        self.logo_scene.addItem(self.logo_item)
        self.logo.setSceneRect(QRectF(self.logo_pixmap.rect()))


        # 🧪 테스트용 더미 로그 (최신 포맷 반영)
        self.listWidget.addItems([
            "1st | home | right | 12:00:01 | Pos(340, 190) | 10 Assist to 7 | Pos(400, 200)",
        ])

        # 🎯 버튼 이벤트 연결
        self.pushButton_delete.clicked.connect(self.delete_selected_item)
        self.pushButton_submitinput.clicked.connect(self.submit_stat)
        self.pushButton_savedata.clicked.connect(self.export_log)
        self.pushButton_export.clicked.connect(self.export_log)
        self.pushButton_uploaddata.clicked.connect(self.upload_data)
        self.setup_radio_groups()

        # timeline 분 단위 카운터
        self.minute_counter = 1  # 기본값 1분
        self.update_timeline_display()
        self.lineEdit_timeline.setReadOnly(True)
        self.pushButton_plus.clicked.connect(self.increment_minute)
        self.pushButton_minus.clicked.connect(self.decrement_minute)

        # ⌨️ 입력창에서 스페이스바 → 스탯 기록
        self.lineEdit_datainput.installEventFilter(self)

        # ⌫ 백스페이스로 도트 삭제
        self.installEventFilter(self)

        # --- ▼▼▼ (수정) 새로운 스탯 사전 정의 ▼▼▼ ---
        self.ACTION_CODES = {
            's': 'Pass', 'c': 'Cross', 'r': 'Dribble', 'e': 'Breakthrough',
            't': 'Tackle', 'u': 'Duel', 'd': 'Shot', 'dd': 'Shot On Target',
            'ddd': 'Goal', 'db': 'Blocked Shot', 'i': 'Intercept', 'l': 'Clear',
            'b': 'Block', 'q': 'Acquisition', 'v': 'Save', 'm': 'Miss', 'f': 'Foul', 'o': 'Offside'
        }
        self.TAG_CODES = {
            'k': 'Key', 'a': 'Assist', 'h': 'Header', 'r': 'Aerial',
            'w': 'Suffered', 'n': 'In-box', 'u': 'Out-box'
        }
        # 두 선수 상호작용이 필요한 액션 코드 정의
        self.TWO_PLAYER_ACTIONS = ['ss', 's', 'cc', 'c']

    def get_id_inputs(self):
        match_id = self.lineEdit_matchid.text().strip() if hasattr(self, "lineEdit_matchid") else ""

        teamid_h = self.lineEdit_teamid_h.text().strip() if hasattr(self, "lineEdit_teamid_h") else ""
        # 팀ID Away 라인에딧 이름이 te**a**mid_a 인지 te**am**in_a 인지 둘 다 대응
        teamid_a_widget = getattr(self, "lineEdit_teamid_a", None) or getattr(self, "lineEdit_teamin_a", None)
        teamid_a = teamid_a_widget.text().strip() if teamid_a_widget else ""

        return match_id, teamid_h, teamid_a

    def update_timeline_display(self):
        # 항상 MM:00 형식으로 표시
        mm = str(self.minute_counter).zfill(2)
        self.lineEdit_timeline.setText(f"{mm}:00")

    def increment_minute(self):
        self.minute_counter += 1
        self.update_timeline_display()

    def decrement_minute(self):
        if self.minute_counter > 0:
            self.minute_counter -= 1
        self.update_timeline_display()


    def setup_radio_groups(self):
        # Half 그룹
        self.half_group = QButtonGroup(self)
        self.half_group.addButton(self.radioButton_1sthalf)
        self.half_group.addButton(self.radioButton_2ndhalf)
        self.half_group.setExclusive(True)

        # Team 그룹
        self.team_group = QButtonGroup(self)
        self.team_group.addButton(self.radioButton_home)
        self.team_group.addButton(self.radioButton_away)
        self.team_group.setExclusive(True)

        # Attack Direction 그룹
        self.direction_group = QButtonGroup(self)
        self.direction_group.addButton(self.radioButton_right)
        self.direction_group.addButton(self.radioButton_left)
        self.direction_group.setExclusive(True)

    def on_mode_changed(self, mode_text):
        if mode_text == "데이터 수집":
            return  # 현재 화면이니까 이동 안 함

        reply = QMessageBox.question(
            self, "모드 이동 확인",
            f"'{mode_text}' 모드로 이동하시겠습니까?",
            QMessageBox.Yes | QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            self.move_to_mode(mode_text)

    # 기존 upload_data 함수를 이 코드로 전체 교체해주세요.
    def upload_data(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Upload Data", "", "Excel Files (*.xlsx);;CSV Files (*.csv)"
        )
        if not file_path:
            return

        try:
            if file_path.endswith('.xlsx'):
                df = pd.read_excel(file_path, sheet_name='Data')
            elif file_path.endswith('.csv'):
                df = pd.read_csv(file_path)
            else:
                QMessageBox.warning(self, "Unsupported", "지원되지 않는 파일 형식입니다.")
                return

            self.listWidget.clear()

            two_player_actions = ['Pass', 'Cross']

            for _, row in df.iterrows():
                # --- ▼▼▼ (수정된 부분) 숫자 형식을 정수로 변환하는 로직 추가 ▼▼▼ ---
                player_raw = row.get('Player', '')
                receiver_raw = row.get('Receiver', '')

                # 실수를 정수로 변환한 뒤 문자열로 변경
                player = str(int(float(player_raw))) if pd.notna(player_raw) and str(player_raw).strip() != '' else ''
                receiver = str(int(float(receiver_raw))) if pd.notna(receiver_raw) and str(
                    receiver_raw).strip() != '' else ''
                # --- ▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲

                half = str(row.get('Half', '')).strip()
                team = str(row.get('Team', '')).strip()
                direction = str(row.get('Direction', '')).strip()
                time = str(row.get('Time', '')).strip()
                action = str(row.get('Action', '')).strip()
                start_x = str(row.get('StartX', '')).strip()
                start_y = str(row.get('StartY', '')).strip()
                end_x = str(row.get('EndX', '')).strip()
                end_y = str(row.get('EndY', '')).strip()
                tags = str(row.get('Tags', '')).strip()

                log_text = f"{half} | {team} | {direction} | {time} | Pos({start_x}, {start_y}) | {player} {action}"

                if action in two_player_actions and receiver:
                    log_text += f" to {receiver} | Pos({end_x}, {end_y})"

                if tags:
                    log_text += f" | Tags: {tags}"

                self.listWidget.addItem(log_text)

        except Exception as e:
            QMessageBox.critical(self, "Error", f"파일을 불러오는 중 오류 발생: {str(e)}")


    def on_field_click(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            scene_pos = self.footballfield.mapToScene(event.pos())
            pixel_x = scene_pos.x()
            pixel_y = scene_pos.y()

            x_meter = round(pixel_x * self.FIELD_WIDTH / self.PIXEL_WIDTH, 2)
            y_meter = round((self.PIXEL_HEIGHT - pixel_y) * self.FIELD_HEIGHT / self.PIXEL_HEIGHT, 2)
            self.lineEdit_position.setText(f"{x_meter}, {y_meter}")

            # 도트 찍기
            radius = 5
            color = QtGui.QColor("#FF7740")
            dot = self.scene.addEllipse(
                pixel_x - radius, pixel_y - radius,
                radius * 2, radius * 2,
                pen=QtGui.QPen(color),
                brush=QtGui.QBrush(color)
            )

            self.dot_items.append(dot)  # 도트 리스트에 저장 ✅

    def delete_selected_item(self):
        selected = self.listWidget.currentRow()
        if selected >= 0:
            self.listWidget.takeItem(selected)

    # 기존 export_log 함수를 이 코드로 전체 교체
    def export_log(self):
        if self.listWidget.count() == 0: QMessageBox.information(self, "내보내기 실패", "저장할 로그가 없습니다."); return
        file_path, _ = QFileDialog.getSaveFileName(self, "로그 저장", "", "Excel Files (*.xlsx);;CSV Files (*.csv)")
        if not file_path: return

        logs = [self.listWidget.item(i).text() for i in range(self.listWidget.count())]
        parsed_logs = []

        for log in logs:
            log_dict = {}
            parts = log.split(' | ')
            log_dict['Half'] = parts[0];
            log_dict['Team'] = parts[1];
            log_dict['Direction'] = parts[2];
            log_dict['Time'] = parts[3]

            pos_match = re.search(r'Pos\((.+?), (.+?)\)', parts[4])
            if pos_match: log_dict['StartX'] = pos_match.group(1); log_dict['StartY'] = pos_match.group(2)

            action_part = parts[5]
            action_match = re.match(r'(\d+) (.+?)(?: to (\d+))?$', action_part)
            if action_match:
                log_dict['Player'] = action_match.group(1)
                log_dict['Action'] = action_match.group(2)
                log_dict['Receiver'] = action_match.group(3) if action_match.group(3) else ''

            log_dict['EndX'] = '';
            log_dict['EndY'] = '';
            log_dict['Tags'] = ''
            for part in parts[6:]:
                if 'Pos' in part:
                    end_pos_match = re.search(r'Pos\((.+?), (.+?)\)', part)
                    if end_pos_match: log_dict['EndX'] = end_pos_match.group(1); log_dict['EndY'] = end_pos_match.group(
                        2)
                elif 'Tags' in part:
                    log_dict['Tags'] = part.replace('Tags: ', '')

            parsed_logs.append(log_dict)

        match_id, teamid_h, teamid_a = self.get_id_inputs()
        for idx, log in enumerate(parsed_logs, start=1):
            log["No"] = idx;
            log["MatchID"] = match_id
            team_val = str(log.get("Team", "")).strip().lower()
            if team_val == "home":
                log["TeamID"] = teamid_h
            elif team_val == "away":
                log["TeamID"] = teamid_a

        columns = ["No", "MatchID", "TeamID", "Half", "Team", "Direction", "Time", "Player", "Receiver", "Action",
                   "StartX", "StartY", "EndX", "EndY", "Tags"]
        df = pd.DataFrame(parsed_logs).reindex(columns=columns)

        df_analyzed = analyze_pass_data(df.copy())

        try:
            if file_path.endswith(".xlsx"):
                with pd.ExcelWriter(file_path, engine='openpyxl') as writer:
                    # 여기에 ReadMe 시트 생성 로직 추가 가능
                    df_analyzed_with_xg = add_xg_to_data(df_analyzed)
                    df_pass_summary = create_player_summary(df_analyzed_with_xg)
                    df_pass_scores = calculate_pass_score(df_pass_summary)
                    df_shooter_summary = create_shooter_summary(df_analyzed_with_xg)
                    df_shooter_scores = calculate_shooting_score(df_shooter_summary)

                    df_analyzed_with_xg.to_excel(writer, sheet_name='Analyzed_Data', index=False)
                    if not df_pass_summary.empty: df_pass_summary.to_excel(writer, sheet_name='Player_Summary')
                    if not df_pass_scores.empty: df_pass_scores.to_excel(writer, sheet_name='Player_Score')
                    if not df_shooter_summary.empty: df_shooter_summary.to_excel(writer, sheet_name='Shooter_Summary')
                    if not df_shooter_scores.empty: df_shooter_scores.to_excel(writer, sheet_name='Shooting_Score')

                    df_cross_summary = create_cross_summary(df_analyzed_with_xg)
                    if not df_cross_summary.empty:
                        df_cross_summary.to_excel(writer, sheet_name='Cross_Summary')

                        df_cross_scores = calculate_cross_score(df_cross_summary)
                        if not df_cross_scores.empty:
                            df_cross_scores.to_excel(writer, sheet_name='Cross_Score')

                    df_tackle_summary = create_tackle_summary(df_analyzed_with_xg)
                    if not df_tackle_summary.empty:
                        df_tackle_summary.to_excel(writer, sheet_name='Tackle_Summary')

                        df_tackle_scores = calculate_tackle_score(df_tackle_summary)
                        if not df_tackle_scores.empty:
                            df_tackle_scores.to_excel(writer, sheet_name='Tackle_Score')

                    df_heading_summary = create_heading_summary(df_analyzed_with_xg)
                    if not df_heading_summary.empty:
                        df_heading_summary.to_excel(writer, sheet_name='Heading_Summary')

                        df_heading_scores = calculate_heading_score(df_heading_summary)
                        if not df_heading_scores.empty:
                            df_heading_scores.to_excel(writer, sheet_name='Heading_Score')

            else:
                if not file_path.endswith('.csv'): file_path += '.csv'
                df_analyzed.to_csv(file_path, index=False, encoding="utf-8-sig")

            QMessageBox.information(self, "저장 완료", f"분석된 로그를 성공적으로 저장했습니다:\n{file_path}")
        except Exception as e:
            QMessageBox.critical(self, "저장 실패", f"파일 저장 중 오류 발생:\n{str(e)}")

    # 기존 submit_stat 함수를 이 코드로 전체 교체해주세요.
    def submit_stat(self):
        time = self.lineEdit_timeline.text().strip()
        stat_input = self.lineEdit_datainput.text().strip().lower()

        if not time: time = QTime.currentTime().toString("HH:mm:ss"); self.lineEdit_timeline.setText(time)
        if not stat_input: QMessageBox.warning(self, "입력 누락", "데이터를 입력해주세요."); return

        try:
            match_info = self.get_match_info()
            half = "1st" if match_info["Half"] == "1st Half" else "2nd"
            team = match_info["Team"].lower();
            direction = match_info["Direction"].lower()

            # 1. 입력값 분리
            parts = stat_input.split('.', 1)
            base_action_part = parts[0]
            tag_codes = parts[1].split('.') if len(parts) > 1 else []

            # 2. 기본 액션 파싱
            match = re.match(r"(\d+)([a-z]+)(\d*)", base_action_part)
            if not match:
                raise ValueError("기본 입력 형식이 올바르지 않습니다 (예: 10ss8 또는 7d).")

            player_from = int(match.group(1))
            action_code = match.group(2)
            player_to = int(match.group(3)) if match.group(3) else ''

            # 3. 액션 이름 및 태그 결정
            action_name = '';
            tags_list = []

            # ▼▼▼▼▼ (수정된 로직) ▼▼▼▼▼
            # 슈팅 예외 규칙 우선 처리
            if action_code in ['d', 'dd', 'ddd', 'db']:
                action_name = self.ACTION_CODES[action_code]
                # 슈팅의 경우에도 Success/Fail 태그를 명시적으로 추가
                if action_code in ['dd', 'ddd']:
                    tags_list.append('Success')
                else:
                    tags_list.append('Fail')
            # 일반 성공/실패 반복 규칙 처리
            elif len(action_code) > 0:
                base_code = action_code[0]
                if base_code in self.ACTION_CODES:
                    action_name = self.ACTION_CODES[base_code]
                    if len(action_code) > 1 and action_code[0] == action_code[1]:
                        tags_list.append('Success')
                    else:
                        tags_list.append('Fail')
            # ▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲

            if not action_name: raise ValueError(f"'{action_code}'는 알 수 없는 액션 코드입니다.")

            # 4. 추가 태그 변환
            for tc in tag_codes:
                if tc in self.TAG_CODES: tags_list.append(self.TAG_CODES[tc])

            # 5. 로그 생성 (이하 동일)
            log_tags_str = f" | Tags: {', '.join(tags_list)}"

            if not self.dot_items: raise ValueError("위치를 먼저 클릭해주세요.")

            if player_to:
                if len(self.dot_items) < 2: raise ValueError("두 개의 위치가 필요합니다.")
                start_dot, end_dot = self.dot_items[-2].rect().center(), self.dot_items[-1].rect().center()
                start_x = round(start_dot.x() * self.FIELD_WIDTH / self.PIXEL_WIDTH, 2)
                start_y = round((self.PIXEL_HEIGHT - start_dot.y()) * self.FIELD_HEIGHT / self.PIXEL_HEIGHT, 2)
                end_x = round(end_dot.x() * self.FIELD_WIDTH / self.PIXEL_WIDTH, 2)
                end_y = round((self.PIXEL_HEIGHT - end_dot.y()) * self.FIELD_HEIGHT / self.PIXEL_HEIGHT, 2)
                log_text = f"{half} | {team} | {direction} | {time} | Pos({start_x}, {start_y}) | {player_from} {action_name} to {player_to} | Pos({end_x}, {end_y})"
            else:
                start_dot = self.dot_items[-1].rect().center()
                start_x = round(start_dot.x() * self.FIELD_WIDTH / self.PIXEL_WIDTH, 2)
                start_y = round((self.PIXEL_HEIGHT - start_dot.y()) * self.FIELD_HEIGHT / self.PIXEL_HEIGHT, 2)
                log_text = f"{half} | {team} | {direction} | {time} | Pos({start_x}, {start_y}) | {player_from} {action_name}"

            self.listWidget.addItem(log_text + log_tags_str)

            for dot in self.dot_items: self.scene.removeItem(dot)
            self.dot_items.clear()
            self.lineEdit_datainput.clear();
            self.lineEdit_position.clear()

        except Exception as e:
            QMessageBox.warning(self, "입력 오류", f"입력 규칙을 확인해주세요.\n오류: {str(e)}")


    def showEvent(self, event):
        super().showEvent(event)
        self.footballfield.fitInView(self.scene.sceneRect(), QtCore.Qt.KeepAspectRatio)
        self.logo.fitInView(self.logo_scene.sceneRect(), QtCore.Qt.KeepAspectRatio)

    def eventFilter(self, obj, event):
        if event.type() == QtCore.QEvent.KeyPress:
            focused_widget = QApplication.focusWidget()

            # ✅ 입력창 포커스 중 스페이스바 입력 시 → submit_stat
            if isinstance(focused_widget, QLineEdit) and event.key() == QtCore.Qt.Key_Space:
                self.submit_stat()
                return True  # 처리 완료

            # ✅ 입력창 포커스 중 → 다른 키는 무시 (기본 입력 동작 유지)
            if isinstance(focused_widget, QLineEdit):
                return False

            # ⌫ 백스페이스 → 도트 삭제
            if event.key() == QtCore.Qt.Key_Backspace and self.dot_items:
                last_dot = self.dot_items.pop()
                self.scene.removeItem(last_dot)
                return True

        return super().eventFilter(obj, event)

    def get_match_info(self):
        # Half
        half = "1st Half" if self.radioButton_1sthalf.isChecked() else "2nd Half"

        # Team
        team = "Home" if self.radioButton_home.isChecked() else "Away"

        # Direction
        direction = "Right" if self.radioButton_right.isChecked() else "Left"

        return {
            "Half": half,
            "Team": team,
            "Direction": direction
        }



if __name__ == "__main__":
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
    app.setFont(QtGui.QFont("Arial", 10))

    # ✅ macOS Dock 아이콘 지정
    try:
        ctypes.cdll.LoadLibrary('/System/Library/Frameworks/AppKit.framework/AppKit')
    except:
        pass

    app.setWindowIcon(QtGui.QIcon(resource_path("assets/fpa_icon.icns")))

    window = DataLogUI()
    window.show()
    sys.exit(app.exec_())