import tkinter as tk
import ctypes
 
from config import APP_TITLE
from ui.main_window import SistemaCadastrosApp, configurar_icone_janela
 
ERROR_ALREADY_EXISTS = 183
MUTEX_NOME = "Global\\ControleDiversosAppMutex"
_mutex_handle = None
 
def criar_mutex_unico():
    global _mutex_handle
 
    try:
        _mutex_handle = ctypes.windll.kernel32.CreateMutexW(None, False, MUTEX_NOME)
        ultimo_erro = ctypes.windll.kernel32.GetLastError()
 
        if ultimo_erro == ERROR_ALREADY_EXISTS:
            return False
 
        return True
    except Exception as e:
        print("Erro ao criar mutex de instância única:", e)
        return True
 
def ativar_janela_existente():
    try:
        user32 = ctypes.windll.user32
 
        hwnd = user32.FindWindowW(None, APP_TITLE)
 
        if hwnd:
            user32.ShowWindow(hwnd, 9)  # SW_RESTORE
            user32.SetForegroundWindow(hwnd)
    except Exception as e:
        print("Erro ao ativar janela existente:", e)

def main():
    if not criar_mutex_unico():
        ativar_janela_existente()
        return
 
    root = tk.Tk()

    # 🔥 MUITO IMPORTANTE: aplicar ícone antes de criar o app
    configurar_icone_janela(root)

    # 🔥 força o Windows reconhecer o ícone
    root.update_idletasks()

    app = SistemaCadastrosApp(root)

    root.mainloop()
 
if __name__ == "__main__":
    main()