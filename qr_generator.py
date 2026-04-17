import os
import qrcode
from config import QR_DIR


def generate_qr(qr_token, action, server_ip, port):
    url = f'http://{server_ip}:{port}/qr/{action}/{qr_token}'
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color='#161616', back_color='#ffffff')

    os.makedirs(QR_DIR, exist_ok=True)
    filename = f'{qr_token}_{action}.png'
    filepath = os.path.join(QR_DIR, filename)
    img.save(filepath)
    return filename


def generate_loan_qrs(qr_token, server_ip, port):
    """대출/이용 시 반납용 QR 1장 생성"""
    returning = generate_qr(qr_token, 'return', server_ip, port)
    return {'return': returning}


def delete_loan_qrs(qr_token):
    for action in ('reading', 'return'):
        filepath = os.path.join(QR_DIR, f'{qr_token}_{action}.png')
        if os.path.exists(filepath):
            os.remove(filepath)
