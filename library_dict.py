"""
장서각 - 딕셔너리 기반 도서관 관리 (단일 파일, CLI)
요구사항 충족용 간이 버전.

실행: python library_dict.py
"""
from datetime import datetime, timedelta

LOAN_PERIOD_DAYS = 14
FINE_PER_DAY = 500  # 원

# ── 데이터 (딕셔너리) ──────────────────────────────────
# 도서: id → {제목, 저자, 대출여부, 대출자, 반납예정일}
books = {
    1: {'title': '파이썬 기초', 'author': '김철수', 'borrowed': False, 'borrower': None, 'due_at': None},
    2: {'title': '자료구조',   'author': '이영희', 'borrowed': False, 'borrower': None, 'due_at': None},
    3: {'title': '운영체제',   'author': '박민수', 'borrowed': False, 'borrower': None, 'due_at': None},
    4: {'title': '데이터베이스', 'author': '최지우', 'borrowed': False, 'borrower': None, 'due_at': None},
    5: {'title': '알고리즘',   'author': '김철수', 'borrowed': False, 'borrower': None, 'due_at': None},
}

# 회원: id → {이름, 대출 중인 책 id 리스트}
members = {
    101: {'name': '홍길동', 'loans': []},
    102: {'name': '강감찬', 'loans': []},
    103: {'name': '이순신', 'loans': []},
}


# ── 핵심 함수 ─────────────────────────────────────────
def borrow(book_id, member_id, today=None):
    """대출. 책이 대출 중이거나 회원이 없으면 실패."""
    today = today or datetime.now()
    if book_id not in books:
        print(f'[실패] 존재하지 않는 도서 id={book_id}')
        return False
    if member_id not in members:
        print(f'[실패] 존재하지 않는 회원 id={member_id}')
        return False
    book = books[book_id]
    if book['borrowed']:
        print(f"[실패] '{book['title']}' 은(는) 이미 대출 중 (대출자: {book['borrower']})")
        return False

    book['borrowed'] = True
    book['borrower'] = member_id
    book['due_at'] = today + timedelta(days=LOAN_PERIOD_DAYS)
    members[member_id]['loans'].append(book_id)
    print(f"[대출] {members[member_id]['name']} → '{book['title']}' (반납예정: {book['due_at']:%Y-%m-%d})")
    return True


def return_book(book_id, today=None):
    """반납. 연체 시 연체료 반환."""
    today = today or datetime.now()
    if book_id not in books or not books[book_id]['borrowed']:
        print(f'[실패] 대출 중이 아닌 도서 id={book_id}')
        return 0
    book = books[book_id]
    member_id = book['borrower']
    fine = calculate_fine(book['due_at'], today)

    members[member_id]['loans'].remove(book_id)
    book['borrowed'] = False
    book['borrower'] = None
    book['due_at'] = None

    msg = f"[반납] '{book['title']}'"
    if fine > 0:
        msg += f' - 연체료 {fine:,}원'
    print(msg)
    return fine


def is_overdue(book_id, today=None):
    """연체 여부."""
    today = today or datetime.now()
    book = books.get(book_id)
    if not book or not book['borrowed']:
        return False
    return today > book['due_at']


def calculate_fine(due_at, today=None):
    """연체료 계산 (일당 FINE_PER_DAY)."""
    today = today or datetime.now()
    overdue_days = max(0, (today - due_at).days)
    return overdue_days * FINE_PER_DAY


def search_books(keyword, by='title'):
    """도서 검색 (제목/저자). 반복문 기반."""
    results = []
    for book_id, book in books.items():
        if keyword.lower() in book[by].lower():
            results.append((book_id, book))
    return results


def print_all_loans(today=None):
    """반복문으로 전체 대출 현황 출력."""
    today = today or datetime.now()
    print('\n── 전체 대출 현황 ──────────────')
    any_loan = False
    for book_id, book in books.items():
        if not book['borrowed']:
            continue
        any_loan = True
        member = members[book['borrower']]
        overdue = '연체!' if is_overdue(book_id, today) else '정상'
        fine = calculate_fine(book['due_at'], today)
        fine_str = f' / 연체료 {fine:,}원' if fine else ''
        print(f"  #{book_id} '{book['title']}' - {member['name']} "
              f"(반납예정 {book['due_at']:%Y-%m-%d}, {overdue}{fine_str})")
    if not any_loan:
        print('  (대출 중인 도서 없음)')
    print('────────────────────────────────\n')


def print_all_books():
    """반복문으로 전체 도서 출력."""
    print('\n── 전체 도서 목록 ──────────────')
    for book_id, book in books.items():
        state = '대출중' if book['borrowed'] else '대출가능'
        print(f"  #{book_id} '{book['title']}' / {book['author']} [{state}]")
    print('────────────────────────────────\n')


def print_members():
    print('\n── 회원 목록 ────────────────────')
    for mid, m in members.items():
        titles = [books[bid]['title'] for bid in m['loans']]
        print(f"  #{mid} {m['name']} - 대출 {len(m['loans'])}권: {titles}")
    print('────────────────────────────────\n')


# ── CLI 메뉴 ──────────────────────────────────────────
def menu():
    actions = {
        '1': ('전체 도서 목록',      lambda: print_all_books()),
        '2': ('도서 검색',          lambda: _do_search()),
        '3': ('대출',               lambda: _do_borrow()),
        '4': ('반납',               lambda: _do_return()),
        '5': ('전체 대출 현황',      lambda: print_all_loans()),
        '6': ('회원 목록',          lambda: print_members()),
        '0': ('종료',               None),
    }
    while True:
        print('==== 장서각 (딕셔너리 버전) ====')
        for k, (label, _) in actions.items():
            print(f'  {k}. {label}')
        choice = input('선택> ').strip()
        if choice == '0':
            print('종료합니다.')
            return
        if choice in actions:
            actions[choice][1]()
        else:
            print('[오류] 잘못된 입력\n')


def _do_search():
    by = input('검색 기준 (title/author): ').strip() or 'title'
    kw = input('검색어: ').strip()
    results = search_books(kw, by=by)
    if not results:
        print('  결과 없음\n')
        return
    print(f'  {len(results)}건:')
    for bid, b in results:
        state = '대출중' if b['borrowed'] else '대출가능'
        print(f"    #{bid} '{b['title']}' / {b['author']} [{state}]")
    print()


def _do_borrow():
    try:
        bid = int(input('도서 id: '))
        mid = int(input('회원 id: '))
    except ValueError:
        print('[오류] 숫자를 입력하세요\n'); return
    borrow(bid, mid)
    print()


def _do_return():
    try:
        bid = int(input('도서 id: '))
    except ValueError:
        print('[오류] 숫자를 입력하세요\n'); return
    return_book(bid)
    print()


# ── 데모 시나리오 (연체 포함) ──────────────────────────
def demo():
    print('\n=== 데모 시나리오 ===')
    today = datetime(2026, 4, 18)
    # 대출 (과거 날짜로 → 연체 상황 연출)
    borrow(1, 101, today=today - timedelta(days=20))  # 20일 전 대출 → 6일 연체
    borrow(3, 102, today=today - timedelta(days=5))   # 5일 전 대출 → 정상
    borrow(1, 103, today=today)  # 실패 (이미 대출 중)

    print_all_loans(today=today)

    # 검색
    print("검색: '김철수' (저자)")
    for bid, b in search_books('김철수', by='author'):
        print(f"  #{bid} '{b['title']}'")
    print()

    # 반납 (연체료 발생)
    return_book(1, today=today)
    print_all_loans(today=today)


if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == 'demo':
        demo()
    else:
        menu()
