import sys
import re
import pandas as pd
import ctypes
from PyQt5 import uic, QtGui, QtCore
from PyQt5.QtWidgets import (
    QApplication, QDialog, QFileDialog, QMessageBox,
    QGraphicsScene, QGraphicsPixmapItem, QLineEdit, QTableWidgetItem, QTableWidget, QLabel, QButtonGroup
)
from PyQt5.QtCore import QTime, QRectF, Qt
from PyQt5.QtGui import QColor, QFont, QPixmap

class DataLogUI(QDialog):
    def __init__(self):
        super().__init__()
        uic.loadUi("/Users/leeyonggeun/Desktop/Python/FPA/UI/fpa_data_coll.ui", self)

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
        self.field_pixmap = QtGui.QPixmap("/Users/leeyonggeun/Desktop/Python/FPA/assets/football_field.png")
        self.field_item = QGraphicsPixmapItem(self.field_pixmap)
        self.scene.addItem(self.field_item)

        # 📃 리스트 위젯 설정 (Drag & Drop 지원)
        self.listWidget.setDragDropMode(self.listWidget.InternalMove)

        # 🖼️ 로고 이미지 삽입
        self.logo_scene = QGraphicsScene(self)
        self.logo.setScene(self.logo_scene)
        self.logo_pixmap = QtGui.QPixmap("/Users/leeyonggeun/Desktop//Python/FPA/assets/logo.png")
        self.logo_item = QGraphicsPixmapItem(self.logo_pixmap)
        self.logo_scene.addItem(self.logo_item)
        self.logo.setSceneRect(QRectF(self.logo_pixmap.rect()))

        # 🖼️ 스탯 가이드 이미지 삽입
        self.statguide_scene = QGraphicsScene(self)
        self.statguide.setScene(self.statguide_scene)
        self.statguide_pixmap = QtGui.QPixmap("/Users/leeyonggeun/Desktop/Python/FPA/assets/statguide.png")
        self.statguide_item = QGraphicsPixmapItem(self.statguide_pixmap)
        self.statguide_scene.addItem(self.statguide_item)
        self.statguide.setSceneRect(QRectF(self.statguide_pixmap.rect()))

        # 🧪 테스트용 더미 로그
        self.listWidget.addItems([
            "12:00:01 | Pos(340, 190) | 10 Assist to 7",
            "12:00:05 | Pos(220, 130) | 11 Shot On Target to N/A",
            "12:00:10 | Pos(170, 290) | 9 Cross Success to 10",
            "12:00:15 | Pos(420, 210) | 8 Dribble to N/A",
            "12:00:20 | Pos(380, 160) | 6 Key Pass to 9",
        ])

        # 🎯 버튼 이벤트 연결
        self.pushButton_delete.clicked.connect(self.delete_selected_item)
        self.pushButton_submitinput.clicked.connect(self.submit_stat)
        self.pushButton_savedata.clicked.connect(self.export_log)
        self.pushButton_export.clicked.connect(self.export_log)
        self.pushButton_uploaddata.clicked.connect(self.upload_data)
        self.comboBox_mode.currentTextChanged.connect(self.on_mode_changed)
        self.setup_radio_groups()

        # timeline 분 단위 카운터
        self.minute_counter = 1  # 기본값 1분
        self.update_timeline_display()

        self.lineEdit_timeline.setReadOnly(True)

        # 버튼 이벤트 연결
        self.pushButton_plus.clicked.connect(self.increment_minute)
        self.pushButton_minus.clicked.connect(self.decrement_minute)


        # ⌨️ 입력창에서 스패이스바 → 스탯 기록
        self.lineEdit_datainput.installEventFilter(self)

        # ⌫ 백스페이스로 도트 삭제
        self.installEventFilter(self)

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

    def move_to_mode(self, mode):
        if mode == "경기 정보":
            self.new_window = MatchInfoUI()
        elif mode == "경기 기록":
            self.new_window = MatchRecordUI()
        else:
            return

        self.new_window.show()
        self.close()

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
            # A타입: Half | Team | Direction | Time | Pos(x1, y1) | num1 Action to num2 | Pos(x2, y2)
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

            # B타입: Half | Team | Direction | Time | Pos(x, y) | num1 Action to N/A
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
                    "Action": b_match.group(8).strip(),
                    "StartX": b_match.group(5).strip(),
                    "StartY": b_match.group(6).strip(),
                    "Receiver": "",
                    "EndX": "",
                    "EndY": "",
                })

        df = pd.DataFrame(parsed_logs)

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
            'ee': 'Breakthrough',
            'rr': 'Dribble',
            'bb': 'Duel Win',
            'b': 'Duel Lose',
            'aa': 'Tackle',
            'q': 'Intercept',
            't': 'Acquisition',
            'w': 'Clear',
            'e': 'Cutout',
            'qw': 'Block',
            'v': 'Catching',
            'p': 'Punching',
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


class MatchInfoUI(QDialog):
    def __init__(self):
        super().__init__()
        uic.loadUi("/Users/leeyonggeun/Desktop/Python/FPA/UI/fpa_match_info.ui", self)
        self.setWindowTitle("경기 정보")

        self.comboBox_mode.currentTextChanged.connect(self.on_mode_changed)

        # ⚽ 필드 이미지 삽입
        self.scene = QGraphicsScene(self)
        self.footballfield.setScene(self.scene)
        self.field_pixmap = QtGui.QPixmap("/Users/leeyonggeun/Desktop/Python/FPA/assets/football_field_90.png")
        self.field_item = QGraphicsPixmapItem(self.field_pixmap)
        self.scene.addItem(self.field_item)
        self.footballfield.setSceneRect(QRectF(self.field_pixmap.rect()))

        # 🖼️ 로고 이미지 삽입
        self.logo_scene = QGraphicsScene(self)
        self.logo.setScene(self.logo_scene)
        self.logo_pixmap = QtGui.QPixmap("/Users/leeyonggeun/Desktop/Python/FPA/assets/logo.png")
        self.logo_item = QGraphicsPixmapItem(self.logo_pixmap)
        self.logo_scene.addItem(self.logo_item)
        self.logo.setSceneRect(QRectF(self.logo_pixmap.rect()))

        # 🧑‍💻 예시 데이터 삽입
        home_starters = [
            ["GK", "21", "오승훈", ""],
            ["DF", "2", "황재원", ""],
            ["DF", "40", "박진영", ""],
            ["DF", "4", "카이오", ""],
            ["DF", "3", "정우재", ""],
            ["MF", "5", "요시노", ""],
            ["MF", "10", "라마스", ""],
            ["MF", "11", "세징야", ""],
            ["MF", "30", "한종우", ""],
            ["FW", "18", "정재상", ""],
            ["FW", "32", "정치민", ""],
        ]
        home_subs = [
            ["", "31", "한태희", ""],
            ["", "22", "정성원", ""],
            ["", "15", "이원우", ""],
            ["", "29", "박재현", ""],
            ["", "74", "이용래", ""],
            ["", "14", "박세진", ""],
            ["", "17", "고재현", ""],
            ["", "9", "에드가", ""],
            ["", "8", "이찬동", ""],
        ]
        self.populate_team_table(self.tableWidget_home, home_starters, home_subs, "박창현")

        away_starters = [
            ["GK", "1", "이광연", ""],
            ["DF", "99", "강준혁", ""],
            ["DF", "23", "강투지", ""],
            ["DF", "13", "이기혁", ""],
            ["DF", "33", "홍철", ""],
            ["MF", "6", "김동현", ""],
            ["MF", "97", "이유현", ""],
            ["MF", "26", "김민준", ""],
            ["MF", "39", "이지호", ""],
            ["FW", "22", "이상현", ""],
            ["FW", "10", "가브리엘", ""],
        ]
        away_subs = [
            ["", "21", "박정호", ""],
            ["", "73", "윤일록", ""],
            ["", "5", "최한솔", ""],
            ["", "24", "박호영", ""],
            ["", "18", "김강국", ""],
            ["", "10", "김경민", ""],
            ["", "15", "진준서", ""],
            ["", "9", "코비체비치", ""],
            ["", "11", "마리오", ""],
        ]
        self.populate_team_table(self.tableWidget_away, away_starters, away_subs, "정경호")

        self.home_player_boxes = []
        self.away_player_boxes = []

        # 포메이션 선택 이벤트 연결
        self.comboBox_homeformation.currentTextChanged.connect(self.update_home_formation)
        self.comboBox_awayformation.currentTextChanged.connect(self.update_away_formation)

        # 포메이션 좌표 (픽셀 기준)
        self.formations = {
            "1-4-4-2": [
                (187, 540),  # GK → 중심은 그대로

                (292, 480), (222, 480), (152, 480), (82, 480),  # DF (좌우 반전)
                (292, 420), (222, 420), (152, 420), (82, 420),  # MF
                (222, 360), (152, 360),  # FW
            ],
            "1-4-3-3": [
                (187, 540),

                (292, 480), (222, 480), (152, 480), (82, 480),  # DF
                (252, 420), (187, 420), (122, 420),  # MF
                (252, 360), (187, 360), (122, 360),  # FW
            ],
            "1-4-2-3-1": [
                (187, 540),

                (292, 480), (222, 480), (152, 480), (82, 480),  # DF
                (222, 430), (152, 430),  # MF
                (252, 380), (187, 380), (122, 380),
                (187, 330)# FW
            ],
            "1-3-5-2": [
                (187, 540),  # GK
                (252, 480), (187, 480), (122, 480),  # DF (3-back)
                (317, 420), (252, 420), (187, 420), (122, 420), (57, 420),  # MF (wide + center 3)
                (222, 360), (152, 360),  # FW
            ],
            "1-4-5-1": [
                (187, 540),  # GK
                (292, 480), (222, 480), (152, 480), (82, 480),  # DF
                (317, 420), (252, 420), (187, 420), (122, 420), (57, 420),  # MF
                (187, 360),  # FW (원톱)
            ],
            "1-3-4-3": [
                (187, 540),
                (252, 480), (187, 480), (122, 480),  # DF
                (292, 420), (222, 420), (152, 420), (82, 420),  # MF
                (252, 360), (187, 360), (122, 360),  # FW
            ],
            "1-5-3-2": [
                (187, 540),
                (292, 480), (252, 480), (187, 480), (122, 480), (82, 480),  # DF (Wingback 포함)
                (222, 420), (187, 420), (152, 420),  # MF
                (222, 360), (152, 360),  # FW
            ],
            "1-4-1-4-1": [
                (187, 540),
                (292, 480), (222, 480), (152, 480), (82, 480),  # DF
                (187, 430),  # DMF
                (292, 380), (222, 380), (152, 380), (82, 380),  # MF
                (187, 330),  # FW
            ]
        }

    def update_home_formation(self, text):
        self.clear_formation(self.home_player_boxes)

        positions = self.formations.get(text, [])

        for x, y in positions:
            # ⬇️ 배경 이미지 먼저 추가
            bg_label = QLabel()
            bg_pixmap = QPixmap("/Users/leeyonggeun/Desktop/Python/FPA/assets/circle_bg.png")
            bg_label.setPixmap(bg_pixmap)
            bg_label.setStyleSheet("background-color: transparent;")
            bg_label.setFixedSize(40, 40)
            bg_label.setScaledContents(True)

            bg_proxy = self.scene.addWidget(bg_label)
            bg_proxy.setZValue(0)  # 텍스트 박스보다 뒤에 배치
            bg_proxy.setPos(x - 20, y - 20)

            # ⬇️ 텍스트 입력 박스 추가
            box = QLineEdit()
            box.setFixedSize(40, 40)
            box.setAlignment(Qt.AlignCenter)
            box.setStyleSheet("""
                QLineEdit {
                    border: 2px solid #ff6600;
                    border-radius: 20px;
                    background-color: transparent;
                    padding: 0px;
                    font-size: 16px;
                    margin: 0px;
                }
            """)
            proxy = self.scene.addWidget(box)
            proxy.setZValue(1)  # 이미지 위에 텍스트 박스 올라가게
            proxy.setPos(x - 20, y - 20)

            self.home_player_boxes.append(proxy)
            self.home_player_boxes.append(bg_proxy)

    def update_away_formation(self, text):
        self.clear_formation(self.away_player_boxes)

        positions = self.formations.get(text, [])

        for x, y in positions:
            # Y축 반전: 어웨이는 위쪽에 배치 (전체 높이: 600)
            y_flipped = 580 - y

            # 1. 원형 배경 이미지 (배경용 레이어)
            bg_label = QLabel()
            bg_label.setFixedSize(40, 40)
            bg_label.setScaledContents(True)
            bg_label.setStyleSheet("background-color: transparent;")
            bg_pixmap = QPixmap("/Users/leeyonggeun/Desktop/Python/FPA/assets/circle_bg.png")
            bg_label.setPixmap(bg_pixmap)

            bg_proxy = self.scene.addWidget(bg_label)
            bg_proxy.setZValue(0)  # 제일 뒤
            bg_proxy.setPos(x - 20, y_flipped - 20)
            self.away_player_boxes.append(bg_proxy)

            # 2. 숫자 입력용 QLineEdit (앞쪽 레이어)
            box = QLineEdit()
            box.setFixedSize(40, 40)
            box.setAlignment(Qt.AlignCenter)
            box.setStyleSheet("""
                QLineEdit {
                    border: 2px solid #ff6600;
                    border-radius: 20px;
                    background-color: transparent;
                    padding: 0px;
                    font-size: 16px;
                    margin: 0px;
                }
            """)
            proxy = self.scene.addWidget(box)
            proxy.setZValue(1)
            proxy.setPos(x - 20, y_flipped - 20)  # 중심 정렬
            self.away_player_boxes.append(proxy)

    def clear_formation(self, box_list):
        for proxy in box_list:
            self.scene.removeItem(proxy)
        box_list.clear()


    def on_mode_changed(self, mode_text):
        if mode_text == "경기 정보":
            return

        reply = QMessageBox.question(
            self, "모드 이동 확인",
            f"'{mode_text}' 모드로 이동하시겠습니까?",
            QMessageBox.Yes | QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            self.move_to_mode(mode_text)

    def move_to_mode(self, mode):
        if mode == "경기 기록":
            self.new_window = MatchRecordUI()
        elif mode == "데이터 수집":
            self.new_window = DataLogUI()
        else:
            return

        self.new_window.show()
        self.close()

    def populate_team_table(self, table_widget: QTableWidget, starters: list, substitutes: list, coach: str):
        total_data_rows = len(starters) + len(substitutes) + 2  # 제목 + 데이터 + 감독
        table_widget.setRowCount(total_data_rows + 2)  # +2: substitute label + coach label
        table_widget.setColumnCount(4)

        # ✅ 진짜 헤더 숨김
        table_widget.horizontalHeader().setVisible(False)
        table_widget.verticalHeader().setVisible(False)

        # ✅ 셀 편집 가능 설정 (수동으로 설정해준 것만 제외)
        table_widget.setEditTriggers(QTableWidget.AllEditTriggers)

        # ✅ 테이블 스타일
        table_widget.setStyleSheet("""
                    QTableWidget {
                        background-color: white;
                        border: none;  /* 테이블 외곽선 제거 */
                        gridline-color: transparent;  /* 셀 경계선 제거 */
                        font-family: 'Helvetica';
                    }
                    QHeaderView::section {
                        background-color: #FCD7C5;
                        font-weight: bold;
                        border: none;  /* 헤더 경계선 제거 */
                    }
                """)

        # ✅ 0행: 제목행 (편집 불가)
        headers = ["포지션", "등번호", "선수명", "교체"]
        for col, title in enumerate(headers):
            item = QTableWidgetItem(title)
            item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)  # 편집 불가
            item.setTextAlignment(Qt.AlignCenter)
            item.setBackground(QColor("white"))
            font = item.font()
            font.setBold(True)
            item.setFont(font)
            table_widget.setItem(0, col, item)

        # ✅ 선발 선수 입력 (2행부터)
        for i, player in enumerate(starters):
            row = i + 1  # 1행은 제목, 2행부터 데이터
            for j, value in enumerate(player):
                item = QTableWidgetItem(value)
                item.setTextAlignment(Qt.AlignCenter)
                bg_color = QColor("#FCD7C5") if i % 2 == 0 else QColor("white")
                item.setBackground(bg_color)
                table_widget.setItem(row, j, item)

        # ✅ Substitute 라벨
        sub_header_row = 1 + len(starters)
        sub_header = QTableWidgetItem("Substitute")
        sub_header.setTextAlignment(Qt.AlignCenter)
        sub_header.setFont(QFont("Helvetica", 10, QFont.Bold))
        sub_header.setBackground(QColor("white"))
        sub_header.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
        table_widget.setSpan(sub_header_row, 0, 1, 4)
        table_widget.setItem(sub_header_row, 0, sub_header)

        # ✅ 교체 선수 입력
        for i, player in enumerate(substitutes):
            row = sub_header_row + 1 + i
            for j, value in enumerate(player):
                item = QTableWidgetItem(value)
                item.setTextAlignment(Qt.AlignCenter)
                bg_color = QColor("#FCD7C5") if i % 2 == 0 else QColor("white")
                item.setBackground(bg_color)
                table_widget.setItem(row, j, item)

        # ✅ Coach 라벨
        coach_label_row = table_widget.rowCount() - 2
        coach_label = QTableWidgetItem("Coach")
        coach_label.setTextAlignment(Qt.AlignCenter)
        coach_label.setFont(QFont("Helvetica", 10, QFont.Bold))
        coach_label.setBackground(QColor("white"))
        coach_label.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
        table_widget.setSpan(coach_label_row, 0, 1, 4)
        table_widget.setItem(coach_label_row, 0, coach_label)

        # ✅ 감독 이름
        coach_name_row = table_widget.rowCount() - 1
        coach_name = QTableWidgetItem(f"감독    {coach}")
        coach_name.setTextAlignment(Qt.AlignCenter)
        coach_name.setBackground(QColor("#FCD7C5"))  # 연주황색
        coach_name.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEditable | Qt.ItemIsEnabled)  # 수정 가능하게
        table_widget.setSpan(coach_name_row, 0, 1, 4)
        table_widget.setItem(coach_name_row, 0, coach_name)

        # ✅ 행 높이 & 열 너비 조정
        for row in range(table_widget.rowCount()):
            table_widget.setRowHeight(row, 25)

        table_widget.setColumnWidth(0, 65)
        table_widget.setColumnWidth(1, 65)
        table_widget.setColumnWidth(2, 180)
        table_widget.setColumnWidth(3, 90)

        # ✅ 스크롤 제거
        table_widget.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)




class MatchRecordUI(QDialog):
    def __init__(self):
        super().__init__()
        uic.loadUi("/Users/leeyonggeun/Desktop/Python/FPA/UI/fpa_match_rec.ui", self)
        self.setWindowTitle("경기 기록")

        self.comboBox_mode.currentTextChanged.connect(self.on_mode_changed)

        # 🖼️ 로고 이미지 삽입
        self.logo_scene = QGraphicsScene(self)
        self.logo.setScene(self.logo_scene)
        self.logo_pixmap = QtGui.QPixmap("/Users/leeyonggeun/Desktop/Python/FPA/assets/logo.png")
        self.logo_item = QGraphicsPixmapItem(self.logo_pixmap)
        self.logo_scene.addItem(self.logo_item)
        self.logo.setSceneRect(QRectF(self.logo_pixmap.rect()))

    def on_mode_changed(self, mode_text):
        if mode_text == "경기 기록":
            return  # 현재 화면이니까 이동 안 함

        reply = QMessageBox.question(
            self, "모드 이동 확인",
            f"'{mode_text}' 모드로 이동하시겠습니까?",
            QMessageBox.Yes | QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            self.move_to_mode(mode_text)

    def move_to_mode(self, mode):
        if mode == "경기 정보":
            self.new_window = MatchInfoUI()
        elif mode == "데이터 수집":
            self.new_window = DataLogUI()
        else:
            return

        self.new_window.show()
        self.close()


class DataVisualizeUI(QDialog):
    def __init__(self):
        super().__init__()
        uic.loadUi("/Users/leeyonggeun/Desktop/Python/FPA/UI/fpa_data_visualize.ui", self)
        self.setWindowTitle("데이터 시각화")

        self.comboBox_mode.currentTextChanged.connect(self.on_mode_changed)

        # 🖼️ 로고 이미지 삽입
        self.logo_scene = QGraphicsScene(self)
        self.logo.setScene(self.logo_scene)
        self.logo_pixmap = QtGui.QPixmap("/Users/leeyonggeun/Desktop/Python/FPA/assets/logo.png")
        self.logo_item = QGraphicsPixmapItem(self.logo_pixmap)
        self.logo_scene.addItem(self.logo_item)
        self.logo.setSceneRect(QRectF(self.logo_pixmap.rect()))

    def on_mode_changed(self, mode_text):
        if mode_text == "데이터 시각화":
            return  # 현재 화면이니까 이동 안 함

        reply = QMessageBox.question(
            self, "모드 이동 확인",
            f"'{mode_text}' 모드로 이동하시겠습니까?",
            QMessageBox.Yes | QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            self.move_to_mode(mode_text)

    def move_to_mode(self, mode):
        if mode == "경기 정보":
            self.new_window = MatchInfoUI()
        elif mode == "데이터 수집":
            self.new_window = DataLogUI()
        else:
            return

        self.new_window.show()
        self.close()


if __name__ == "__main__":
    app = QApplication(sys.argv)

    # ✅ macOS에서 Dock 아이콘 지정
    ctypes.cdll.LoadLibrary('/System/Library/Frameworks/AppKit.framework/AppKit')
    app.setWindowIcon(QtGui.QIcon("/Users/leeyonggeun/Desktop/Python/FPA/assets/fpa_icon.png"))  # 원하는 아이콘 경로로 변경

    window = DataLogUI()
    window.show()
    sys.exit(app.exec_())