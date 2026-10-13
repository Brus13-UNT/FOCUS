"""
Hábitos - Reloj de hábitos + Música por actividad + Frases motivadoras + Notificaciones con sonido
Python + Flet 0.28.x / 0.80.x

Ejecutar en escritorio:  flet run main.py
Compilar para Android:   flet build apk
"""
import ssl

ssl._create_default_https_context = ssl._create_unverified_context
import asyncio
import datetime as dt
import inspect
import json
import math
import os
import random
import time
import uuid

import flet as ft
import flet.canvas as cv

try:
    import flet_audio as fta
except ImportError:  # la app funciona, pero sin reproducir música
    fta = None

try:
    from mutagen.mp3 import MP3  # opcional: para mostrar la duración de los MP3
except ImportError:
    MP3 = None

# ----------------------------------------------------------------------------
# Constantes y utilidades
# ----------------------------------------------------------------------------
INDIGO = "#4F46E5"
INK = "#0F172A"
GREY = "#64748B"
BORDER = "#E2E8F0"
PALETTE = ["#10B981", "#F59E0B", "#3B82F6", "#8B5CF6", "#EF4444", "#EC4899"]

STATUS_STYLE = {
    "EN CURSO": ("#D1FAE5", "#059669"),
    "PRÓXIMO": ("#FEF3C7", "#B45309"),
    "FINALIZADO": ("#E2E8F0", "#64748B"),
    "PENDIENTE": ("#E0E7FF", "#4338CA"),
    "HECHA": ("#D1FAE5", "#059669"),
}

INTERVAL_OPTIONS = [
    ("5 min", 5),
    ("10 min", 10),
    ("15 min", 15),
    ("30 min", 30),
    ("1 hora", 60),
    ("2 horas", 120),
    ("Desactivado", 0),
]


def uid():
    return uuid.uuid4().hex[:8]


def tomin(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def fmt12(value) -> str:
    """'15:00' (o minutos del día) -> '3:00 PM'."""
    m = tomin(value) if isinstance(value, str) else int(value)
    h, mm = divmod(m, 60)
    return f"{(h % 12) or 12}:{mm:02d} {'AM' if h < 12 else 'PM'}"


def segs(ev):
    """Tramos (inicio, fin) en minutos del día. Soporta eventos que cruzan la medianoche."""
    s, e = tomin(ev["start"]), tomin(ev["end"])
    if e > s:
        return [(s, e)]
    if e < s:
        return [(s, 1440), (0, e)]
    return [(s, s + 1)]


def duration_min(ev) -> int:
    s, e = tomin(ev["start"]), tomin(ev["end"])
    return (e - s) % 1440 or 1


def event_status(ev, nowm: int) -> str:
    for s, e in segs(ev):
        if s <= nowm < e:
            return "EN CURSO"
    return "PRÓXIMO" if tomin(ev["start"]) > nowm else "FINALIZADO"


def song_duration(path) -> str:
    if MP3 and path:
        try:
            secs = int(MP3(path).info.length)
            return f"{secs // 60}:{secs % 60:02d}"
        except Exception:
            pass
    return "--:--"


# ----------------------------------------------------------------------------
# Frases motivadoras
# ----------------------------------------------------------------------------
PACKS = [
    {
        "name": "Disciplina y Foco", "tag": "Diario", "icon": ft.Icons.TRACK_CHANGES,
        "color": "#4F46E5", "bg": "#E0E7FF",
        "quotes": [
            ("Primero dite a ti mismo qué quieres ser; después haz lo que tengas que hacer.", "Epicteto"),
            ("Un viaje de mil millas comienza con un solo paso.", "Lao Tse"),
            ("No importa lo lento que vayas, siempre que no te detengas.", "Confucio (atribuida)"),
            ("Mientras aplazamos la vida, la vida se pasa.", "Séneca"),
            ("Somos lo que hacemos repetidamente. La excelencia, entonces, es un hábito.", "Will Durant"),
            ("Si algo es humanamente posible, piensa que también está a tu alcance.", "Marco Aurelio"),
        ],
    },
    {
        "name": "Productividad", "tag": "Enfoque", "icon": ft.Icons.BOLT,
        "color": "#2563EB", "bg": "#DBEAFE",
        "quotes": [
            ("No es que tengamos poco tiempo, sino que perdemos mucho.", "Séneca"),
            ("Si no sabes a qué puerto te diriges, ningún viento te será favorable.", "Séneca"),
            ("Haz cada acto de tu vida como si fuera el último.", "Marco Aurelio"),
            ("Quien domina el comienzo, tiene medio camino hecho.", "Horacio"),
            ("Lo que se hace con prisa se hace mal; hazlo con calma y con constancia.", "Lao Tse"),
            ("La naturaleza no se apresura, y sin embargo todo se cumple.", "Lao Tse"),
        ],
    },
    {
        "name": "Deporte & Fitness", "tag": "Energía", "icon": ft.Icons.FITNESS_CENTER,
        "color": "#059669", "bg": "#D1FAE5",
        "quotes": [
            ("Mente sana en cuerpo sano.", "Juvenal"),
            ("La fortuna ayuda a los audaces.", "Virgilio"),
            ("El obstáculo se convierte en el camino.", "Marco Aurelio"),
            ("No nos atrevemos porque las cosas son difíciles; son difíciles porque no nos atrevemos.", "Séneca"),
            ("Ningún hombre tiene derecho a ser aficionado en el entrenamiento de su cuerpo.", "Sócrates"),
            ("Nadie sabe de qué es capaz hasta que lo intenta.", "Publilio Siro"),
        ],
    },
    {
        "name": "Paz Interior", "tag": "Anti-estrés", "icon": ft.Icons.CIRCLE_OUTLINED,
        "color": "#7C3AED", "bg": "#EDE9FE",
        "quotes": [
            ("No son las cosas las que nos perturban, sino los juicios que hacemos sobre ellas.", "Epicteto"),
            ("Sufrimos más en la imaginación que en la realidad.", "Séneca"),
            ("Tienes poder sobre tu mente, no sobre los acontecimientos. Entiéndelo y hallarás la fuerza.", "Marco Aurelio"),
            ("Conocer a los demás es sabiduría; conocerse a uno mismo es iluminación.", "Lao Tse"),
            ("Somos lo que pensamos; todo lo que somos surge con nuestros pensamientos.", "Buda"),
            ("La felicidad de tu vida depende de la calidad de tus pensamientos.", "Marco Aurelio"),
        ],
    },
]

# ----------------------------------------------------------------------------
# Persistencia con archivo local (.json)
# ----------------------------------------------------------------------------
DATA_FILE = "datos_habitos.json"


def default_data():
    return {
        "events": [
            {"id": uid(), "name": "Ejercicio Rutina", "start": "15:00", "end": "16:30",
             "details": "Rutina de cardio e hipertrofia", "color": PALETTE[0], "songs": []},
            {"id": uid(), "name": "Lectura y Estudio", "start": "19:00", "end": "21:00",
             "details": "Capítulo 4 del libro de hábitos", "color": PALETTE[1], "songs": []},
            {"id": uid(), "name": "Meditación Matutina", "start": "06:30", "end": "07:00",
             "details": "Respiración guiada", "color": PALETTE[3], "songs": []},
        ],
        "tasks": [
            {"id": uid(), "name": "Comprar insumos de oficina", "time": "18:00", "details": "", "done": False},
        ],
        "packs": ["Disciplina y Foco"],
        "quote_interval": 15,
    }


def load_data(page: ft.Page):
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                d = json.load(f)
                base = default_data()
                for k in base:
                    d.setdefault(k, base[k])
                return d
        except Exception as ex:
            print("Error al cargar desde archivo:", ex)
    return default_data()


def save_data(page: ft.Page, data):
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    except Exception as ex:
        print("Error al guardar en archivo:", ex)


# ----------------------------------------------------------------------------
# Dibujo del reloj
# ----------------------------------------------------------------------------
def clock_shapes(now: dt.datetime, events, size: float):
    c = size / 2
    R = size / 2 - 8
    TAU = 2 * math.pi
    shapes = [
        cv.Circle(c, c, R + 4, ft.Paint(color=BORDER, style=ft.PaintingStyle.STROKE, stroke_width=4)),
        cv.Circle(c, c, R, ft.Paint(color="white", style=ft.PaintingStyle.FILL)),
    ]

    half0 = 720 if now.hour >= 12 else 0
    layers = []
    for ev in events:
        for s, e in segs(ev):
            a, b = max(s, half0), min(e, half0 + 720)
            if b > a:
                layers.append([a - half0, b - half0, ev["color"], 0])
    layers.sort(key=lambda x: x[0])
    lane_ends = []
    for lay in layers:
        for i, end in enumerate(lane_ends):
            if end <= lay[0]:
                lane_ends[i] = lay[1]
                lay[3] = i
                break
        else:
            lane_ends.append(lay[1])
            lay[3] = len(lane_ends) - 1
    for a, b, color, lane in sorted(layers, key=lambda x: x[3]):
        r = R * (1 - 0.16 * lane)
        shapes.append(cv.Arc(
            c - r, c - r, 2 * r, 2 * r,
            start_angle=a / 720 * TAU - math.pi / 2,
            sweep_angle=(b - a) / 720 * TAU,
            use_center=True,
            paint=ft.Paint(color=color, style=ft.PaintingStyle.FILL),
        ))

    for i in range(60):
        ang = i / 60 * TAU - math.pi / 2
        long_tick = i % 5 == 0
        r1 = R - (9 if long_tick else 5)
        shapes.append(cv.Line(
            c + r1 * math.cos(ang), c + r1 * math.sin(ang),
            c + R * math.cos(ang), c + R * math.sin(ang),
            ft.Paint(color="#94A3B8" if long_tick else "#CBD5E1", stroke_width=2 if long_tick else 1),
        ))
    for n in range(1, 13):
        ang = n / 12 * TAU - math.pi / 2
        shapes.append(cv.Text(
            c + R * 0.78 * math.cos(ang), c + R * 0.78 * math.sin(ang), str(n),
            ft.TextStyle(size=13, weight=ft.FontWeight.BOLD, color="#334155"),
            alignment=ft.Alignment.CENTER,
        ))

    def hand(angle, length, width, color):
        return cv.Line(
            c, c, c + length * math.cos(angle), c + length * math.sin(angle),
            ft.Paint(color=color, stroke_width=width, stroke_cap=ft.StrokeCap.ROUND),
        )

    h_ang = ((now.hour % 12) + now.minute / 60) / 12 * TAU - math.pi / 2
    m_ang = (now.minute + now.second / 60) / 60 * TAU - math.pi / 2
    s_ang = now.second / 60 * TAU - math.pi / 2
    shapes += [
        hand(h_ang, R * 0.50, 5, INK),
        hand(m_ang, R * 0.78, 4, INK),
        hand(s_ang, R * 0.72, 2, "#EF4444"),
        cv.Circle(c, c, 6, ft.Paint(color=INK, style=ft.PaintingStyle.FILL)),
        cv.Circle(c, c, 2.5, ft.Paint(color="white", style=ft.PaintingStyle.FILL)),
    ]
    return shapes


# ----------------------------------------------------------------------------
# Aplicación Principal
# ----------------------------------------------------------------------------
def main(page: ft.Page):
    page.title = "Hábitos"
    page.bgcolor = "#F8FAFC"
    page.padding = 0
    page.theme_mode = ft.ThemeMode.LIGHT
    try:
        page.window.width, page.window.height = 400, 820
    except Exception:
        pass

    data = load_data(page)
    CLOCK = 270
    state = {
        "sheet": None,
        "last_min": -1,
        "notified": set(),
        "dismissed": set(),
        "pick_event": None,
        "last_quote_min": int(time.time() // 60),
    }
    player = {"audio": None, "path": None, "playing": False}

    NEW_FLET = hasattr(page, "show_dialog")

    def open_dialog(ctrl):
        if NEW_FLET:
            page.show_dialog(ctrl)
        else:
            page.open(ctrl)

    def close_dialog(ctrl=None):
        if NEW_FLET:
            page.pop_dialog()
        else:
            page.close(ctrl)

    def add_service(ctrl):
        (page.services if NEW_FLET else page.overlay).append(ctrl)

    def remove_service(ctrl):
        (page.services if NEW_FLET else page.overlay).remove(ctrl)

    def run_maybe_async(result):
        if inspect.iscoroutine(result):
            async def _w():
                await result
            page.run_task(_w)

    def snack(msg):
        open_dialog(ft.SnackBar(ft.Text(msg)))

    def chip(label):
        bg, fg = STATUS_STYLE.get(label, ("#E2E8F0", "#64748B"))
        return ft.Container(
            ft.Text(label, size=10, weight=ft.FontWeight.BOLD, color=fg),
            bgcolor=bg, padding=ft.Padding.symmetric(horizontal=10, vertical=4), border_radius=20,
        )

    def pill(label, icon, bg, fg, on_click, expand=1):
        return ft.Container(
            ft.Row([ft.Icon(icon, color=fg, size=18), ft.Text(label, color=fg, weight=ft.FontWeight.W_600)],
                   alignment=ft.MainAxisAlignment.CENTER, spacing=6),
            bgcolor=bg, border_radius=16, padding=ft.Padding.symmetric(vertical=16),
            on_click=on_click, expand=expand, ink=True,
        )

    def card(content, **kw):
        return ft.Container(content, bgcolor="white", border=ft.Border.all(1, BORDER),
                            border_radius=14, padding=12, **kw)

    def close_sheet(e=None):
        if state["sheet"] is not None:
            try:
                close_dialog(state["sheet"])
            except Exception:
                pass
            state["sheet"] = None

    def show_sheet(content, height=None):
        close_sheet()
        body = ft.Container(content, padding=ft.Padding.only(left=20, right=20, top=4, bottom=30),
                            bgcolor="white", height=height)
        try:
            bs = ft.BottomSheet(content=body, scrollable=True, show_drag_handle=True, bgcolor="white")
        except TypeError:
            bs = ft.BottomSheet(content=body, is_scroll_controlled=True, show_drag_handle=True, bgcolor="white")
        bs.on_dismiss = lambda e, b=bs: state.update(sheet=None) if state["sheet"] is b else None
        state["sheet"] = bs
        open_dialog(bs)

    def sheet_header(title, subtitle, icon=None, icon_bg=None, icon_color=None):
        left = []
        if icon:
            left.append(ft.Container(ft.Icon(icon, color=icon_color, size=22), bgcolor=icon_bg,
                                     border_radius=12, padding=8))
        left.append(ft.Column([ft.Text(title, size=19, weight=ft.FontWeight.BOLD, color=INK),
                               ft.Text(subtitle, size=12, color=GREY)], spacing=0, expand=True))
        return ft.Row(left + [ft.IconButton(ft.Icons.CLOSE, on_click=close_sheet, icon_color="#475569",
                                            bgcolor="#F1F5F9")],
                      vertical_alignment=ft.CrossAxisAlignment.CENTER, spacing=10)

    # UI del reloj
    canvas = cv.Canvas(shapes=[], width=CLOCK, height=CLOCK)
    digital = ft.Text("00:00:00 AM", size=32, weight=ft.FontWeight.W_800, color=INK)
    banner_title = ft.Text("", size=14, weight=ft.FontWeight.BOLD, color=INK)
    banner_sub = ft.Text("", size=12, color=GREY)
    banner = ft.Container(
        ft.Row([
            ft.Container(ft.Icon(ft.Icons.CHECK, color=INDIGO, size=18), bgcolor="#E0E7FF",
                         border_radius=20, padding=8),
            ft.Column([banner_title, banner_sub], spacing=0, expand=True),
        ], spacing=12),
        bgcolor="white", border=ft.Border.all(1.5, "#38BDF8"), border_radius=14,
    )
    upcoming_col = ft.Column(spacing=8)

    def banner_dismiss(e):
        for ev in data["events"]:
            if event_status(ev, now_min()) == "EN CURSO":
                state["dismissed"].add(ev["id"])
        banner.visible = False
        banner.update()

    banner.on_click = banner_dismiss

    def now_min():
        n = dt.datetime.now()
        return n.hour * 60 + n.minute

    # ---------- Modal de Detalle de Evento ----------
    def show_event_details(ev):
        nm = now_min()
        st = event_status(ev, nm)
        songs_count = len(ev.get("songs", []))

        def delete_and_close(e):
            if ev in data["events"]:
                data["events"].remove(ev)
            close_dialog(dlg)
            refresh_all()
            snack("Evento eliminado 🗑️")

        def edit_and_close(e):
            close_dialog(dlg)
            form_event(target_event=ev)

        dlg = ft.AlertDialog(
            title=ft.Row([
                ft.Container(width=14, height=14, bgcolor=ev["color"], border_radius=7),
                ft.Text(ev["name"], weight=ft.FontWeight.BOLD, size=18, color=INK, expand=True),
                chip(st)
            ], spacing=10),
            content=ft.Column([
                ft.Row([
                    ft.Icon(ft.Icons.ACCESS_TIME, size=18, color=GREY),
                    ft.Text(f"{fmt12(ev['start'])} - {fmt12(ev['end'])} ({duration_min(ev)} min)", size=13, color=INK, weight=ft.FontWeight.W_500)
                ], spacing=8),
                ft.Row([
                    ft.Icon(ft.Icons.MUSIC_NOTE, size=18, color=GREY),
                    ft.Text(f"{songs_count} canción(es) vinculada(s)", size=13, color=INK)
                ], spacing=8),
                ft.Divider(height=1, color=BORDER),
                ft.Text("Detalles / Notas:", size=11, weight=ft.FontWeight.BOLD, color=GREY),
                ft.Text(ev.get("details") if ev.get("details") else "Sin detalles adicionales.", size=13, color=INK, italic=not bool(ev.get("details"))),
            ], tight=True, spacing=12),
            actions=[
                ft.OutlinedButton("Eliminar evento", icon=ft.Icons.DELETE_OUTLINE, icon_color="#EF4444",
                                  style=ft.ButtonStyle(color="#EF4444"), on_click=delete_and_close),
                ft.FilledButton("Editar evento", icon=ft.Icons.EDIT,
                                style=ft.ButtonStyle(bgcolor=INDIGO), on_click=edit_and_close),
            ],
            actions_alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        )
        open_dialog(dlg)

    def refresh_upcoming():
        nm = now_min()
        rows = []
        for ev in sorted(data["events"], key=lambda x: tomin(x["start"])):
            st = event_status(ev, nm)
            if st == "FINALIZADO":
                continue
            rows.append(card(
                ft.Row([
                    ft.Container(width=5, height=26, bgcolor=ev["color"], border_radius=3),
                    ft.Column([ft.Text(ev["name"], weight=ft.FontWeight.BOLD, size=14, color=INK),
                               ft.Text(f"{fmt12(ev['start'])} - {fmt12(ev['end'])}", size=11, color=GREY)],
                              spacing=0, expand=True),
                    chip(st),
                ], spacing=10),
                on_click=lambda e, target_ev=ev: show_event_details(target_ev),
                ink=True
            ))
        if not rows:
            rows = [ft.Text("No tienes eventos pendientes para hoy 🎉", size=13, color=GREY)]
        upcoming_col.controls = rows[:4]

    def update_banner(now):
        nm = now.hour * 60 + now.minute
        active = [e for e in data["events"]
                  if event_status(e, nm) == "EN CURSO" and e["id"] not in state["dismissed"]]
        if active:
            ev = active[0]
            banner_title.value = f"{fmt12(ev['start'])} • Hábito en curso"
            banner_sub.value = f"Es hora de: {ev['name']} ({duration_min(ev)} min)"
            banner.visible = True
        else:
            banner.visible = False

    def random_quote():
        names = data["packs"] or [p["name"] for p in PACKS]
        pool = [(q, a, p) for p in PACKS if p["name"] in names for q, a in p["quotes"]]
        q, a, _ = random_choice(pool or [(q, a, p) for p in PACKS for q, a in p["quotes"]])
        return q, a

    def show_quote(e=None):
        q, a = random_quote()
        dlg = ft.AlertDialog(
            title=ft.Text("✨ Tu frase motivadora"),
            content=ft.Column([ft.Text(f"“{q}”", size=17, italic=True, color=INK),
                               ft.Text(f"— {a}", size=13, color=GREY, weight=ft.FontWeight.BOLD)],
                              tight=True, spacing=12),
            actions=[ft.TextButton("Otra frase", on_click=lambda ev: (close_dialog(dlg), show_quote())),
                     ft.TextButton("Cerrar", on_click=lambda ev: close_dialog(dlg))],
        )
        open_dialog(dlg)

    # ---------- Triggers de Notificación con Sonido ----------
    def trigger_habit(ev):
        q, a = random_quote()

        # Reproducir canción asignada o tono de Campana por defecto
        if ev.get("songs") and fta:
            play_path(ev["songs"][0]["path"])
        elif fta:
            play_path("/Campana.mp3")

        def on_stop_music(e):
            stop_audio()
            e.control.disabled = True
            e.control.text = "Música detenida"
            e.control.update()

        actions = []
        if ev.get("songs") and fta:
            actions.append(
                ft.TextButton("Detener música", icon=ft.Icons.STOP, icon_color="#EF4444", on_click=on_stop_music)
            )

        actions.append(
            ft.FilledButton("¡Comenzar!", on_click=lambda e: close_dialog(dlg), style=ft.ButtonStyle(bgcolor=INDIGO))
        )

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Row([
                ft.Icon(ft.Icons.ALARM, color=INDIGO, size=28),
                ft.Text("¡Hora de tu Actividad!", weight=ft.FontWeight.BOLD, color=INK)
            ], spacing=10),
            content=ft.Column([
                ft.Text(f"Es momento de: {ev['name']}", size=18, weight=ft.FontWeight.BOLD, color=INDIGO),
                ft.Text(f"Duración: {duration_min(ev)} min ({fmt12(ev['start'])} - {fmt12(ev['end'])})", size=13, color=GREY),
                ft.Divider(height=1),
                ft.Text(f"“{q}”", size=15, italic=True, color=INK),
                ft.Text(f"— {a}", size=12, color=GREY, weight=ft.FontWeight.BOLD),
            ], tight=True, spacing=10),
            actions=actions,
            actions_alignment=ft.MainAxisAlignment.SPACE_BETWEEN if ev.get("songs") else ft.MainAxisAlignment.CENTER,
        )
        open_dialog(dlg)

    def trigger_task_notification(t):
        # Reproducir sonido de Silbido para la tarea
        if fta:
            play_path("/Silbido.mp3")

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Row([
                ft.Icon(ft.Icons.CHECK_CIRCLE_OUTLINE, color=INDIGO, size=28),
                ft.Text("¡Recordatorio de Tarea!", weight=ft.FontWeight.BOLD, color=INK)
            ], spacing=10),
            content=ft.Column([
                ft.Text(f"Es hora de realizar: {t['name']}", size=16, weight=ft.FontWeight.BOLD, color=INDIGO),
                ft.Text(f"Hora programada: {fmt12(t['time'])}", size=13, color=GREY),
                ft.Text(t.get("details", ""), size=12, color=INK) if t.get("details") else ft.Container(),
            ], tight=True, spacing=10),
            actions=[
                ft.FilledButton("Entendido", on_click=lambda e: close_dialog(dlg), style=ft.ButtonStyle(bgcolor=INDIGO))
            ],
            actions_alignment=ft.MainAxisAlignment.CENTER,
        )
        open_dialog(dlg)

    def update_clock():
        now = dt.datetime.now()
        canvas.shapes = clock_shapes(now, data["events"], CLOCK)
        digital.value = now.strftime("%I:%M:%S %p")
        now_total_min = int(time.time() // 60)

        # Frases automáticas periódicas
        interval = data.get("quote_interval", 15)
        if interval > 0 and data.get("packs"):
            last_q = state.get("last_quote_min", now_total_min)
            if now_total_min - last_q >= interval:
                state["last_quote_min"] = now_total_min
                show_quote()

        if now.minute != state["last_min"]:
            state["last_min"] = now.minute
            nm = now.hour * 60 + now.minute

            # Notificar Eventos
            for ev in data["events"]:
                key = f"ev-{ev['id']}-{now.date()}"
                if tomin(ev["start"]) == nm and key not in state["notified"]:
                    state["notified"].add(key)
                    state["dismissed"].discard(ev["id"])
                    trigger_habit(ev)

            # Notificar Tareas
            for t in data["tasks"]:
                if t.get("time") and not t.get("done"):
                    key = f"task-{t['id']}-{now.date()}"
                    if tomin(t["time"]) == nm and key not in state["notified"]:
                        state["notified"].add(key)
                        trigger_task_notification(t)

            refresh_upcoming()
        update_banner(now)
        page.update()

    async def ticker():
        while True:
            await asyncio.sleep(1)
            try:
                update_clock()
            except Exception:
                break

    def refresh_all():
        save_data(page, data)
        refresh_upcoming()
        update_clock()

    # Audio
    def stop_audio():
        a = player["audio"]
        if a is not None:
            try:
                run_maybe_async(a.pause())
                remove_service(a)
            except Exception:
                pass
        player.update(audio=None, path=None, playing=False)

    def on_audio_state(e):
        if str(getattr(e, "state", None) or getattr(e, "data", None)).lower().endswith("completed"):
            player["playing"] = False
            if state.get("music_open"):
                render_music()

    def play_path(path):
        if fta is None:
            snack("Instala flet-audio para reproducir música")
            return
        if not path:
            return
        if player["audio"] is not None and player["path"] == path:
            if player["playing"]:
                run_maybe_async(player["audio"].pause())
                player["playing"] = False
            else:
                run_maybe_async(player["audio"].resume())
                player["playing"] = True
            return
        stop_audio()
        try:
            audio = fta.Audio(src=path, autoplay=True, on_state_changed=on_audio_state)
        except TypeError:
            audio = fta.Audio(src=path, autoplay=True, on_state_change=on_audio_state)
        add_service(audio)
        page.update()
        player.update(audio=audio, path=path, playing=True)

    # Selector MP3
    def handle_files(files):
        ev = next((x for x in data["events"] if x["id"] == state["pick_event"]), None)
        if not files or ev is None:
            return
        added = 0
        for f in files:
            if not f.path or not f.name.lower().endswith(".mp3"):
                continue
            ev["songs"].append({"name": os.path.splitext(f.name)[0], "path": f.path})
            added += 1
        if added:
            save_data(page, data)
            render_music()

    if NEW_FLET:
        picker = ft.FilePicker()
    else:
        picker = ft.FilePicker(on_result=lambda e: handle_files(e.files))
    add_service(picker)

    async def pick_async():
        files = await picker.pick_files(dialog_title="Elige tus audios MP3", allow_multiple=True,
                                        file_type=ft.FilePickerFileType.CUSTOM, allowed_extensions=["mp3"])
        handle_files(files)

    def add_song(event_id):
        state["pick_event"] = event_id
        if NEW_FLET:
            page.run_task(pick_async)
        else:
            picker.pick_files(dialog_title="Elige tus audios MP3", allow_multiple=True,
                              file_type=ft.FilePickerFileType.CUSTOM, allowed_extensions=["mp3"])

    # Hojas desplegables
    music_col = ft.Column(spacing=10, scroll=ft.ScrollMode.AUTO, expand=True)

    def render_music():
        controls = []
        for ev in sorted(data["events"], key=lambda x: tomin(x["start"])):
            n = len(ev["songs"])
            label = "Sin música" if n == 0 else ("1 canción" if n == 1 else f"{n} canciones")
            color = ev["color"]
            controls.append(ft.Container(
                ft.Row([ft.Container(width=5, height=20, bgcolor=color, border_radius=3),
                        ft.Text(ev["name"], weight=ft.FontWeight.BOLD, color=INK, expand=True),
                        ft.Text(label, size=11, color=color, weight=ft.FontWeight.W_600)], spacing=8),
                bgcolor=ft.Colors.with_opacity(0.10, color), border=ft.Border.all(1, ft.Colors.with_opacity(0.4, color)),
                border_radius=12, padding=12))
            for s in ev["songs"]:
                is_playing = player["path"] == s["path"] and player["playing"]
                controls.append(card(ft.Row([
                    ft.IconButton(ft.Icons.PAUSE if is_playing else ft.Icons.PLAY_ARROW,
                                  icon_color="white" if is_playing else GREY,
                                  bgcolor=INDIGO if is_playing else "#F1F5F9", icon_size=18,
                                  on_click=lambda e, p=s["path"]: (play_path(p), render_music())),
                    ft.Column([ft.Text(s["name"], size=13, weight=ft.FontWeight.BOLD, color=INK,
                                       max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                               ft.Text("Descargado • MP3", size=10, color=GREY)], spacing=0, expand=True),
                    ft.Text(song_duration(s["path"]), size=11, color=GREY),
                    ft.IconButton(ft.Icons.DELETE_OUTLINE, icon_size=18, icon_color="#94A3B8",
                                  on_click=lambda e, ev=ev, s=s: remove_song(ev, s)),
                ], spacing=4, vertical_alignment=ft.CrossAxisAlignment.CENTER)))
            controls.append(ft.Container(
                ft.Text("+ Agregar Canción", color=INDIGO, weight=ft.FontWeight.W_600, size=13),
                alignment=ft.Alignment.CENTER, padding=12, border_radius=12, ink=True,
                border=ft.Border.all(1.5, INDIGO if n else "#C7D2FE"),
                on_click=lambda e, i=ev["id"]: add_song(i)))
        if not data["events"]:
            controls.append(ft.Text("Primero crea un evento para vincularle música.", color=GREY))
        music_col.controls = controls
        try:
            music_col.update()
        except Exception:
            pass

    def remove_song(ev, s):
        if player["path"] == s["path"]:
            stop_audio()
        if s in ev["songs"]:
            ev["songs"].remove(s)
        save_data(page, data)
        render_music()

    def show_music(e=None):
        state["music_open"] = True
        render_music()
        show_sheet(ft.Column([
            sheet_header("Música por Actividad", "Canciones vinculadas a tus hábitos",
                         ft.Icons.MUSIC_NOTE, "#E0E7FF", INDIGO),
            music_col,
        ], spacing=14), height=page.height * 0.78)

    # Motivación e Intervalos
    packs_col = ft.Column(spacing=10)
    interval_row = ft.Row(wrap=True, spacing=8)

    def set_quote_interval(val):
        data["quote_interval"] = val
        state["last_quote_min"] = int(time.time() // 60)
        save_data(page, data)
        render_interval_chips()
        snack(f"Frecuencia actualizada: {next(label for label, m in INTERVAL_OPTIONS if m == val)}")

    def render_interval_chips():
        current = data.get("quote_interval", 15)
        chips = []
        for label, val in INTERVAL_OPTIONS:
            selected = current == val
            chips.append(ft.Container(
                ft.Text(label, size=11, weight=ft.FontWeight.BOLD if selected else ft.FontWeight.NORMAL,
                        color="white" if selected else INK),
                bgcolor=INDIGO if selected else "#F1F5F9",
                border_radius=12,
                padding=ft.Padding.symmetric(horizontal=10, vertical=6),
                on_click=lambda e, v=val: set_quote_interval(v),
                ink=True
            ))
        interval_row.controls = chips
        try:
            interval_row.update()
        except Exception:
            pass

    def toggle_pack(name):
        if name in data["packs"]:
            data["packs"].remove(name)
        else:
            data["packs"].append(name)
        save_data(page, data)
        render_packs()

    def pack_card(p):
        active = p["name"] in data["packs"]
        fg = "white" if active else INK
        sub = "#C7D2FE" if active else GREY
        top = [ft.Container(ft.Icon(p["icon"], color=p["color"], size=18), bgcolor=p["bg"],
                            border_radius=10, padding=7)]
        if active:
            top = [ft.Container(ft.Text("ACTIVO", size=9, weight=ft.FontWeight.BOLD, color="white"),
                                bgcolor="#6366F1", border_radius=8,
                                padding=ft.Padding.symmetric(horizontal=8, vertical=3))]
        return ft.Container(
            ft.Column([
                ft.Row(top + [ft.Container(expand=True),
                              ft.Icon(ft.Icons.CHECK_CIRCLE, color="white", size=18, visible=active)]),
                ft.Text(p["name"], size=13, weight=ft.FontWeight.BOLD, color=fg),
                ft.Text(f"{len(p['quotes'])} Frases • {p['tag']}", size=10, color=sub),
            ], spacing=6),
            bgcolor=INDIGO if active else "white", border=ft.Border.all(1, INDIGO if active else BORDER),
            border_radius=14, padding=12, expand=1, ink=True,
            on_click=lambda e, n=p["name"]: toggle_pack(n))

    def render_packs():
        rows = []
        for i in range(0, len(PACKS), 2):
            rows.append(ft.Row([pack_card(PACKS[i]), pack_card(PACKS[i + 1])], spacing=10))
        packs_col.controls = rows
        try:
            packs_col.update()
        except Exception:
            pass

    def show_motivation(e=None):
        render_interval_chips()
        render_packs()
        show_sheet(ft.Column([
            sheet_header("Motivación", "Activa paquetes y frecuencia de frases",
                         ft.Icons.WATER_DROP_OUTLINED, "#FEF3C7", "#D97706"),
            ft.Column([
                ft.Text("Frecuencia de frases automáticas:", size=12, weight=ft.FontWeight.BOLD, color=GREY),
                interval_row,
                ft.Divider(height=1, color=BORDER),
                ft.Text("Paquetes de frases activos:", size=12, weight=ft.FontWeight.BOLD, color=GREY),
                packs_col,
                ft.FilledButton("Dame una frase ahora", icon=ft.Icons.AUTO_AWESOME,
                                on_click=lambda e: (close_sheet(), show_quote()),
                                style=ft.ButtonStyle(bgcolor=INDIGO)),
            ], scroll=ft.ScrollMode.AUTO, spacing=14, expand=True),
        ], spacing=14), height=page.height * 0.85)

    def time_button(label, getter, setter):
        btn = ft.OutlinedButton(f"{label}: {fmt12(getter())}", icon=ft.Icons.ACCESS_TIME)

        def on_pick(e):
            t = e.control.value
            setter(t.strftime("%H:%M"))
            btn.text = f"{label}: {fmt12(getter())}"
            btn.update()

        def open_picker(e):
            h, m = map(int, getter().split(":"))
            open_dialog(ft.TimePicker(value=dt.time(h, m), on_change=on_pick,
                                      help_text="Selecciona la hora", cancel_text="Cancelar",
                                      confirm_text="Aceptar"))

        btn.on_click = open_picker
        return btn

    def form_event(e=None, target_event=None):
        is_edit = target_event is not None
        if is_edit:
            f = {"start": target_event["start"], "end": target_event["end"], "color": target_event["color"]}
            default_name = target_event["name"]
            default_details = target_event.get("details", "")
        else:
            f = {"start": dt.datetime.now().strftime("%H:00"), "end": "", "color": PALETTE[len(data["events"]) % 6]}
            f["end"] = f"{(tomin(f['start']) // 60 + 1) % 24:02d}:00"
            default_name = ""
            default_details = ""

        name = ft.TextField(value=default_name, hint_text="Ej. Entrenamiento de cardio", border_radius=12, autofocus=True)
        details = ft.TextField(value=default_details, hint_text="Detalles (opcional)", multiline=True, min_lines=2, border_radius=12)
        colors_row = ft.Row(spacing=10)

        def render_colors():
            colors_row.controls = [ft.Container(
                width=30, height=30, bgcolor=c, border_radius=15,
                border=ft.Border.all(3, INK) if c == f["color"] else None,
                on_click=lambda e, c=c: (f.update(color=c), render_colors())) for c in PALETTE]
            try:
                colors_row.update()
            except Exception:
                pass

        render_colors()

        def save(e):
            if not name.value.strip():
                name.error_text = "Escribe un nombre"
                name.update()
                return
            if is_edit:
                target_event["name"] = name.value.strip()
                target_event["start"] = f["start"]
                target_event["end"] = f["end"]
                target_event["details"] = details.value or ""
                target_event["color"] = f["color"]
                msg = "Evento actualizado ✏️"
            else:
                data["events"].append({"id": uid(), "name": name.value.strip(), "start": f["start"],
                                       "end": f["end"], "details": details.value or "",
                                       "color": f["color"], "songs": []})
                msg = "Evento guardado ✅"
            close_sheet()
            refresh_all()
            snack(msg)

        sheet_title = "Editar evento" if is_edit else "Nuevo evento"
        sheet_sub = "Modifica los datos del hábito" if is_edit else "Define el bloque de tiempo de tu hábito"

        show_sheet(ft.Column([
            sheet_header(sheet_title, sheet_sub),
            name,
            ft.Row([time_button("Inicio", lambda: f["start"], lambda v: f.update(start=v)),
                    time_button("Fin", lambda: f["end"], lambda v: f.update(end=v))],
                   wrap=True),
            details,
            ft.Text("Color en el reloj", size=12, color=GREY),
            colors_row,
            ft.FilledButton("Guardar cambios" if is_edit else "Guardar evento", on_click=save, height=50,
                            style=ft.ButtonStyle(bgcolor=INDIGO, shape=ft.RoundedRectangleBorder(radius=14))),
        ], spacing=14, tight=True, scroll=ft.ScrollMode.AUTO))

    def form_task(e=None):
        f = {"time": dt.datetime.now().strftime("%H:%M")}
        name = ft.TextField(hint_text="Ej. Comprar cuadernos", border_radius=12, autofocus=True)
        details = ft.TextField(hint_text="Detalles (opcional)", multiline=True, min_lines=2, border_radius=12)
        tbtn = ft.OutlinedButton(f"Hora: {fmt12(f['time'])}", icon=ft.Icons.ACCESS_TIME)

        def on_pick(ev):
            f["time"] = ev.control.value.strftime("%H:%M")
            tbtn.text = f"Hora: {fmt12(f['time'])}"
            tbtn.update()

        def open_task_picker(ev):
            h, m = map(int, f["time"].split(":"))
            open_dialog(ft.TimePicker(value=dt.time(h, m), on_change=on_pick, help_text="Hora del recordatorio"))

        tbtn.on_click = open_task_picker

        def save(ev):
            if not name.value.strip():
                name.error_text = "Escribe un nombre"
                name.update()
                return
            data["tasks"].append({"id": uid(), "name": name.value.strip(), "time": f["time"],
                                  "details": details.value or "", "done": False})
            close_sheet()
            refresh_all()
            snack("Tarea guardada ✅")

        show_sheet(ft.Column([
            sheet_header("Nueva tarea", "Recordatorio fuera del reloj"),
            name, ft.Row([tbtn]), details,
            ft.FilledButton("Guardar tarea", on_click=save, height=50,
                            style=ft.ButtonStyle(bgcolor=INDIGO, shape=ft.RoundedRectangleBorder(radius=14))),
        ], spacing=14, tight=True, scroll=ft.ScrollMode.AUTO))

    def delete_event(ev):
        if ev in data["events"]:
            data["events"].remove(ev)
        refresh_all()
        show_activities()

    def delete_task(t):
        if t in data["tasks"]:
            data["tasks"].remove(t)
        refresh_all()
        show_activities()

    def toggle_task(t):
        t["done"] = not t["done"]
        refresh_all()
        show_activities()

    def show_activities(e=None):
        nm = now_min()
        rows = []
        for ev in sorted(data["events"], key=lambda x: tomin(x["start"])):
            rows.append(card(ft.Row([
                ft.Container(width=5, height=34, bgcolor=ev["color"], border_radius=3),
                ft.Column([ft.Text(ev["name"], weight=ft.FontWeight.BOLD, size=14, color=INK),
                           ft.Text(f"Evento • {fmt12(ev['start'])} - {fmt12(ev['end'])}", size=11, color=GREY)],
                          spacing=0, expand=True),
                chip(event_status(ev, nm)),
                ft.IconButton(ft.Icons.DELETE_OUTLINE, icon_size=18, icon_color="#94A3B8",
                              on_click=lambda e, ev=ev: delete_event(ev)),
            ], spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER)))
        for t in data["tasks"]:
            sub = "Tarea • " + (f"{fmt12(t['time'])}" if t.get("time") else "Para hoy")
            rows.append(card(ft.Row([
                ft.Icon(ft.Icons.CHECK_CIRCLE if t["done"] else ft.Icons.RADIO_BUTTON_UNCHECKED,
                        color="#059669" if t["done"] else "#94A3B8", size=20),
                ft.Column([ft.Text(t["name"], weight=ft.FontWeight.BOLD, size=14, color=INK,
                                   style=ft.TextStyle(decoration=ft.TextDecoration.LINE_THROUGH)
                                   if t["done"] else None),
                           ft.Text(sub, size=11, color=GREY)], spacing=0, expand=True),
                chip("HECHA" if t["done"] else "PENDIENTE"),
                ft.IconButton(ft.Icons.DELETE_OUTLINE, icon_size=18, icon_color="#94A3B8",
                              on_click=lambda e, t=t: delete_task(t)),
            ], spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                on_click=lambda e, t=t: toggle_task(t)))
        total = len(data["events"]) + len(data["tasks"])
        show_sheet(ft.Column([
            ft.Row([ft.Column([ft.Text("Todas las actividades", size=19, weight=ft.FontWeight.BOLD, color=INK),
                               ft.Text("Historial completo de eventos y tareas", size=12, color=GREY)],
                              spacing=0, expand=True),
                    ft.IconButton(ft.Icons.CLOSE, on_click=close_sheet, bgcolor="#F1F5F9")]),
            ft.Row([
                ft.FilledButton("Crear evento", icon=ft.Icons.ADD, on_click=form_event, expand=2, height=46,
                                style=ft.ButtonStyle(bgcolor=INDIGO)),
                ft.OutlinedButton("Crear tarea", icon=ft.Icons.CHECK_CIRCLE_OUTLINE, on_click=form_task,
                                  expand=2, height=46),
            ], spacing=10),
            ft.Divider(height=1, color=BORDER),
            ft.Text(f"ACTIVIDADES REGISTRADAS ({total})", size=11, weight=ft.FontWeight.BOLD, color=GREY),
            ft.Column(rows or [ft.Text("Aún no tienes actividades.", color=GREY)],
                      spacing=8, scroll=ft.ScrollMode.AUTO, expand=True),
        ], spacing=12), height=page.height * 0.78)

    # Vista principal
    page.add(ft.SafeArea(ft.Container(
        ft.Column([
            banner,
            ft.Container(canvas, alignment=ft.Alignment.CENTER, margin=ft.Margin.only(top=6)),
            ft.Column([digital, ft.Text("Hora actual sincronizada", size=12, color=GREY)],
                      spacing=0, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
            ft.Text("Próximos eventos", size=14, weight=ft.FontWeight.BOLD, color="#334155"),
            upcoming_col,
            ft.Row([
                ft.Container(ft.Text("✨ Motívame", color="#7E22CE", weight=ft.FontWeight.W_600),
                             bgcolor="#F3E8FF", border_radius=16, padding=ft.Padding.symmetric(vertical=18),
                             alignment=ft.Alignment.CENTER, on_click=show_motivation, expand=2, ink=True),
                pill("Crear", ft.Icons.ADD, INDIGO, "white", show_activities, expand=3),
                pill("Música", ft.Icons.MUSIC_NOTE, "#EEF2FF", INDIGO, show_music, expand=2),
            ], spacing=10),
        ], spacing=14, horizontal_alignment=ft.CrossAxisAlignment.CENTER, scroll=ft.ScrollMode.AUTO),
        padding=ft.Padding.symmetric(horizontal=18, vertical=12)), expand=True))

    refresh_upcoming()
    update_clock()
    page.run_task(ticker)


if __name__ == "__main__":
    ft.run(main)
