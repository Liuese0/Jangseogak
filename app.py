import os
import random
from functools import wraps
from datetime import datetime

from flask import (
    Flask, render_template, request, redirect, url_for,
    session, flash, jsonify, send_from_directory
)

import models
from config import SECRET_KEY, QR_DIR, SERVER_PORT, SECTIONS, FINE_PER_DAY, get_local_ip
from qr_generator import generate_loan_qrs

app = Flask(__name__)
app.secret_key = SECRET_KEY

SERVER_IP = get_local_ip()


# ── Template context ──

@app.context_processor
def inject_globals():
    return {
        'sections': SECTIONS,
        'now': datetime.now(),
        'server_ip': SERVER_IP,
        'server_port': SERVER_PORT,
        'fine_per_day': FINE_PER_DAY,
    }


@app.template_filter('dateformat')
def dateformat(value, fmt='%Y-%m-%d'):
    if not value:
        return ''
    if isinstance(value, str):
        try:
            value = datetime.strptime(value, '%Y-%m-%d %H:%M:%S')
        except ValueError:
            return value
    return value.strftime(fmt)


@app.template_filter('is_overdue')
def is_overdue_filter(due_at_str):
    if not due_at_str:
        return False
    try:
        due = datetime.strptime(due_at_str, '%Y-%m-%d %H:%M:%S')
        return datetime.now() > due
    except ValueError:
        return False


@app.template_filter('calc_fine')
def calc_fine_filter(due_at_str):
    if not due_at_str:
        return 0
    return models.calculate_fine(due_at_str)


@app.template_filter('overdue_days')
def overdue_days_filter(due_at_str):
    if not due_at_str:
        return 0
    try:
        due = datetime.strptime(due_at_str, '%Y-%m-%d %H:%M:%S')
        delta = datetime.now() - due
        return max(0, delta.days)
    except ValueError:
        return 0


# ── Auth decorators ──

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'member_id' not in session:
            flash('로그인이 필요합니다.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'member_id' not in session:
            flash('로그인이 필요합니다.', 'warning')
            return redirect(url_for('login'))
        if session.get('role') != 'admin':
            flash('관리자 권한이 필요합니다.', 'error')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated


# ── Public routes ──

@app.route('/')
def index():
    stats = models.get_dashboard_stats()
    all_books = models.get_all_books()
    # 3D 책장에 표시할 도서 최대 12권 무작위 선택
    sample = random.sample(list(all_books), min(12, len(all_books))) if all_books else []
    featured_books = [
        {
            'id': b['id'],
            'title': b['title'],
            'author': b['author'],
            'cover_color': b['cover_color'] or '#c6c6c6',
        }
        for b in sample
    ]
    return render_template('index.html', stats=stats, featured_books=featured_books)


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        member = models.authenticate(username, password)
        if member:
            session['member_id'] = member['id']
            session['name'] = member['name']
            session['role'] = member['role']
            session['username'] = member['username']
            flash(f'{member["name"]}님, 환영합니다!', 'success')
            if member['role'] == 'admin':
                return redirect(url_for('admin_dashboard'))
            return redirect(url_for('catalog'))
        flash('아이디 또는 비밀번호가 올바르지 않습니다.', 'error')
    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    flash('로그아웃되었습니다.', 'info')
    return redirect(url_for('index'))


# ── User routes ──

@app.route('/catalog')
@login_required
def catalog():
    q = request.args.get('q', '').strip()
    by = request.args.get('by', 'title')
    section = request.args.get('section', '').strip()
    books = models.get_all_books(
        search_query=q if q else None,
        search_by=by,
        section=section if section else None
    )
    return render_template('catalog.html', books=books, q=q, by=by, section=section)


@app.route('/book/<int:book_id>')
@login_required
def book_detail(book_id):
    book = models.get_book(book_id)
    if not book:
        flash('도서를 찾을 수 없습니다.', 'error')
        return redirect(url_for('catalog'))

    loan_history = models.get_book_loans(book_id)
    active_loan = models.get_active_loan_for_book(book_id)

    qr_return = None
    if active_loan:
        token = active_loan['qr_token']
        qr_return = f'qr/{token}_return.png'
        if not os.path.exists(os.path.join(QR_DIR, f'{token}_return.png')):
            generate_loan_qrs(token, SERVER_IP, SERVER_PORT)

    is_my_loan = active_loan and active_loan['member_id'] == session.get('member_id')
    has_overdue = models.has_overdue_loans(session['member_id']) if session.get('member_id') else False

    return render_template('book_detail.html',
                           book=book, loan_history=loan_history,
                           active_loan=active_loan, is_my_loan=is_my_loan,
                           qr_return=qr_return, has_overdue=has_overdue)


@app.route('/book/<int:book_id>/borrow', methods=['POST'])
@login_required
def borrow(book_id):
    loan_type = request.form.get('loan_type', 'external')

    # 외부 대출만 연체 차단 (도서관내 이용은 허용)
    if loan_type == 'external' and models.has_overdue_loans(session['member_id']):
        flash('연체 중인 도서가 있어 신규 대출이 불가합니다. 먼저 연체 도서를 반납해 주세요.', 'error')
        return redirect(url_for('book_detail', book_id=book_id))

    loan = models.borrow_book(book_id, session['member_id'], loan_type=loan_type)
    if not loan:
        flash('이 도서는 현재 대출할 수 없습니다.', 'error')
        return redirect(url_for('book_detail', book_id=book_id))

    generate_loan_qrs(loan['qr_token'], SERVER_IP, SERVER_PORT)
    if loan_type == 'internal':
        flash('도서관내 이용이 시작되었습니다. 반납 QR 코드를 확인하세요.', 'success')
    else:
        flash('대출이 완료되었습니다! 반납 QR 코드를 확인하세요.', 'success')
    return redirect(url_for('book_detail', book_id=book_id))


@app.route('/my-loans')
@login_required
def my_loans():
    loans = models.get_member_loans(session['member_id'])
    return render_template('my_loans.html', loans=loans)


@app.route('/floorplan')
@login_required
def floorplan():
    highlight = request.args.get('highlight', '')
    counts = models.get_section_counts()
    return render_template('floorplan.html', highlight=highlight, counts=counts)


# ── QR routes (no login required) ──

@app.route('/qr/return/<qr_token>')
def qr_return(qr_token):
    loan = models.return_book(qr_token)
    if not loan:
        return render_template('qr_confirm.html',
                               success=False,
                               message='유효하지 않거나 이미 반납된 도서입니다.')
    book = models.get_book(loan['book_id'])
    fine = loan['fine_amount']
    if fine > 0:
        msg = f'"{book["title"]}" 도서가 반납되었습니다. 연체료: {fine:,}원'
    else:
        msg = f'"{book["title"]}" 도서가 반납되었습니다. 연체료 없음.'
    return render_template('qr_confirm.html',
                           success=True,
                           action='return',
                           message=msg,
                           book=book, loan=loan, fine=fine)


# ── Admin routes ──

@app.route('/admin')
@admin_required
def admin_dashboard():
    stats = models.get_dashboard_stats()
    overdue = models.get_overdue_loans()
    return render_template('admin/dashboard.html', stats=stats, overdue=overdue)


@app.route('/admin/books')
@admin_required
def admin_books():
    q = request.args.get('q', '').strip()
    books = models.get_all_books(search_query=q if q else None)
    return render_template('admin/books.html', books=books, q=q)


@app.route('/admin/books/add', methods=['GET', 'POST'])
@admin_required
def admin_book_add():
    if request.method == 'POST':
        models.add_book(
            title=request.form['title'],
            author=request.form['author'],
            isbn=request.form.get('isbn', ''),
            publisher=request.form.get('publisher', ''),
            year=int(request.form['year']) if request.form.get('year') else None,
            location_section=request.form['location_section'],
            location_shelf=int(request.form['location_shelf']),
            location_row=int(request.form['location_row']),
            cover_color=request.form.get('cover_color', '#c6c6c6'),
        )
        flash('도서가 등록되었습니다.', 'success')
        return redirect(url_for('admin_books'))
    return render_template('admin/book_form.html', book=None)


@app.route('/admin/books/<int:book_id>/edit', methods=['GET', 'POST'])
@admin_required
def admin_book_edit(book_id):
    book = models.get_book(book_id)
    if not book:
        flash('도서를 찾을 수 없습니다.', 'error')
        return redirect(url_for('admin_books'))

    if request.method == 'POST':
        models.update_book(
            book_id=book_id,
            title=request.form['title'],
            author=request.form['author'],
            isbn=request.form.get('isbn', ''),
            publisher=request.form.get('publisher', ''),
            year=int(request.form['year']) if request.form.get('year') else None,
            location_section=request.form['location_section'],
            location_shelf=int(request.form['location_shelf']),
            location_row=int(request.form['location_row']),
            cover_color=request.form.get('cover_color', '#c6c6c6'),
        )
        flash('도서 정보가 수정되었습니다.', 'success')
        return redirect(url_for('admin_books'))
    return render_template('admin/book_form.html', book=book)


@app.route('/admin/books/<int:book_id>/delete', methods=['POST'])
@admin_required
def admin_book_delete(book_id):
    if models.delete_book(book_id):
        flash('도서가 삭제되었습니다.', 'success')
    else:
        flash('대출 중인 도서는 삭제할 수 없습니다.', 'error')
    return redirect(url_for('admin_books'))


@app.route('/admin/members')
@admin_required
def admin_members():
    members = models.get_all_members()
    return render_template('admin/members.html', members=members)


@app.route('/admin/members/add', methods=['GET', 'POST'])
@admin_required
def admin_member_add():
    if request.method == 'POST':
        try:
            models.add_member(
                username=request.form['username'],
                password=request.form['password'],
                name=request.form['name'],
                role=request.form.get('role', 'user'),
            )
            flash('회원이 등록되었습니다.', 'success')
            return redirect(url_for('admin_members'))
        except Exception:
            flash('이미 존재하는 아이디입니다.', 'error')
    return render_template('admin/member_form.html', member=None)


@app.route('/admin/members/<int:member_id>/edit', methods=['GET', 'POST'])
@admin_required
def admin_member_edit(member_id):
    member = models.get_member(member_id)
    if not member:
        flash('회원을 찾을 수 없습니다.', 'error')
        return redirect(url_for('admin_members'))

    if request.method == 'POST':
        pw = request.form.get('password', '').strip()
        models.update_member(
            member_id=member_id,
            name=request.form['name'],
            role=request.form.get('role', 'user'),
            password=pw if pw else None,
        )
        flash('회원 정보가 수정되었습니다.', 'success')
        return redirect(url_for('admin_members'))
    return render_template('admin/member_form.html', member=member)


@app.route('/admin/members/<int:member_id>/delete', methods=['POST'])
@admin_required
def admin_member_delete(member_id):
    if models.delete_member(member_id):
        flash('회원이 삭제되었습니다.', 'success')
    else:
        flash('대출 중인 회원은 삭제할 수 없습니다.', 'error')
    return redirect(url_for('admin_members'))


@app.route('/admin/loans')
@admin_required
def admin_loans():
    loans = models.get_all_loans()
    return render_template('admin/loans.html', loans=loans)


@app.route('/admin/overdue')
@admin_required
def admin_overdue():
    loans = models.get_overdue_loans()
    return render_template('admin/overdue.html', loans=loans)


@app.route('/admin/loans/<int:loan_id>/adjust', methods=['POST'])
@admin_required
def admin_loan_adjust(loan_id):
    new_date = request.form.get('due_date', '').strip()
    if not new_date:
        flash('날짜를 입력해주세요.', 'error')
        return redirect(url_for('admin_loans'))
    try:
        # YYYY-MM-DD 형식 → YYYY-MM-DD 23:59:59
        parsed = datetime.strptime(new_date, '%Y-%m-%d')
        new_due_at = parsed.replace(hour=23, minute=59, second=59).strftime('%Y-%m-%d %H:%M:%S')
    except ValueError:
        flash('날짜 형식이 올바르지 않습니다.', 'error')
        return redirect(url_for('admin_loans'))

    if models.update_loan_due_date(loan_id, new_due_at):
        flash(f'반납 기한이 {new_date}로 수정되었습니다.', 'success')
    else:
        flash('기한 수정에 실패했습니다.', 'error')
    return redirect(request.referrer or url_for('admin_loans'))


@app.route('/admin/loans/<int:loan_id>/return', methods=['POST'])
@admin_required
def admin_return(loan_id):
    loan = models.return_book_admin(loan_id)
    if loan:
        fine = loan['fine_amount']
        if fine > 0:
            flash(f'반납 완료. 연체료: {fine:,}원', 'warning')
        else:
            flash('반납이 완료되었습니다.', 'success')
    else:
        flash('반납 처리에 실패했습니다.', 'error')
    return redirect(url_for('admin_loans'))


# ── Main ──

if __name__ == '__main__':
    models.init_db()
    os.makedirs(QR_DIR, exist_ok=True)

    # Run seed if DB is empty
    from seed_data import seed_if_empty
    seed_if_empty()

    ip = get_local_ip()
    port = SERVER_PORT
    print(f'\n{"=" * 54}')
    print(f'  장서각 (Jangseogak) Library Management System')
    print(f'  Local:   http://127.0.0.1:{port}')
    print(f'  Network: http://{ip}:{port}')
    print(f'  Admin:   admin / admin123')
    print(f'{"=" * 54}\n')
    app.run(host='0.0.0.0', port=port, debug=True)
