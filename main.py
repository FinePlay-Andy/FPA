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


def create_player_summary(df_analyzed):
    # ... (기존의 1, 2번 로직은 동일) ...
    pass_actions = ['Pass Success', 'Pass Fail', 'Key Pass', 'Assist']
    df_pass = df_analyzed[df_analyzed['Action'].isin(pass_actions)].copy()
    if df_pass.empty: return pd.DataFrame()
    df_pass['is_success'] = np.where(df_pass['Action'] == 'Pass Fail', 0, 1)

    # 3. (수정) 선수별 기본 통계에 Key_Pass와 Assist 추가
    summary = df_pass.groupby('Player').agg(
        Total_Pass=('Action', 'count'),
        Success_Pass=('is_success', 'sum'),
        Key_Pass=('Action', lambda x: (x == 'Key Pass').sum()),
        Assist=('Action', lambda x: (x == 'Assist').sum())
    )

    # ... (이후 4, 5, 6, 7, 8, 9번 로직은 이전과 동일) ...
    summary['Fail_Pass'] = summary['Total_Pass'] - summary['Success_Pass']
    summary['Pass_Success_Rate'] = (summary['Success_Pass'] / summary['Total_Pass'] * 100).round(2)
    pivot_direction = pd.pivot_table(df_pass, values='Action', index='Player', columns='Pass_Direction',
                                     aggfunc='count', fill_value=0)
    pivot_distance = pd.pivot_table(df_pass, values='Action', index='Player', columns='Pass_Distance', aggfunc='count',
                                    fill_value=0)
    summary = summary.join(pivot_direction, how='left').join(pivot_distance, how='left').fillna(0)

    ALL_DIRECTIONS = ['forward', 'left', 'right', 'backward']
    ALL_DISTANCES = ['short', 'middle', 'long']
    for col in ALL_DIRECTIONS:
        if col not in summary.columns: summary[col] = 0
    for col in ALL_DISTANCES:
        if col not in summary.columns: summary[col] = 0

    int_cols = ['Total_Pass', 'Success_Pass', 'Fail_Pass', 'Key_Pass', 'Assist'] + ALL_DIRECTIONS + ALL_DISTANCES
    for col in int_cols:
        if col in summary.columns: summary[col] = summary[col].astype(int)

    final_columns_order = [
        'Total_Pass', 'Success_Pass', 'Fail_Pass', 'Pass_Success_Rate',
        'Key_Pass', 'Assist',  # <-- 추가
        'forward', 'backward', 'left', 'right',
        'short', 'middle', 'long'
    ]
    ordered_cols = [col for col in final_columns_order if col in summary.columns]
    summary = summary[ordered_cols]
    summary = summary.sort_values(by='Total_Pass', ascending=False)

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


def create_shooter_summary(df_with_xg):
    """
    xG가 포함된 데이터로부터 선수별 슈팅 요약 통계를 생성합니다.
    """
    shot_actions = ['Goal', 'Shot On Target', 'Shot', 'Blocked Shot']
    df_shots = df_with_xg[df_with_xg['Action'].isin(shot_actions)].copy()

    if df_shots.empty:
        return pd.DataFrame()

    summary = df_shots.groupby('Player').agg(
        Total_Shots=('Action', 'count'),
        Shots_On_Target=('Action', lambda x: x.isin(['Shot On Target', 'Goal']).sum()),
        Goals=('Action', lambda x: (x == 'Goal').sum()),
        Total_xG=('xG', 'sum')
    ).fillna(0)

    # 보기 좋게 정렬
    summary = summary.sort_values(by='Goals', ascending=False)

    return summary


def calculate_shooting_score(df_shooter_summary):
    """
    선수별 슈팅 요약 통계로부터 슈팅 점수를 계산합니다. (절대평가)
    """
    summary = df_shooter_summary.copy()
    if summary.empty:
        return summary

    # 1. '결정력'과 '위협도'를 기반으로 Raw Score 계산
    # 결정력(Finishing) = 실제 득점이 기대 득점보다 얼마나 많았는가
    # 위협도(Threat) = 얼마나 득점 확률 높은 슛을 많이 만들어냈는가
    finishing_score = (summary['Goals'] - summary['Total_xG']) * 15
    threat_score = summary['Total_xG'] * 20

    summary['Raw_Shooting_Score'] = finishing_score + threat_score

    # 2. Sigmoid 함수를 이용해 1~100점 절대 점수로 변환
    mid_point = 10  # Raw_Shooting_Score가 10점일 때 50점이 되는 기준점
    steepness = 0.15  # 곡선의 기울기

    raw_scores = summary['Raw_Shooting_Score']
    shooting_scores = 100 / (1 + np.exp(-steepness * (raw_scores - mid_point)))

    summary['Shooting_Score'] = shooting_scores.round(0).astype(int)

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


    def upload_data(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Upload Data", "", "CSV Files (*.csv);;Excel Files (*.xlsx)"
        )
        if not file_path:
            return

        try:
            if file_path.endswith('.xlsx'):
                # ▼▼▼ 여기에 sheet_name='Data'를 추가해서 'Data' 시트만 읽도록 수정! ▼▼▼
                df = pd.read_excel(file_path, sheet_name='Data')
            elif file_path.endswith('.csv'):
                df = pd.read_csv(file_path)
            else:
                QMessageBox.warning(self, "Unsupported", "지원되지 않는 파일 형식입니다.")
                return

            required_columns = {
                'Half', 'Team', 'Direction', 'Time',
                'Player', 'Receiver', 'Action',
                'StartX', 'StartY', 'EndX', 'EndY'
            }
            if not required_columns.issubset(df.columns):
                QMessageBox.critical(
                    self, "형식 오류",
                    "파일에 필요한 컬럼이 없습니다:\nHalf, Team, Direction, Time, Player, Receiver, Action, StartX, StartY, EndX, EndY"
                )
                return

            self.listWidget.clear()
            for _, row in df.iterrows():
                half = str(row.get('Half', '')).strip()
                team = str(row.get('Team', '')).strip()
                direction = str(row.get('Direction', '')).strip()
                time = str(row.get('Time', '')).strip()

                player_raw = row.get('Player', '')
                receiver_raw = row.get('Receiver', '')
                action = str(row.get('Action', '')).strip()

                start_x = str(row.get('StartX', '')).strip()
                start_y = str(row.get('StartY', '')).strip()
                end_x = str(row.get('EndX', '')).strip()
                end_y = str(row.get('EndY', '')).strip()

                # 숫자 변환
                player = str(int(player_raw)) if pd.notna(player_raw) and str(player_raw).strip() != '' else ''
                receiver = str(int(receiver_raw)) if pd.notna(receiver_raw) and str(receiver_raw).strip() != '' else ''

                # 로그 문자열 구성
                log = f"{half} | {team} | {direction} | {time} | Pos({start_x}, {start_y})"
                if player or action:
                    log += f" | {player} {action}"
                if receiver:
                    log += f" to {receiver}"
                elif end_x and end_y:
                    log += " to N/A"
                if end_x and end_y:
                    log += f" | Pos({end_x}, {end_y})"

                self.listWidget.addItem(log)

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

    def export_log(self):
        # 1. 저장할 로그가 있는지 먼저 확인합니다.
        if self.listWidget.count() == 0:
            QMessageBox.information(self, "내보내기 실패", "저장할 로그가 없습니다.")
            return

        # 2. 사용자에게 어디에 저장할지 물어봅니다.
        #    파일 필터를 수정하여 Excel이 기본으로 선택되도록 순서를 변경했습니다.
        file_path, _ = QFileDialog.getSaveFileName(
            self, "로그 저장", "", "Excel Files (*.xlsx);;CSV Files (*.csv)"
        )

        # 사용자가 취소하면 아무것도 하지 않습니다.
        if not file_path:
            return

        # 3. listWidget에서 모든 로그 텍스트를 가져옵니다.
        logs = [self.listWidget.item(i).text() for i in range(self.listWidget.count())]

        # 4. 텍스트 로그를 파싱하여 딕셔너리 리스트로 변환합니다.
        parsed_logs = []
        for log in logs:
            # A타입 매칭 (패스, 어시스트 등)
            a_match = re.match(
                r"(.+?) \| (.+?) \| (.+?) \| (.+?) \| Pos\((.+?), (.+?)\) \| (\d+) (.+?) to (\d+) \| Pos\((.+?), (.+?)\)",
                log
            )
            if a_match:
                parsed_logs.append({
                    "Half": a_match.group(1).strip(), "Team": a_match.group(2).strip(),
                    "Direction": a_match.group(3).strip(), "Time": a_match.group(4).strip(),
                    "Player": a_match.group(7).strip(), "Receiver": a_match.group(9).strip(),
                    "Action": a_match.group(8).strip(), "StartX": a_match.group(5).strip(),
                    "StartY": a_match.group(6).strip(), "EndX": a_match.group(10).strip(),
                    "EndY": a_match.group(11).strip(),
                })
                continue

            # B타입 매칭 (슛, 드리블 등)
            b_match = re.match(
                r"(.+?) \| (.+?) \| (.+?) \| (.+?) \| Pos\((.+?), (.+?)\) \| (\d+) (.+?) to N/A",
                log
            )
            if b_match:
                parsed_logs.append({
                    "Half": b_match.group(1).strip(), "Team": b_match.group(2).strip(),
                    "Direction": b_match.group(3).strip(), "Time": b_match.group(4).strip(),
                    "Player": b_match.group(7).strip(), "Receiver": "",
                    "Action": b_match.group(8).strip(), "StartX": b_match.group(5).strip(),
                    "StartY": b_match.group(6).strip(), "EndX": "", "EndY": "",
                })

        # 5. 추가 정보(No, MatchID, TeamID)를 주입합니다.
        match_id, teamid_h, teamid_a = self.get_id_inputs()
        for idx, log in enumerate(parsed_logs, start=1):
            log["No"] = idx
            log["MatchID"] = match_id
            team_val = str(log.get("Team", "")).strip().lower()
            if team_val == "home":
                log["TeamID"] = teamid_h
            elif team_val == "away":
                log["TeamID"] = teamid_a
            else:
                log["TeamID"] = ""

        # 6. 파싱된 데이터를 DataFrame으로 만듭니다.
        columns = [
            "No", "MatchID", "TeamID", "Half", "Team", "Direction", "Time",
            "Player", "Receiver", "Action", "StartX", "StartY", "EndX", "EndY"]
        df = pd.DataFrame(parsed_logs).reindex(columns=columns)

        # 7. 데이터 분석 함수를 호출합니다.
        df_analyzed = analyze_pass_data(df.copy())

        # 8. 분석이 완료된 DataFrame을 파일로 저장합니다.
        try:
            if file_path.endswith(".xlsx"):
                # --- ReadMe 시트 데이터 생성 ---
                readme_data = {
                    '컬럼명': [
                        'No', 'MatchID', 'TeamID', 'Half', 'Team', 'Direction', 'Time', 'Player', 'Receiver', 'Action',
                        'StartX', 'StartY', 'EndX', 'EndY',
                        'StartX_adj', 'StartY_adj', 'EndX_adj', 'EndY_adj',
                        'Distance', 'Pass_Distance', 'Angle', 'Pass_Direction'
                    ],
                    '설명': [
                        '이벤트 순번', '경기 고유 ID', '팀 고유 ID', '전반(1st)/후반(2nd)', '팀 구분 (home/away)', '공격 방향 (left/right)',
                        '이벤트 발생 시간',
                        '이벤트 주체 선수 등번호', '이벤트 대상 선수 등번호', '이벤트 종류',
                        '이벤트 시작 X좌표 (m)', '이벤트 시작 Y좌표 (m)', '이벤트 종료 X좌표 (m)', '이벤트 종료 Y좌표 (m)',
                        '공격 방향을 오른쪽으로 통일한 X좌표', '공격 방향을 오른쪽으로 통일한 Y좌표',
                        '공격 방향을 오른쪽으로 통일한 종료 X좌표', '공격 방향을 오른쪽으로 통일한 종료 Y좌표',
                        '패스 거리 (m)', '패스 거리 구분 (short/middle/long)', '패스 각도 (0-360도)',
                        '패스 방향 구분 (forward/left/right/backward)'
                    ]
                }
                df_readme = pd.DataFrame(readme_data)

                # --- ExcelWriter를 사용하여 여러 시트에 저장 ---
                with pd.ExcelWriter(file_path, engine='openpyxl') as writer:
                    df_readme.to_excel(writer, sheet_name='ReadMe', index=False)
                    df_analyzed.to_excel(writer, sheet_name='Data', index=False)

                    # ▼▼▼ 요약 통계 생성 및 새 시트로 저장하는 코드 추가 ▼▼▼
                    df_summary = create_player_summary(df_analyzed)
                    if not df_summary.empty:
                        df_summary.to_excel(writer, sheet_name='Player_Summary')

                        # ▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼
                        # (추가된 부분) 패스 점수 계산 및 새 시트로 저장
                        df_scores = calculate_pass_score(df_summary)
                        if not df_scores.empty:
                            df_scores.to_excel(writer, sheet_name='Player_Score')
                        # ▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲

                 # ▼▼▼▼▼▼▼▼▼▼▼▼ (추가된 슈팅 점수 로직) ▼▼▼▼▼▼▼▼▼▼▼▼
                    # 1. 데이터에 xG 값 추가
                    df_with_xg = add_xg_to_data(df_analyzed)

                    # 2. 슈팅 데이터 요약
                    df_shooter_summary = create_shooter_summary(df_with_xg)
                    if not df_shooter_summary.empty:
                        df_shooter_summary.to_excel(writer, sheet_name='Shooter_Summary')

                        # 3. 슈팅 점수 계산 및 저장
                        df_shooting_scores = calculate_shooting_score(df_shooter_summary)
                        if not df_shooting_scores.empty:
                                df_shooting_scores.to_excel(writer, sheet_name='Shooting_Score')
                # ▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲



            else:  # CSV 파일은 단일 시트만 지원하므로 기존 방식대로 저장
                # 사용자가 파일 이름에 .csv를 직접 입력할 경우를 대비
                if not file_path.endswith('.csv'):
                    file_path += '.csv'
                df_analyzed.to_csv(file_path, index=False, encoding="utf-8-sig")

            QMessageBox.information(self, "저장 완료", f"분석된 로그를 성공적으로 저장했습니다:\n{file_path}")
        except Exception as e:
            QMessageBox.critical(self, "저장 실패", f"파일 저장 중 오류 발생:\n{str(e)}")


    def submit_stat(self):
        time = self.lineEdit_timeline.text().strip()
        stat_input = self.lineEdit_datainput.text().strip()

        # ✅ timeline이 비어있을 때만 시스템 시간 채우기
        if not time:
            time = QTime.currentTime().toString("HH:mm:ss")
            self.lineEdit_timeline.setText(time)

        if not stat_input:
            QMessageBox.warning(self, "입력 누락", "스탯 입력(등번호, 코드 등)을 작성해주세요.")
            return

        match_info = self.get_match_info()  # ✅ Half / Team / Direction 가져오기
        half = "1st" if match_info["Half"] == "1st Half" else "2nd"
        team = match_info["Team"].lower()  # "Home" → "home"
        direction = match_info["Direction"].lower()

        # 스탯 사전
        actions_A = {
            'zz': 'Assist',
            'cc': 'Cross Success',
            'ss': 'Pass Success',
            'z': 'Key Pass',
            'c': 'Cross Fail',
            's': 'Pass Fail',
        }

        actions_B = {
            'ddd': 'Goal',
            'dd': 'Shot On Target',
            'd': 'Shot',
            'db': 'Blocked Shot',
            'ee': 'Breakthrough',
            'rr': 'Dribble',
            'bb': 'Duel Win',
            'b': 'Duel Lose',
            'aa': 'Tackle',
            'q': 'Intercept',
            'qq': 'Acquisition',
            'w': 'Clear',
            'ww': 'Cutout',
            'qw': 'Block',
            'v': 'Catching',
            'vv': 'Punching',
            'f': 'Foul',
            'ff': 'Be Fouled',
            'o': 'Offside',
            'gp': 'Gain',
            'm': 'Miss'
        }


        all_actions = {**actions_A, **actions_B}

        for key in sorted(all_actions.keys(), key=len, reverse=True):
            match = re.fullmatch(rf"(\d+){key}(\d*)", stat_input)
            if match:
                action = all_actions[key]

                if key in actions_A:  # A타입
                    if not match.group(2):
                        QMessageBox.warning(self, "입력 오류", "A타입 스탯은 '플레이어번호 + 코드 + 플레이어번호' 형식이어야 합니다.")
                        return
                    try:
                        player_from = int(match.group(1))
                        player_to = int(match.group(2))
                    except ValueError:
                        QMessageBox.warning(self, "입력 오류", "선수 번호는 숫자여야 합니다.")
                        return

                    if len(self.dot_items) < 2:
                        QMessageBox.warning(self, "위치 부족", "A타입 스탯은 두 개의 위치(도트)가 필요합니다.")
                        return

                    start_dot = self.dot_items[-2].rect().center()
                    end_dot = self.dot_items[-1].rect().center()

                    start_x = round(start_dot.x() * self.FIELD_WIDTH / self.PIXEL_WIDTH, 2)
                    start_y = round((self.PIXEL_HEIGHT - start_dot.y()) * self.FIELD_HEIGHT / self.PIXEL_HEIGHT, 2)
                    end_x = round(end_dot.x() * self.FIELD_WIDTH / self.PIXEL_WIDTH, 2)
                    end_y = round((self.PIXEL_HEIGHT - end_dot.y()) * self.FIELD_HEIGHT / self.PIXEL_HEIGHT, 2)

                    log_text = f"{half} | {team} | {direction} | {time} | Pos({start_x}, {start_y}) | {player_from} {action} to {player_to} | Pos({end_x}, {end_y})"

                else:  # B타입
                    try:
                        player_from = int(match.group(1))
                    except ValueError:
                        QMessageBox.warning(self, "입력 오류", "선수 번호는 숫자여야 합니다.")
                        return

                    if not self.dot_items:
                        QMessageBox.warning(self, "위치 누락", "필드에서 위치를 먼저 클릭해주세요.")
                        return

                    dot = self.dot_items[-1].rect().center()
                    x = round(dot.x() * self.FIELD_WIDTH / self.PIXEL_WIDTH, 2)
                    y = round((self.PIXEL_HEIGHT - dot.y()) * self.FIELD_HEIGHT / self.PIXEL_HEIGHT, 2)

                    log_text = f"{half} | {team} | {direction} | {time} | Pos({x}, {y}) | {player_from} {action} to N/A"

                # ✅ 로그 추가
                self.listWidget.addItem(log_text)
                for dot in self.dot_items:
                    self.scene.removeItem(dot)
                self.dot_items.clear()

                self.lineEdit_datainput.clear()
                self.lineEdit_position.clear()
                return

        # ❌ 매칭 실패 시
        QMessageBox.warning(self, "알 수 없는 스탯", "유효한 액션 코드가 아닙니다.")

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