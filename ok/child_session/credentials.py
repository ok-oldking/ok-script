"""The child-session sign-in password, kept in Windows Credential Manager.

Credential Manager encrypts it for the current Windows user. ok-script never logs it.
"""

CRED_TARGET = 'ok-script/child-session/localhost'


def load():
    """``(user_name, password)`` or None."""
    import win32cred
    try:
        cred = win32cred.CredRead(CRED_TARGET, win32cred.CRED_TYPE_GENERIC)
    except Exception:
        return None
    blob = cred['CredentialBlob']
    password = blob.decode('utf-16-le') if isinstance(blob, bytes) else blob
    return cred['UserName'], password


def exists() -> bool:
    return load() is not None


def save(user_name: str, password: str) -> None:
    import win32cred
    win32cred.CredWrite({
        'Type': win32cred.CRED_TYPE_GENERIC,
        'TargetName': CRED_TARGET,
        'UserName': user_name,
        'CredentialBlob': password,
        'Persist': win32cred.CRED_PERSIST_LOCAL_MACHINE,
        'Comment': 'ok-script child session sign-in',
    }, 0)


def forget() -> bool:
    import win32cred
    try:
        win32cred.CredDelete(CRED_TARGET, win32cred.CRED_TYPE_GENERIC, 0)
        return True
    except Exception:
        return False
