from tkinter import ttk


def aplicar_estilos():
    style = ttk.Style()

    try:
        style.theme_use("clam")
    except Exception:
        pass

    style.configure("TFrame", background="#0b1220")
    style.configure(
        "TLabel",
        background="#0b1220",
        foreground="#f8fafc",
        font=("Segoe UI", 10),
    )

    style.configure(
        "Titulo.TLabel",
        background="#0b1220",
        foreground="#f8fafc",
        font=("Segoe UI", 21, "bold"),
    )

    style.configure(
        "Subtitulo.TLabel",
        background="#0b1220",
        foreground="#94a3b8",
        font=("Segoe UI", 10),
    )

    style.configure(
        "Secao.TLabel",
        background="#111827",
        foreground="#f8fafc",
        font=("Segoe UI", 12, "bold"),
    )

    style.configure(
        "TButton",
        font=("Segoe UI", 10, "bold"),
        padding=8,
        relief="flat",
        borderwidth=0,
    )

    style.map(
        "TButton",
        background=[
            ("active", "#1f2937"),
            ("pressed", "#111827"),
        ],
        foreground=[("!disabled", "#f8fafc")],
    )

    style.configure(
        "Primary.TButton",
        font=("Segoe UI", 10, "bold"),
        padding=9,
        borderwidth=0,
    )

    style.map(
        "Primary.TButton",
        background=[
            ("active", "#2563eb"),
            ("pressed", "#1d4ed8"),
            ("!disabled", "#3b82f6"),
        ],
        foreground=[("!disabled", "white")],
    )

    style.configure(
        "Success.TButton",
        font=("Segoe UI", 10, "bold"),
        padding=9,
    )

    style.map(
        "Success.TButton",
        background=[
            ("active", "#15803d"),
            ("!disabled", "#16a34a"),
        ],
        foreground=[("!disabled", "white")],
    )

    style.configure(
        "Vertical.TScrollbar",
        gripcount=0,
        background="#1f2937",
        darkcolor="#1f2937",
        lightcolor="#1f2937",
        troughcolor="#0b1220",
        bordercolor="#0b1220",
        arrowcolor="#94a3b8",
    )

    style.configure(
        "TSeparator",
        background="#1f2937",
    )