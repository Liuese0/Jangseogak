import socket
import os

SECRET_KEY = 'jangseogak-library-secret-key-2026'
DATABASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'jangseogak.db')
LOAN_PERIOD_DAYS = 14
FINE_PER_DAY = 500  # KRW
QR_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'qr')
SERVER_PORT = 5000

SECTIONS = {
    'A': '문학 (Literature)',
    'B': '역사 (History)',
    'C': '과학 (Science)',
    'D': '예술 (Arts)',
    'E': '철학 (Philosophy)',
    'F': '기타 (Others)',
}


def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('10.255.255.255', 1))
        ip = s.getsockname()[0]
    except Exception:
        ip = '127.0.0.1'
    finally:
        s.close()
    return ip
