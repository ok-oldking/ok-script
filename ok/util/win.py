import ctypes


def is_admin():
    try:
        # Only Windows users with admin privileges can read the C drive directly
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False
