import numpy as np
import sounddevice as sd
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.widget import Widget
from kivy.graphics import Color, Line, Rectangle
from kivy.clock import Clock
from kivy.core.text import LabelBase
from kivy.core.window import Window
from kivy.uix.popup import Popup
from kivy.uix.boxlayout import BoxLayout

import time

# 日本語を使う場合は、コードと同じフォルダにfontsフォルダを作り、NotoSansJP-VF.ttfを入れる
# Android（Buildozer）の場合は、日本語フォント(NotoSansJP-Regular.ttf)をプロジェクト内の fonts フォルダに置き、
# buildozer.spec の source.include_exts に ttf を追加する必要があります。
# source.include_exts = py,png,jpg,kv,atlas,ttf

LabelBase.register(
    name="JP",
    # fn_regular="/Fonts/Noto Sans JP/Noto Sans JP-VF.ttf"
    fn_regular="fonts/HGRPP1.TTC" # 日本語フォント
)

THRESHOLD = 0.25
MIN_INTERVAL = 0.1

DISPLAY_SEC = 0.8 #表示を0.8秒にする
SAMPLERATE = 44100 #サンプルレート Hz

# ===== 波形ウィジェット =====
class WaveformWidget(Widget):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # self.buffer = np.zeros(44100 // 2)

        self.buffer = np.zeros(
            int(SAMPLERATE * DISPLAY_SEC)
        )

        self.first_hit_pos = None # 1回目の衝撃音位置

        # 固定表示用
        self.freeze_buffer = None

        with self.canvas.before:
            Color(0.1, 0.1, 0.1)
            self.bg = Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=self.update_bg, size=self.update_bg)

    # def mark_first_hit(self):
    #     self.first_hit_pos = self.width * 0.8

    def update_bg(self, *args):
        self.bg.pos = self.pos
        self.bg.size = self.size

    def update_waveform(self, new_samples):
        if self.height < 20:
            return

        L = len(new_samples)
        self.buffer = np.roll(self.buffer, -L)
        self.buffer[-L:] = new_samples

        self.canvas.clear()
        with self.canvas:
            # 中央線
            w = self.width
            h = self.height
            px, py = self.pos
            Color(0.5, 0.5, 0.5)
            Line(
                points=[px, py + h/2, px + w, py + h/2],
                width=1
            )

            for t in np.arange(0, DISPLAY_SEC + 0.001, 0.2):
                x = self.pos[0] + self.width * t / DISPLAY_SEC

                Color(0.3, 0.3, 0.3)
                Line(points=[x, self.pos[1], x, self.pos[1] + self.height])

            Color(0, 1, 0)
            points = []
            w = self.width
            h = self.height
            px, py = self.pos
            step = max(1, len(self.buffer) // int(w))
            for i in range(0, len(self.buffer), step):
                s = self.buffer[i]
                x = px + w * i / len(self.buffer)
                y = py + h/2 + s * (h/2)
                points.extend([x, y])
            Line(points=points, width=1.2)

            # 固定波形（赤） 表示用に間引いている。
            if self.freeze_buffer is not None:
                Color(1, 0, 0)
                freeze_points = []
                step = max(1, len(self.freeze_buffer) // int(w))
                for i in range(0, len(self.freeze_buffer), step):
                    GAIN = 2.0
                    s = self.freeze_buffer[i]
                    x = px + w * i / len(self.freeze_buffer)
                    y = py + h/2 + s * (h/2)*GAIN
                    freeze_points.extend([x, y])
                Line(points=freeze_points, width=2)

            if self.first_hit_pos is not None:
                x = px + w * self.first_hit_pos / DISPLAY_SEC
                Color(1, 1, 0) #黄色
                Line(
                    points=[x, py, x, py + h],
                    width=1
                )


# ===== メインアプリ =====
class CollisionApp(App):

    def build(self):
        # 点Aの初期値
        self.x1 = 0
        self.y1 = 0

        # 点Bの初期値
        self.x2 = 0.0 # フットラインからの距離 ボール何個分か
        self.y2 = 0.5 # レールからの距離　ボール何個分か

        self.BallDia = 5.71 # cm
        self.distance_cm = 0  #初期化

        self.latest_samples = np.zeros(1024)
        self.stream = sd.InputStream(
            samplerate=SAMPLERATE,
            channels=1,
            dtype='float32',
            callback=self.audio_callback
        )
        self.stream.start()
        Clock.schedule_interval(self.audio_loop, 1/60)

        Window.bind(size=self.on_window_resize)
        self.detecting = False
        self.first_collision_time = None
        self.last_collision_time = 0
        self.wave_stopped = False
        root = self.build_portrait()
        self.root_widget = root

        return root

    # -------------------------
    # 縦レイアウト
    # -------------------------
    def build_portrait(self):
        root = BoxLayout(orientation='vertical')

        self.wave = WaveformWidget(size_hint=(1, 1/2))
        root.add_widget(self.wave)

        root.add_widget(self.build_settings(size_hint=(1, 1/4)))
        root.add_widget(self.build_bottom(size_hint=(1, 1/4)))

        return root

    # -------------------------
    # 横レイアウト
    # -------------------------
    def build_landscape(self):
        root = BoxLayout(orientation='horizontal')

        self.wave = WaveformWidget(size_hint=(0.6, 1))
        root.add_widget(self.wave)

        right = BoxLayout(orientation='vertical', size_hint=(0.4, 1))
        right.add_widget(self.build_settings(size_hint=(1, 0.5)))
        right.add_widget(self.build_bottom(size_hint=(1, 0.5)))

        root.add_widget(right)
        return root

    # -------------------------
    # 設定部分
    # -------------------------
    def build_settings(self, size_hint):
        TITLE = 0.25
        TEXT  = 0.25
        BTN   = 0.10
        VALUE = 0.10
        UNIT  = 0.10

        layout = BoxLayout(
            orientation='vertical',
            spacing=5,
            padding=5,
            size_hint=size_hint
        )

        row_x = BoxLayout(orientation='horizontal')

        row_x.add_widget(Label(
            text="手玉の位置",
            font_size=30,
            font_name="JP",
            bold=True,
            size_hint_x=TITLE
        ))

        row_x.add_widget(Label(
            text="フットから球",
            font_size=30,
            font_name="JP",
            size_hint_x=TEXT
        ))

        minus_x = Button(text="-",font_size=40, size_hint_x=BTN)
        minus_x.bind(on_press=self.sub_x2)
        row_x.add_widget(minus_x)

        # self.x2_label = Label(
        #     text=f"{self.x2:.1f}",
        #     font_size=36,
        #     bold=True,
        #     font_name="JP",
        #     size_hint_x=VALUE,
        #     halign="center"
        # )
        self.x2_label = Label(
            text=f"{self.x2:.1f}",
            font_size=36,
            size_hint_x=VALUE
        )
        self.x2_label.bind(
            size=lambda s, *_: setattr(s, "text_size", s.size)
        )

        row_x.add_widget(self.x2_label)

        plus_x = Button(text="+",font_size=40, size_hint_x=BTN)
        plus_x.bind(on_press=self.add_x2)
        row_x.add_widget(plus_x)

        row_x.add_widget(Label(
            text="個分",
            font_size=30,
            font_name="JP",
            size_hint_x=UNIT
        ))
        layout.add_widget(row_x)

        row_y = BoxLayout(orientation='horizontal')

        row_y.add_widget(Label(
            text="",
            size_hint_x=TITLE
        ))

        row_y.add_widget(Label(
            text="レールから球",
            font_size=30,
            font_name="JP",
            size_hint_x=TEXT
        ))

        minus_y = Button(text="-",font_size=40, size_hint_x=BTN)
        minus_y.bind(on_press=self.sub_y2)  
        row_y.add_widget(minus_y)

        # self.y2_label = Label(
        #     text=f"{self.y2:.1f}",
        #     font_size=36,
        #     bold=True,
        #     font_name="JP",
        #     size_hint_x=VALUE
        # )
        self.y2_label = Label(
            text=f"{self.y2:.1f}",
            font_size=36,
            size_hint_x=VALUE
        )
        self.y2_label.bind(
            size=lambda s, *_: setattr(s, "text_size", s.size)
        )

        row_y.add_widget(self.y2_label)
        plus_y = Button(text="+",font_size=40, size_hint_x=BTN)
        plus_y.bind(on_press=self.add_y2)
        row_y.add_widget(plus_y)

        row_y.add_widget(Label(
            text="個分",
            font_size=30,
            font_name="JP",
            size_hint_x=UNIT
        ))

        layout.add_widget(row_y)
    
        # 2行目
        row2 = BoxLayout(
            orientation='horizontal',
            size_hint_y=None,
            height=60
        )

        calc_btn = Button(
            text="距離を計算(Push)　", font_size=32,
            font_name="JP",
            size_hint_x=0.4
        )

        calc_btn.bind(on_press=self.update_distance)
        self.label_info = Label(
            text="距離 : -- cm", font_size=32,
            font_name="JP",
            size_hint_x=0.6
        )

        row2.add_widget(calc_btn)
        row2.add_widget(self.label_info)

        layout.add_widget(row2)
        return layout


    #増減処理　0.1刻み
    def add_x2(self, instance):
        self.x2 = round(self.x2 + 0.1, 1)
        self.x2_label.text = f"{self.x2:.1f}"

    def sub_x2(self, instance):
        self.x2 = max(0, round(self.x2 - 0.1, 1))
        self.x2_label.text = f"{self.x2:.1f}"

    def add_y2(self, instance):
        self.y2 = round(self.y2 + 0.1, 1)
        self.y2_label.text = f"{self.y2:.1f}"

    def sub_y2(self, instance):
        self.y2 = max(0, round(self.y2 - 0.1, 1))
        self.y2_label.text = f"{self.y2:.1f}"

        # Button(text="+", font_size=40, size_hint_x=0.15)

        # Button(text="-", font_size=40, size_hint_x=0.15)

    def update_distance(self, instance):
        self.calculate_distance()

    def calculate_distance(self):
        # x1 = float(self.x1_input.text)
        # y1 = float(self.y1_input.text)
        # x2 = float(self.x2_input.text)
        # y2 = float(self.y2_input.text)
        from math import sqrt
        real_x2 = 127+self.x2*self.BallDia
        real_y2 = 63.5-self.y2*self.BallDia
        distance = sqrt((real_x2 - self.x1) ** 2 + (real_y2 - self.y1) ** 2)
        distance -= self.BallDia # 1番と手玉分の距離を差し引いて移動距離にする
        self.distance_cm = distance
        self.label_info.text = f"距離: {distance:.2f} cm"

    def audio_callback(self, indata, frames, time_info, status):
        if status:
            print(status)
        self.latest_samples = indata[:, 0].copy()

    # -------------------------
    # 結果＋ボタン部分
    # -------------------------
    def build_bottom(self, size_hint):
        self.result_label = Label(text="速度: -- km/h", font_size=32, font_name="JP")

        layout = BoxLayout(orientation='vertical', size_hint=size_hint)
        layout.add_widget(self.result_label)

        self.start_btn = Button(text="スタート", font_size=40, font_name="JP")
        self.start_btn.bind(on_press=self.start_detection)
        layout.add_widget(self.start_btn)

        return layout

    # -------------------------
    # 画面回転時のレイアウト切り替え
    # -------------------------
    def on_window_resize(self, *args):
        pass
        # if Window.width > Window.height:
        #     new_root = self.build_landscape()
        # else:
        #     new_root = self.build_portrait()

        # self.root_window.remove_widget(self.root_widget)
        # self.root_window.add_widget(new_root)
        # self.root_widget = new_root

    # -------------------------
    # 衝突検出開始
    # -------------------------
    def start_detection(self, instance):
        self.result_label.text = "衝突音を待っています…"
        self.detecting = True
        self.hit_count = 0
        self.first_collision_time = None
        self.last_collision_time = 0
        self.wave.freeze_buffer = None
        self.start_time = time.time() # 開始時刻
        self.wave.first_hit_pos = None
        self.wave_stopped = False

    def freeze_first_hit(self, dt):
        buf = self.wave.buffer.copy()
        # shift = int(0.2 * SAMPLERATE)
        # buf = np.roll(buf, -shift)
        # self.wave.freeze_buffer = buf
        # 衝撃音位置を画面上で0.2秒にする

        peak = np.argmax(np.abs(buf))
        target = int(0.25 * len(buf))
        shift = peak - target
        buf = np.roll(buf, -shift)
        self.wave.freeze_buffer = buf
        # 黄線の位置を0.2秒にする
        self.wave.first_hit_pos = 0.2

        # print("固定波形保存")
        # print(len(self.wave.freeze_buffer), len(self.wave.buffer))
        print("peak=", peak,"target=", target,"shift=", shift)

    # -------------------------
    # 音声ループ
    # -------------------------
    def audio_loop(self, dt):
        samples = self.latest_samples.copy()
        samples = samples.flatten()
        samples = self.latest_samples.flatten()

        if not self.wave_stopped:
            self.wave.update_waveform(samples)

        if not self.detecting:
            return

        volume = np.max(np.abs(samples))
        now = time.time()

        if self.wave.freeze_buffer is not None:
            print(np.max(np.abs(self.wave.freeze_buffer)))

        # --------- 10秒タイムアウト ---------
        if self.first_collision_time is None:
            remaining = 10 - (now - self.start_time)
            if remaining <= 0:
                self.result_label.text = "タイムアウト"
                self.detecting = False
                return

            self.result_label.text = f"待機中 {remaining:.1f}秒"

        if volume > THRESHOLD and (now - self.last_collision_time) > MIN_INTERVAL:
            self.last_collision_time = now
            self.hit_count += 1

            if self.hit_count == 1:
                self.first_collision_time = now
                # バッファ内で衝撃が起きた位置を保存    - len(samples)
                self.first_hit_index = len(self.wave.buffer)
                Clock.schedule_once(self.freeze_first_hit, 0.2)
                self.result_label.text = "ブレイク 検出"

            elif self.hit_count == 2:
                diff = now - self.first_collision_time
                self.result_label.text = "ブレイク＆ヒット 検出"

                speed_kmh = (self.distance_cm / 100.0) / diff * 3.6

                self.result_label.text = f"速度: {speed_kmh:.2f} km/h"
                # 2回目を拾ったので終了
                self.detecting = False
                self.wave_stopped = True


    def on_stop(self):
        if hasattr(self, "stream"):
            self.stream.stop()
            self.stream.close()


CollisionApp().run()
