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

import time

LabelBase.register(
    name="JP",
    fn_regular="fonts/static/NotoSansJP-Regular.ttf"
)

THRESHOLD = 0.25
MIN_INTERVAL = 0.1


# ===== 波形ウィジェット =====
class WaveformWidget(Widget):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.buffer = np.zeros(44100 // 2)

        with self.canvas.before:
            Color(0.1, 0.1, 0.1)
            self.bg = Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=self.update_bg, size=self.update_bg)

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
            Color(0, 1, 0)
            points = []
            w = self.width
            h = self.height
            for i, s in enumerate(self.buffer):
                x = w * i / len(self.buffer)
                y = h/2 + s * (h/2)
                points.extend([x, y])
            Line(points=points, width=1.2)


# ===== メインアプリ =====
class CollisionApp(App):

    def build(self):
        Window.bind(size=self.on_window_resize)
        self.detecting = False
        self.first_collision_time = None
        self.last_collision_time = 0

        root = self.build_portrait()
        self.root_widget = root

        Clock.schedule_interval(self.audio_loop, 1/60)
        return root

    # -------------------------
    # 縦レイアウト
    # -------------------------
    def build_portrait(self):
        root = BoxLayout(orientation='vertical')

        self.wave = WaveformWidget(size_hint=(1, 1/3))
        root.add_widget(self.wave)

        root.add_widget(self.build_settings(size_hint=(1, 1/3)))
        root.add_widget(self.build_bottom(size_hint=(1, 1/3)))

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
        layout = BoxLayout(orientation='vertical', size_hint=size_hint)

        self.label_info = Label(text="距離（cm）を入力してください", font_name="JP", font_size=22)
        layout.add_widget(self.label_info)

        self.distance_input = TextInput(text="142", font_size=28, multiline=False)
        layout.add_widget(self.distance_input)

        return layout

    # -------------------------
    # 結果＋ボタン部分
    # -------------------------
    def build_bottom(self, size_hint):
        layout = BoxLayout(orientation='vertical', size_hint=size_hint)

        self.result_label = Label(text="速度: -- km/h", font_name="JP", font_size=32)
        layout.add_widget(self.result_label)

        self.start_btn = Button(text="スタート", font_name="JP", font_size=40)
        self.start_btn.bind(on_press=self.start_detection)
        layout.add_widget(self.start_btn)

        return layout

    # -------------------------
    # 画面回転時のレイアウト切り替え
    # -------------------------
    def on_window_resize(self, *args):
        if Window.width > Window.height:
            new_root = self.build_landscape()
        else:
            new_root = self.build_portrait()

        self.root_window.remove_widget(self.root_widget)
        self.root_window.add_widget(new_root)
        self.root_widget = new_root

    # -------------------------
    # 衝突検出開始
    # -------------------------
    def start_detection(self, instance):
        self.result_label.text = "衝突音を待っています…"
        self.detecting = True
        self.first_collision_time = None

    # -------------------------
    # 音声ループ
    # -------------------------
    def audio_loop(self, dt):
        try:
            with sd.InputStream(
                samplerate=44100,
                channels=1,
                dtype='float32'
            ) as stream:
                samples, _ = stream.read(1024)
                samples = samples.flatten()
                self.wave.update_waveform(samples)

        except Exception as e:
            print("録音エラー:", e)
            return

        if not self.detecting:
            return

        volume = np.max(np.abs(samples))
        now = time.time()

        if volume > THRESHOLD and (now - self.last_collision_time) > MIN_INTERVAL:
            self.last_collision_time = now

            if self.first_collision_time is None:
                self.first_collision_time = now
                self.result_label.text = "衝突音1検出…"
            else:
                diff = now - self.first_collision_time
                dist_m = float(self.distance_input.text) / 100.0
                speed_kmh = (dist_m / diff) * 3.6

                self.result_label.text = f"速度: {speed_kmh:.2f} km/h"
                self.detecting = False

CollisionApp().run()
