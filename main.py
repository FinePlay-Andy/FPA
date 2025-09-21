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

class DataLogUI(QDialog):
    def __init__(self):
        super().__init__()
        uic.loadUi(resource_path("UI/fpa_data_coll_exe.ui"), self)

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
            if file_path.endswith('.csv'):
                df = pd.read_csv(file_path)
            elif file_path.endswith('.xlsx'):
                df = pd.read_excel(file_path)
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
        if self.listWidget.count() == 0:
            QMessageBox.information(self, "내보내기 실패", "저장할 로그가 없습니다.")
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self, "로그 저장", "", "CSV Files (*.csv);;Excel Files (*.xlsx)"
        )

        if not file_path:
            return

        logs = [self.listWidget.item(i).text() for i in range(self.listWidget.count())]

        parsed_logs = []
        for log in logs:
            # A타입 매칭
            a_match = re.match(
                r"(.+?) \| (.+?) \| (.+?) \| (.+?) \| Pos\((.+?), (.+?)\) \| (\d+) (.+?) to (\d+) \| Pos\((.+?), (.+?)\)",
                log
            )
            if a_match:
                parsed_logs.append({
                    "Half": a_match.group(1).strip(),
                    "Team": a_match.group(2).strip(),
                    "Direction": a_match.group(3).strip(),
                    "Time": a_match.group(4).strip(),
                    "Player": a_match.group(7).strip(),
                    "Receiver": a_match.group(9).strip(),
                    "Action": a_match.group(8).strip(),
                    "StartX": a_match.group(5).strip(),
                    "StartY": a_match.group(6).strip(),
                    "EndX": a_match.group(10).strip(),
                    "EndY": a_match.group(11).strip(),
                })
                continue

            # B타입 매칭
            b_match = re.match(
                r"(.+?) \| (.+?) \| (.+?) \| (.+?) \| Pos\((.+?), (.+?)\) \| (\d+) (.+?) to N/A",
                log
            )
            if b_match:
                parsed_logs.append({
                    "Half": b_match.group(1).strip(),
                    "Team": b_match.group(2).strip(),
                    "Direction": b_match.group(3).strip(),
                    "Time": b_match.group(4).strip(),
                    "Player": b_match.group(7).strip(),
                    "Receiver": "",
                    "Action": b_match.group(8).strip(),
                    "StartX": b_match.group(5).strip(),
                    "StartY": b_match.group(6).strip(),
                    "EndX": "",
                    "EndY": "",
                })

        # ✅ No 열 추가
        for idx, log in enumerate(parsed_logs, start=1):
            log["No"] = idx

        # ✅ 여기서 MatchID / TeamID 주입
        match_id, teamid_h, teamid_a = self.get_id_inputs()

        for log in parsed_logs:
            # MatchID는 사용자가 입력한 값 그대로
            log["MatchID"] = match_id

            # TeamID는 Team 값(home/away)에 따라 분기
            team_val = str(log.get("Team", "")).strip().lower()
            if team_val == "home":
                log["TeamID"] = teamid_h
            elif team_val == "away":
                log["TeamID"] = teamid_a
            else:
                # 혹시 대소문자 섞여 들어오면 보정
                if "home" in team_val:
                    log["TeamID"] = teamid_h
                elif "away" in team_val:
                    log["TeamID"] = teamid_a
                else:
                    log["TeamID"] = ""  # 알 수 없을 때 빈칸

        # ✅ 열 순서 지정 (2열: MatchID, 3열: TeamID)
        columns = [
            "No", "MatchID", "TeamID",
            "Half", "Team", "Direction", "Time",
            "Player", "Receiver", "Action", "StartX", "StartY", "EndX", "EndY"]

        df = pd.DataFrame(parsed_logs)[columns]

        try:
            if file_path.endswith(".csv"):
                df.to_csv(file_path, index=False, encoding="utf-8-sig")
            elif file_path.endswith(".xlsx"):
                df.to_excel(file_path, index=False)
            else:
                df.to_csv(file_path + ".csv", index=False, encoding="utf-8-sig")

            QMessageBox.information(self, "저장 완료", f"로그를 성공적으로 저장했습니다:\n{file_path}")
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