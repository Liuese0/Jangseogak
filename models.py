import sqlite3
import uuid
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash
from config import DATABASE, LOAN_PERIOD_DAYS, FINE_PER_DAY


def get_db():
    db = sqlite3.connect(DATABASE)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA foreign_keys=ON")
    return db


def init_db():
    db = get_db()
    db.executescript('''
        CREATE TABLE IF NOT EXISTS members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            name TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'user',
            created_at TEXT DEFAULT (datetime('now', 'localtime'))
        );

        CREATE TABLE IF NOT EXISTS books (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            author TEXT NOT NULL,
            isbn TEXT,
            publisher TEXT,
            year INTEGER,
            location_section TEXT NOT NULL,
            location_shelf INTEGER NOT NULL,
            location_row INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'available',
            cover_color TEXT DEFAULT '#c6c6c6',
            created_at TEXT DEFAULT (datetime('now', 'localtime'))
        );

        CREATE TABLE IF NOT EXISTS loans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            book_id INTEGER NOT NULL REFERENCES books(id),
            member_id INTEGER NOT NULL REFERENCES members(id),
            borrowed_at TEXT DEFAULT (datetime('now', 'localtime')),
            due_at TEXT NOT NULL,
            returned_at TEXT,
            qr_token TEXT UNIQUE NOT NULL,
            status TEXT NOT NULL DEFAULT 'borrowed',
            fine_amount INTEGER DEFAULT 0
        );
    ''')
    db.commit()
    db.close()


# ── Member operations ──

def get_member_by_username(username):
    db = get_db()
    member = db.execute('SELECT * FROM members WHERE username = ?', (username,)).fetchone()
    db.close()
    return member


def authenticate(username, password):
    member = get_member_by_username(username)
    if member and check_password_hash(member['password'], password):
        return member
    return None


def get_member(member_id):
    db = get_db()
    member = db.execute('SELECT * FROM members WHERE id = ?', (member_id,)).fetchone()
    db.close()
    return member


def get_all_members():
    db = get_db()
    members = db.execute('SELECT * FROM members ORDER BY name').fetchall()
    db.close()
    return members


def add_member(username, password, name, role='user'):
    db = get_db()
    hashed = generate_password_hash(password)
    db.execute('INSERT INTO members (username, password, name, role) VALUES (?, ?, ?, ?)',
               (username, hashed, name, role))
    db.commit()
    db.close()


def update_member(member_id, name, role, password=None):
    db = get_db()
    if password:
        hashed = generate_password_hash(password)
        db.execute('UPDATE members SET name=?, role=?, password=? WHERE id=?',
                   (name, role, hashed, member_id))
    else:
        db.execute('UPDATE members SET name=?, role=? WHERE id=?',
                   (name, role, member_id))
    db.commit()
    db.close()


def delete_member(member_id):
    db = get_db()
    active = db.execute(
        "SELECT COUNT(*) as cnt FROM loans WHERE member_id=? AND status != 'returned'",
        (member_id,)
    ).fetchone()['cnt']
    if active > 0:
        db.close()
        return False
    db.execute('DELETE FROM members WHERE id=?', (member_id,))
    db.commit()
    db.close()
    return True


# ── Book operations ──

def get_all_books(search_query=None, search_by='title', section=None):
    db = get_db()
    query = 'SELECT * FROM books'
    params = []
    conditions = []

    if search_query:
        if search_by == 'author':
            conditions.append('author LIKE ?')
        else:
            conditions.append('title LIKE ?')
        params.append(f'%{search_query}%')

    if section:
        conditions.append('location_section = ?')
        params.append(section)

    if conditions:
        query += ' WHERE ' + ' AND '.join(conditions)

    query += ' ORDER BY title'
    books = db.execute(query, params).fetchall()
    db.close()
    return books


def get_book(book_id):
    db = get_db()
    book = db.execute('SELECT * FROM books WHERE id = ?', (book_id,)).fetchone()
    db.close()
    return book


def add_book(title, author, isbn, publisher, year, location_section, location_shelf, location_row, cover_color='#c6c6c6'):
    db = get_db()
    db.execute(
        '''INSERT INTO books (title, author, isbn, publisher, year,
           location_section, location_shelf, location_row, cover_color)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
        (title, author, isbn, publisher, year, location_section, location_shelf, location_row, cover_color)
    )
    db.commit()
    db.close()


def update_book(book_id, title, author, isbn, publisher, year, location_section, location_shelf, location_row, cover_color):
    db = get_db()
    db.execute(
        '''UPDATE books SET title=?, author=?, isbn=?, publisher=?, year=?,
           location_section=?, location_shelf=?, location_row=?, cover_color=?
           WHERE id=?''',
        (title, author, isbn, publisher, year, location_section, location_shelf, location_row, cover_color, book_id)
    )
    db.commit()
    db.close()


def delete_book(book_id):
    db = get_db()
    active = db.execute(
        "SELECT COUNT(*) as cnt FROM loans WHERE book_id=? AND status != 'returned'",
        (book_id,)
    ).fetchone()['cnt']
    if active > 0:
        db.close()
        return False
    db.execute('DELETE FROM books WHERE id=?', (book_id,))
    db.commit()
    db.close()
    return True


def get_section_counts():
    db = get_db()
    rows = db.execute(
        '''SELECT location_section, COUNT(*) as total,
           SUM(CASE WHEN status='available' THEN 1 ELSE 0 END) as available
           FROM books GROUP BY location_section'''
    ).fetchall()
    db.close()
    return {r['location_section']: {'total': r['total'], 'available': r['available']} for r in rows}


# ── Loan operations ──

def has_overdue_loans(member_id):
    """사용자가 연체 중인 대출이 있는지 확인 (외부 대출만 연체 검사)"""
    db = get_db()
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    row = db.execute(
        """SELECT COUNT(*) as c FROM loans
           WHERE member_id=? AND status='borrowed' AND due_at < ?""",
        (member_id, now)
    ).fetchone()
    db.close()
    return row['c'] > 0


def borrow_book(book_id, member_id, loan_type='external'):
    """
    대출 처리.
    loan_type='external': 외부 대출 (14일, 책을 가져감) → status='borrowed', book='on_loan'
    loan_type='internal': 도서관내 이용 (당일) → status='in_use', book='in_use'
    """
    db = get_db()
    book = db.execute('SELECT * FROM books WHERE id=?', (book_id,)).fetchone()
    if not book or book['status'] != 'available':
        db.close()
        return None

    qr_token = str(uuid.uuid4())
    now = datetime.now()

    if loan_type == 'internal':
        # 도서관내 이용: 당일 자정까지
        due_at = now.replace(hour=23, minute=59, second=59)
        loan_status = 'in_use'
        book_status = 'in_use'
    else:
        # 외부 대출: 14일
        due_at = now + timedelta(days=LOAN_PERIOD_DAYS)
        loan_status = 'borrowed'
        book_status = 'on_loan'

    db.execute(
        'INSERT INTO loans (book_id, member_id, borrowed_at, due_at, qr_token, status) VALUES (?, ?, ?, ?, ?, ?)',
        (book_id, member_id, now.strftime('%Y-%m-%d %H:%M:%S'),
         due_at.strftime('%Y-%m-%d %H:%M:%S'), qr_token, loan_status)
    )
    db.execute("UPDATE books SET status=? WHERE id=?", (book_status, book_id))
    db.commit()

    loan = db.execute('SELECT * FROM loans WHERE qr_token=?', (qr_token,)).fetchone()
    db.close()
    return loan


def update_loan_due_date(loan_id, new_due_at):
    """관리자: 대출 반납 기한 수정"""
    db = get_db()
    loan = db.execute('SELECT * FROM loans WHERE id=?', (loan_id,)).fetchone()
    if not loan or loan['status'] == 'returned':
        db.close()
        return False
    db.execute('UPDATE loans SET due_at=? WHERE id=?', (new_due_at, loan_id))
    db.commit()
    db.close()
    return True


def return_book(qr_token):
    db = get_db()
    loan = db.execute('SELECT * FROM loans WHERE qr_token=?', (qr_token,)).fetchone()
    if not loan or loan['status'] == 'returned':
        db.close()
        return None

    now = datetime.now()
    fine = calculate_fine(loan['due_at'], now)

    db.execute(
        "UPDATE loans SET status='returned', returned_at=?, fine_amount=? WHERE qr_token=?",
        (now.strftime('%Y-%m-%d %H:%M:%S'), fine, qr_token)
    )
    db.execute("UPDATE books SET status='available' WHERE id=?", (loan['book_id'],))
    db.commit()

    loan = db.execute('SELECT * FROM loans WHERE qr_token=?', (qr_token,)).fetchone()
    db.close()
    return loan


def return_book_admin(loan_id):
    db = get_db()
    loan = db.execute('SELECT * FROM loans WHERE id=?', (loan_id,)).fetchone()
    if not loan or loan['status'] == 'returned':
        db.close()
        return None

    now = datetime.now()
    fine = calculate_fine(loan['due_at'], now)

    db.execute(
        "UPDATE loans SET status='returned', returned_at=?, fine_amount=? WHERE id=?",
        (now.strftime('%Y-%m-%d %H:%M:%S'), fine, loan_id)
    )
    db.execute("UPDATE books SET status='available' WHERE id=?", (loan['book_id'],))
    db.commit()

    loan = db.execute('SELECT * FROM loans WHERE id=?', (loan_id,)).fetchone()
    db.close()
    return loan


def calculate_fine(due_at_str, returned_at=None):
    due = datetime.strptime(due_at_str, '%Y-%m-%d %H:%M:%S')
    if returned_at is None:
        returned_at = datetime.now()
    overdue_days = max(0, (returned_at - due).days)
    return overdue_days * FINE_PER_DAY


def get_member_loans(member_id):
    db = get_db()
    loans = db.execute(
        '''SELECT l.*, b.title, b.author FROM loans l
           JOIN books b ON l.book_id = b.id
           WHERE l.member_id = ?
           ORDER BY CASE WHEN l.status='returned' THEN 1 ELSE 0 END, l.borrowed_at DESC''',
        (member_id,)
    ).fetchall()
    db.close()
    return loans


def get_all_active_loans():
    db = get_db()
    loans = db.execute(
        '''SELECT l.*, b.title, b.author, m.name as member_name
           FROM loans l
           JOIN books b ON l.book_id = b.id
           JOIN members m ON l.member_id = m.id
           WHERE l.status != 'returned'
           ORDER BY l.due_at ASC'''
    ).fetchall()
    db.close()
    return loans


def get_overdue_loans():
    db = get_db()
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    loans = db.execute(
        '''SELECT l.*, b.title, b.author, m.name as member_name
           FROM loans l
           JOIN books b ON l.book_id = b.id
           JOIN members m ON l.member_id = m.id
           WHERE l.status != 'returned' AND l.due_at < ?
           ORDER BY l.due_at ASC''',
        (now,)
    ).fetchall()
    db.close()
    return loans


def get_all_loans():
    db = get_db()
    loans = db.execute(
        '''SELECT l.*, b.title, b.author, m.name as member_name
           FROM loans l
           JOIN books b ON l.book_id = b.id
           JOIN members m ON l.member_id = m.id
           ORDER BY l.borrowed_at DESC'''
    ).fetchall()
    db.close()
    return loans


def get_book_loans(book_id):
    db = get_db()
    loans = db.execute(
        '''SELECT l.*, m.name as member_name FROM loans l
           JOIN members m ON l.member_id = m.id
           WHERE l.book_id = ?
           ORDER BY l.borrowed_at DESC''',
        (book_id,)
    ).fetchall()
    db.close()
    return loans


def get_active_loan_for_book(book_id):
    db = get_db()
    loan = db.execute(
        "SELECT * FROM loans WHERE book_id=? AND status != 'returned' ORDER BY borrowed_at DESC LIMIT 1",
        (book_id,)
    ).fetchone()
    db.close()
    return loan


def get_dashboard_stats():
    db = get_db()
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    stats = {
        'total_books': db.execute('SELECT COUNT(*) as c FROM books').fetchone()['c'],
        'available_books': db.execute("SELECT COUNT(*) as c FROM books WHERE status='available'").fetchone()['c'],
        'total_members': db.execute("SELECT COUNT(*) as c FROM members WHERE role='user'").fetchone()['c'],
        'active_loans': db.execute("SELECT COUNT(*) as c FROM loans WHERE status != 'returned'").fetchone()['c'],
        'overdue_loans': db.execute(
            "SELECT COUNT(*) as c FROM loans WHERE status != 'returned' AND due_at < ?", (now,)
        ).fetchone()['c'],
        'total_fines': db.execute(
            "SELECT COALESCE(SUM(fine_amount), 0) as c FROM loans WHERE fine_amount > 0"
        ).fetchone()['c'],
    }
    db.close()
    return stats
